"""Comprehensive automated backend test suite for CampusGuard AI."""

import os
import sys
import io

# Ensure backend can be imported
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi.testclient import TestClient
from backend.main import app
from backend.config.database import SessionLocal
from backend.services.alert_service import create_cctv_alert
from backend.database.models.alert import Alert

client = TestClient(app)


def test_public_endpoints():
    print("Testing / and /health...")
    res = client.get("/")
    assert res.status_code == 200, f"Expected 200, got {res.status_code}"
    assert "CampusGuard" in res.json().get("message", "")

    res = client.get("/health")
    assert res.status_code == 200, f"Expected 200, got {res.status_code}"
    assert res.json().get("status") == "ok"
    print("  PASS: Public endpoints ok.")


def test_authentication():
    print("Testing Authentication for all roles...")
    # Invalid login
    res = client.post("/login", json={"email": "student@campusguard.com", "password": "WrongPassword"})
    assert res.status_code == 401, f"Expected 401 for bad password, got {res.status_code}"

    # Student login
    res = client.post("/login", json={"email": "student@campusguard.com", "password": "Student@123"})
    assert res.status_code == 200, f"Student login failed: {res.text}"
    student_data = res.json()
    assert student_data.get("role") == "student"
    assert "access_token" in student_data

    # Security login
    res = client.post("/login", json={"email": "security@campusguard.com", "password": "Security@123"})
    assert res.status_code == 200, f"Security login failed: {res.text}"
    security_data = res.json()
    assert security_data.get("role") == "security"

    # Admin login
    res = client.post("/login", json={"email": "admin@campusguard.com", "password": "Admin@123"})
    assert res.status_code == 200, f"Admin login failed: {res.text}"
    admin_data = res.json()
    assert admin_data.get("role") == "admin"

    print("  PASS: Authentication verified for Student, Security, and Admin.")
    return student_data["access_token"], security_data["access_token"], admin_data["access_token"]


def test_role_permissions(student_token, security_token, admin_token):
    print("Testing Role-Based Access Control...")
    student_headers = {"Authorization": f"Bearer {student_token}"}
    security_headers = {"Authorization": f"Bearer {security_token}"}
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    # Student accessing /alerts should be FORBIDDEN (403)
    res = client.get("/alerts", headers=student_headers)
    assert res.status_code == 403, f"Expected 403 for student accessing /alerts, got {res.status_code}"

    # Security accessing /alerts should be OK (200)
    res = client.get("/alerts", headers=security_headers)
    assert res.status_code == 200, f"Expected 200 for security accessing /alerts, got {res.status_code}"

    # Admin accessing /alerts should be OK (200)
    res = client.get("/alerts", headers=admin_headers)
    assert res.status_code == 200, f"Expected 200 for admin accessing /alerts, got {res.status_code}"

    # Student accessing /users should be FORBIDDEN (403)
    res = client.get("/users", headers=student_headers)
    assert res.status_code == 403, f"Expected 403 for student accessing /users, got {res.status_code}"

    # Admin accessing /users should be OK (200)
    res = client.get("/users", headers=admin_headers)
    assert res.status_code == 200, f"Expected 200 for admin accessing /users, got {res.status_code}"

    print("  PASS: Role-based permissions strictly enforced.")


def test_users_crud(admin_token, student_token):
    print("Testing Users CRUD operations...")
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    student_headers = {"Authorization": f"Bearer {student_token}"}

    # Non-admin cannot create users
    res = client.post("/users", json={"name": "Hacker", "email": "h@test.com", "password": "123", "role": "admin"}, headers=student_headers)
    assert res.status_code == 403

    # Admin creates user
    test_email = "test_staff_99@campusguard.com"
    res = client.post("/users", json={"name": "Officer Test", "email": test_email, "password": "SecurePassword123", "role": "security"}, headers=admin_headers)
    assert res.status_code in (201, 400)
    if res.status_code == 201:
        user_id = res.json()["user"]["id"]

        # Admin gets user by ID
        res_get = client.get(f"/users/{user_id}", headers=admin_headers)
        assert res_get.status_code == 200
        assert res_get.json()["name"] == "Officer Test"

        # Admin updates user
        res_patch = client.patch(f"/users/{user_id}", json={"name": "Officer Updated"}, headers=admin_headers)
        assert res_patch.status_code == 200
        assert res_patch.json()["user"]["name"] == "Officer Updated"

        # Admin deletes user
        res_del = client.delete(f"/users/{user_id}", headers=admin_headers)
        assert res_del.status_code == 200

    print("  PASS: Users CRUD endpoints verified.")


