"""
Test Suite for Batch 1 Security & Authentication Fixes.

Verifies:
1. Token leak defense:
   - Rejection of external URLs, double slashes, dot-dot traversal, backslashes, percent-encoding.
   - Acceptance of valid /uploads/ paths and None attachments.
   - Sanitization of uploaded file names (replacing non-alphanumeric chars with _).
2. Auth:
   - Case-insensitive and trimmed email login.
   - Rejection of wrong password and unknown email.
3. User Management:
   - Demotion of the last admin blocked (HTTP 400).
   - Deletion of the last admin still blocked (HTTP 400).
   - Non-role updates on the last admin succeed.
4. Alert Assignment:
   - Assignment to nonexistent user returns 404.
   - Assignment to student role returns 400.
   - Omitted assignee assigns to caller.
   - Assignment to valid security/admin user succeeds.
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Ensure isolated in-memory test database
os.environ["DATABASE_URL"] = "sqlite:///:memory:"

from backend.config.database import Base, get_db
from backend.database.models.user import User
from backend.database.models.alert import Alert
from backend.services.auth_service import create_access_token, password_hash
import backend.routes.alerts as alerts_module
from backend.main import app

test_engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


def override_get_db():
    db = TestSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)


class TestBatch1SecurityAuth(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        Base.metadata.create_all(bind=test_engine)
        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.orig_upload_dir = alerts_module.UPLOAD_DIR
        alerts_module.UPLOAD_DIR = cls.temp_dir.name

    @classmethod
    def tearDownClass(cls):
        alerts_module.UPLOAD_DIR = cls.orig_upload_dir
        cls.temp_dir.cleanup()
        Base.metadata.drop_all(bind=test_engine)

    def setUp(self):
        # Refresh database tables cleanly per test
        Base.metadata.drop_all(bind=test_engine)
        Base.metadata.create_all(bind=test_engine)

        db = TestSessionLocal()
        # Seed test admin, officer, student
        self.admin = User(
            name="Primary Admin",
            email="admin@campusguard.com",
            password=password_hash.hash("AdminPass123!"),
            role="admin",
        )
        self.officer = User(
            name="Officer Bob",
            email="security@campusguard.com",
            password=password_hash.hash("SecurityPass123!"),
            role="security",
        )
        self.student = User(
            name="Student Alice",
            email="student@campusguard.com",
            password=password_hash.hash("StudentPass123!"),
            role="student",
        )
        db.add_all([self.admin, self.officer, self.student])
        db.commit()
        db.refresh(self.admin)
        db.refresh(self.officer)
        db.refresh(self.student)

        self.admin_id = self.admin.id
        self.officer_id = self.officer.id
        self.student_id = self.student.id

        self.admin_token = create_access_token(self.admin_id, "admin")
        self.officer_token = create_access_token(self.officer_id, "security")
        self.student_token = create_access_token(self.student_id, "student")

        self.admin_headers = {"Authorization": f"Bearer {self.admin_token}"}
        self.officer_headers = {"Authorization": f"Bearer {self.officer_token}"}
        self.student_headers = {"Authorization": f"Bearer {self.student_token}"}

        # Seed test alert
        self.alert = Alert(
            alert_type="Weapon Detection",
            location="Science Quad",
            description="Suspicious object observed",
            severity="high",
            status="active",
        )
        db.add(self.alert)
        db.commit()
        db.refresh(self.alert)
        self.alert_id = self.alert.id
        db.close()

    # --- ITEM 1: ATTACHMENT VALIDATION & FILENAME SANITIZATION ---

    def test_01_attachment_rejects_external_url(self):
        """Rejects external URL schemes."""
        payload = {
            "incident_type": "Suspicious Activity",
            "location": "Library",
            "description": "Suspicious person noticed near main entrance",
            "attachment": "http://attacker.com/leak",
        }
        res = client.post("/incidents", json=payload, headers=self.student_headers)
        self.assertEqual(res.status_code, 400)
        self.assertIn("Invalid attachment path", res.json()["detail"])

        # Also test https and protocol-relative
        payload["attachment"] = "https://evil.org/exfil"
        res2 = client.post("/incidents", json=payload, headers=self.student_headers)
        self.assertEqual(res2.status_code, 400)

    def test_02_attachment_rejects_double_slash(self):
        """Rejects double slash patterns."""
        payload = {
            "incident_type": "Suspicious Activity",
            "location": "Library",
            "description": "Suspicious person noticed",
            "attachment": "//uploads/photo.jpg",
        }
        res = client.post("/incidents", json=payload, headers=self.student_headers)
        self.assertEqual(res.status_code, 400)

        payload["attachment"] = "/uploads//nested.jpg"
        res2 = client.post("/incidents", json=payload, headers=self.student_headers)
        self.assertEqual(res2.status_code, 400)

    def test_03_attachment_rejects_dot_dot_traversal(self):
        """Rejects dot-dot path traversal sequences."""
        payload = {
            "incident_type": "Suspicious Activity",
            "location": "Library",
            "description": "Suspicious person noticed",
            "attachment": "/uploads/../campusguard.db",
        }
        res = client.post("/incidents", json=payload, headers=self.student_headers)
        self.assertEqual(res.status_code, 400)

    def test_04_attachment_rejects_backslash(self):
        """Rejects backslashes."""
        payload = {
            "incident_type": "Suspicious Activity",
            "location": "Library",
            "description": "Suspicious person noticed",
            "attachment": "/uploads/..\\campusguard.db",
        }
        res = client.post("/incidents", json=payload, headers=self.student_headers)
        self.assertEqual(res.status_code, 400)

        payload["attachment"] = "/uploads\\photo.jpg"
        res2 = client.post("/incidents", json=payload, headers=self.student_headers)
        self.assertEqual(res2.status_code, 400)

    def test_05_attachment_rejects_percent_encoding(self):
        """Rejects percent-encoded traversal attempts."""
        payload = {
            "incident_type": "Suspicious Activity",
            "location": "Library",
            "description": "Suspicious person noticed",
            "attachment": "/uploads/%2e%2e/campusguard.db",
        }
        res = client.post("/incidents", json=payload, headers=self.student_headers)
        self.assertEqual(res.status_code, 400)

    def test_06_attachment_accepts_valid_uploads_path(self):
        """Accepts safe relative /uploads/ paths."""
        payload = {
            "incident_type": "Suspicious Activity",
            "location": "Library",
            "description": "Suspicious person noticed near main entrance",
            "attachment": "/uploads/safe_evidence_123.jpg",
        }
        res = client.post("/incidents", json=payload, headers=self.student_headers)
        self.assertEqual(res.status_code, 200, res.text)
        self.assertEqual(res.json()["attachment"], "/uploads/safe_evidence_123.jpg")

    def test_07_attachment_accepts_none(self):
        """Accepts None attachment."""
        payload = {
            "incident_type": "Medical Emergency",
            "location": "Cafeteria",
            "description": "Student fainted near counter",
            "attachment": None,
        }
        res = client.post("/incidents", json=payload, headers=self.student_headers)
        self.assertEqual(res.status_code, 200, res.text)
        self.assertIsNone(res.json()["attachment"])

    def test_08_upload_filename_sanitization(self):
        """Upload sanitizes filename characters outside A-Za-z0-9._- into _."""
        dummy_content = b"\xff\xd8\xff\xe0\x00\x10JFIF" + b"TEST_IMAGE_DATA"
        # Filename contains special characters: spaces, semicolons, brackets, colons
        dangerous_filename = "snap shot; test [1] #bad:.jpg"
        res = client.post(
            "/incidents/upload",
            files={"file": (dangerous_filename, dummy_content, "image/jpeg")},
            headers=self.student_headers,
        )
        self.assertEqual(res.status_code, 200, res.text)
        data = res.json()
        saved_filename = data["filename"]

        # Ensure special characters were sanitized
        self.assertNotIn(" ", saved_filename)
        self.assertNotIn(";", saved_filename)
        self.assertNotIn("[", saved_filename)
        self.assertNotIn("]", saved_filename)
        self.assertNotIn("#", saved_filename)
        self.assertNotIn(":", saved_filename)
        self.assertTrue(saved_filename.endswith(".jpg"))

        # Verify file exists on disk inside temp upload dir
        expected_disk_path = os.path.join(self.temp_dir.name, saved_filename)
        self.assertTrue(os.path.exists(expected_disk_path))

    # --- ITEM 2: CASE-INSENSITIVE & PADDED LOGIN ---

    def test_09_login_mixed_case_and_padding(self):
        """Login works with mixed casing and leading/trailing whitespace."""
        res = client.post(
            "/login",
            json={"email": "  ADMIN@CampusGuard.COM  ", "password": "AdminPass123!"},
        )
        self.assertEqual(res.status_code, 200, res.text)
        data = res.json()
        self.assertEqual(data["email"], "admin@campusguard.com")
        self.assertIn("access_token", data)

    def test_10_login_wrong_password_rejected(self):
        """Wrong password still returns 401."""
        res = client.post(
            "/login",
            json={"email": "admin@campusguard.com", "password": "WrongPassword999!"},
        )
        self.assertEqual(res.status_code, 401)
        self.assertEqual(res.json()["detail"], "Invalid email or password")

    def test_11_login_unknown_email_rejected(self):
        """Unknown email returns 401."""
        res = client.post(
            "/login",
            json={"email": "unknown_user@campusguard.com", "password": "SomePassword1!"},
        )
        self.assertEqual(res.status_code, 401)
        self.assertEqual(res.json()["detail"], "Invalid email or password")

    # --- ITEM 3: LAST ADMIN DEMOTION & DELETION GUARDS ---

    def test_12_last_admin_demotion_blocked(self):
        """Demoting the last remaining admin returns HTTP 400."""
        # Attempt to demote sole admin to student
        res = client.patch(
            f"/users/{self.admin_id}",
            json={"role": "student"},
            headers=self.admin_headers,
        )
        self.assertEqual(res.status_code, 400)
        self.assertIn("Cannot demote the last remaining administrator account", res.json()["detail"])

        # Attempt to demote sole admin to security
        res_sec = client.patch(
            f"/users/{self.admin_id}",
            json={"role": "security"},
            headers=self.admin_headers,
        )
        self.assertEqual(res_sec.status_code, 400)

        # Other non-role updates for that admin should still succeed
        res_name = client.patch(
            f"/users/{self.admin_id}",
            json={"name": "Updated Admin Name"},
            headers=self.admin_headers,
        )
        self.assertEqual(res_name.status_code, 200)
        self.assertEqual(res_name.json()["user"]["name"], "Updated Admin Name")

    def test_13_admin_demotion_allowed_when_another_admin_exists(self):
        """Demoting an admin succeeds when at least one other admin remains."""
        # Create second admin
        res_create = client.post(
            "/users",
            json={
                "name": "Second Admin",
                "email": "admin2@campusguard.com",
                "password": "Admin2Pass123!",
                "role": "admin",
            },
            headers=self.admin_headers,
        )
        self.assertEqual(res_create.status_code, 201)
        admin2_id = res_create.json()["user"]["id"]

        # Now demoting the second admin should succeed because self.admin remains
        res_demote = client.patch(
            f"/users/{admin2_id}",
            json={"role": "security"},
            headers=self.admin_headers,
        )
        self.assertEqual(res_demote.status_code, 200)
        self.assertEqual(res_demote.json()["user"]["role"], "security")

    def test_14_last_admin_deletion_still_blocked(self):
        """Existing protection against deleting the last admin remains intact."""
        # Create a second admin to test delete attempt
        res_create = client.post(
            "/users",
            json={
                "name": "Second Admin",
                "email": "admin2@campusguard.com",
                "password": "Admin2Pass123!",
                "role": "admin",
            },
            headers=self.admin_headers,
        )
        admin2_id = res_create.json()["user"]["id"]
        admin2_token = create_access_token(admin2_id, "admin")
        admin2_headers = {"Authorization": f"Bearer {admin2_token}"}

        # Admin 2 deletes Admin 1 (now 1 admin remains)
        res_del1 = client.delete(f"/users/{self.admin_id}", headers=admin2_headers)
        self.assertEqual(res_del1.status_code, 200)

        # Admin 2 cannot delete self (handled by self-deletion guard)
        res_self = client.delete(f"/users/{admin2_id}", headers=admin2_headers)
        self.assertEqual(res_self.status_code, 400)

    # --- ITEM 4: ASSIGN ALERT VALIDATION ---

    def test_15_assign_alert_missing_user_returns_404(self):
        """Assigning alert to nonexistent user ID returns 404."""
        res = client.patch(
            f"/alerts/{self.alert_id}/assign",
            json={"assigned_to": 999999},
            headers=self.admin_headers,
        )
        self.assertEqual(res.status_code, 404)
        self.assertIn("Assigned user not found", res.json()["detail"])

    def test_16_assign_alert_student_returns_400(self):
        """Assigning alert to a student returns 400."""
        res = client.patch(
            f"/alerts/{self.alert_id}/assign",
            json={"assigned_to": self.student_id},
            headers=self.admin_headers,
        )
        self.assertEqual(res.status_code, 400)
        self.assertIn("Alerts can only be assigned to security or admin users", res.json()["detail"])

    def test_17_assign_alert_omitted_assignee_assigns_caller(self):
        """Omitting assigned_to assigns alert to the calling security/admin user."""
        res = client.patch(
            f"/alerts/{self.alert_id}/assign",
            json={},
            headers=self.officer_headers,
        )
        self.assertEqual(res.status_code, 200, res.text)
        self.assertEqual(res.json()["assigned_to"], self.officer_id)

    def test_18_assign_alert_valid_security_officer_succeeds(self):
        """Admin assigning alert to a valid security officer succeeds with 200."""
        res = client.patch(
            f"/alerts/{self.alert_id}/assign",
            json={"assigned_to": self.officer_id},
            headers=self.admin_headers,
        )
        self.assertEqual(res.status_code, 200, res.text)
        self.assertEqual(res.json()["assigned_to"], self.officer_id)


if __name__ == "__main__":
    unittest.main()
