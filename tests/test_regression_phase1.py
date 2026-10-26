"""Isolated Phase 1 Regression Test Suite for CampusGuard AI.

Tests database registration, foreign keys, authentication, authorization,
and safe user deletion using an isolated in-memory SQLite database.
Never touches the operational campusguard.db.
"""

import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
import jwt

# Ensure project root is in sys.path
PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy.exc import IntegrityError
from fastapi.testclient import TestClient

# 1. Setup isolated in-memory test engine with SQLite foreign keys enabled
test_engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)


@event.listens_for(test_engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    if test_engine.dialect.name == "sqlite":
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

from backend.config.database import Base, get_db
from backend.database.models.user import User
from backend.database.models.alert import Alert
from backend.database.models.incident import Incident
from backend.database.models.incident_log import IncidentLog
from backend.database.models.camera import Camera
import backend.database.db as db_initializer

from backend.main import app
from backend.services.auth_service import (
    create_access_token,
    password_hash,
    SECRET_KEY,
    ALGORITHM,
)


# Override get_db dependency in FastAPI app for all routes and auth checks
def override_get_db():
    db = TestSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)


class Phase1RegressionTestSuite(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app.dependency_overrides[get_db] = override_get_db
        Base.metadata.create_all(bind=test_engine)

    @classmethod
    def tearDownClass(cls):
        app.dependency_overrides.pop(get_db, None)

    def setUp(self):
        app.dependency_overrides[get_db] = override_get_db
        self.db = TestSessionLocal()
        # Clean isolated test tables between tests
        self.db.query(IncidentLog).delete()
        self.db.query(Incident).delete()
        self.db.query(Alert).delete()
        self.db.query(Camera).delete()
        self.db.query(User).delete()
        self.db.commit()

    def tearDown(self):
        self.db.close()

    def test_01_models_registration_and_table_creation(self):
        """Verifies all five models are registered in Base.metadata and created."""
        registered_tables = sorted(list(Base.metadata.tables.keys()))
        expected_tables = ["alerts", "cameras", "incident_logs", "incidents", "users"]
        self.assertEqual(registered_tables, expected_tables)

        with test_engine.connect() as conn:
            created_tables = sorted([
                r[0] for r in conn.execute(
                    text("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
                ).fetchall()
            ])
            self.assertEqual(created_tables, expected_tables)

    def test_02_foreign_key_enforcement(self):
        """Verifies SQLite foreign-key enforcement and rejection of invalid references."""
        with test_engine.connect() as conn:
            fk_status = conn.execute(text("PRAGMA foreign_keys")).scalar()
            self.assertEqual(fk_status, 1)

        # Valid reference
        u = User(id=1, name="Test", email="t@test.com", password=password_hash.hash("p"), role="student")
        self.db.add(u)
        self.db.commit()

        a_valid = Alert(id=1, user_id=1, alert_type="SOS", location="Campus", status="active")
        self.db.add(a_valid)
        self.db.commit()

        # Invalid user_id reference
        a_invalid = Alert(id=2, user_id=9999, alert_type="SOS", location="Campus", status="active")
        self.db.add(a_invalid)
        with self.assertRaises(IntegrityError):
            self.db.commit()
        self.db.rollback()

        # Invalid incident_id reference in incident_logs
        log_invalid = IncidentLog(id=1, incident_id=9999, action="submitted")
        self.db.add(log_invalid)
        with self.assertRaises(IntegrityError):
            self.db.commit()
        self.db.rollback()

    def test_03_authentication_and_stale_role_protection(self):
        """Verifies valid, expired, malformed, deleted, and demoted user tokens."""
        # 3a: Valid token and existing user
        u = User(id=10, name="Alice", email="alice@test.com", password=password_hash.hash("p123"), role="security")
        self.db.add(u)
        self.db.commit()

        token = create_access_token(user_id=10, role="security")
        res = client.get("/alerts", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(res.status_code, 200)

        # 3b: Expired token
        expired_payload = {
            "sub": "10",
            "role": "security",
            "exp": datetime.now(timezone.utc) - timedelta(minutes=5),
        }
        expired_token = jwt.encode(expired_payload, SECRET_KEY, algorithm=ALGORITHM)
        res_exp = client.get("/alerts", headers={"Authorization": f"Bearer {expired_token}"})
        self.assertEqual(res_exp.status_code, 401)
        self.assertIn("Invalid or expired token", res_exp.json().get("detail", ""))

        # 3c: Malformed token
        res_malformed = client.get("/alerts", headers={"Authorization": "Bearer malformed.jwt.token"})
        self.assertEqual(res_malformed.status_code, 401)

        # 3d: Deleted user token
        ghost_token = create_access_token(user_id=9999, role="security")
        res_ghost = client.get("/alerts", headers={"Authorization": f"Bearer {ghost_token}"})
        self.assertEqual(res_ghost.status_code, 401)
        self.assertIn("User not found or account deactivated", res_ghost.json().get("detail", ""))

        # 3e: Demoted user - Token issued with 'admin', but DB role updated to 'student'
        u_admin = User(id=20, name="Bob Admin", email="bob@test.com", password=password_hash.hash("p"), role="admin")
        self.db.add(u_admin)
        self.db.commit()

        admin_token = create_access_token(user_id=20, role="admin")
        admin_headers = {"Authorization": f"Bearer {admin_token}"}
        self.assertEqual(client.get("/users", headers=admin_headers).status_code, 200)

        # Demote user 20 in database to student
        u_admin.role = "student"
        self.db.commit()

        # Token still has role='admin' in payload, but live DB role 'student' blocks request with 403
        res_demoted = client.get("/users", headers=admin_headers)
        self.assertEqual(res_demoted.status_code, 403)
        self.assertEqual(res_demoted.json().get("detail"), "Access forbidden")

    def test_04_role_based_authorization(self):
        """Verifies endpoint authorization for Admin, Security, and Student roles."""
        u_stu = User(id=30, name="Stu", email="stu@test.com", password=password_hash.hash("p"), role="student")
        u_sec = User(id=31, name="Sec", email="sec@test.com", password=password_hash.hash("p"), role="security")
        u_adm = User(id=32, name="Adm", email="adm@test.com", password=password_hash.hash("p"), role="admin")
        self.db.add_all([u_stu, u_sec, u_adm])
        self.db.commit()

        stu_hdr = {"Authorization": f"Bearer {create_access_token(30, 'student')}"}
        sec_hdr = {"Authorization": f"Bearer {create_access_token(31, 'security')}"}
        adm_hdr = {"Authorization": f"Bearer {create_access_token(32, 'admin')}"}

        # /users: Admin only
        self.assertEqual(client.get("/users", headers=stu_hdr).status_code, 403)
        self.assertEqual(client.get("/users", headers=sec_hdr).status_code, 403)
        self.assertEqual(client.get("/users", headers=adm_hdr).status_code, 200)

        # /alerts: Admin & Security, but Student forbidden
        self.assertEqual(client.get("/alerts", headers=stu_hdr).status_code, 403)
        self.assertEqual(client.get("/alerts", headers=sec_hdr).status_code, 200)
        self.assertEqual(client.get("/alerts", headers=adm_hdr).status_code, 200)

        # /cameras: Admin & Security, but Student forbidden
        self.assertEqual(client.get("/cameras", headers=stu_hdr).status_code, 403)
        self.assertEqual(client.get("/cameras", headers=sec_hdr).status_code, 200)
        self.assertEqual(client.get("/cameras", headers=adm_hdr).status_code, 200)

    def test_05_safe_user_deletion(self):
        """Verifies reference nullification, self-deletion prevention, and last admin guard."""
        adm1 = User(id=40, name="Admin 1", email="adm1@test.com", password=password_hash.hash("p"), role="admin")
        adm2 = User(id=41, name="Admin 2", email="adm2@test.com", password=password_hash.hash("p"), role="admin")
        target = User(id=42, name="Target", email="target@test.com", password=password_hash.hash("p"), role="security")
        self.db.add_all([adm1, adm2, target])
        self.db.commit()

        adm1_hdr = {"Authorization": f"Bearer {create_access_token(40, 'admin')}"}

        # Setup references across all four columns
        al1 = Alert(id=10, user_id=42, alert_type="SOS", location="Loc 1", status="active")
        al2 = Alert(id=11, assigned_to=42, alert_type="CCTV", location="Loc 2", status="active")
        inc = Incident(id=10, user_id=42, incident_type="Fire", location="Lab", description="Smoke detected")
        self.db.add_all([al1, al2, inc])
        self.db.commit()

        log = IncidentLog(id=10, incident_id=10, action="submitted", performed_by=42)
        self.db.add(log)
        self.db.commit()

        # 5a: Safe deletion succeeds, references nullified, no FK violation
        res_del = client.delete("/users/42", headers=adm1_hdr)
        self.assertEqual(res_del.status_code, 200)
        self.assertEqual(res_del.json()["deleted_user_id"], 42)

        self.assertIsNone(self.db.query(User).filter(User.id == 42).first())
        self.assertIsNone(self.db.query(Alert).filter(Alert.id == 10).first().user_id)
        self.assertIsNone(self.db.query(Alert).filter(Alert.id == 11).first().assigned_to)
        self.assertIsNone(self.db.query(Incident).filter(Incident.id == 10).first().user_id)
        self.assertIsNone(self.db.query(IncidentLog).filter(IncidentLog.id == 10).first().performed_by)

        with test_engine.connect() as conn:
            violations = conn.execute(text("PRAGMA foreign_key_check")).fetchall()
            self.assertEqual(violations, [])

        # 5b: Nonexistent user returns 404
        res_404 = client.delete("/users/9999", headers=adm1_hdr)
        self.assertEqual(res_404.status_code, 404)
        self.assertEqual(res_404.json()["detail"], "User not found")

        # 5c: Self-deletion blocked with 400
        res_self = client.delete("/users/40", headers=adm1_hdr)
        self.assertEqual(res_self.status_code, 400)
        self.assertIn("Cannot delete your own administrator account", res_self.json()["detail"])

        # 5d: Last administrator cannot be deleted
        res_del_adm2 = client.delete("/users/41", headers=adm1_hdr)
        self.assertEqual(res_del_adm2.status_code, 200)

        # Now only Admin 40 remains. Non-admin cannot delete admin:
        u_other = User(id=50, name="Other", email="other@test.com", password=password_hash.hash("p"), role="student")
        self.db.add(u_other)
        self.db.commit()
        other_hdr = {"Authorization": f"Bearer {create_access_token(50, 'student')}"}
        self.assertEqual(client.delete("/users/40", headers=other_hdr).status_code, 403)


if __name__ == "__main__":
    unittest.main()
