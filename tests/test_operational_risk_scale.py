import unittest
from unittest.mock import patch
import cv2
import numpy as np
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

from backend.config.database import Base, get_db
from backend.database.models.user import User
from backend.database.models.alert import Alert
from backend.ml_models.risk_prediction import (
    OPERATIONAL_SEVERITY_SCALE,
    get_operational_score,
)
from sqlalchemy.pool import StaticPool
from backend.services.risk_service import risk_service, create_risk_alert
from backend.services.auth_service import create_access_token, password_hash
from backend.main import app

test_engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestSession = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


def override_get_db():
    db = TestSession()
    try:
        yield db
    finally:
        db.close()


class TestOperationalRiskScale(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        Base.metadata.create_all(bind=test_engine)
        app.dependency_overrides[get_db] = override_get_db
        cls.client = TestClient(app)

        # Seed test security operator
        db = TestSession()
        cls.test_user = User(
            name="Security Operator",
            email="sec_ops_option_b@campusguard.com",
            password=password_hash.hash("Secret123!"),
            role="security",
        )
        db.add(cls.test_user)
        db.commit()
        db.refresh(cls.test_user)
        cls.token = create_access_token(cls.test_user.id, "security")
        cls.auth_headers = {"Authorization": f"Bearer {cls.token}"}
        db.close()

        cls.sample_image_bytes = cv2.imencode(".jpg", np.zeros((100, 100, 3), dtype=np.uint8))[1].tobytes()

    @classmethod
    def tearDownClass(cls):
        app.dependency_overrides.pop(get_db, None)

    def setUp(self):
        app.dependency_overrides[get_db] = override_get_db
        self.db = TestSession()
        self.db.query(Alert).delete()
        self.db.commit()

    def tearDown(self):
        self.db.rollback()
        self.db.query(Alert).delete()
        self.db.commit()
        self.db.close()

    # 1. Operational scale mapping verification
    def test_01_operational_score_mapping(self):
        """Verifies operational scale: Low=20, Medium=50, High=80, Critical=100."""
        self.assertEqual(OPERATIONAL_SEVERITY_SCALE["low"], 20)
        self.assertEqual(OPERATIONAL_SEVERITY_SCALE["medium"], 50)
        self.assertEqual(OPERATIONAL_SEVERITY_SCALE["high"], 80)
        self.assertEqual(OPERATIONAL_SEVERITY_SCALE["critical"], 100)

        # Helper case-insensitivity
        self.assertEqual(get_operational_score("critical"), 100)
        self.assertEqual(get_operational_score("CRITICAL"), 100)
        self.assertEqual(get_operational_score("High"), 80)
        self.assertEqual(get_operational_score("MEDIUM"), 50)
        self.assertEqual(get_operational_score("low"), 20)
        self.assertIsNone(get_operational_score(None))
        self.assertIsNone(get_operational_score(""))

    # 2. Random Forest ML score scale preserved (does not predict Critical)
    def test_02_ml_risk_model_mapping_preserved(self):
        """Verifies Random Forest classes remain Low, Medium, High and scores are 20, 50, 80."""
        pred_clean = risk_service.predict()
        self.assertEqual(pred_clean["risk_level"], "Low")
        self.assertEqual(pred_clean["risk_score"], 20)

        # Compound weapon threat
        pred_weapon = risk_service.predict(weapon=True)
        self.assertIn(pred_weapon["risk_level"], ["Medium", "High"])
        self.assertIn(pred_weapon["risk_score"], [50, 80])
        self.assertNotEqual(pred_weapon["risk_level"], "Critical")  # RF never predicts Critical

    # 3. Weapon alert behavior: Critical operational severity vs Medium ML score
    def test_03_weapon_alert_dual_score_separation(self):
        """Verifies CCTV weapon alert gets Operational Severity 100 while retaining ML score 50."""
        res = create_risk_alert(
            db=self.db,
            location="North Gate",
            weapon=True,
            detected_weapons=[{"weapon": "gun"}],
        )

        # Operational metrics
        self.assertEqual(res["operational_severity"], "Critical")
        self.assertEqual(res["operational_score"], 100)

        # ML metrics (Random Forest single weapon -> Medium, 50)
        self.assertEqual(res["risk_level"], "Medium")
        self.assertEqual(res["risk_score"], 50)
        self.assertNotEqual(res["operational_score"], res["risk_score"])

        # Persisted alert verification
        self.assertIsNotNone(res["alert_id"])
        alert = self.db.query(Alert).filter_by(id=res["alert_id"]).first()
        self.assertIsNotNone(alert)
        self.assertEqual(alert.severity, "critical")
        self.assertEqual(alert.operational_score, 100)

        # Description explicitly distinguishes both scores
        self.assertIn("Operational Threat Severity: CRITICAL (Operational Severity Score: 100/100)", alert.description)
        self.assertIn("ML Risk Score: 50/100 (Level: Medium)", alert.description)

    # 4. Fall alert behavior: High operational severity
    def test_04_fall_alert_operational_score(self):
        """Verifies fall detection creates an alert with operational score 80."""
        res = create_risk_alert(
            db=self.db,
            location="Hallway B",
            fall=True,
        )

        self.assertEqual(res["operational_severity"], "High")
        self.assertEqual(res["operational_score"], 80)

        alert = self.db.query(Alert).filter_by(id=res["alert_id"]).first()
        self.assertIsNotNone(alert)
        self.assertEqual(alert.severity, "high")
        self.assertEqual(alert.operational_score, 80)
        self.assertIn("Operational Severity Score: 80/100", alert.description)

    # 5. Clean baseline: Low operational severity (20/100) and no alert
    def test_05_clean_baseline_operational_score(self):
        """Verifies baseline frame has operational score 20 and creates no alert."""
        res = create_risk_alert(
            db=self.db,
            location="Library",
        )

        self.assertEqual(res["operational_severity"], "Low")
        self.assertEqual(res["operational_score"], 20)
        self.assertIsNone(res["alert_id"])
        self.assertEqual(self.db.query(Alert).count(), 0)

    # 6. SOS alerts preserve NULL operational_score
    def test_06_sos_alert_preserves_null_operational_score(self):
        """Verifies SOS alerts retain severity='high' and do not assign arbitrary operational score."""
        sos_alert = Alert(
            user_id=1,
            alert_type="SOS",
            location="Quad",
            description="Student SOS Broadcast",
            severity="high",
            status="active",
        )
        self.db.add(sos_alert)
        self.db.commit()
        self.db.refresh(sos_alert)

        self.assertIsNone(sos_alert.operational_score)
        self.assertEqual(sos_alert.severity, "high")

    # 7. Non-probability score semantics
    def test_07_non_probability_score_semantics(self):
        """Verifies scores are out of 100 points and not probabilities."""
        res = create_risk_alert(db=None, weapon=True)
        self.assertIn("operational_score_scale", res)
        self.assertIn("Low=20, Medium=50, High=80, Critical=100", res["operational_score_scale"])
        self.assertIsInstance(res["operational_score"], int)
        self.assertIsInstance(res["risk_score"], int)
        self.assertGreaterEqual(res["operational_score"], 0)
        self.assertLessEqual(res["operational_score"], 100)

    # 8. CCTV Image Analysis Endpoint returns dual scores
    @patch("backend.routes.camera.ml_service.analyze_frame")
    def test_08_cctv_image_analyze_endpoint_dual_scores(self, mock_analyze):
        """Verifies POST /camera/analyze returns operational_severity, operational_score, and risk."""
        mock_analyze.return_value = {
            "fall_detected": False,
            "fight_detected": False,
            "fight_proximity": False,
            "weapon_detected": True,
            "detected_weapons": [{"weapon": "gun", "confidence": 0.92}],
            "person_count": 1,
            "people": [{"x1": 10, "y1": 10, "x2": 50, "y2": 100}],
            "restricted_entry": False,
            "restricted_zone": None,
            "after_hours": False,
            "after_hours_message": "Within campus hours",
            "detector_errors": {},
        }

        files = {"file": ("gun_test.jpg", self.sample_image_bytes, "image/jpeg")}
        res = self.client.post("/camera/analyze", files=files, headers=self.auth_headers)
        self.assertEqual(res.status_code, 200, res.text)
        data = res.json()

        # Check root level operational fields
        self.assertEqual(data["operational_severity"], "Critical")
        self.assertEqual(data["operational_score"], 100)

        # Check nested risk fields
        self.assertIn("risk", data)
        self.assertEqual(data["risk"]["operational_severity"], "Critical")
        self.assertEqual(data["risk"]["operational_score"], 100)
        self.assertEqual(data["risk"]["risk_level"], "Medium")
        self.assertEqual(data["risk"]["risk_score"], 50)

        # Check persistent alert
        self.assertIsNotNone(data["alert_id"])
        db = TestSession()
        alert = db.query(Alert).filter_by(id=data["alert_id"]).first()
        self.assertIsNotNone(alert)
        self.assertEqual(alert.severity, "critical")
        self.assertEqual(alert.operational_score, 100)
        db.close()

    # 9. GET /alerts returns operational_score field
    def test_09_alerts_api_serialization(self):
        """Verifies GET /alerts serializes operational_score for alerts."""
        db = TestSession()
        alert = Alert(
            user_id=self.test_user.id,
            alert_type="Weapon Detection",
            location="Science Hall",
            description="Operational Threat Severity: CRITICAL (Operational Severity Score: 100/100) | ML Risk Score: 50/100 (Level: Medium)",
            severity="critical",
            operational_score=100,
            status="active",
        )
        db.add(alert)
        db.commit()
        db.close()

        res = self.client.get("/alerts", headers=self.auth_headers)
        self.assertEqual(res.status_code, 200)
        alerts = res.json()
        self.assertGreaterEqual(len(alerts), 1)
        found = next((a for a in alerts if a["alert_type"] == "Weapon Detection"), None)
        self.assertIsNotNone(found)
        self.assertEqual(found["operational_score"], 100)
        self.assertEqual(found["severity"], "critical")


if __name__ == "__main__":
    unittest.main()