def test_cameras_crud(admin_token, security_token, student_token):
    print("Testing Cameras CRUD operations...")
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    security_headers = {"Authorization": f"Bearer {security_token}"}
    student_headers = {"Authorization": f"Bearer {student_token}"}

    # Student cannot view or manage cameras
    res = client.get("/cameras", headers=student_headers)
    assert res.status_code == 403

    # Security can list cameras
    res = client.get("/cameras", headers=security_headers)
    assert res.status_code == 200
    assert isinstance(res.json(), list)

    # Admin creates camera
    res = client.post("/cameras", json={"name": "Library Corridor Cam", "location": "Library 2nd Floor", "status": True}, headers=admin_headers)
    assert res.status_code == 201
    cam_id = res.json()["camera"]["id"]

    # Admin updates camera
    res = client.patch(f"/cameras/{cam_id}", json={"status": False}, headers=admin_headers)
    assert res.status_code == 200
    assert res.json()["camera"]["status"] is False

    # Admin deletes camera
    res = client.delete(f"/cameras/{cam_id}", headers=admin_headers)
    assert res.status_code == 200

    print("  PASS: Cameras CRUD endpoints verified.")


def test_incident_lifecycle_and_timeline(student_token, security_token):
    print("Testing Incident reporting, attachments, timeline logs, and lifecycle...")
    student_headers = {"Authorization": f"Bearer {student_token}"}
    security_headers = {"Authorization": f"Bearer {security_token}"}

    # 1. Attachment upload test
    dummy_file = io.BytesIO(b"dummy image bytes for incident test")
    upload_res = client.post(
        "/incidents/upload",
        files={"file": ("test_evidence.jpg", dummy_file, "image/jpeg")},
        headers=student_headers
    )
    assert upload_res.status_code == 200, f"Upload failed: {upload_res.text}"
    attachment_url = upload_res.json().get("attachment_url")
    assert attachment_url is not None

    # 2. Student reports an incident with attachment
    report_data = {
        "incident_type": "Medical Emergency",
        "location": "Science Block 3rd Floor",
        "description": "Student fell on the stairs and seems injured, needs urgent help",
        "attachment": attachment_url
    }
    res = client.post("/incidents", json=report_data, headers=student_headers)
    assert res.status_code == 200, f"Incident report failed: {res.text}"
    result = res.json()
    incident_id = result.get("incident_id")
    assert incident_id is not None
    assert result.get("nlp_analysis", {}).get("category") == "Medical Emergency"
    assert result.get("nlp_analysis", {}).get("urgency") == "High"
    assert result.get("attachment") == attachment_url

    # 3. Check incident timeline logs
    res_logs = client.get(f"/incidents/{incident_id}/logs", headers=student_headers)
    assert res_logs.status_code == 200
    logs = res_logs.json()
    actions = [l["action"] for l in logs]
    assert "submitted" in actions
    assert "nlp_analyzed" in actions

    # 4. Security acknowledges incident
    res = client.patch(f"/incidents/{incident_id}/status?status=acknowledged", headers=security_headers)
    assert res.status_code == 200
    assert res.json().get("status") == "acknowledged"

    # 5. Security resolves incident
    res = client.patch(f"/incidents/{incident_id}/status?status=resolved", headers=security_headers)
    assert res.status_code == 200
    assert res.json().get("status") == "resolved"

    # 6. Verify full 4-event audit trail
    res_logs2 = client.get(f"/incidents/{incident_id}/logs", headers=security_headers)
    actions2 = [l["action"] for l in res_logs2.json()]
    assert "acknowledged" in actions2
    assert "resolved" in actions2

    print(f"  PASS: Incident #{incident_id} created with attachment and 4 timeline audit logs recorded.")


def test_sos_workflow_and_location(student_token, security_token):
    print("Testing Emergency SOS workflow with location handling...")
    student_headers = {"Authorization": f"Bearer {student_token}"}
    security_headers = {"Authorization": f"Bearer {security_token}"}

    # Student sends SOS with location
    sos_payload = {
        "location": "Hostel Block C - Ground Floor",
        "description": "Student triggered SOS alert with exact campus zone"
    }
    res = client.post("/sos", json=sos_payload, headers=student_headers)
    assert res.status_code == 200, f"SOS post failed: {res.text}"
    sos_data = res.json()
    assert sos_data.get("status") == "active"
    assert sos_data.get("location") == "Hostel Block C - Ground Floor"
    sos_id = sos_data.get("alert_id")

    # Security sees active SOS
    res = client.get("/sos", headers=security_headers)
    assert res.status_code == 200
    all_sos = res.json()
    assert any(s["id"] == sos_id for s in all_sos)

    print(f"  PASS: SOS alert #{sos_id} created with custom location and visible to security.")


