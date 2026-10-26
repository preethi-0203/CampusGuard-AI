"""
CampusGuard AI — System Setup and Health Diagnostic Tool
Safely checks Python version, environment configuration (.env), installed dependencies,
AI model checkpoints, database integrity, and frontend readiness on Windows.
"""

import sys
import os
import shutil
import subprocess
from pathlib import Path

# ANSI colors if supported, else plain text
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
BOLD = "\033[1m"
RESET = "\033[0m"


def print_header(title: str):
    print(f"\n{BOLD}{CYAN}{'=' * 68}{RESET}")
    print(f"{BOLD}{CYAN}  {title}{RESET}")
    print(f"{BOLD}{CYAN}{'=' * 68}{RESET}")


def check_python_version() -> bool:
    print(f"\n{BOLD}[1/7] Python Environment Check{RESET}")
    version = sys.version_info
    py_str = f"{version.major}.{version.minor}.{version.micro}"
    print(f"  Current Python executable: {sys.executable}")
    print(f"  Current Python version:    {py_str}")

    if version.major == 3 and version.minor >= 10:
        print(f"  {GREEN}[OK]{RESET} Python version satisfies requirement (>= 3.10).")
        return True
    else:
        print(f"  {RED}[FAIL]{RESET} Python 3.10 or higher is required. Found {py_str}.")
        return False


def check_environment_file(root_dir: Path) -> bool:
    print(f"\n{BOLD}[2/7] Environment Configuration (.env){RESET}")
    env_path = root_dir / ".env"
    example_path = root_dir / ".env.example"

    if not env_path.exists():
        print(f"  {RED}[FAIL]{RESET} .env file not found!")
        print(f"         Run: Copy-Item .env.example .env (or copy .env.example to .env)")
        print(f"         Then configure CAMPUSGUARD_SECRET_KEY.")
        return False

    print(f"  {GREEN}[OK]{RESET} .env file exists at {env_path.name}")

    # Inspect contents
    env_content = env_path.read_text(encoding="utf-8")
    lines = [line.strip() for line in env_content.splitlines() if line.strip() and not line.startswith("#")]
    config = {}
    for line in lines:
        if "=" in line:
            k, v = line.split("=", 1)
            config[k.strip()] = v.strip().strip('"').strip("'")

    secret = config.get("CAMPUSGUARD_SECRET_KEY", "")
    gemini_key = config.get("GEMINI_API_KEY", "")

    if not secret:
        print(f"  {RED}[FAIL]{RESET} CAMPUSGUARD_SECRET_KEY is empty in .env.")
        print(f"         Generate a key: python -c \"import secrets; print(secrets.token_hex(32))\"")
        return False
    elif secret == "change-this-to-a-random-secret-before-deployment" or secret == "your_generated_secret_key_here":
        print(f"  {RED}[FAIL]{RESET} CAMPUSGUARD_SECRET_KEY is still set to placeholder value.")
        print(f"         Backend will refuse to start. Replace it with a secure random key.")
        return False
    else:
        print(f"  {GREEN}[OK]{RESET} CAMPUSGUARD_SECRET_KEY is configured ({len(secret)} characters).")

    if gemini_key and gemini_key != "your_optional_gemini_api_key_here":
        print(f"  {GREEN}[OK]{RESET} GEMINI_API_KEY is configured (LLM generation enabled).")
    else:
        print(f"  {YELLOW}[INFO]{RESET} GEMINI_API_KEY is not set (AI Assistant will use local hybrid RAG fallback).")

    return True


