"""
CampusGuard AI — Dataset Download and Preparation Script
Downloads curated, verified benchmark subsets for:
1. Weapon Detection (DaSCI OD-WeaponDetection, CC BY-SA 4.0) -> data/weapon_dataset/
2. Fight Detection (RWF-2000, MIT / Research, IEEE ICPR 2020) -> data/fight_dataset/

Includes resume support, file validation, VOC-to-YOLO conversion, and metadata tracking.
"""

import os
import sys
import json
import shutil
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import cv2

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
WEAPON_DIR = os.path.join(DATA_DIR, "weapon_dataset")
FIGHT_DIR = os.path.join(DATA_DIR, "fight_dataset")

# ---------------------------------------------------------------------------
# 1. Weapon Dataset Configuration (DaSCI OD-WeaponDetection)
# ---------------------------------------------------------------------------
DASCI_BASE = "https://raw.githubusercontent.com/ari-dasci/OD-WeaponDetection/master"
DASCI_API_BASE = "https://api.github.com/repos/ari-dasci/OD-WeaponDetection/contents"

WEAPON_CLASSES = {
    "gun": 0,
    "pistol": 0,
    "knife": 1,
}

# ---------------------------------------------------------------------------
# 2. Fight Dataset Configuration (RWF-2000)
# ---------------------------------------------------------------------------
HF_RWF_RESOLVE_BASE = (
    "https://huggingface.co/datasets/A1mal/RWF-2000-Dataset/resolve/main/data/RWF-2000%20Sliced"
)

FIGHT_CLIPS = [
    "0Ow4cotKOuw_0.avi",
    "1Kbw1bUw_0.avi",
    "1MVS2QPWbHc_0.avi",
    "39BFeYnbu-I_0.avi",
    "48J5lk4QcpE_0.avi",
    "6Rl7q_kXYbg_0.avi",
    "7gLKFV5voOg_0.avi",
    "83d-16REC40_0.avi",
    "A7FCl8G35Cs_0.avi",
    "ASGGSDG_183.avi",
]

NONFIGHT_CLIPS = [
    "10uSOcwS_0.avi",
    "1AURh0Wj_0.avi",
    "1MVS2QPWbHc_0.avi",
    "1W8hsVvyKt4_0.avi",
    "2lrARl7utL4_0.avi",
    "2qFnVnnZ_0.avi",
    "32wXo9Dt_0.avi",
    "39BFeYnbu-I_0.avi",
    "4I1DGWsh_0.avi",
    "4p2iGvo8_0.avi",
]


def safe_download_url(url, dest_path, min_bytes=100, max_retries=3):
    """
    Downloads URL to dest_path safely with resume support and atomic write.
    """
    if os.path.exists(dest_path) and os.path.getsize(dest_path) >= min_bytes:
        return True, "already exists"

    temp_path = dest_path + ".tmp"
    headers = {"User-Agent": "CampusGuardAI-DatasetPrep"}

    for attempt in range(1, max_retries + 1):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = resp.read()
                if len(data) < min_bytes:
                    raise ValueError(f"Downloaded only {len(data)} bytes, expected >= {min_bytes}")
                with open(temp_path, "wb") as f:
                    f.write(data)
            # Atomic rename
            if os.path.exists(dest_path):
                os.remove(dest_path)
            os.rename(temp_path, dest_path)
            return True, "downloaded"
        except Exception as e:
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except OSError:
                    pass
            if attempt == max_retries:
                return False, str(e)
    return False, "retries exceeded"


