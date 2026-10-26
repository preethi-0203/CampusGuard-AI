"""
CampusGuard AI — Complete Runnable ZIP Packaging Script
Packages the complete, runnable CampusGuard AI project for sharing on Windows.

Includes:
- All backend source code, routes, services, config, database migrations
- All trained AI models (.pt, .keras, .pkl, .task)
- Frontend-new source code (src, public, config, package.json, index.html)
- SQLite database (campusguard.db)
- RAG safety corpus (campus_documents/) & vector embeddings (chroma_db/)
- Verification datasets for UI testing (data/weapon_dataset/, data/fight_dataset/, risk_data.csv)
- Test suite (tests/)
- Diagnostic script (check_setup.py) and documentation (README.md, data/README.md)
- Environment template (.env.example)

Excludes:
- .env (preserves user secrets)
- venv/ (virtual environment)
- frontend-new/node_modules/ & frontend-new/dist/
- data/fall/ (8.65 GB raw academic training videos/zips)
- data/fall_dataset/ (241 MB CNN retraining frames)
- .git/ & __pycache__/ & temporary caches/logs
"""

import os
import sys
import zipfile
from pathlib import Path


def create_complete_zip(dry_run: bool = False):
    root_dir = Path(__file__).resolve().parent.parent
    output_zip = root_dir.parent / "CampusGuard-AI-Complete.zip"

    # Explicit inclusions from project root
    included_dirs = [
        "backend",
        "frontend-new",
        "models",
        "campus_documents",
        "chroma_db",
        "tests",
        "scripts",
        "notebooks",
        "docs",
        "data",
    ]

    included_root_files = [
        "README.md",
        "requirements.txt",
        ".env.example",
        ".gitignore",
        "check_setup.py",
        "create_security.py",
        "migrate_alerts.py",
        "migrate_incidents.py",
    ]

    skip_dir_names = {
        ".git",
        "venv",
        "node_modules",
        "dist",
        "__pycache__",
        ".pytest_cache",
        "runs",
        "backups",
        "backup",
        "scratch",
    }

    # Specifically skip raw heavy training datasets not required for runtime
    skip_relative_paths = {
        os.path.join("data", "fall"),
        os.path.join("data", "fall_dataset"),
    }

    skip_extensions = {
        ".pyc",
        ".pyo",
        ".log",
        ".tmp",
    }

    files_to_pack = []
    total_uncompressed_bytes = 0

    # 1. Root files
    for filename in included_root_files:
        fpath = root_dir / filename
        if fpath.exists() and fpath.is_file():
            size = fpath.stat().st_size
            files_to_pack.append((fpath, filename, size))
            total_uncompressed_bytes += size

    # 2. Directories
    for dirname in included_dirs:
        dir_path = root_dir / dirname
        if not dir_path.exists():
            continue

        for base_str, dirs, names in os.walk(dir_path):
            base = Path(base_str)
            rel_base = base.relative_to(root_dir)

            # Filter out skip_dir_names
            dirs[:] = [d for d in dirs if d not in skip_dir_names]

            # Check if this directory path should be skipped (e.g. data/fall)
            rel_str = str(rel_base)
            if any(rel_str == sp or rel_str.startswith(sp + os.sep) for sp in skip_relative_paths):
                dirs[:] = []
                continue

            for name in names:
                if name.startswith(".env") and name != ".env.example":
                    continue
                ext = os.path.splitext(name)[1].lower()
                if ext in skip_extensions:
                    continue

                full_path = base / name
                rel_path = full_path.relative_to(root_dir)
                rel_path_str = rel_path.as_posix()

                # Skip any file within skipped relative paths
                if any(rel_path_str == sp.replace("\\", "/") or rel_path_str.startswith(sp.replace("\\", "/") + "/") for sp in skip_relative_paths):
                    continue

                # Skip node_modules or dist if nested
                parts = rel_path.parts
                if any(p in skip_dir_names for p in parts):
                    continue

                # Exclude real relational database files while preserving chroma_db
                if ext in [".db", ".sqlite", ".sqlite3"] and "chroma_db" not in parts:
                    continue

                size = full_path.stat().st_size
                files_to_pack.append((full_path, rel_path_str, size))
                total_uncompressed_bytes += size

    print("=" * 70)
    print("CAMPUSGUARD AI — COMPLETE SHARING ZIP PACKAGER")
    print("=" * 70)
    print(f"Total files identified:       {len(files_to_pack)}")
    print(f"Total uncompressed size:     {total_uncompressed_bytes / (1024 * 1024):.2f} MB")
    print(f"Target destination:          {output_zip}")

    # Breakdown by category
    models_found = []
    for fpath, rel, sz in files_to_pack:
        if ext := os.path.splitext(fpath)[1].lower() in [".pt", ".keras", ".pkl", ".task"]:
            models_found.append((rel, sz))

    print(f"\nAI Models included ({len(models_found)} files):")
    for rel, sz in sorted(models_found):
        print(f"  - {rel:<48} ({sz / (1024 * 1024):.2f} MB)")

    if dry_run:
        print("\n[DRY RUN COMPLETED - NO ZIP WRITTEN]")
        return len(files_to_pack), total_uncompressed_bytes

    print(f"\nCreating ZIP file at {output_zip} ...")
    with zipfile.ZipFile(output_zip, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for idx, (fpath, rel, sz) in enumerate(files_to_pack, 1):
            if idx % 50 == 0 or idx == len(files_to_pack):
                print(f"  [{idx:>4}/{len(files_to_pack)}] Packing: {rel[:55]}")
            z.write(fpath, rel)

    final_size = output_zip.stat().st_size
    print("\n" + "=" * 70)
    print(f"SUCCESS: Package created at {output_zip}")
    print(f"Compressed ZIP Size: {final_size / (1024 * 1024):.2f} MB")
    print(f"Compression Ratio:   {(1.0 - final_size / total_uncompressed_bytes) * 100:.1f}% reduction")
    print("=" * 70)
    return len(files_to_pack), final_size


if __name__ == "__main__":
    is_dry = "--dry-run" in sys.argv
    create_complete_zip(dry_run=is_dry)