def check_python_packages() -> bool:
    print(f"\n{BOLD}[3/7] Python Dependencies Check{RESET}")
    required_packages = [
        ("fastapi", "fastapi"),
        ("uvicorn", "uvicorn"),
        ("sqlalchemy", "sqlalchemy"),
        ("pydantic", "pydantic"),
        ("python-dotenv", "dotenv"),
        ("opencv-python", "cv2"),
        ("ultralytics", "ultralytics"),
        ("tensorflow", "tensorflow"),
        ("mediapipe", "mediapipe"),
        ("joblib", "joblib"),
        ("scikit-learn", "sklearn"),
        ("chromadb", "chromadb"),
        ("sentence-transformers", "sentence_transformers"),
    ]

    all_ok = True
    for pkg_display, import_name in required_packages:
        try:
            __import__(import_name)
            print(f"  {GREEN}[OK]{RESET} {pkg_display:<24} (module '{import_name}')")
        except ImportError:
            print(f"  {RED}[MISSING]{RESET} {pkg_display:<24} (failed to import '{import_name}')")
            all_ok = False

    if not all_ok:
        print(f"\n  {YELLOW}To install missing packages, run:{RESET}")
        print("  pip install -r requirements.txt")

    return all_ok


def check_models(root_dir: Path) -> bool:
    print(f"\n{BOLD}[4/7] AI Model Checkpoints Check{RESET}")
    models_to_check = [
        ("Weapon Detection (Preferred)", root_dir / "backend" / "ml_models" / "weapon_detection_trained.pt", True),
        ("Weapon Detection (Base/Fallback)", root_dir / "backend" / "ml_models" / "best.pt", False),
        ("Person Detection", root_dir / "backend" / "ml_models" / "person_detection.pt", True),
        ("Fight Detection Landmarker", root_dir / "backend" / "ml_models" / "pose_landmarker_lite.task", True),
        ("Fall Detection CNN", root_dir / "models" / "fall_detection_cnn.keras", True),
        ("Risk Prediction Classifier", root_dir / "models" / "risk_prediction_model.pkl", True),
    ]

    all_critical_ok = True
    for label, path, is_critical in models_to_check:
        if path.exists():
            size_mb = path.stat().st_size / (1024 * 1024)
            rel_path = path.relative_to(root_dir)
            print(f"  {GREEN}[OK]{RESET} {label:<32} -> {str(rel_path):<40} ({size_mb:.2f} MB)")
        else:
            rel_path = path.relative_to(root_dir)
            if is_critical:
                print(f"  {RED}[MISSING]{RESET} {label:<32} -> {str(rel_path)}")
                all_critical_ok = False
            else:
                print(f"  {YELLOW}[OPTIONAL]{RESET} {label:<32} -> {str(rel_path)}")

    return all_critical_ok


def check_database(root_dir: Path) -> bool:
    print(f"\n{BOLD}[5/7] Database & User Accounts Check{RESET}")
    db_path = root_dir / "campusguard.db"

    if not db_path.exists():
        print(f"  {YELLOW}[INFO]{RESET} campusguard.db does not exist yet.")
        print(f"         It will be created automatically on first backend startup.")
        return True

    size_kb = db_path.stat().st_size / 1024
    print(f"  {GREEN}[OK]{RESET} Operational database found: campusguard.db ({size_kb:.1f} KB)")

    # Test reading tables and users safely
    try:
        import sqlite3
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [row[0] for row in cursor.fetchall()]
        print(f"  {GREEN}[OK]{RESET} Existing tables: {', '.join(sorted(tables))}")

        if "users" in tables:
            cursor.execute("SELECT email, role FROM users;")
            users = cursor.fetchall()
            print(f"  {GREEN}[OK]{RESET} Seeded accounts detected ({len(users)} total):")
            for email, role in users:
                print(f"       - {email:<28} (Role: {role})")
        conn.close()
        return True
    except Exception as exc:
        print(f"  {YELLOW}[WARN]{RESET} Could not inspect SQLite database: {exc}")
        return True


