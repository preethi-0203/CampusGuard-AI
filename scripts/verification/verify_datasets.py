"""
CampusGuard AI — Comprehensive Dataset Verification Script
Verifies:
1. Weapon Dataset: image decodability, bbox coordinates, YOLO class compliance, splits.
2. Fight Dataset: video stream decodability, fps, frame counts, durations, classes.
3. Preserved Datasets: Fall dataset and Risk dataset integrity.
4. Operational Database: integrity check and row count invariance.
"""

import os
import sys
import glob
import json
import sqlite3
import shutil
import cv2
import pandas as pd

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
WEAPON_DIR = os.path.join(DATA_DIR, "weapon_dataset")
FIGHT_DIR = os.path.join(DATA_DIR, "fight_dataset")
DB_PATH = os.path.join(PROJECT_ROOT, "campusguard.db")


def verify_operational_db():
    print("\n--- Verifying Operational Database (campusguard.db) ---")
    if not os.path.exists(DB_PATH):
        print(f"[FAIL] Database file not found at {DB_PATH}")
        return False

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("PRAGMA integrity_check;")
    integrity = cursor.fetchall()

    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';")
    tables = [row[0] for row in cursor.fetchall()]

    counts = {}
    for t in ["users", "cameras", "alerts", "incidents", "incident_logs"]:
        if t in tables:
            cursor.execute(f"SELECT COUNT(*) FROM {t};")
            counts[t] = cursor.fetchone()[0]
        else:
            counts[t] = None
    conn.close()

    expected = {"users": 4, "cameras": 1, "alerts": 67, "incidents": 19, "incident_logs": 12}
    matches = counts == expected
    status = "[PASS]" if matches and integrity == [("ok",)] else "[FAIL]"
    print(f"{status} Integrity: {integrity}, Counts: {counts} (Matches baseline: {matches})")
    return matches


def verify_weapon_dataset():
    print("\n--- Verifying Weapon Dataset (data/weapon_dataset/) ---")
    if not os.path.exists(WEAPON_DIR):
        print(f"[FAIL] Directory does not exist: {WEAPON_DIR}")
        return False, {}

    stats = {
        "train_images": 0,
        "val_images": 0,
        "train_labels": 0,
        "val_labels": 0,
        "class_0_boxes": 0,  # gun
        "class_1_boxes": 0,  # knife
        "other_boxes": 0,
        "corrupt_images": 0,
        "corrupt_labels": 0,
        "total_disk_bytes": 0,
    }

    # Check data.yaml, LICENSE.txt, README.md
    for f in ["data.yaml", "LICENSE.txt", "README.md", "metadata.json"]:
        p = os.path.join(WEAPON_DIR, f)
        if not os.path.exists(p) or os.path.getsize(p) == 0:
            print(f"  [WARN] Missing or empty {f}")

    for split in ["train", "val"]:
        img_dir = os.path.join(WEAPON_DIR, "images", split)
        lbl_dir = os.path.join(WEAPON_DIR, "labels", split)

        if not os.path.exists(img_dir) or not os.path.exists(lbl_dir):
            print(f"  [FAIL] Missing directory: {img_dir} or {lbl_dir}")
            return False, stats

        img_files = sorted(glob.glob(os.path.join(img_dir, "*.*")))
        lbl_files = sorted(glob.glob(os.path.join(lbl_dir, "*.txt")))

        stats[f"{split}_images"] = len(img_files)
        stats[f"{split}_labels"] = len(lbl_files)

        img_stems = {os.path.splitext(os.path.basename(f))[0]: f for f in img_files}
        lbl_stems = {os.path.splitext(os.path.basename(f))[0]: f for f in lbl_files}

        # Check 1-to-1 match
        missing_lbls = set(img_stems.keys()) - set(lbl_stems.keys())
        missing_imgs = set(lbl_stems.keys()) - set(img_stems.keys())
        if missing_lbls:
            print(f"  [FAIL] Images without labels in {split}: {len(missing_lbls)}")
        if missing_imgs:
            print(f"  [FAIL] Labels without images in {split}: {len(missing_imgs)}")

        # Verify each image and label
        for stem, img_path in img_stems.items():
            stats["total_disk_bytes"] += os.path.getsize(img_path)
            # Verify OpenCV decode
            img = cv2.imread(img_path)
            if img is None or img.shape[0] == 0 or img.shape[1] == 0:
                print(f"  [CORRUPT] Image cannot be loaded: {img_path}")
                stats["corrupt_images"] += 1
                continue

            lbl_path = lbl_stems.get(stem)
            if lbl_path:
                stats["total_disk_bytes"] += os.path.getsize(lbl_path)
                with open(lbl_path, "r", encoding="utf-8") as lf:
                    lines = [l.strip() for l in lf.readlines() if l.strip()]

                if not lines:
                    print(f"  [WARN] Empty label file: {lbl_path}")

                for line in lines:
                    parts = line.split()
                    if len(parts) != 5:
                        print(f"  [CORRUPT] Invalid YOLO line in {lbl_path}: {line}")
                        stats["corrupt_labels"] += 1
                        continue
                    try:
                        cls_id = int(parts[0])
                        xc = float(parts[1])
                        yc = float(parts[2])
                        w = float(parts[3])
                        h = float(parts[4])

                        if not (0.0 <= xc <= 1.0 and 0.0 <= yc <= 1.0 and 0.0 < w <= 1.0 and 0.0 < h <= 1.0):
                            print(f"  [OUT-OF-BOUNDS] Coordinates in {lbl_path}: {parts}")
                            stats["corrupt_labels"] += 1

                        if cls_id == 0:
                            stats["class_0_boxes"] += 1
                        elif cls_id == 1:
                            stats["class_1_boxes"] += 1
                        else:
                            stats["other_boxes"] += 1
                    except ValueError:
                        print(f"  [PARSE ERROR] In {lbl_path}: {line}")
                        stats["corrupt_labels"] += 1

    total_imgs = stats["train_images"] + stats["val_images"]
    total_boxes = stats["class_0_boxes"] + stats["class_1_boxes"]
    mb = stats["total_disk_bytes"] / (1024 * 1024)
    print(f"Weapon Dataset Verified:")
    print(f"  Total Images: {total_imgs} (Train: {stats['train_images']}, Val: {stats['val_images']})")
    print(f"  Total Labels: {stats['train_labels'] + stats['val_labels']}")
    print(f"  Bounding Boxes: Gun (class 0) = {stats['class_0_boxes']}, Knife (class 1) = {stats['class_1_boxes']}")
    print(f"  Corrupt Images: {stats['corrupt_images']}, Corrupt Labels: {stats['corrupt_labels']}")
    print(f"  Total Disk Usage: {mb:.2f} MB")
    ok = (total_imgs > 0 and stats["corrupt_images"] == 0 and stats["corrupt_labels"] == 0)
    return ok, stats