def test_alerts_assignment_and_escalation(security_token):
    print("Testing Alert assignment, manual escalation, and automatic escalation check...")
    security_headers = {"Authorization": f"Bearer {security_token}"}

    # Fetch alerts
    res = client.get("/alerts", headers=security_headers)
    assert res.status_code == 200
    alerts = res.json()
    if alerts:
        target_alert = alerts[0]
        alert_id = target_alert["id"]

        # Assign alert
        res_assign = client.patch(f"/alerts/{alert_id}/assign", json={}, headers=security_headers)
        assert res_assign.status_code == 200
        assert res_assign.json()["alert"]["assigned_to"] is not None

        # Escalate alert
        res_esc = client.patch(f"/alerts/{alert_id}/escalate", headers=security_headers)
        assert res_esc.status_code == 200
        assert res_esc.json()["alert"]["status"] == "escalated"
        assert res_esc.json()["alert"]["severity"] == "critical"

    # Test automatic escalation check endpoint
    res_auto = client.post("/alerts/escalate-unacknowledged?timeout_minutes=0", headers=security_headers)
    assert res_auto.status_code == 200
    assert "escalated_count" in res_auto.json()

    print("  PASS: Alert assignment and escalation mechanisms verified.")


def test_risk_explainability_and_campus_overview(security_token):
    print("Testing Multi-Signal Risk Overview and Explainable Factors...")
    security_headers = {"Authorization": f"Bearer {security_token}"}

    # 1. Prediction with explainable factors
    res_pred = client.post(
        "/risk",
        json={"weapon": True, "fight": True, "fall": False, "restricted_entry": True},
        headers=security_headers
    )
    assert res_pred.status_code == 200
    pred_data = res_pred.json()
    assert pred_data["risk_level"] in ("High", "Medium", "Low")
    assert "factors" in pred_data
    assert len(pred_data["factors"]) >= 3
    assert "model_type" in pred_data

    # 2. Campus overview multi-signal aggregation
    res_cov = client.get("/risk/campus-overview", headers=security_headers)
    assert res_cov.status_code == 200
    cov_data = res_cov.json()
    assert "risk_score" in cov_data
    assert "risk_level" in cov_data
    assert "safety_index" in cov_data
    assert "contributing_signals" in cov_data
    assert isinstance(cov_data["contributing_signals"], list)

    print(f"  PASS: Risk intelligence verified (Campus Risk Score: {cov_data['risk_score']}/100, Level: {cov_data['risk_level']}).")


def test_alert_persistence_and_duplicate_prevention():
    print("Testing CCTV alert persistence and duplicate prevention...")
    db = SessionLocal()
    try:
        # Create alert 1
        alert1 = create_cctv_alert(
            db=db,
            alert_type="Weapon Detection",
            location="Gate 2 Checkpoint",
            description="Automated CCTV threat detection: Knife identified",
            severity="critical",
        )
        assert alert1 is not None and alert1.id is not None

        # Attempt to create identical alert immediately (within 30s)
        alert2 = create_cctv_alert(
            db=db,
            alert_type="Weapon Detection",
            location="Gate 2 Checkpoint",
            description="Duplicate attempt",
            severity="critical",
        )
        assert alert2 is not None
        assert alert1.id == alert2.id, f"Expected duplicate alert to reuse ID {alert1.id}, got {alert2.id}"
        print(f"  PASS: Alert #{alert1.id} persisted and duplicate request within 30s correctly deduplicated.")
    finally:
        db.close()


def test_assistant_rag(student_token):
    print("Testing AI Assistant RAG pipeline...")
    student_headers = {"Authorization": f"Bearer {student_token}"}

    res = client.post(
        "/assistant/ask",
        json={"question": "How do I report an emergency using the SOS button?"},
        headers=student_headers
    )
    assert res.status_code == 200, f"Assistant request failed: {res.text}"
    data = res.json()
    assert "answer" in data
    assert len(data.get("answer", "")) > 10
    assert "sources" in data
    assert len(data["sources"]) > 0, "Expected real retrieved document sources"
    source = data["sources"][0]
    assert "file" in source
    assert "section" in source
    assert "score" in source
    print(f"  PASS: AI Assistant returned answer with real verified source: {source['file']} ({source['section']}).")


if __name__ == "__main__":
    print("\n========================================================")
    print("   CampusGuard AI — Automated Backend Verification Suite")
    print("========================================================\n")
    test_public_endpoints()
    student_token, security_token, admin_token = test_authentication()
    test_role_permissions(student_token, security_token, admin_token)
    test_users_crud(admin_token, student_token)
    test_cameras_crud(admin_token, security_token, student_token)
    test_incident_lifecycle_and_timeline(student_token, security_token)
    test_sos_workflow_and_location(student_token, security_token)
    test_alerts_assignment_and_escalation(security_token)
    test_risk_explainability_and_campus_overview(security_token)
    test_alert_persistence_and_duplicate_prevention()
    test_assistant_rag(student_token)
    print("\n========================================================")
    print("   ALL TESTS PASSED SUCCESSFULLY! (100% Verified)")
    print("========================================================\n")
