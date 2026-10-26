"""
Isolated Test Suite for Secure Uploaded Evidence Access Control (CG-004).

Verifies:
1. Unauthenticated requests to /uploads/{filename} return 401 Unauthorized.
2. Invalid or expired JWT tokens return 401 Unauthorized.
3. Valid authenticated requests return 200 OK with correct MIME types for images and PDFs.
4. Missing files return 404 Not Found.
5. Path traversal attempts return 404 Not Found.
6. Unsupported file extensions return 404 Not Found.
7. Upload and authenticated retrieval work end-to-end.

Uses an isolated in-memory SQLite database and temporary directory.
Never touches campusguard.db or production evidence files.
"""

import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
import jwt

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

os.environ["DATABASE_URL"] = "sqlite:///:memory:"

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient

from backend.config.database import Base, get_db
from backend.database.models.user import User
from backend.database.models.incident import Incident
from backend.services.auth_service import (
    create_access_token,
    password_hash,
    SECRET_KEY,
    ALGORITHM,
)
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


class TestSecureUploads(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app.dependency_overrides[get_db] = override_get_db
        Base.metadata.create_all(bind=test_engine)

        # Seed test student and test officer in isolated in-memory DB
        db = TestSessionLocal()
        cls.student_user = User(
            name="Upload Test Student",
            email="upload_student@campusguard.com",
            password=password_hash.hash("StudentPass123!"),
            role="student",
        )
        cls.other_student_user = User(
            name="Other Test Student",
            email="other_student@campusguard.com",
            password=password_hash.hash("StudentPass123!"),
            role="student",
        )
        cls.security_user = User(
            name="Upload Test Officer",
            email="upload_officer@campusguard.com",
            password=password_hash.hash("SecurityPass123!"),
            role="security",
        )
        db.add(cls.student_user)
        db.add(cls.other_student_user)
        db.add(cls.security_user)
        db.commit()
        db.refresh(cls.student_user)
        db.refresh(cls.other_student_user)
        db.refresh(cls.security_user)

        cls.student_id = cls.student_user.id
        cls.other_student_id = cls.other_student_user.id
        cls.security_id = cls.security_user.id
        db.close()

        cls.student_token = create_access_token(cls.student_id, "student")
        cls.other_student_token = create_access_token(cls.other_student_id, "student")
        cls.security_token = create_access_token(cls.security_id, "security")

        cls.student_headers = {"Authorization": f"Bearer {cls.student_token}"}
        cls.other_student_headers = {"Authorization": f"Bearer {cls.other_student_token}"}
        cls.security_headers = {"Authorization": f"Bearer {cls.security_token}"}

        # Create isolated temporary directory for upload tests
        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.orig_upload_dir = alerts_module.UPLOAD_DIR
        alerts_module.UPLOAD_DIR = cls.temp_dir.name

        # Create sample evidence files in the temp directory
        cls.sample_jpg = "sample_evidence.jpg"
        with open(os.path.join(cls.temp_dir.name, cls.sample_jpg), "wb") as f:
            f.write(b"\xff\xd8\xff\xe0\x00\x10JFIF" + b"\x00" * 32)

        cls.sample_pdf = "sample_report.pdf"
        with open(os.path.join(cls.temp_dir.name, cls.sample_pdf), "wb") as f:
            f.write(b"%PDF-1.4 sample pdf content")

        cls.sample_png = "sample_screenshot.png"
        with open(os.path.join(cls.temp_dir.name, cls.sample_png), "wb") as f:
            f.write(b"\x89PNG\r\n\x1a\n" + b"\x00" * 32)

        cls.sample_txt = "unsupported_notes.txt"
        with open(os.path.join(cls.temp_dir.name, cls.sample_txt), "wb") as f:
            f.write(b"plain text document")

    @classmethod
    def tearDownClass(cls):
        alerts_module.UPLOAD_DIR = cls.orig_upload_dir
        cls.temp_dir.cleanup()
        app.dependency_overrides.pop(get_db, None)

    # 1. Unauthenticated access blocked
    def test_01_unauthenticated_access_returns_401(self):
        """Unauthenticated GET /uploads/{filename} must return 401 Unauthorized."""
        res = client.get(f"/uploads/{self.sample_jpg}")
        self.assertEqual(res.status_code, 401, f"Expected 401, got {res.status_code}")
        self.assertIn("detail", res.json())

    # 2. Invalid JWT token blocked
    def test_02_invalid_token_returns_401(self):
        """GET /uploads/{filename} with malformed or tampered token must return 401."""
        bad_headers = {"Authorization": "Bearer bad.token.value"}
        res = client.get(f"/uploads/{self.sample_jpg}", headers=bad_headers)
        self.assertEqual(res.status_code, 401, f"Expected 401, got {res.status_code}")

    # 3. Expired JWT token blocked
    def test_03_expired_token_returns_401(self):
        """GET /uploads/{filename} with expired token must return 401."""
        expired_exp = datetime.now(timezone.utc) - timedelta(hours=2)
        expired_payload = {"sub": str(self.student_id), "role": "student", "exp": expired_exp}
        expired_token = jwt.encode(expired_payload, SECRET_KEY, algorithm=ALGORITHM)

        headers = {"Authorization": f"Bearer {expired_token}"}
        res = client.get(f"/uploads/{self.sample_jpg}", headers=headers)
        self.assertEqual(res.status_code, 401, f"Expected 401, got {res.status_code}")

    # 4. Valid token serves files with appropriate MIME types
    def test_04_authenticated_user_can_view_supported_types(self):
        """Authenticated student or officer can retrieve JPG, PNG, and PDF with correct MIME types."""
        # Test JPG
        res_jpg = client.get(f"/uploads/{self.sample_jpg}", headers=self.student_headers)
        self.assertEqual(res_jpg.status_code, 200)
        self.assertEqual(res_jpg.headers.get("content-type"), "image/jpeg")
        self.assertTrue(res_jpg.content.startswith(b"\xff\xd8\xff"))

        # Test PDF
        res_pdf = client.get(f"/uploads/{self.sample_pdf}", headers=self.security_headers)
        self.assertEqual(res_pdf.status_code, 200)
        self.assertEqual(res_pdf.headers.get("content-type"), "application/pdf")
        self.assertTrue(res_pdf.content.startswith(b"%PDF-1.4"))

        # Test PNG
        res_png = client.get(f"/uploads/{self.sample_png}", headers=self.student_headers)
        self.assertEqual(res_png.status_code, 200)
        self.assertEqual(res_png.headers.get("content-type"), "image/png")

    # 5. Missing file returns 404
    def test_05_missing_file_returns_404(self):
        """Authenticated GET for nonexistent file must return 404."""
        res = client.get("/uploads/missing_photo_999.jpg", headers=self.student_headers)
        self.assertEqual(res.status_code, 404, f"Expected 404, got {res.status_code}")

    # 6. Path traversal attempts rejected with 404
    def test_06_path_traversal_attempts_return_404(self):
        """Path traversal patterns must be rejected and return 404."""
        traversal_paths = [
            "../campusguard.db",
            "..\\campusguard.db",
            "../../etc/passwd",
            "..%2f..%2fcampusguard.db",
            "subfolder/test.jpg",
        ]
        for path in traversal_paths:
            with self.subTest(path=path):
                res = client.get(f"/uploads/{path}", headers=self.student_headers)
                self.assertEqual(
                    res.status_code,
                    404,
                    f"Expected 404 for traversal '{path}', got {res.status_code}",
                )

    # 7. Unsupported file extensions rejected with 404
    def test_07_unsupported_extension_returns_404(self):
        """Non-evidence file extensions (.txt, .exe, .db) must be rejected with 404."""
        res = client.get(f"/uploads/{self.sample_txt}", headers=self.student_headers)
        self.assertEqual(res.status_code, 404, f"Expected 404 for .txt, got {res.status_code}")

    # 8. Upload and authenticated retrieval end-to-end
    def test_08_upload_and_retrieve_end_to_end(self):
        """Uploading via /incidents/upload produces an attachment that requires auth to read."""
        dummy_content = b"\xff\xd8\xff\xe0\x00\x10JFIF" + b"EVIDENCE_DATA_TEST"
        upload_res = client.post(
            "/incidents/upload",
            files={"file": ("incident_snap.jpg", dummy_content, "image/jpeg")},
            headers=self.student_headers,
        )
        self.assertEqual(upload_res.status_code, 200, upload_res.text)
        attachment_url = upload_res.json().get("attachment_url")
        self.assertTrue(attachment_url.startswith("/uploads/"))

        # 1. Unauthenticated retrieval fails with 401
        get_unauth = client.get(attachment_url)
        self.assertEqual(get_unauth.status_code, 401)

        # 2. Authenticated retrieval succeeds with 200
        get_auth = client.get(attachment_url, headers=self.student_headers)
        self.assertEqual(get_auth.status_code, 200)
        self.assertEqual(get_auth.content, dummy_content)

    # 9. Evidence authorization: student can view own incident attachment, security can view, but another student receives 403
    def test_09_evidence_access_authorized_per_user_role(self):
        """Uploaded evidence attached to an incident is restricted to the owner student, security, and admin."""
        # Create an incident with an attachment for student 1
        db = TestSessionLocal()
        incident = Incident(
            user_id=self.student_id,
            incident_type="Theft",
            location="Library 2nd Floor",
            description="Stolen backpack with evidence photo",
            nlp_category="Theft",
            nlp_urgency="Normal",
            attachment=f"/uploads/{self.sample_jpg}",
            status="submitted",
        )
        db.add(incident)
        db.commit()
        incident_id = incident.id
        db.close()

        try:
            # 1. Owner student can access evidence (200)
            res_owner = client.get(f"/uploads/{self.sample_jpg}", headers=self.student_headers)
            self.assertEqual(res_owner.status_code, 200)

            # 2. Security officer can access evidence (200)
            res_sec = client.get(f"/uploads/{self.sample_jpg}", headers=self.security_headers)
            self.assertEqual(res_sec.status_code, 200)

            # 3. Another student CANNOT access evidence (403 Forbidden)
            res_other = client.get(f"/uploads/{self.sample_jpg}", headers=self.other_student_headers)
            self.assertEqual(res_other.status_code, 403)
            self.assertIn("Access denied", res_other.json().get("detail", ""))
        finally:
            # Cleanup incident
            db = TestSessionLocal()
            inc = db.query(Incident).filter(Incident.id == incident_id).first()
            if inc:
                db.delete(inc)
                db.commit()
            db.close()


if __name__ == "__main__":
    unittest.main()