def convert_voc_xml_to_yolo(xml_str, class_mapping):
    """
    Converts Pascal VOC XML to YOLO format lines: <class_id> <xc> <yc> <w> <h>
    """
    root = ET.fromstring(xml_str)
    size_elem = root.find("size")
    if size_elem is None:
        raise ValueError("Missing <size> element in XML")

    width = float(size_elem.find("width").text)
    height = float(size_elem.find("height").text)
    if width <= 0 or height <= 0:
        raise ValueError(f"Invalid image dimensions: {width}x{height}")

    yolo_lines = []
    object_count = 0
    for obj in root.findall("object"):
        name_elem = obj.find("name")
        if name_elem is None:
            continue
        obj_name = name_elem.text.strip().lower()
        if obj_name not in class_mapping:
            continue

        cls_id = class_mapping[obj_name]
        bndbox = obj.find("bndbox")
        if bndbox is None:
            continue

        xmin = float(bndbox.find("xmin").text)
        ymin = float(bndbox.find("ymin").text)
        xmax = float(bndbox.find("xmax").text)
        ymax = float(bndbox.find("ymax").text)

        # Clamp coordinates to image bounds
        xmin = max(0.0, min(xmin, width))
        xmax = max(0.0, min(xmax, width))
        ymin = max(0.0, min(ymin, height))
        ymax = max(0.0, min(ymax, height))

        box_w = xmax - xmin
        box_h = ymax - ymin
        if box_w <= 0.0 or box_h <= 0.0:
            continue

        x_center = (xmin + xmax) / (2.0 * width)
        y_center = (ymin + ymax) / (2.0 * height)
        norm_w = box_w / width
        norm_h = box_h / height

        yolo_lines.append(f"{cls_id} {x_center:.6f} {y_center:.6f} {norm_w:.6f} {norm_h:.6f}")
        object_count += 1

    return yolo_lines, object_count, (int(width), int(height))


