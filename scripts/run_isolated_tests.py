"""
CampusGuard AI — Complete Test Suite Runner
Runs each of the 12 unit test suites and the backend API test suite
in clean, isolated subprocesses with temporary database protection.
Guarantees campusguard.db is NEVER touched or modified.
"""

import os
import sys
import shutil
import tempfile
import uuid
import subprocess
import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

TEST_SUITES = [
    "tests/test_batch1_security_auth.py",
    "tests/test_batch2_lifecycle_tracking.py",
    "tests/test_batch3_nlp_assistant.py",
    "tests/test_batch4_concurrency_uploads.py",
    "tests/test_cctv_video_pipeline.py",
    "tests/test_model_verification.py",
    "tests/test_operational_risk_scale.py",
    "tests/test_rag_assistant.py",
    "tests/test_regression_phase1.py",
    "tests/test_restricted_zone.py",
    "tests/test_secure_uploads.py",
    "tests/test_weapon_detection.py",
]

def verify_operational_db():
    op_db = ROOT / "campusguard.db"
    if not op_db.exists():
        raise FileNotFoundError("campusguard.db missing!")
    h = hashlib.sha256(op_db.read_bytes()).hexdigest()
    return h

def main():
    print("=" * 70)
    print("CAMPUSGUARD AI — COMPREHENSIVE TEST VERIFICATION")
    print("=" * 70)

    initial_hash = verify_operational_db()
    print(f"[Safety Gate] campusguard.db hash: {initial_hash[:16]}... ({ROOT / 'campusguard.db':} intact)\n")

    python_bin = sys.executable
    total_passed = 0
    total_failed = 0
    failed_suites = []

    # 1. Run all 12 test suites in isolated subprocesses
    print("=== PART 1: RUNNING 12 UNIT & PIPELINE TEST SUITES ===")
    for suite in TEST_SUITES:
        suite_path = ROOT / suite
        if not suite_path.exists():
            print(f"[ERROR] Suite not found: {suite}")
            total_failed += 1
            failed_suites.append(suite)
            continue

        temp_db = os.path.join(tempfile.gettempdir(), f"test_cg_{uuid.uuid4().hex}.db")
        # Seed from option_b backup
        opt_b = ROOT / "campusguard_backup_option_b.db"
        if opt_b.exists():
            shutil.copy2(opt_b, temp_db)
        else:
            shutil.copy2(ROOT / "backups" / "campusguard_backup_exam_prep_20261026.db", temp_db)

        env = os.environ.copy()
        env["DATABASE_URL"] = f"sqlite:///{temp_db}"

        print(f"Running {suite}...", end=" ", flush=True)
        res = subprocess.run(
            [python_bin, "-m", "unittest", suite],
            cwd=str(ROOT),
            env=env,
            capture_output=True,
            text=True,
        )

        try:
            if os.path.exists(temp_db):
                os.remove(temp_db)
        except Exception:
            pass

        if res.returncode == 0:
            print("[PASS]")
            total_passed += 1
        else:
            print("[FAIL]")
            print(f"--- Output for {suite} ---")
            print(res.stderr or res.stdout)
            total_failed += 1
            failed_suites.append(suite)

    print(f"\nUnit Test Results: {total_passed} / {len(TEST_SUITES)} suites passed.")
    if total_failed > 0:
        print(f"[FAIL] Failing suites: {failed_suites}")
        sys.exit(1)

    # 2. Run backend/test_api_suite.py
    print("\n=== PART 2: RUNNING BACKEND API INTEGRATION SUITE (11 sections) ===")
    temp_api_db = os.path.join(tempfile.gettempdir(), f"test_api_{uuid.uuid4().hex}.db")
    opt_b = ROOT / "campusguard_backup_option_b.db"
    if opt_b.exists():
        shutil.copy2(opt_b, temp_api_db)
    else:
        shutil.copy2(ROOT / "backups" / "campusguard_backup_exam_prep_20261026.db", temp_api_db)

    env = os.environ.copy()
    env["DATABASE_URL"] = f"sqlite:///{temp_api_db}"

    res_api = subprocess.run(
        [python_bin, "backend/test_api_suite.py"],
        cwd=str(ROOT),
        env=env,
        capture_output=True,
        text=True,
    )

    try:
        if os.path.exists(temp_api_db):
            os.remove(temp_api_db)
    except Exception:
        pass

    if res_api.returncode == 0:
        print(res_api.stdout)
        print("[PASS] Backend API integration test suite passed 100%!")
    else:
        print("[FAIL] Backend API suite failed:")
        print(res_api.stderr or res_api.stdout)
        sys.exit(1)

    # 3. Verify operational database integrity
    final_hash = verify_operational_db()
    assert initial_hash == final_hash, "CRITICAL ERROR: campusguard.db hash modified!"
    print(f"[PASS] Operational database verified untouched (Hash: {final_hash[:16]}...)")

    print("\n" + "=" * 70)
    print("ALL TESTS PASSED WITH 100% SUCCESS!")
    print("=" * 70)

if __name__ == "__main__":
    main()
