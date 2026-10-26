import zipfile
import sys
from pathlib import Path

root_dir = Path(__file__).resolve().parent.parent
zip_path = Path(sys.argv[1]) if len(sys.argv) > 1 else (root_dir.parent / "CampusGuard-AI-Complete.zip")

print("=== 1. Testing ZIP Integrity ===")
if not zipfile.is_zipfile(zip_path):
    print("ERROR: Not a valid ZIP file!")
    sys.exit(1)

with zipfile.ZipFile(zip_path, "r") as z:
    test_res = z.testzip()
    if test_res is not None:
        print(f"ERROR: Corrupt entry found in zip: {test_res}")
        sys.exit(1)
    print("CRC checksum check passed: All files are healthy and uncorrupted.")

    names = z.namelist()
    print(f"Total archive entries: {len(names)}")

    print("\n=== 2. Required Models Check ===")
    required_models = [
        "backend/ml_models/best.pt",
        "backend/ml_models/weapon_detection_trained.pt",
        "backend/ml_models/person_detection.pt",
        "backend/ml_models/pose_landmarker_lite.task",
        "models/fall_detection_cnn.keras",
        "models/risk_prediction_model.pkl"
    ]
    for m in required_models:
        present = m in names
        info = z.getinfo(m) if present else None
        sz_mb = info.file_size / (1024 * 1024) if info else 0
        status = "[OK]" if present else "[FAIL]"
        print(f"  {status} {m} ({sz_mb:.2f} MB)")
        assert present, f"Missing required model: {m}"

    duplicate_model = "models/weapon_detection_trained.pt"
    print(f"  Duplicate model in models/ excluded: {duplicate_model not in names}")
    assert duplicate_model not in names

    print("\n=== 3. Active RAG Database Check ===")
    has_active_chroma = any(n.startswith("chroma_db/") for n in names)
    has_stale_chroma = any(n.startswith("data/chroma_db/") for n in names)
    print(f"  Active chroma_db/ included: {has_active_chroma}")
    print(f"  Stale data/chroma_db/ excluded: {not has_stale_chroma}")
    assert has_active_chroma
    assert not has_stale_chroma

    print("\n=== 4. Secrets & Caches Exclusion Check ===")
    has_env = any(n == ".env" or n.endswith("/.env") for n in names)
    has_root_example = ".env.example" in names
    has_frontend_example = "frontend-new/.env.example" in names
    has_node_modules = any("node_modules" in n for n in names)
    has_venv = any(n.startswith("venv") for n in names)
    print(f"  .env excluded (no real secrets): {not has_env}")
    print(f"  root .env.example included: {has_root_example}")
    print(f"  frontend .env.example included: {has_frontend_example}")
    print(f"  node_modules excluded: {not has_node_modules}")
    print(f"  venv excluded: {not has_venv}")
    assert not has_env, "Real .env found in archive"
    assert has_root_example, "Root .env.example missing from archive"
    assert has_frontend_example, "Frontend .env.example missing from archive"
    assert not has_node_modules, "node_modules found in archive"
    assert not has_venv, "venv found in archive"

    print("\n=== 5. Database Exclusion, Frontend & Diagnostics Check ===")
    relational_dbs = [n for n in names if n.endswith(".db") or (n.endswith(".sqlite3") and not n.startswith("chroma_db/"))]
    has_relational_db = len(relational_dbs) > 0
    has_backups = any("backup" in n.lower() for n in names)
    has_frontend = "frontend-new/src/App.jsx" in names
    has_diagnostics = "check_setup.py" in names
    has_campus_docs = any(n.startswith("campus_documents/") for n in names)
    print(f"  Relational database files excluded: {not has_relational_db}")
    print(f"  Backups directory excluded: {not has_backups}")
    print(f"  Campus documents included: {has_campus_docs}")
    print(f"  Frontend source included: {has_frontend}")
    print(f"  check_setup.py included: {has_diagnostics}")
    assert not has_relational_db, f"Database files found in archive: {relational_dbs}"
    assert not has_backups, "Backup files found in archive"
    assert has_campus_docs, "campus_documents/ missing from archive"
    assert has_frontend, "frontend-new/src/App.jsx missing from archive"
    assert has_diagnostics, "check_setup.py missing from archive"

print("\nALL ARCHIVE VERIFICATION CHECKS PASSED SUCCESSFULLY!")