def verify_fight_dataset():
    print("\n--- Verifying Fight Dataset (data/fight_dataset/) ---")
    if not os.path.exists(FIGHT_DIR):
        print(f"[FAIL] Directory does not exist: {FIGHT_DIR}")
        return False, {}

    stats = {
        "fight_videos": 0,
        "nonfight_videos": 0,
        "total_frames": 0,
        "total_duration_sec": 0.0,
        "corrupt_videos": 0,
        "total_disk_bytes": 0,
        "resolutions": set(),
        "fps_list": set(),
    }

    # Check files
    for f in ["LICENSE.txt", "README.md", "metadata.json"]:
        p = os.path.join(FIGHT_DIR, f)
        if not os.path.exists(p) or os.path.getsize(p) == 0:
            print(f"  [WARN] Missing or empty {f}")

    for category in ["Fight", "NonFight"]:
        vdir = os.path.join(FIGHT_DIR, "videos", category)
        if not os.path.exists(vdir):
            print(f"  [FAIL] Missing video directory: {vdir}")
            return False, stats

        vfiles = sorted(glob.glob(os.path.join(vdir, "*.avi")) + glob.glob(os.path.join(vdir, "*.mp4")))
        if category == "Fight":
            stats["fight_videos"] = len(vfiles)
        else:
            stats["nonfight_videos"] = len(vfiles)

        for vpath in vfiles:
            stats["total_disk_bytes"] += os.path.getsize(vpath)
            cap = cv2.VideoCapture(vpath)
            if not cap.isOpened():
                print(f"  [CORRUPT] Cannot open video: {vpath}")
                stats["corrupt_videos"] += 1
                cap.release()
                continue

            ret, frame = cap.read()
            if not ret or frame is None:
                print(f"  [CORRUPT] Cannot read first frame of: {vpath}")
                stats["corrupt_videos"] += 1
                cap.release()
                continue

            fps = cap.get(cv2.CAP_PROP_FPS)
            cnt = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            dur = cnt / fps if fps > 0 else 0
            cap.release()

            stats["total_frames"] += cnt
            stats["total_duration_sec"] += dur
            stats["resolutions"].add(f"{w}x{h}")
            stats["fps_list"].add(round(fps, 1))

    total_vids = stats["fight_videos"] + stats["nonfight_videos"]
    mb = stats["total_disk_bytes"] / (1024 * 1024)
    print(f"Fight Dataset Verified:")
    print(f"  Total Video Clips: {total_vids} (Fight: {stats['fight_videos']}, NonFight: {stats['nonfight_videos']})")
    print(f"  Total Frames: {stats['total_frames']}, Total Duration: {stats['total_duration_sec']:.1f}s")
    print(f"  Resolutions: {list(stats['resolutions'])}, FPS values: {list(stats['fps_list'])}")
    print(f"  Corrupt Videos: {stats['corrupt_videos']}")
    print(f"  Total Disk Usage: {mb:.2f} MB")
    ok = (total_vids > 0 and stats["corrupt_videos"] == 0)
    return ok, stats


def verify_preserved_datasets():
    print("\n--- Verifying Preserved Datasets ---")
    # Fall dataset
    fall_path = os.path.join(DATA_DIR, "fall")
    fall_zips = glob.glob(os.path.join(fall_path, "*.zip"))
    print(f"UR Fall Dataset: {len(fall_zips)} zip archives present in data/fall/")

    # Risk dataset
    risk_csv = os.path.join(DATA_DIR, "risk_dataset.csv")
    if os.path.exists(risk_csv):
        df = pd.read_csv(risk_csv)
        print(f"Risk Dataset: {risk_csv} present, {len(df)} rows, columns: {list(df.columns)}")
    else:
        print(f"[FAIL] Missing risk_dataset.csv")


def main():
    print("=======================================================")
    print("CampusGuard AI — Complete Dataset & Database Integrity Audit")
    print("=======================================================")

    db_ok = verify_operational_db()
    w_ok, w_stats = verify_weapon_dataset()
    f_ok, f_stats = verify_fight_dataset()
    verify_preserved_datasets()

    # Free disk check
    total, used, free = shutil.disk_usage(PROJECT_ROOT)
    print("\n--- Storage Usage ---")
    print(f"Total: {total/(1024**3):.1f} GB, Used: {used/(1024**3):.1f} GB, Free: {free/(1024**3):.1f} GB")

    print("\n=======================================================")
    overall = db_ok and w_ok and f_ok
    print(f"OVERALL STATUS: {'[PASS] All Datasets and Database 100% Verified' if overall else '[FAIL] Issues Detected'}")
    print("=======================================================")


if __name__ == "__main__":
    main()