def check_campus_documents(root_dir: Path) -> bool:
    print(f"\n{BOLD}[6/7] Campus Safety Documents (RAG Assistant Corpus){RESET}")
    doc_dir = root_dir / "campus_documents"

    if not doc_dir.exists():
        print(f"  {RED}[FAIL]{RESET} campus_documents directory missing.")
        return False

    txt_files = list(doc_dir.rglob("*.txt"))
    if txt_files:
        print(f"  {GREEN}[OK]{RESET} Found {len(txt_files)} document file(s) for safety assistant:")
        for f in txt_files:
            rel = f.relative_to(root_dir)
            print(f"       - {str(rel)} ({f.stat().st_size} bytes)")
        return True
    else:
        print(f"  {YELLOW}[WARN]{RESET} No .txt files found in campus_documents/")
        return False


def check_frontend(root_dir: Path) -> bool:
    print(f"\n{BOLD}[7/7] Frontend Readiness Check{RESET}")
    frontend_dir = root_dir / "frontend-new"

    if not frontend_dir.exists():
        print(f"  {RED}[FAIL]{RESET} frontend-new directory missing.")
        return False

    pkg_json = frontend_dir / "package.json"
    if not pkg_json.exists():
        print(f"  {RED}[FAIL]{RESET} frontend-new/package.json missing.")
        return False
    print(f"  {GREEN}[OK]{RESET} frontend-new/package.json found.")

    node_bin = shutil.which("node")
    npm_bin = shutil.which("npm")

    if node_bin and npm_bin:
        try:
            node_v = subprocess.check_output([node_bin, "--version"], text=True).strip()
            npm_v = subprocess.check_output([npm_bin, "--version"], text=True).strip()
            print(f"  {GREEN}[OK]{RESET} Node.js {node_v} and npm {npm_v} detected on PATH.")
        except Exception:
            print(f"  {GREEN}[OK]{RESET} Node.js and npm found on PATH.")
    else:
        print(f"  {YELLOW}[WARN]{RESET} Node.js or npm not detected in PATH.")
        print("         Ensure Node.js 18+ is installed from https://nodejs.org/")

    node_modules = frontend_dir / "node_modules"
    if node_modules.exists():
        print(f"  {GREEN}[OK]{RESET} node_modules installed.")
    else:
        print(f"  {YELLOW}[INFO]{RESET} node_modules not present.")
        print(f"         Run: cd frontend-new; npm install")

    return True


def main():
    print_header("CAMPUSGUARD AI — ENVIRONMENT & DEPENDENCY CHECK")
    root_dir = Path(__file__).resolve().parent

    results = {
        "Python Version": check_python_version(),
        "Environment (.env)": check_environment_file(root_dir),
        "Python Dependencies": check_python_packages(),
        "AI Models": check_models(root_dir),
        "Database": check_database(root_dir),
        "Safety Documents": check_campus_documents(root_dir),
        "Frontend Readiness": check_frontend(root_dir),
    }

    print_header("SUMMARY & DIAGNOSTIC REPORT")
    all_passed = True
    for item, passed in results.items():
        status = f"{GREEN}PASSED{RESET}" if passed else f"{RED}ACTION REQUIRED{RESET}"
        print(f"  {item:<25} : {status}")
        if not passed:
            all_passed = False

    print("\n" + "-" * 68)
    if all_passed:
        print(f"{GREEN}{BOLD}All critical checks passed! You are ready to start CampusGuard AI.{RESET}\n")
        print("To start the backend (Terminal 1):")
        print("  uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload\n")
        print("To start the frontend (Terminal 2):")
        print("  cd frontend-new")
        print("  npm run dev\n")
        print("Login with demo credentials at http://localhost:5173:")
        print("  - Student:  student@campusguard.com  / Student@123")
        print("  - Security: security@campusguard.com / Security@123")
        print("  - Admin:    admin@campusguard.com    / Admin@123")
    else:
        print(f"{YELLOW}{BOLD}Some setup items require attention before running the system.{RESET}")
        print("Review the red [FAIL] or [MISSING] items above and apply the suggested fixes.")
    print("=" * 68)


if __name__ == "__main__":
    main()
