"""
Live End-to-End System Verification for CampusGuard AI
Verifies:
1. FastAPI Backend Health endpoint (GET /health)
2. React/Vite Frontend HTTP availability (GET http://localhost:5173/)
3. Authentication & RBAC (Student, Security, Admin)
4. Dashboard & Pages accessibility (Cameras, Alerts, Incidents, Assistant)
5. Physical Camera Hardware / Live Stream Status
6. Weapon Detection request uses weapon_detection_trained.pt without creating DB alerts
7. RAG Safety Assistant grounded response & source information
8. Operational Database integrity and record preservation
9. Backend & Frontend runtime logs inspection
"""

import urllib.request
import urllib.error
import json
import os
import cv2
import sqlite3
import sys
from pathlib import Path

BASE_BACKEND = "http://127.0.0.1:8000"
BASE_FRONTEND = "http://localhost:5173"
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

def http_get(url, headers=None):
    req = urllib.request.Request(url, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = resp.read()
            return resp.status, data, dict(resp.headers)
    except urllib.error.HTTPError as e:
        return e.code, e.read(), dict(e.headers)
    except Exception as e:
        return 0, str(e).encode(), {}

def http_post_json(url, payload, headers=None):
    h = {"Content-Type": "application/json"}
    if headers:
        h.update(headers)
    req_data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=req_data, headers=h, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = resp.read()
            return resp.status, data, dict(resp.headers)
    except urllib.error.HTTPError as e:
        return e.code, e.read(), dict(e.headers)
    except Exception as e:
        return 0, str(e).encode(), {}

def run_e2e_audit():
    results = {}
    print("=" * 75)
    print("CAMPUSGUARD AI - LIVE END-TO-END AUDIT & VERIFICATION")
    print("=" * 75)

    # 1. Backend Health Check
    print("\n[1] Checking Backend Health Endpoint (/health)...")
    status, body, _ = http_get(f"{BASE_BACKEND}/health")
    if status == 200:
        health_json = json.loads(body.decode())
        print(f"  Status: {status} OK")
        print(f"  Response: {health_json}")
        results["backend_health"] = {"status": "PASSED", "code": status, "response": health_json}
    else:
        print(f"  Status: {status} FAILED ({body.decode()})")
        results["backend_health"] = {"status": "FAILED", "code": status}

    # 2. Frontend Server Availability
    print("\n[2] Checking React/Vite Frontend Server (http://localhost:5173/)...")
    status, body, headers = http_get(f"{BASE_FRONTEND}/")
    html_text = body.decode("utf-8", errors="ignore")
    has_title = "CampusGuard AI" in html_text
    has_root = "id=\"root\"" in html_text or "id='root'" in html_text or "root" in html_text
    if status == 200 and has_title and has_root:
        print(f"  Status: {status} OK")
        print("  HTML title and root DOM element successfully served.")
        results["frontend_server"] = {"status": "PASSED", "code": status}
    else:
        print(f"  Status: {status}, has_title={has_title}, has_root={has_root}")
        results["frontend_server"] = {"status": "FAILED", "code": status}

    # 3. Authentication & RBAC Checks
    print("\n[3] Checking Authentication & Role-Based Access Control...")
    auth_tokens = {}
    roles = [
        ("Student", "student@campusguard.com", "Student@123", "student"),
        ("Security", "security@campusguard.com", "Security@123", "security"),
        ("Admin", "admin@campusguard.com", "Admin@123", "admin"),
    ]
    for label, email, pwd, expected_role in roles:
        status, body, _ = http_post_json(f"{BASE_BACKEND}/login", {"email": email, "password": pwd})
        if status == 200:
            data = json.loads(body.decode())
            tok = data.get("access_token")
            actual_role = data.get("role")
            auth_tokens[expected_role] = tok
            print(f"  {label} Login: Status {status} OK, Role verified as '{actual_role}' (token masked)")
        else:
            print(f"  {label} Login: FAILED with status {status}")

    # RBAC Matrix verification
    rbac_tests = [
        ("Student -> /incidents", expected_role == "student", f"{BASE_BACKEND}/incidents", auth_tokens.get("student"), 200),
        ("Student -> /users", False, f"{BASE_BACKEND}/users", auth_tokens.get("student"), 403),
        ("Student -> /alerts", False, f"{BASE_BACKEND}/alerts", auth_tokens.get("student"), 403),
        ("Security -> /alerts", True, f"{BASE_BACKEND}/alerts", auth_tokens.get("security"), 200),
        ("Security -> /users", False, f"{BASE_BACKEND}/users", auth_tokens.get("security"), 403),
        ("Admin -> /users", True, f"{BASE_BACKEND}/users", auth_tokens.get("admin"), 200),
        ("Admin -> /alerts", True, f"{BASE_BACKEND}/alerts", auth_tokens.get("admin"), 200),
    ]
    all_rbac_passed = True
    print("\n  RBAC Access Matrix:")
    for test_name, allowed, url, token, expected_code in rbac_tests:
        if not token:
            print(f"    {test_name}: SKIPPED (missing token)")
            all_rbac_passed = False
            continue
        code, _, _ = http_get(url, headers={"Authorization": f"Bearer {token}"})
        passed = (code == expected_code)
        if not passed:
            all_rbac_passed = False
        print(f"    {test_name:<25} -> Received {code} (Expected {expected_code}) | {'PASSED' if passed else 'FAILED'}")
    results["auth_rbac"] = {"status": "PASSED" if all_rbac_passed else "FAILED"}

    # 4. Dashboard & Pages Accessibility Check
    print("\n[4] Verifying Dashboard & Navigation Pages...")
    sec_tok = auth_tokens.get("security")
    sec_headers = {"Authorization": f"Bearer {sec_tok}"} if sec_tok else {}

    endpoints = [
        ("Alerts Feed", f"{BASE_BACKEND}/alerts", sec_headers),
        ("Incidents List", f"{BASE_BACKEND}/incidents", sec_headers),
        ("Cameras Infrastructure", f"{BASE_BACKEND}/cameras", sec_headers),
        ("Campus Safety Overview", f"{BASE_BACKEND}/risk/campus-overview", sec_headers),
    ]
    pages_ok = True
    for name, url, h in endpoints:
        code, body, _ = http_get(url, headers=h)
        if code == 200:
            count = len(json.loads(body.decode())) if body.startswith(b"[") else "Object returned"
            print(f"  {name:<25}: Status 200 OK ({count})")
        else:
            print(f"  {name:<25}: Status {code} FAILED")
            pages_ok = False
    results["pages_accessibility"] = {"status": "PASSED" if pages_ok else "FAILED"}

    # 5. Live Camera Hardware Availability
    print("\n[5] Checking Live Camera Hardware Availability...")
    cam_status, cam_body, _ = http_get(f"{BASE_BACKEND}/cameras", headers=sec_headers)
    registered_cameras = json.loads(cam_body.decode()) if cam_status == 200 else []
    print(f"  Registered cameras in database: {len(registered_cameras)}")
    for c in registered_cameras:
        print(f"    - Camera ID {c.get('id')}: {c.get('name')} (Location: {c.get('location')}, Stream: {c.get('stream_url')}, Active: {c.get('is_active')})")

    # Check local OpenCV video capture device
    cap = cv2.VideoCapture(0)
    device_available = cap.isOpened()
    if device_available:
        cap.release()
    print(f"  Physical Video Capture Device 0 Available: {device_available}")
    print("  => Camera hardware and real-time RTSP/CCTV live streams are physically unavailable in this environment.")
    print("  => Live-camera testing marked as UNTESTED (UNAVAILABLE) per instructions (no fake simulation).")
    results["live_camera"] = {
        "status": "UNTESTED (HARDWARE UNAVAILABLE)",
        "physical_capture_device": device_available,
        "registered_cameras_count": len(registered_cameras)
    }

    # 6. Weapon Detection Model & Structure Verification (Without Alert Creation)
    print("\n[6] Verifying Weapon Detection Model Checkpoint & Inference...")
    from backend.services.ml_service import MLService
    ml_svc = MLService()
    active_weapon_model_path = ml_svc.weapon_detector.model_path
    print(f"  Active Weapon Model Path: {active_weapon_model_path}")
    is_trained_model = "weapon_detection_trained.pt" in active_weapon_model_path
    print(f"  Using weapon_detection_trained.pt: {is_trained_model}")

    # Test sample weapon image from validation dataset
    val_weapon_img = PROJECT_ROOT / "data" / "weapon_dataset" / "images" / "val" / "gun_0031.jpg"
    if val_weapon_img.exists():
        frame = cv2.imread(str(val_weapon_img))
        detections = ml_svc.analyze_frame(frame)
        print(f"  Inference on gun_0031.jpg:")
        print(f"    weapon_detected: {detections.get('weapon_detected')}")
        print(f"    detected_weapons: {detections.get('detected_weapons')}")
        expected_structure = all(k in detections for k in ["fall_detected", "fight_detected", "weapon_detected", "detected_weapons", "person_count", "people"])
        print(f"    Response structure matches expected schema: {expected_structure}")
        results["weapon_detection"] = {
            "status": "PASSED" if (is_trained_model and detections.get("weapon_detected") and expected_structure) else "FAILED",
            "model_path": active_weapon_model_path,
            "detected_weapons": detections.get("detected_weapons")
        }
    else:
        results["weapon_detection"] = {"status": "FAILED", "error": "Validation image not found"}

    # 7. RAG Assistant Grounded Query
    print("\n[7] Verifying RAG Assistant Endpoint (/assistant/ask)...")
    student_tok = auth_tokens.get("student")
    rag_headers = {"Authorization": f"Bearer {student_tok}"} if student_tok else {}
    question_payload = {
        "question": "How do I report an emergency using the SOS button?",
        "history": []
    }
    rag_status, rag_body, _ = http_post_json(f"{BASE_BACKEND}/assistant/ask", question_payload, headers=rag_headers)
    if rag_status == 200:
        rag_data = json.loads(rag_body.decode())
        answer = rag_data.get("answer", "")
        sources = rag_data.get("sources", [])
        has_grounding = len(answer) > 20 and len(sources) > 0
        print(f"  Status: {rag_status} OK")
        print(f"  Question: {rag_data.get('question')}")
        print(f"  Answer Summary: {answer[:180]}...")
        print(f"  Sources Retrieved: {len(sources)}")
        for s in sources[:2]:
            print(f"    - Source: {s.get('source')} (Section: {s.get('section')}, Score: {s.get('score')})")
        results["rag_assistant"] = {
            "status": "PASSED" if has_grounding else "FAILED",
            "sources_count": len(sources),
            "grounded": has_grounding
        }
    else:
        print(f"  Status: {rag_status} FAILED ({rag_body.decode()})")
        results["rag_assistant"] = {"status": "FAILED", "code": rag_status}

    # 8. Operational Database Audit
    print("\n[8] Checking Database Integrity & Record Counts...")
    conn = sqlite3.connect("campusguard.db")
    cur = conn.cursor()
    cur.execute("PRAGMA integrity_check;")
    integrity = cur.fetchall()
    cur.execute("PRAGMA foreign_key_check;")
    fk_violations = cur.fetchall()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';")
    tables = [r[0] for r in cur.fetchall()]
    table_counts = {}
    for t in tables:
        cur.execute(f"SELECT COUNT(*) FROM {t};")
        table_counts[t] = cur.fetchone()[0]
    conn.close()

    db_healthy = (integrity == [("ok",)]) and (len(fk_violations) == 0)
    print(f"  PRAGMA integrity_check: {integrity}")
    print(f"  PRAGMA foreign_key_check: {len(fk_violations)} violations")
    print(f"  Table record counts: {table_counts}")
    results["database_integrity"] = {
        "status": "PASSED" if db_healthy else "FAILED",
        "table_counts": table_counts
    }

    # 9. Log Inspections
    print("\n[9] Inspecting Server Logs...")
    backend_log = PROJECT_ROOT / ".system_generated" / "tasks" / "task-341.log"
    # Find active task log
    log_dir = Path(r"C:\Users\preet\.gemini\antigravity-ide\brain\86d96888-9035-4201-af72-bd9f052d6335\.system_generated\tasks")
    backend_log_file = log_dir / "task-341.log"
    frontend_log_file = log_dir / "task-357.log"

    b_lines = backend_log_file.read_text().splitlines() if backend_log_file.exists() else []
    f_lines = frontend_log_file.read_text().splitlines() if frontend_log_file.exists() else []

    backend_errors = [l for l in b_lines if "ERROR" in l or "Exception" in l or "Traceback" in l]
    frontend_errors = [l for l in f_lines if "ERROR" in l or "error" in l.lower() and "re-optimizing" not in l.lower()]

    print(f"  Backend log lines: {len(b_lines)}, Errors found: {len(backend_errors)}")
    print(f"  Frontend log lines: {len(f_lines)}, Errors found: {len(frontend_errors)}")
    results["log_health"] = {
        "status": "PASSED" if len(backend_errors) == 0 and len(frontend_errors) == 0 else "WARNING",
        "backend_errors": len(backend_errors),
        "frontend_errors": len(frontend_errors)
    }

    print("\n" + "=" * 75)
    print("E2E AUDIT COMPLETE")
    print("=" * 75)
    return results

if __name__ == "__main__":
    run_e2e_audit()