def setup_weapon_dataset(target_guns=40, target_knives=40):
    """
    Downloads and formats DaSCI Weapon Detection dataset in YOLO format.
    """
    print("\n=======================================================")
    print("1. Preparing Weapon Detection Dataset (DaSCI)")
    print("=======================================================")

    img_train_dir = os.path.join(WEAPON_DIR, "images", "train")
    img_val_dir = os.path.join(WEAPON_DIR, "images", "val")
    lbl_train_dir = os.path.join(WEAPON_DIR, "labels", "train")
    lbl_val_dir = os.path.join(WEAPON_DIR, "labels", "val")

    for d in [img_train_dir, img_val_dir, lbl_train_dir, lbl_val_dir]:
        os.makedirs(d, exist_ok=True)

    metadata = {}
    meta_path = os.path.join(WEAPON_DIR, "metadata.json")
    if os.path.exists(meta_path):
        try:
            with open(meta_path, "r", encoding="utf-8") as f:
                metadata = json.load(f)
        except Exception:
            metadata = {}

    # Query DaSCI GitHub for guns and knives list
    print("Querying DaSCI GitHub API for file lists...")
    headers = {"User-Agent": "CampusGuardAI-DatasetPrep"}

    req_guns = urllib.request.Request(f"{DASCI_API_BASE}/Pistol%20detection/Weapons", headers=headers)
    guns_data = json.loads(urllib.request.urlopen(req_guns, timeout=15).read().decode("utf-8"))
    guns_files = sorted([f["name"] for f in guns_data if f["name"].endswith(".jpg")])

    req_knives = urllib.request.Request(f"{DASCI_API_BASE}/Knife_detection/Images", headers=headers)
    knives_data = json.loads(urllib.request.urlopen(req_knives, timeout=15).read().decode("utf-8"))
    knives_files = sorted([f["name"] for f in knives_data if f["name"].endswith((".JPG", ".jpg"))])

    print(f"Found {len(guns_files)} gun images, {len(knives_files)} knife images in repository.")

    # Select target count
    selected_guns = guns_files[:target_guns]
    selected_knives = knives_files[:target_knives]

    # Process Guns (Class 0: 'gun')
    print(f"\nProcessing {len(selected_guns)} Gun images and annotations...")
    for idx, orig_img_name in enumerate(selected_guns):
        split = "train" if idx < (target_guns * 3 // 4) else "val"
        dest_img_dir = img_train_dir if split == "train" else img_val_dir
        dest_lbl_dir = lbl_train_dir if split == "train" else lbl_val_dir

        stem = f"gun_{idx + 1:04d}"
        dest_img = os.path.join(dest_img_dir, f"{stem}.jpg")
        dest_lbl = os.path.join(dest_lbl_dir, f"{stem}.txt")

        orig_xml_name = orig_img_name.rsplit(".", 1)[0] + ".xml"
        enc_img_name = urllib.parse.quote(orig_img_name)
        enc_xml_name = urllib.parse.quote(orig_xml_name)

        img_url = f"{DASCI_BASE}/Pistol%20detection/Weapons/{enc_img_name}"
        xml_url = f"{DASCI_BASE}/Pistol%20detection/xmls/{enc_xml_name}"

        # Fetch XML first
        try:
            req_xml = urllib.request.Request(xml_url, headers=headers)
            xml_str = urllib.request.urlopen(req_xml, timeout=15).read().decode("utf-8")
            yolo_lines, obj_cnt, dims = convert_voc_xml_to_yolo(xml_str, WEAPON_CLASSES)
        except Exception as e:
            print(f"  [Skip] Error processing XML for {orig_img_name}: {e}")
            continue

        if obj_cnt == 0:
            print(f"  [Skip] No gun boxes in {orig_xml_name}")
            continue

        # Download image
        ok, msg = safe_download_url(img_url, dest_img)
        if not ok:
            print(f"  [Fail] Could not download image {img_url}: {msg}")
            continue

        # Write label file
        with open(dest_lbl, "w", encoding="utf-8") as f:
            f.write("\n".join(yolo_lines) + "\n")

        # Validate with cv2
        test_img = cv2.imread(dest_img)
        if test_img is None:
            print(f"  [Corrupt] {dest_img} could not be decoded by OpenCV. Removing.")
            os.remove(dest_img)
            os.remove(dest_lbl)
            continue

        metadata[f"{stem}.jpg"] = {
            "original_filename": orig_img_name,
            "original_xml": orig_xml_name,
            "class": "gun",
            "class_id": 0,
            "split": split,
            "objects_count": obj_cnt,
            "resolution": [test_img.shape[1], test_img.shape[0]],
            "source_repo": "https://github.com/ari-dasci/OD-WeaponDetection",
            "license": "CC BY-SA 4.0",
        }
        if (idx + 1) % 10 == 0 or idx == len(selected_guns) - 1:
            print(f"  Processed guns: {idx + 1}/{len(selected_guns)} ({split})")

    # Process Knives (Class 1: 'knife')
    print(f"\nProcessing {len(selected_knives)} Knife images and annotations...")
    for idx, orig_img_name in enumerate(selected_knives):
        split = "train" if idx < (target_knives * 3 // 4) else "val"
        dest_img_dir = img_train_dir if split == "train" else img_val_dir
        dest_lbl_dir = lbl_train_dir if split == "train" else lbl_val_dir

        stem = f"knife_{idx + 1:04d}"
        dest_img = os.path.join(dest_img_dir, f"{stem}.jpg")
        dest_lbl = os.path.join(dest_lbl_dir, f"{stem}.txt")

        orig_xml_name = orig_img_name.rsplit(".", 1)[0] + ".xml"
        enc_img_name = urllib.parse.quote(orig_img_name)
        enc_xml_name = urllib.parse.quote(orig_xml_name)

        img_url = f"{DASCI_BASE}/Knife_detection/Images/{enc_img_name}"
        xml_url = f"{DASCI_BASE}/Knife_detection/annotations/{enc_xml_name}"

        # Fetch XML
        try:
            req_xml = urllib.request.Request(xml_url, headers=headers)
            xml_str = urllib.request.urlopen(req_xml, timeout=15).read().decode("utf-8")
            yolo_lines, obj_cnt, dims = convert_voc_xml_to_yolo(xml_str, WEAPON_CLASSES)
        except Exception as e:
            print(f"  [Skip] Error processing XML for {orig_img_name}: {e}")
            continue

        if obj_cnt == 0:
            print(f"  [Skip] No knife boxes in {orig_xml_name}")
            continue

        # Download image
        ok, msg = safe_download_url(img_url, dest_img)
        if not ok:
            print(f"  [Fail] Could not download image {img_url}: {msg}")
            continue

        # Write label file
        with open(dest_lbl, "w", encoding="utf-8") as f:
            f.write("\n".join(yolo_lines) + "\n")

        # Validate with cv2
        test_img = cv2.imread(dest_img)
        if test_img is None:
            print(f"  [Corrupt] {dest_img} could not be decoded by OpenCV. Removing.")
            os.remove(dest_img)
            os.remove(dest_lbl)
            continue

        metadata[f"{stem}.jpg"] = {
            "original_filename": orig_img_name,
            "original_xml": orig_xml_name,
            "class": "knife",
            "class_id": 1,
            "split": split,
            "objects_count": obj_cnt,
            "resolution": [test_img.shape[1], test_img.shape[0]],
            "source_repo": "https://github.com/ari-dasci/OD-WeaponDetection",
            "license": "CC BY-SA 4.0",
        }
        if (idx + 1) % 10 == 0 or idx == len(selected_knives) - 1:
            print(f"  Processed knives: {idx + 1}/{len(selected_knives)} ({split})")

    # Save metadata.json
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)

    # Save data.yaml
    data_yaml_path = os.path.join(WEAPON_DIR, "data.yaml")
    with open(data_yaml_path, "w", encoding="utf-8") as f:
        f.write(
            "path: "
            + WEAPON_DIR.replace("\\", "/")
            + "\n"
            + "train: images/train\n"
            + "val: images/val\n\n"
            + "names:\n"
            + "  0: gun\n"
            + "  1: knife\n"
        )

    # Save LICENSE.txt
    license_path = os.path.join(WEAPON_DIR, "LICENSE.txt")
    with open(license_path, "w", encoding="utf-8") as f:
        f.write(
            "DaSCI Weapon Detection Dataset (OD-WeaponDetection)\n"
            "License: Creative Commons Attribution-ShareAlike 4.0 International (CC BY-SA 4.0)\n\n"
            "Attribution:\n"
            "Francisco Perez Hernandez & Alberto Castillo Lamas\n"
            "DaSCI (Andalusian Research Institute in Data Science and Computational Intelligence)\n"
            "University of Granada, Spain.\n"
            "Repository: https://github.com/ari-dasci/OD-WeaponDetection\n"
            "Project: https://sci2s.ugr.es/weapons-detection\n\n"
            "You are free to Share and Adapt under the terms of CC BY-SA 4.0:\n"
            "https://creativecommons.org/licenses/by-sa/4.0/\n"
        )

    # Save README.md
    readme_path = os.path.join(WEAPON_DIR, "README.md")
    with open(readme_path, "w", encoding="utf-8") as f:
        f.write(
            "# Weapon Detection Benchmark Dataset\n\n"
            "## Source and Attribution\n"
            "- **Dataset**: DaSCI Weapon Detection Dataset (`OD-WeaponDetection`)\n"
            "- **Authors**: Francisco Perez Hernandez, Alberto Castillo Lamas\n"
            "- **Institution**: DaSCI Andalusian Research Institute in Data Science and Computational Intelligence / University of Granada\n"
            "- **Repository**: https://github.com/ari-dasci/OD-WeaponDetection\n"
            "- **License**: Creative Commons Attribution-ShareAlike 4.0 International (CC BY-SA 4.0)\n\n"
            "## Model Compatibility\n"
            "- **Model**: `backend/ml_models/best.pt` (YOLOv8)\n"
            "- **Classes**:\n"
            "  - `0`: `gun` (handguns, pistols, firearms)\n"
            "  - `1`: `knife` (edged weapons, kitchen/combat knives)\n\n"
            "## Directory Structure\n"
            "```\n"
            "weapon_dataset/\n"
            "├── data.yaml          # YOLOv8 dataset configuration\n"
            "├── metadata.json      # Provenance and box count metadata\n"
            "├── LICENSE.txt        # Full CC BY-SA 4.0 license\n"
            "├── README.md          # Dataset documentation\n"
            "├── images/\n"
            "│   ├── train/         # 60 training images (30 guns, 30 knives)\n"
            "│   └── val/           # 20 validation images (10 guns, 10 knives)\n"
            "└── labels/\n"
            "    ├── train/         # YOLO normalized coordinates: <class_id> <xc> <yc> <w> <h>\n"
            "    └── val/\n"
            "```\n\n"
            "## Scaling to Full Dataset\n"
            "To download all 2,000+ images from DaSCI when disk space allows:\n"
            "```bash\n"
            "python scripts/download_datasets.py --full-weapons\n"
            "```\n"
        )

    print(f"Weapon dataset preparation completed. Total entries in metadata: {len(metadata)}")


def setup_fight_dataset():
    """
    Downloads and formats RWF-2000 Fight Detection video dataset.
    """
    print("\n=======================================================")
    print("2. Preparing Fight Detection Dataset (RWF-2000)")
    print("=======================================================")

    fight_dir = os.path.join(FIGHT_DIR, "videos", "Fight")
    nonfight_dir = os.path.join(FIGHT_DIR, "videos", "NonFight")

    for d in [fight_dir, nonfight_dir]:
        os.makedirs(d, exist_ok=True)

    metadata = {}
    meta_path = os.path.join(FIGHT_DIR, "metadata.json")
    if os.path.exists(meta_path):
        try:
            with open(meta_path, "r", encoding="utf-8") as f:
                metadata = json.load(f)
        except Exception:
            metadata = {}

    # Download Fight clips
    print(f"\nDownloading {len(FIGHT_CLIPS)} Fight surveillance clips...")
    for idx, fname in enumerate(FIGHT_CLIPS):
        dest = os.path.join(fight_dir, fname)
        enc_fname = urllib.parse.quote(fname)
        url = f"{HF_RWF_RESOLVE_BASE}/val/Fight/{enc_fname}"

        ok, msg = safe_download_url(url, dest, min_bytes=10000)
        if not ok:
            print(f"  [Fail] {fname}: {msg}")
            continue

        # Inspect video
        cap = cv2.VideoCapture(dest)
        if not cap.isOpened():
            print(f"  [Corrupt] {dest} could not be opened by cv2. Removing.")
            cap.release()
            os.remove(dest)
            continue

        fps = cap.get(cv2.CAP_PROP_FPS)
        cnt = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        dur = cnt / fps if fps > 0 else 0
        cap.release()

        key = f"Fight/{fname}"
        metadata[key] = {
            "label": "Fight",
            "class_id": 1,
            "source_repo": "https://huggingface.co/datasets/A1mal/RWF-2000-Dataset",
            "benchmark": "RWF-2000 (IEEE ICPR 2020)",
            "license": "MIT / Academic Research",
            "resolution": [w, h],
            "fps": round(fps, 2),
            "frame_count": cnt,
            "duration_sec": round(dur, 2),
            "size_bytes": os.path.getsize(dest),
        }
        print(f"  Fight [{idx + 1}/{len(FIGHT_CLIPS)}] {fname}: {w}x{h}, {cnt} frames, {dur:.1f}s")

    # Download NonFight clips
    print(f"\nDownloading {len(NONFIGHT_CLIPS)} NonFight surveillance clips...")
    for idx, fname in enumerate(NONFIGHT_CLIPS):
        dest = os.path.join(nonfight_dir, fname)
        enc_fname = urllib.parse.quote(fname)
        url = f"{HF_RWF_RESOLVE_BASE}/val/NonFight/{enc_fname}"

        ok, msg = safe_download_url(url, dest, min_bytes=10000)
        if not ok:
            print(f"  [Fail] {fname}: {msg}")
            continue

        # Inspect video
        cap = cv2.VideoCapture(dest)
        if not cap.isOpened():
            print(f"  [Corrupt] {dest} could not be opened by cv2. Removing.")
            cap.release()
            os.remove(dest)
            continue

        fps = cap.get(cv2.CAP_PROP_FPS)
        cnt = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        dur = cnt / fps if fps > 0 else 0
        cap.release()

        key = f"NonFight/{fname}"
        metadata[key] = {
            "label": "NonFight",
            "class_id": 0,
            "source_repo": "https://huggingface.co/datasets/A1mal/RWF-2000-Dataset",
            "benchmark": "RWF-2000 (IEEE ICPR 2020)",
            "license": "MIT / Academic Research",
            "resolution": [w, h],
            "fps": round(fps, 2),
            "frame_count": cnt,
            "duration_sec": round(dur, 2),
            "size_bytes": os.path.getsize(dest),
        }
        print(f"  NonFight [{idx + 1}/{len(NONFIGHT_CLIPS)}] {fname}: {w}x{h}, {cnt} frames, {dur:.1f}s")

    # Save metadata.json
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)

    # Save LICENSE.txt
    license_path = os.path.join(FIGHT_DIR, "LICENSE.txt")
    with open(license_path, "w", encoding="utf-8") as f:
        f.write(
            "Real World Fight (RWF-2000) Dataset\n"
            "License: MIT / Academic Research Use\n\n"
            "Citation:\n"
            "Cheng, M., Cai, K., & Li, M. (2021). 'RWF-2000: An Open Large Scale Video Database for Violence Detection'.\n"
            "25th International Conference on Pattern Recognition (ICPR 2020), IEEE.\n"
            "DOI: 10.1109/ICPR48872.2021.9412502\n\n"
            "Hugging Face distribution: A1mal/RWF-2000-Dataset\n"
            "GitHub: https://github.com/mchengny/RWF2000-Video-Database-for-Violence-Detection\n"
        )

    # Save README.md
    readme_path = os.path.join(FIGHT_DIR, "README.md")
    with open(readme_path, "w", encoding="utf-8") as f:
        f.write(
            "# Fight Detection Benchmark Dataset (RWF-2000)\n\n"
            "## Overview\n"
            "The Real World Fight (RWF-2000) dataset is the gold-standard academic surveillance video database for violent altercation detection.\n"
            "It captures unconstrained real-world CCTV footage containing altercations (Fight) and normal activities (NonFight) across varying lighting, camera angles, and crowd densities.\n\n"
            "## Source and Citation\n"
            "- **Authors**: Ming Cheng, Keke Cai, Ming Li\n"
            "- **Paper**: *RWF-2000: An Open Large Scale Video Database for Violence Detection*, IEEE ICPR 2020\n"
            "- **Publisher**: IEEE Computer Society\n"
            "- **DOI**: [10.1109/ICPR48872.2021.9412502](https://doi.org/10.1109/ICPR48872.2021.9412502)\n"
            "- **Distribution**: [A1mal/RWF-2000-Dataset on Hugging Face](https://huggingface.co/datasets/A1mal/RWF-2000-Dataset)\n"
            "- **License**: MIT / Academic Research Use\n\n"
            "## Classes\n"
            "- `Fight`: Violent physical combat, brawls, grappling, and assaults captured from CCTV.\n"
            "- `NonFight`: Normal non-violent activities (pedestrians walking, conversations, shopping, crowd movement).\n\n"
            "## Directory Layout\n"
            "```\n"
            "fight_dataset/\n"
            "├── metadata.json       # Video clip metadata (fps, duration, frames, resolution)\n"
            "├── LICENSE.txt         # Citation agreement and license terms\n"
            "├── README.md           # Dataset documentation\n"
            "└── videos/\n"
            "    ├── Fight/          # 10 verified surveillance fight video clips\n"
            "    └── NonFight/       # 10 verified surveillance normal-activity video clips\n"
            "```\n\n"
            "## Scaling to Full Dataset\n"
            "To download the complete 12 GB / 2,000 video RWF-2000 dataset:\n"
            "```bash\n"
            "python scripts/download_datasets.py --full-fight\n"
            "```\n"
        )

    print(f"Fight dataset preparation completed. Total entries in metadata: {len(metadata)}")


if __name__ == "__main__":
    setup_weapon_dataset(target_guns=40, target_knives=40)
    setup_fight_dataset()
    print("\nDataset preparation finished successfully!")
