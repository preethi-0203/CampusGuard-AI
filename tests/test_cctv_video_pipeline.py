"""Isolated Test Suite for Unified CCTV Video Risk Pipeline (Phase 2, Step 9).

Tests end-to-end video analysis, multi-threat evaluation, composite risk scoring,
alert creation, fight heuristic safety, invalid video handling, and response compatibility.
Uses an isolated in-memory SQLite database. NEVER writes to campusguard.db.
"""

import sys
import os
import unittest
from unittest.mock import patch, MagicMock
from pathlib import Path
import tempfile
import cv2
import numpy as np

# Ensure project root is in sys.path
PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
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
import backend.database.db as db_initializer

from backend.main import app
from backend.services.auth_service import (
    create_access_token,
    password_hash,
)
from backend.services.risk_service import risk_service, create_risk_alert
from backend.services.loitering_service import LoiteringService


def override_get_db():
    db = TestSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)


def create_synthetic_mp4(num_frames=15, fps=30.0, width=320, height=240) -> bytes:
    """Creates a valid, synthetic MP4 byte stream in memory without touching disk permanently."""
    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tf:
        temp_path = tf.name

    try:
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        out = cv2.VideoWriter(temp_path, fourcc, fps, (width, height))
        for _ in range(num_frames):
            frame = np.zeros((height, width, 3), dtype=np.uint8)
            out.write(frame)
        out.release()

        with open(temp_path, "rb") as f:
            return f.read()
    finally:
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass


