"""
Test Suite for Batch 4: Concurrency, Uploads, and Missing-Model Handling.

Verifies:
1. Oversize uploads rejected as soon as size limit is exceeded (without reading unnecessary data):
   - /incidents/upload (limit 10 MB) -> 413
   - /camera/analyze (limit 20 MB) -> 413
   - /camera/analyze-video (limit 100 MB) -> 413
2. Content-Length header exceeding limit is rejected immediately with 413.
3. Missing detectors (person_detection, weapon_detection) report 'unavailable' in detector_statuses
   and detector_analysis, and never report 'clear' or false negatives.
4. Optional threshold_seconds query parameter on /camera/analyze-video:
   - Defaults to 5 seconds
   - Accepts values between 1 and 600 seconds
   - Rejects values < 1 or > 600 with 400
5. Thread concurrency / lock test:
   - Two concurrent threads executing model analysis are serialized via ANALYSIS_LOCK.
"""

import io
import os
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch, MagicMock

import cv2
import numpy as np

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.config.database import Base, get_db
from backend.database.models.user import User
from backend.services.auth_service import create_access_token, password_hash
from backend.routes.camera import ANALYSIS_LOCK
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


def create_synthetic_mp4(num_frames=10, width=64, height=64, fps=10.0):
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tf:
        temp_path = tf.name
    try:
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