class TestUnifiedVideoRiskPipeline(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app.dependency_overrides[get_db] = override_get_db
        # Create all tables in the isolated in-memory DB
        Base.metadata.create_all(bind=test_engine)

        # Seed test admin user for authenticated requests
        db = TestSessionLocal()
        cls.test_user = User(
            name="Security Operator",
            email="operator_step9@campusguard.com",
            password=password_hash.hash("SecretPassword123!"),
            role="security",
        )
        db.add(cls.test_user)
        db.commit()
        db.refresh(cls.test_user)
        cls.user_id = cls.test_user.id
        db.close()

        cls.token = create_access_token(cls.user_id, "security")
        cls.auth_headers = {"Authorization": f"Bearer {cls.token}"}
        cls.sample_video_bytes = create_synthetic_mp4(num_frames=15, fps=30.0)
        cls.sample_image_bytes = cv2.imencode(".jpg", np.zeros((100, 100, 3), dtype=np.uint8))[1].tobytes()

    @classmethod
    def tearDownClass(cls):
        app.dependency_overrides.pop(get_db, None)

    def setUp(self):
        app.dependency_overrides[get_db] = override_get_db
        # Clear tables between test runs in memory
        db = TestSessionLocal()
        db.query(IncidentLog).delete()
        db.query(Incident).delete()
        db.query(Alert).delete()
        db.commit()
        db.close()

    # 1. Video with no detections -> baseline normal risk
    @patch("backend.routes.camera.ml_service.analyze_video_frame")
    def test_01_video_no_detections_baseline_risk(self, mock_analyze):
        mock_analyze.return_value = {
            "person_count": 0,
            "tracked_ids": [],
            "loitering_detected": False,
            "loitering_people": [],
            "weapon_detected": False,
            "detected_weapons": [],
            "fall_detected": False,
            "fight_proximity": False,
            "restricted_entry": False,
            "restricted_zone": None,
        }

        files = {"file": ("normal_patrol.mp4", self.sample_video_bytes, "video/mp4")}
        res = client.post("/camera/analyze-video", files=files, headers=self.auth_headers)

        self.assertEqual(res.status_code, 200, res.text)
        data = res.json()

        # Existing response field compatibility
        self.assertEqual(data["message"], "Video analysis completed")
        self.assertGreater(data["frames_analyzed"], 0)
        self.assertFalse(data["loitering_detected"])
        self.assertEqual(data["loitering_person_ids"], [])
        self.assertEqual(data["loitering_frames"], 0)
        self.assertEqual(data["loitering_threshold_seconds"], 5)
        self.assertIsNone(data["alert_id"])

        # New unified threat fields
        self.assertFalse(data["weapon_detected"])
        self.assertFalse(data["fall_detected"])
        self.assertFalse(data["fight_detected"])
        self.assertFalse(data["restricted_entry"])

        # Risk assessment
        self.assertIn("risk", data)
        self.assertEqual(data["risk"]["risk_level"], "Low")
        self.assertEqual(data["risk"]["risk_score"], 20)

        # No alert in database
        db = TestSessionLocal()
        self.assertEqual(db.query(Alert).count(), 0)
        db.close()

    # 2. Video with simulated weapon signal -> weapon detection alert created
    @patch("backend.routes.camera.ml_service.analyze_video_frame")
    def test_02_video_with_simulated_weapon_signal(self, mock_analyze):
        mock_analyze.return_value = {
            "person_count": 1,
            "tracked_ids": [101],
            "loitering_detected": False,
            "loitering_people": [],
            "weapon_detected": True,
            "detected_weapons": [{"weapon": "gun", "confidence": 0.89}],
            "fall_detected": False,
            "fight_proximity": False,
            "restricted_entry": False,
            "restricted_zone": None,
        }

        files = {"file": ("weapon_event.mp4", self.sample_video_bytes, "video/mp4")}
        res = client.post("/camera/analyze-video", files=files, headers=self.auth_headers)

        self.assertEqual(res.status_code, 200, res.text)
        data = res.json()

        self.assertTrue(data["weapon_detected"])
        self.assertGreater(data["weapon_frames"], 0)
        self.assertEqual(len(data["detected_weapons"]), 1)
        self.assertEqual(data["detected_weapons"][0]["weapon"], "gun")

        # Risk score and alert
        self.assertIsNotNone(data["alert_id"])
        self.assertIn("risk", data)

        # Verify persisted alert in isolated DB
        db = TestSessionLocal()
        alert = db.query(Alert).filter_by(id=data["alert_id"]).first()
        self.assertIsNotNone(alert)
        self.assertEqual(alert.alert_type, "Weapon Detection")
        self.assertEqual(alert.severity, "critical")
        self.assertIn("gun", alert.description)
        db.close()

    # 3. Video with simulated fall signal -> fall detection alert created
    @patch("backend.routes.camera.ml_service.analyze_video_frame")
    def test_03_video_with_simulated_fall_signal(self, mock_analyze):
        mock_analyze.return_value = {
            "person_count": 1,
            "tracked_ids": [202],
            "loitering_detected": False,
            "loitering_people": [],
            "weapon_detected": False,
            "detected_weapons": [],
            "fall_detected": True,
            "fight_proximity": False,
            "restricted_entry": False,
            "restricted_zone": None,
        }

        files = {"file": ("fall_event.mp4", self.sample_video_bytes, "video/mp4")}
        res = client.post("/camera/analyze-video", files=files, headers=self.auth_headers)

        self.assertEqual(res.status_code, 200, res.text)
        data = res.json()

        self.assertTrue(data["fall_detected"])
        self.assertGreater(data["fall_frames"], 0)
        self.assertIsNotNone(data["alert_id"])

        db = TestSessionLocal()
        alert = db.query(Alert).filter_by(id=data["alert_id"]).first()
        self.assertIsNotNone(alert)
        self.assertEqual(alert.alert_type, "Fall Detection")
        self.assertEqual(alert.severity, "high")
        db.close()

    # 4. Video with simulated restricted-zone signal -> restricted entry alert created
    @patch("backend.routes.camera.ml_service.analyze_video_frame")
    def test_04_video_with_restricted_zone_signal(self, mock_analyze):
        mock_analyze.return_value = {
            "person_count": 1,
            "tracked_ids": [303],
            "loitering_detected": False,
            "loitering_people": [],
            "weapon_detected": False,
            "detected_weapons": [],
            "fall_detected": False,
            "fight_proximity": False,
            "restricted_entry": True,
            "restricted_zone": "Server Room Area",
        }

        files = {"file": ("zone_event.mp4", self.sample_video_bytes, "video/mp4")}
        res = client.post("/camera/analyze-video", files=files, headers=self.auth_headers)

        self.assertEqual(res.status_code, 200, res.text)
        data = res.json()

        self.assertTrue(data["restricted_entry"])
        self.assertEqual(data["restricted_zone"], "Server Room Area")
        self.assertIsNotNone(data["alert_id"])

        db = TestSessionLocal()
        alert = db.query(Alert).filter_by(id=data["alert_id"]).first()
        self.assertIsNotNone(alert)
        self.assertEqual(alert.alert_type, "Restricted Entry")
        self.assertIn(alert.severity, ("high", "critical"))
        self.assertIn("Server Room Area", alert.location)
        db.close()

    # 5. Loitering aggregation & deduplication via create_risk_alert / create_cctv_alert
    @patch("backend.routes.camera.ml_service.analyze_video_frame")
    def test_05_loitering_aggregation_and_deduplication(self, mock_analyze):
        mock_analyze.return_value = {
            "person_count": 1,
            "tracked_ids": [404],
            "loitering_detected": True,
            "loitering_people": [{"person_id": 404, "x1": 10, "y1": 10, "x2": 50, "y2": 100, "loitering": True}],
            "weapon_detected": False,
            "detected_weapons": [],
            "fall_detected": False,
            "fight_proximity": False,
            "restricted_entry": False,
            "restricted_zone": None,
        }

        files = {"file": ("loitering_event.mp4", self.sample_video_bytes, "video/mp4")}
        res1 = client.post("/camera/analyze-video", files=files, headers=self.auth_headers)
        self.assertEqual(res1.status_code, 200, res1.text)
        data1 = res1.json()

        self.assertTrue(data1["loitering_detected"])
        self.assertEqual(data1["loitering_person_ids"], [404])
        self.assertIsNotNone(data1["alert_id"])
        first_alert_id = data1["alert_id"]

        # Run immediately again (within 30 seconds) -> deduplication must return same alert ID
        files2 = {"file": ("loitering_event2.mp4", self.sample_video_bytes, "video/mp4")}
        res2 = client.post("/camera/analyze-video", files=files2, headers=self.auth_headers)
        self.assertEqual(res2.status_code, 200, res2.text)
        data2 = res2.json()

        self.assertEqual(data2["alert_id"], first_alert_id)

        # Database should have exactly 1 Alert record due to deduplication
        db = TestSessionLocal()
        self.assertEqual(db.query(Alert).count(), 1)
        alert = db.query(Alert).first()
        self.assertEqual(alert.alert_type, "Loitering Detection")
        self.assertEqual(alert.severity, "medium")
        db.close()

    # 6. Fight heuristic safety check: proximity does NOT trigger confirmed critical fight alert
    @patch("backend.routes.camera.ml_service.analyze_video_frame")
    def test_06_fight_proximity_heuristic_does_not_trigger_critical_fight_alert(self, mock_analyze):
        mock_analyze.return_value = {
            "person_count": 2,
            "tracked_ids": [501, 502],
            "loitering_detected": False,
            "loitering_people": [],
            "weapon_detected": False,
            "detected_weapons": [],
            "fall_detected": False,
            "fight_proximity": True,  # 2D centroid distance < 0.25 heuristic
            "restricted_entry": False,
            "restricted_zone": None,
        }

        files = {"file": ("two_walking.mp4", self.sample_video_bytes, "video/mp4")}
        res = client.post("/camera/analyze-video", files=files, headers=self.auth_headers)

        self.assertEqual(res.status_code, 200, res.text)
        data = res.json()

        # Crucial safety assertions:
        # 1. fight_detected must be False (unconfirmed)
        self.assertFalse(data["fight_detected"])
        # 2. fight_proximity_detected must record the heuristic signal
        self.assertTrue(data["fight_proximity_detected"])
        self.assertGreater(data["fight_proximity_frames"], 0)
        # 3. experimental_signals note present
        self.assertIn("experimental_signals", data)
        self.assertTrue(data["experimental_signals"]["fight_proximity_detected"])
        # 4. No high/critical fight alert created in DB
        self.assertIsNone(data["alert_id"])
        db = TestSessionLocal()
        self.assertEqual(db.query(Alert).count(), 0)
        db.close()

    # 7. Invalid video handling and resource cleanup
    def test_07_invalid_video_handling_and_cleanup(self):
        # Bad extension
        files = {"file": ("malicious.exe", b"not a video", "application/octet-stream")}
        res = client.post("/camera/analyze-video", files=files, headers=self.auth_headers)
        self.assertEqual(res.status_code, 400)
        self.assertIn("MP4, AVI, MOV, or MKV", res.json()["detail"])

        # Empty video
        files = {"file": ("empty.mp4", b"", "video/mp4")}
        res = client.post("/camera/analyze-video", files=files, headers=self.auth_headers)
        self.assertEqual(res.status_code, 400)
        self.assertIn("Empty video", res.json()["detail"])

        # Corrupt video bytes
        files = {"file": ("corrupt.mp4", b"corrupted random data bytes here", "video/mp4")}
        res = client.post("/camera/analyze-video", files=files, headers=self.auth_headers)
        self.assertEqual(res.status_code, 400)

    # 8. Risk model input compatibility and feature integrity
    def test_08_risk_model_input_compatibility(self):
        # Baseline normal
        pred_clean = risk_service.predict()
        self.assertEqual(pred_clean["risk_level"], "Low")
        self.assertEqual(pred_clean["risk_score"], 20)

        # Single threat
        pred_weapon = risk_service.predict(weapon=True)
        self.assertIn(pred_weapon["risk_level"], ["Medium", "High"])

        # Multi-threat combination
        pred_multi = risk_service.predict(weapon=True, fall=True, restricted_entry=True)
        self.assertEqual(pred_multi["risk_level"], "High")
        self.assertEqual(pred_multi["risk_score"], 80)

        # Verify create_risk_alert returns expected dictionary schema
        risk_alert = create_risk_alert(
            db=None,
            weapon=True,
            fall=False,
            loitering=True,
        )
        self.assertIn("risk_level", risk_alert)
        self.assertIn("risk_score", risk_alert)
        self.assertIn("factors", risk_alert)
        self.assertIsNone(risk_alert["alert_id"])  # db is None

    # 9. Existing response fields compatibility
    @patch("backend.routes.camera.ml_service.analyze_video_frame")
    def test_09_existing_response_fields_remain_compatible(self, mock_analyze):
        mock_analyze.return_value = {
            "person_count": 0,
            "tracked_ids": [],
            "loitering_detected": False,
            "loitering_people": [],
            "weapon_detected": False,
            "detected_weapons": [],
            "fall_detected": False,
            "fight_proximity": False,
            "restricted_entry": False,
            "restricted_zone": None,
        }

        files = {"file": ("compat_test.mp4", self.sample_video_bytes, "video/mp4")}
        res = client.post("/camera/analyze-video", files=files, headers=self.auth_headers)
        self.assertEqual(res.status_code, 200)
        data = res.json()

        # All existing legacy keys MUST be present:
        legacy_keys = [
            "message",
            "frames_analyzed",
            "loitering_detected",
            "loitering_person_ids",
            "loitering_frames",
            "loitering_threshold_seconds",
            "alert_id",
        ]
        for k in legacy_keys:
            self.assertIn(k, data, f"Missing legacy key {k}")

        # All new unified pipeline keys MUST be present:
        new_keys = [
            "analysis_status",
            "detector_analysis",
            "video_duration_seconds",
            "person_count",
            "weapon_detected",
            "detected_weapons",
            "weapon_frames",
            "fall_detected",
            "fall_frames",
            "fight_detected",
            "fight_proximity_detected",
            "fight_proximity_frames",
            "restricted_entry",
            "restricted_zone",
            "restricted_entry_frames",
            "after_hours",
            "risk",
            "detector_statuses",
            "processing_errors",
            "experimental_signals",
        ]
        for k in new_keys:
            self.assertIn(k, data, f"Missing new key {k}")

    # 10. Real unmocked service integration test
    def test_10_unmocked_video_real_service_integration(self):
        """Exercises the real endpoint, OpenCV decoding, and real vision detectors with ZERO mocks."""
        files = {"file": ("real_integration.mp4", self.sample_video_bytes, "video/mp4")}
        res = client.post("/camera/analyze-video", files=files, headers=self.auth_headers)

        self.assertEqual(res.status_code, 200, res.text)
        data = res.json()

        # Real video properties
        self.assertGreater(data["frames_analyzed"], 0)
        self.assertIsNotNone(data["video_duration_seconds"])

        # Real vision detectors ran without unhandled crashes
        self.assertIn("detector_statuses", data)
        self.assertEqual(data["detector_statuses"]["person_detection"], "active")
        self.assertEqual(data["detector_statuses"]["weapon_detection"], "active")
        self.assertEqual(data["detector_statuses"]["loitering_detection"], "active")
        self.assertEqual(data["detector_statuses"]["restricted_zone"], "active")

        # Zero processing errors on synthetic clean video
        self.assertEqual(data["processing_errors"], {})
        self.assertEqual(data["analysis_status"], "success")

        # Unmocked video evaluates real CNN model: black frames produce fall_detected=True (CNN prediction <= 0.5)
        self.assertIn("risk", data)
        self.assertTrue(data["fall_detected"])
        self.assertEqual(data["risk"]["risk_level"], "Medium")
        self.assertEqual(data["risk"]["risk_score"], 50)
        self.assertEqual(data["risk"]["model_type"], "Random Forest Classifier (Trained ML Model)")
        self.assertIsNotNone(data["alert_id"])

    # 11. Detector exception reported accurately instead of silently becoming negative detection
    def test_11_detector_exception_reported_accurately_not_swallowed(self):
        """Verifies detector exceptions are tracked in processing_errors and detector_statuses."""
        from backend.routes.camera import ml_service

        with patch.object(ml_service.weapon_detector, "detect", side_effect=RuntimeError("Simulated Detector Crash")):
            files = {"file": ("exception_test.mp4", self.sample_video_bytes, "video/mp4")}
            res = client.post("/camera/analyze-video", files=files, headers=self.auth_headers)

            self.assertEqual(res.status_code, 200, res.text)
            data = res.json()

            # Error must NOT be silently swallowed as a verified negative detection
            self.assertIsNone(data["weapon_detected"])
            self.assertEqual(data["analysis_status"], "partial")
            self.assertIn("processing_errors", data)
            self.assertIn("weapon_detection", data["processing_errors"])
            self.assertIn("Simulated Detector Crash", data["processing_errors"]["weapon_detection"])

            # Detector status and analysis mapping must accurately reflect error state
            self.assertIn("error: Simulated Detector Crash", data["detector_statuses"]["weapon_detection"])
            self.assertEqual(data["detector_analysis"]["weapon_detection"], "error")

    # 12. Risk model fallback confidence semantics and error reporting
    def test_12_risk_model_fallback_confidence_not_hardcoded_and_reports_error(self):
        """Verifies rule-based fallback heuristic does not hardcode confidence 1.0 and reports errors."""
        from backend.services.risk_service import RiskService

        # Instance with no model loaded
        service_no_model = RiskService()
        service_no_model.model = None
        service_no_model.model_load_error = "Model weights unavailable in test"

        result_fallback = service_no_model.predict(weapon=True)
        # Confidence must be None when not calibrated from an ML model
        self.assertIsNone(result_fallback["confidence"])
        self.assertEqual(result_fallback["confidence_type"], "uncalibrated_heuristic")
        self.assertEqual(result_fallback["risk_score_type"], "rule_based_additive_points")
        self.assertIn("Model load error", result_fallback["model_type"])
        self.assertEqual(result_fallback["model_load_error"], "Model weights unavailable in test")

        # Instance where inference raises an unexpected exception
        service_broken_infer = RiskService()
        with patch("backend.services.risk_service.predict_risk", side_effect=ValueError("Corrupted feature vector")):
            result_broken = service_broken_infer.predict(fall=True)
            self.assertIsNone(result_broken["confidence"])
            self.assertIn("Inference error: Corrupted feature vector", result_broken["model_type"])
            self.assertEqual(result_broken["inference_error"], "Corrupted feature vector")

    # 13. Black-frame fall prediction regression documentation
    def test_13_synthetic_black_frame_fall_prediction_documented(self):
        """Documents that synthetic all-zero frames produce a fall prediction due to CNN out-of-distribution response."""
        from backend.ml_models.fall_detection import FallDetection

        detector = FallDetection()
        if detector.model is not None:
            black_frame = np.zeros((240, 320, 3), dtype=np.uint8)
            result = detector.detect(black_frame)
            # The trained Keras sigmoid output on zero pixels is ~0.43 (<= 0.5), yielding 1.0 - 0.43 = 0.57 >= 0.5 (True)
            self.assertTrue(result)

    # 14. Partial failure preserves signals from functioning detectors without creating false incident
    @patch("backend.routes.camera.ml_service.analyze_video_frame")
    def test_14_partial_detector_failure_preserves_functioning_signals(self, mock_analyze):
        """Verifies partial detector failure preserves functioning detector signals without creating false incident for crashed detector."""
        mock_analyze.return_value = {
            "person_count": 1,
            "tracked_ids": [601],
            "loitering_detected": True,
            "loitering_people": [{"person_id": 601, "x1": 10, "y1": 10, "x2": 50, "y2": 100, "loitering": True}],
            "weapon_detected": False,
            "detected_weapons": [],
            "fall_detected": False,
            "fight_proximity": False,
            "restricted_entry": False,
            "restricted_zone": None,
            "detector_errors": {"weapon_detection": "Sensor read failure"},
        }

        files = {"file": ("partial_fail.mp4", self.sample_video_bytes, "video/mp4")}
        res = client.post("/camera/analyze-video", files=files, headers=self.auth_headers)

        self.assertEqual(res.status_code, 200, res.text)
        data = res.json()

        self.assertEqual(data["analysis_status"], "partial")
        self.assertIsNone(data["weapon_detected"])  # Not False
        self.assertTrue(data["loitering_detected"])  # Preserved

        # Alert is created for LOITERING, NOT for the crashed weapon detector
        self.assertIsNotNone(data["alert_id"])
        db = TestSessionLocal()
        alert = db.query(Alert).filter_by(id=data["alert_id"]).first()
        self.assertIsNotNone(alert)
        self.assertEqual(alert.alert_type, "Loitering Detection")
        self.assertNotEqual(alert.alert_type, "Weapon Detection")
        db.close()

    # 15. Risk score semantics clarification
    def test_15_risk_score_semantics_clarification(self):
        """Verifies risk score and confidence are explicitly typed and distinguished from event probabilities."""
        pred = risk_service.predict(weapon=True, fall=True)
        self.assertEqual(pred["risk_score_type"], "discrete_tier_score")
        self.assertEqual(pred["confidence_type"], "model_class_confidence")
        self.assertIn(pred["risk_score"], [20, 50, 80])
        self.assertIsInstance(pred["confidence"], float)

    # 16. Image analysis fight proximity heuristic safety
    @patch("backend.routes.camera.ml_service.analyze_frame")
    def test_16_image_analysis_fight_proximity_heuristic_safety(self, mock_analyze):
        """Image analysis proximity heuristic does NOT create a confirmed high/critical fight alert in DB."""
        mock_analyze.return_value = {
            "fall_detected": False,
            "fight_detected": True,  # Heuristic proximity triggered
            "fight_proximity": True,
            "weapon_detected": False,
            "detected_weapons": [],
            "person_count": 2,
            "people": [{"x1": 100, "y1": 100, "x2": 200, "y2": 300}, {"x1": 120, "y1": 110, "x2": 220, "y2": 310}],
            "restricted_entry": False,
            "restricted_zone": None,
            "after_hours": False,
            "after_hours_message": "Within campus hours",
            "detector_errors": {},
        }

        files = {"file": ("people_close.jpg", self.sample_image_bytes, "image/jpeg")}
        res = client.post("/camera/analyze", files=files, headers=self.auth_headers)

        self.assertEqual(res.status_code, 200, res.text)
        data = res.json()

        # Fight detected must remain False (unconfirmed), while proximity is reported
        self.assertFalse(data["fight_detected"])
        self.assertTrue(data["fight_proximity_detected"])
        self.assertIn("experimental_signals", data)
        self.assertTrue(data["experimental_signals"]["fight_proximity_detected"])

        # No unconfirmed fight alert created in the database
        self.assertIsNone(data["alert_id"])
        db = TestSessionLocal()
        self.assertEqual(db.query(Alert).count(), 0)
        db.close()

    # 17. Alert lifecycle: creation -> assign -> escalate -> resolve
    @patch("backend.routes.camera.ml_service.analyze_video_frame")
    def test_17_alert_lifecycle_from_cctv_creation_to_resolve(self, mock_analyze):
        """Trace CCTV alert creation through acknowledgment, escalation, and resolution."""
        mock_analyze.return_value = {
            "person_count": 1,
            "tracked_ids": [101],
            "loitering_detected": False,
            "loitering_people": [],
            "weapon_detected": True,
            "detected_weapons": [{"weapon": "gun", "confidence": 0.88}],
            "fall_detected": False,
            "fight_proximity": False,
            "restricted_entry": False,
            "restricted_zone": None,
        }

        files = {"file": ("weapon_event.mp4", self.sample_video_bytes, "video/mp4")}
        res = client.post("/camera/analyze-video", files=files, headers=self.auth_headers)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        alert_id = data["alert_id"]
        self.assertIsNotNone(alert_id)

        # 1. Verify alert created as active
        db = TestSessionLocal()
        alert = db.query(Alert).filter_by(id=alert_id).first()
        self.assertEqual(alert.status, "active")
        self.assertEqual(alert.alert_type, "Weapon Detection")
        db.close()

        # 2. Acknowledge alert
        res_ack = client.patch(f"/alerts/{alert_id}/acknowledge", headers=self.auth_headers)
        self.assertEqual(res_ack.status_code, 200)
        self.assertEqual(res_ack.json()["alert"]["status"], "acknowledged")

        # 3. Escalate alert
        res_esc = client.patch(f"/alerts/{alert_id}/escalate", headers=self.auth_headers)
        self.assertEqual(res_esc.status_code, 200)
        self.assertEqual(res_esc.json()["alert"]["status"], "escalated")
        self.assertEqual(res_esc.json()["alert"]["severity"], "critical")

        # 4. Resolve alert
        res_res = client.patch(f"/alerts/{alert_id}/resolve", headers=self.auth_headers)
        self.assertEqual(res_res.status_code, 200)
        self.assertEqual(res_res.json()["alert"]["status"], "resolved")

        # 5. Cannot re-acknowledge resolved alert
        res_err = client.patch(f"/alerts/{alert_id}/acknowledge", headers=self.auth_headers)
        self.assertEqual(res_err.status_code, 400)

    # 18. Incident reporting and timeline audit logging
    def test_18_incident_reporting_workflow_and_audit_trail(self):
        """User reports incident -> NLP categorization -> status updates -> timeline audit logs recorded."""
        # 1. Report incident
        payload = {
            "incident_type": "Suspicious Activity",
            "location": "Library 2nd Floor",
            "description": "Unattended suspicious backpack left near computer terminal",
            "attachment": "/uploads/backpack.jpg",
        }
        res_report = client.post("/incidents", json=payload, headers=self.auth_headers)
        self.assertEqual(res_report.status_code, 200, res_report.text)
        incident_id = res_report.json()["incident_id"]

        # 2. Update status: submitted -> acknowledged
        res_ack = client.patch(f"/incidents/{incident_id}/status?status=acknowledged", headers=self.auth_headers)
        self.assertEqual(res_ack.status_code, 200)
        self.assertEqual(res_ack.json()["status"], "acknowledged")

        # 3. Update status: acknowledged -> resolved
        res_res = client.patch(f"/incidents/{incident_id}/status?status=resolved", headers=self.auth_headers)
        self.assertEqual(res_res.status_code, 200)
        self.assertEqual(res_res.json()["status"], "resolved")

        # 4. Verify 4 chronological audit events in timeline: submitted, nlp_analyzed, acknowledged, resolved
        res_logs = client.get(f"/incidents/{incident_id}/logs", headers=self.auth_headers)
        self.assertEqual(res_logs.status_code, 200)
        actions = [log["action"] for log in res_logs.json()]
        self.assertEqual(actions, ["submitted", "nlp_analyzed", "acknowledged", "resolved"])

    # 19. Successful alert-to-incident promotion
    def test_19_successful_alert_to_incident_promotion(self):
        """Promote an active CCTV alert into a formal incident ticket with audit linkage."""
        # 1. Create CCTV alert in test DB
        db = TestSessionLocal()
        alert = Alert(
            alert_type="Weapon Detection",
            location="Science Block - North Wing",
            description="CCTV Threat Alert: Weapons detected: gun. Risk Level: High (Score: 80/100).",
            severity="critical",
            status="active",
        )
        db.add(alert)
        db.commit()
        db.refresh(alert)
        alert_id = alert.id
        db.close()

        # 2. Promote to incident with officer notes
        payload = {"notes": "Security response unit deployed to Science Block"}
        res = client.post(f"/alerts/{alert_id}/promote-to-incident", json=payload, headers=self.auth_headers)
        self.assertEqual(res.status_code, 200, res.text)
        data = res.json()

        self.assertFalse(data["is_duplicate"])
        self.assertEqual(data["alert_id"], alert_id)
        self.assertIsNotNone(data["incident_id"])

        # 3. Verify incident record in DB
        db = TestSessionLocal()
        incident = db.query(Incident).filter_by(id=data["incident_id"]).first()
        self.assertIsNotNone(incident)
        self.assertEqual(incident.alert_id, alert_id)
        self.assertEqual(incident.location, "Science Block - North Wing")
        self.assertEqual(incident.incident_type, "Weapon Detection")
        self.assertEqual(incident.nlp_urgency, "High")
        self.assertIn("Officer Notes: Security response unit deployed", incident.description)

        # 4. Originating alert transitioned to acknowledged and assigned
        alert_updated = db.query(Alert).filter_by(id=alert_id).first()
        self.assertEqual(alert_updated.status, "acknowledged")
        self.assertEqual(alert_updated.assigned_to, self.user_id)

        # 5. Incident audit logs recorded
        logs = db.query(IncidentLog).filter_by(incident_id=incident.id).order_by(IncidentLog.id.asc()).all()
        self.assertEqual(len(logs), 2)
        self.assertEqual(logs[0].action, "promoted_from_cctv")
        self.assertIn("Promoted from CCTV Alert", logs[0].details)
        self.assertEqual(logs[0].performed_by, self.user_id)
        self.assertEqual(logs[1].action, "nlp_analyzed")
        db.close()

    # 20. Prevent duplicate incidents on repeated promotion requests
    def test_20_duplicate_promotion_prevention(self):
        """Repeated promotion requests for the same alert return the existing incident without duplicates."""
        db = TestSessionLocal()
        alert = Alert(
            alert_type="Fall Detection",
            location="Gymnasium Entrance",
            description="Person fall detected by CCTV intelligence",
            severity="high",
            status="active",
        )
        db.add(alert)
        db.commit()
        db.refresh(alert)
        alert_id = alert.id
        db.close()

        # First promotion
        res1 = client.post(f"/alerts/{alert_id}/promote-to-incident", json={}, headers=self.auth_headers)
        self.assertEqual(res1.status_code, 200)
        data1 = res1.json()
        self.assertFalse(data1["is_duplicate"])
        first_incident_id = data1["incident_id"]

        # Repeated promotion request
        res2 = client.post(f"/alerts/{alert_id}/promote-to-incident", json={}, headers=self.auth_headers)
        self.assertEqual(res2.status_code, 200)
        data2 = res2.json()
        self.assertTrue(data2["is_duplicate"])
        self.assertEqual(data2["incident_id"], first_incident_id)
        self.assertIn("already been promoted", data2["message"])

        # Exactly 1 incident exists in DB
        db = TestSessionLocal()
        self.assertEqual(db.query(Incident).filter_by(alert_id=alert_id).count(), 1)
        db.close()

    # 21. Promotion for missing alert returns 404
    def test_21_promote_missing_alert_returns_404(self):
        """Promoting a nonexistent alert ID returns 404 Not Found."""
        res = client.post("/alerts/999999/promote-to-incident", json={}, headers=self.auth_headers)
        self.assertEqual(res.status_code, 404)
        self.assertIn("Alert #999999 not found", res.json()["detail"])

    # 22. Promotion authorization checks
    def test_22_promote_unauthorized_access(self):
        """Students and unauthenticated users cannot promote alerts."""
        db = TestSessionLocal()
        alert = Alert(
            alert_type="Restricted Entry",
            location="Main Campus",
            description="Restricted entry alert",
            severity="high",
            status="active",
        )
        db.add(alert)
        db.commit()
        db.refresh(alert)
        alert_id = alert.id
        db.close()

        # Student user (forbidden)
        db = TestSessionLocal()
        student_user = User(
            name="Student User",
            email="student_promo_test@campusguard.com",
            password=password_hash.hash("StudentPass123!"),
            role="student",
        )
        db.add(student_user)
        db.commit()
        db.refresh(student_user)
        student_id = student_user.id
        db.close()

        student_token = create_access_token(student_id, "student")
        student_headers = {"Authorization": f"Bearer {student_token}"}
        res_student = client.post(f"/alerts/{alert_id}/promote-to-incident", json={}, headers=student_headers)
        self.assertEqual(res_student.status_code, 403)

        # Unauthenticated request (unauthorized)
        res_no_auth = client.post(f"/alerts/{alert_id}/promote-to-incident", json={})
        self.assertEqual(res_no_auth.status_code, 401)


if __name__ == "__main__":
    unittest.main()