class TestBatch4ConcurrencyUploads(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app.dependency_overrides[get_db] = override_get_db
        Base.metadata.create_all(bind=test_engine)

        db = TestSessionLocal()
        cls.sec_user = User(
            name="Batch4 Officer",
            email="b4_officer@campusguard.com",
            password=password_hash.hash("Security123!"),
            role="security",
        )
        db.add(cls.sec_user)
        db.commit()
        db.refresh(cls.sec_user)
        cls.sec_id = cls.sec_user.id
        db.close()

        cls.token = create_access_token(cls.sec_id, "security")
        cls.auth_headers = {"Authorization": f"Bearer {cls.token}"}
        cls.sample_video_bytes = create_synthetic_mp4()
        cls.sample_image_bytes = cv2.imencode(".jpg", np.zeros((30, 30, 3), dtype=np.uint8))[1].tobytes()

    @classmethod
    def tearDownClass(cls):
        app.dependency_overrides.pop(get_db, None)

    # 1. Content-Length header too large is rejected immediately
    def test_01_content_length_too_large_rejected(self):
        # /incidents/upload (limit 10 MB)
        res = client.post(
            "/incidents/upload",
            files={"file": ("test.jpg", b"small_payload", "image/jpeg")},
            headers={**self.auth_headers, "Content-Length": str(15 * 1024 * 1024)},
        )
        self.assertEqual(res.status_code, 413)
        self.assertIn("10 MB", res.json()["detail"])

        # /camera/analyze (limit 20 MB)
        res = client.post(
            "/camera/analyze",
            files={"file": ("test.jpg", self.sample_image_bytes, "image/jpeg")},
            headers={**self.auth_headers, "Content-Length": str(25 * 1024 * 1024)},
        )
        self.assertEqual(res.status_code, 413)
        self.assertIn("20 MB", res.json()["detail"])

        # /camera/analyze-video (limit 100 MB)
        res = client.post(
            "/camera/analyze-video",
            files={"file": ("test.mp4", self.sample_video_bytes, "video/mp4")},
            headers={**self.auth_headers, "Content-Length": str(120 * 1024 * 1024)},
        )
        self.assertEqual(res.status_code, 413)
        self.assertIn("100 MB", res.json()["detail"])

    # 2. Oversize chunked upload rejected without reading the whole body
    def test_02_oversize_chunked_upload_rejected_early(self):
        from fastapi import UploadFile
        from backend.routes.alerts import upload_incident_attachment
        from backend.routes.camera import analyze_camera, analyze_video

        # Create a file-like stream that counts how many bytes are read
        class MonitoredStream(io.BytesIO):
            def __init__(self, total_size):
                super().__init__()
                self.total_size = total_size
                self.bytes_read = 0

            def read(self, size=-1):
                if self.bytes_read >= self.total_size:
                    return b""
                take = min(size if size > 0 else 1024 * 1024, self.total_size - self.bytes_read)
                self.bytes_read += take
                return b"x" * take

        # Test incident upload limit (10 MB): stream 15 MB
        stream_incident = MonitoredStream(15 * 1024 * 1024)
        upload_incident = UploadFile(filename="incident_big.jpg", file=stream_incident)
        from fastapi import HTTPException
        with self.assertRaises(HTTPException) as ctx:
            upload_incident_attachment(file=upload_incident, request=None, user={"role": "security"})
        self.assertEqual(ctx.exception.status_code, 413)
        self.assertIn("10 MB", ctx.exception.detail)
        # Verify it aborted early and did not read the entire 15 MB body
        self.assertLess(stream_incident.bytes_read, 15 * 1024 * 1024)
        self.assertEqual(stream_incident.bytes_read, 11 * 1024 * 1024)

        # Test image upload limit (20 MB): stream 25 MB
        stream_image = MonitoredStream(25 * 1024 * 1024)
        upload_img = UploadFile(filename="image_big.jpg", file=stream_image)
        with self.assertRaises(HTTPException) as ctx:
            analyze_camera(request=None, file=upload_img, db=MagicMock(), user={"role": "security"})
        self.assertEqual(ctx.exception.status_code, 413)
        self.assertIn("20 MB", ctx.exception.detail)
        self.assertLess(stream_image.bytes_read, 25 * 1024 * 1024)
        self.assertEqual(stream_image.bytes_read, 21 * 1024 * 1024)

        # Test video upload limit (100 MB): stream 120 MB
        stream_video = MonitoredStream(120 * 1024 * 1024)
        upload_vid = UploadFile(filename="video_big.mp4", file=stream_video)
        with self.assertRaises(HTTPException) as ctx:
            analyze_video(request=None, file=upload_vid, threshold_seconds=5, db=MagicMock(), user={"role": "security"})
        self.assertEqual(ctx.exception.status_code, 413)
        self.assertIn("100 MB", ctx.exception.detail)
        self.assertLess(stream_video.bytes_read, 120 * 1024 * 1024)
        self.assertEqual(stream_video.bytes_read, 101 * 1024 * 1024)

    # 3. Missing detector reported as 'unavailable', never as 'clear' or false negative
    @patch("backend.routes.camera.ml_service.analyze_video_frame")
    def test_03_missing_detector_reported_as_unavailable(self, mock_analyze):
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
            "detector_errors": {},
        }

        from backend.routes.camera import ml_service

        orig_weapon = ml_service.weapon_detector
        orig_person = ml_service.person_model

        try:
            # Simulate weapon detector unavailable (missing model file)
            ml_service.weapon_detector = None
            ml_service.person_model = None

            files = {"file": ("test_missing.mp4", self.sample_video_bytes, "video/mp4")}
            res = client.post("/camera/analyze-video", files=files, headers=self.auth_headers)
            self.assertEqual(res.status_code, 200, res.text)
            data = res.json()

            # Must report "unavailable" in detector_statuses and detector_analysis
            self.assertEqual(data["detector_statuses"]["weapon_detection"], "unavailable")
            self.assertEqual(data["detector_statuses"]["person_detection"], "unavailable")
            self.assertEqual(data["detector_statuses"]["loitering_detection"], "unavailable")

            self.assertEqual(data["detector_analysis"]["weapon_detection"], "unavailable")
            self.assertEqual(data["detector_analysis"]["loitering_detection"], "unavailable")

            # Must NOT report false negative or clear
            self.assertNotEqual(data["detector_analysis"]["weapon_detection"], "clear")
            self.assertNotEqual(data["detector_analysis"]["loitering_detection"], "clear")
            self.assertIsNone(data["weapon_detected"])

            # All expected contract keys must remain present
            expected_keys = [
                "analysis_status",
                "detector_analysis",
                "detector_statuses",
                "loitering_threshold_seconds",
                "weapon_detected",
                "loitering_detected",
                "fall_detected",
                "fight_detected",
                "risk",
            ]
            for key in expected_keys:
                self.assertIn(key, data)

        finally:
            ml_service.weapon_detector = orig_weapon
            ml_service.person_model = orig_person

    # 4. threshold_seconds parameter works and invalid values are rejected
    @patch("backend.routes.camera.ml_service.analyze_video_frame")
    def test_04_threshold_seconds_works_and_rejects_invalid(self, mock_analyze):
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
            "detector_errors": {},
        }

        files = {"file": ("test_thresh.mp4", self.sample_video_bytes, "video/mp4")}

        # Default is 5
        res_default = client.post("/camera/analyze-video", files=files, headers=self.auth_headers)
        self.assertEqual(res_default.status_code, 200)
        self.assertEqual(res_default.json()["loitering_threshold_seconds"], 5)

        # Valid custom threshold: 15
        files = {"file": ("test_thresh.mp4", self.sample_video_bytes, "video/mp4")}
        res_15 = client.post("/camera/analyze-video?threshold_seconds=15", files=files, headers=self.auth_headers)
        self.assertEqual(res_15.status_code, 200)
        self.assertEqual(res_15.json()["loitering_threshold_seconds"], 15)

        # Valid boundaries: 1 and 600
        files = {"file": ("test_thresh.mp4", self.sample_video_bytes, "video/mp4")}
        res_1 = client.post("/camera/analyze-video?threshold_seconds=1", files=files, headers=self.auth_headers)
        self.assertEqual(res_1.status_code, 200)
        self.assertEqual(res_1.json()["loitering_threshold_seconds"], 1)

        files = {"file": ("test_thresh.mp4", self.sample_video_bytes, "video/mp4")}
        res_600 = client.post("/camera/analyze-video?threshold_seconds=600", files=files, headers=self.auth_headers)
        self.assertEqual(res_600.status_code, 200)
        self.assertEqual(res_600.json()["loitering_threshold_seconds"], 600)

        # Invalid: < 1
        files = {"file": ("test_thresh.mp4", self.sample_video_bytes, "video/mp4")}
        res_0 = client.post("/camera/analyze-video?threshold_seconds=0", files=files, headers=self.auth_headers)
        self.assertEqual(res_0.status_code, 400)
        self.assertIn("threshold_seconds must be between 1 and 600", res_0.json()["detail"])

        # Invalid: > 600
        files = {"file": ("test_thresh.mp4", self.sample_video_bytes, "video/mp4")}
        res_601 = client.post("/camera/analyze-video?threshold_seconds=601", files=files, headers=self.auth_headers)
        self.assertEqual(res_601.status_code, 400)
        self.assertIn("threshold_seconds must be between 1 and 600", res_601.json()["detail"])

        # Invalid: negative
        files = {"file": ("test_thresh.mp4", self.sample_video_bytes, "video/mp4")}
        res_neg = client.post("/camera/analyze-video?threshold_seconds=-10", files=files, headers=self.auth_headers)
        self.assertEqual(res_neg.status_code, 400)

    # 5. Lock test: two threads cannot execute model analysis concurrently
    def test_05_two_threads_cannot_analyse_concurrently(self):
        concurrent_analyses = []
        max_concurrency = [0]
        lock_held_checks = []
        counter_lock = threading.Lock()

        active_count = [0]

        def slow_analyze_frame(image):
            # Check if ANALYSIS_LOCK is held by current thread
            is_locked = ANALYSIS_LOCK.locked()
            with counter_lock:
                active_count[0] += 1
                current_active = active_count[0]
                if current_active > max_concurrency[0]:
                    max_concurrency[0] = current_active
                concurrent_analyses.append(current_active)
                lock_held_checks.append(is_locked)

            time.sleep(0.05)  # Simulate model inference time

            with counter_lock:
                active_count[0] -= 1

            return {
                "fall_detected": False,
                "fight_detected": False,
                "fight_proximity": False,
                "weapon_detected": False,
                "detected_weapons": [],
                "person_count": 0,
                "people": [],
                "restricted_entry": False,
                "restricted_zone": None,
                "after_hours": False,
                "after_hours_message": "Within campus hours",
                "detector_errors": {},
            }

        with patch("backend.routes.camera.ml_service.analyze_frame", side_effect=slow_analyze_frame):
            errors = []

            def worker():
                try:
                    files = {"file": ("snap.jpg", self.sample_image_bytes, "image/jpeg")}
                    res = client.post("/camera/analyze", files=files, headers=self.auth_headers)
                    if res.status_code != 200:
                        errors.append(f"HTTP {res.status_code}: {res.text}")
                except Exception as exc:
                    errors.append(str(exc))

            threads = [threading.Thread(target=worker) for _ in range(4)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

            self.assertEqual(errors, [], f"Thread worker encountered errors: {errors}")
            # Max concurrency inside the model analysis block must never exceed 1
            self.assertEqual(max_concurrency[0], 1, f"Concurrent analyses exceeded 1: {concurrent_analyses}")
            self.assertTrue(all(lock_held_checks), "ANALYSIS_LOCK was not locked during analysis")


if __name__ == "__main__":
    unittest.main()
