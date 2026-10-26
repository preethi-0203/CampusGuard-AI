# CampusGuard AI — Datasets Documentation

This directory contains the training, evaluation, and benchmark datasets supporting the computer vision and risk prediction components of **CampusGuard AI**.

---

## Table of Contents
1. [Dataset Inventory Overview](#1-dataset-inventory-overview)
2. [Weapon Detection Dataset (`weapon_dataset/`)](#2-weapon-detection-dataset-weapon_dataset)
3. [Fight Detection Dataset (`fight_dataset/`)](#3-fight-detection-dataset-fight_dataset)
4. [Fall Detection Dataset (`fall/` & `fall_dataset/`)](#4-fall-detection-dataset-fall--fall_dataset)
5. [Campus Security Risk Prediction Dataset (`risk_dataset.csv`)](#5-campus-security-risk-prediction-dataset-risk_datasetcsv)
6. [Verification and Integrity Auditing](#6-verification-and-integrity-auditing)
7. [Scaling to Full Academic Datasets](#7-scaling-to-full-academic-datasets)
8. [Ethical Considerations and Licensing Summary](#8-ethical-considerations-and-licensing-summary)

---

## 1. Dataset Inventory Overview

| Dataset | Modality | Classes / Targets | Format | Primary Model | License |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **DaSCI Weapon Detection** | RGB Images + Labels | `0: gun`, `1: knife` | YOLOv8 Bounding Boxes | `backend/ml_models/best.pt` | CC BY-SA 4.0 |
| **RWF-2000 Fight Detection** | Surveillance Video Clips | `Fight`, `NonFight` | AVI / H.264 (30 fps / 10 fps) | VideoMAE / Action Classifiers | MIT / Academic |
| **UR Fall Detection** | RGB Image Sequences | `Fall`, `ADL` (Daily Living) | JPEG sequences / Zip archives | `models/fall_detection_cnn.keras` | Academic Research |
| **Campus Risk Dataset** | Tabular Incident Features | `risk_level` (Low, Medium, High) | CSV (2,000 samples) | `models/risk_prediction_model.pkl` | Project Benchmark |

---

## 2. Weapon Detection Dataset (`weapon_dataset/`)

### Source and Attribution
- **Dataset**: DaSCI Weapon Detection Dataset (`OD-WeaponDetection`)
- **Creators**: Francisco Pérez Hernández & Alberto Castillo Lamas
- **Institution**: DaSCI (Andalusian Research Institute in Data Science and Computational Intelligence), University of Granada, Spain.
- **Academic Project**: [Weapon detection for security and video surveillance project](https://sci2s.ugr.es/weapons-detection)
- **Repository**: [https://github.com/ari-dasci/OD-WeaponDetection](https://github.com/ari-dasci/OD-WeaponDetection)
- **License**: Creative Commons Attribution-ShareAlike 4.0 International ([CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/))

### Model Mapping and Classes
The bounding box labels are strictly formatted for YOLOv8 object detection, perfectly aligned with the class indices in `backend/ml_models/best.pt`:
- **Class `0` (`gun`)**: Handguns, pistols, firearms in varying poses and occlusions.
- **Class `1` (`knife`)**: Kitchen knives, utility blades, and edged weapons.

### Coordinate Format
Normalized YOLO bounding box format:
```
<class_id> <x_center> <y_center> <width> <height>
```
Where all coordinate values are floats normalized to $[0.0, 1.0]$ relative to image width and height.

### Directory Structure
```
data/weapon_dataset/
├── data.yaml              # YOLOv8 configuration file pointing to train/val splits
├── metadata.json          # File-by-file provenance, source URL, resolution, object counts
├── LICENSE.txt            # Full CC BY-SA 4.0 legal text
├── README.md              # Dataset-specific documentation
├── images/
│   ├── train/             # Training split (30 gun images, 30 knife images = 60 images)
│   └── val/               # Validation split (10 gun images, 10 knife images = 20 images)
└── labels/
    ├── train/             # 60 corresponding YOLO format .txt label files
    └── val/               # 20 corresponding YOLO format .txt label files
```

---

## 3. Fight Detection Dataset (`fight_dataset/`)

### Source and Attribution
- **Dataset**: Real World Fight (RWF-2000) Dataset
- **Authors**: Ming Cheng, Keke Cai, and Ming Li (2021)
- **Citation**: 
  > Ming Cheng, Keke Cai, and Ming Li. *"RWF-2000: An Open Large Scale Video Database for Violence Detection"*. 25th International Conference on Pattern Recognition (ICPR 2020), IEEE Computer Society, 2021.
  > DOI: [10.1109/ICPR48872.2021.9412502](https://doi.org/10.1109/ICPR48872.2021.9412502)
- **Distribution**: [A1mal/RWF-2000-Dataset on Hugging Face](https://huggingface.co/datasets/A1mal/RWF-2000-Dataset)
- **Original Repository**: [https://github.com/mchengny/RWF2000-Video-Database-for-Violence-Detection](https://github.com/mchengny/RWF2000-Video-Database-for-Violence-Detection)
- **License**: MIT / Academic Research Use

### Dataset Characteristics
- Captured exclusively from real surveillance cameras (CCTV) in public spaces, hallways, plazas, and commercial premises.
- Unconstrained scenarios with realistic lighting, shadows, variable camera resolutions, and authentic motion blur.
- Classes:
  - `Fight`: Physical altercation, wrestling, striking, pushing, and violent grappling.
  - `NonFight`: Pedestrians walking, normal gathering, talking, shopping, and everyday non-violent interactions.

### Directory Structure
```
data/fight_dataset/
├── metadata.json          # Video properties (fps, duration, frame counts, resolution, hash)
├── LICENSE.txt            # Research license and citation terms
├── README.md              # Dataset-specific documentation
└── videos/
    ├── Fight/             # 10 verified surveillance fight video clips (.avi)
    └── NonFight/          # 10 verified surveillance normal activity video clips (.avi)
```

---

## 4. Fall Detection Dataset (`fall/` & `fall_dataset/`)

### Source and Attribution
- **Dataset**: UR Fall Detection Dataset (URFD)
- **Institution**: University of Rzeszow, Interdisciplinary Centre for Computational Modelling
- **Citation**:
  > B. Kwolek, M. Kepski. *"Human fall detection on embedded platform using depth maps and wireless accelerometer"*. Computer Methods and Programs in Biomedicine, 117(3):489-501, 2014.
- **License**: Academic Research Use

### Characteristics
- Captured using RGB and depth camera streams.
- Contains 30 falls and 40 Activities of Daily Living (ADL).
- Preprocessed frame sequences are used for training and evaluating `models/fall_detection_cnn.keras`.
- Raw camera zip archives and extracted sequences are preserved intact in `data/fall/`.

---

## 5. Campus Security Risk Prediction Dataset (`risk_dataset.csv`)

### Schema & Feature Definitions
Contains 2,000 structured incident observations used by `models/risk_prediction_model.pkl`:
- `fall` (`0` or `1`): Fall detection event detected in camera feed.
- `fight` (`0` or `1`): Fight detection event detected in camera feed.
- `weapon` (`0` or `1`): Weapon detection event detected in camera feed.
- `restricted_entry` (`0` or `1`): Bounding box centroid located inside configured restricted perimeter.
- `after_hours` (`0` or `1`): Event timestamp falling outside authorized campus hours.
- `loitering` (`0` or `1`): Prolonged stationary presence in sensitive area.
- `risk_level` (`Low`, `Medium`, `High`): Multi-class target variable for campus safety prioritization.

---

## 6. Verification and Integrity Auditing

To independently audit the integrity of all datasets, label correctness, video stream decodability, and database state, run:

```bash
# From project root using the virtual environment
.\venv\Scripts\python.exe scratch\verify_datasets.py
```

The script automatically verifies:
1. **Weapon Bounding Boxes**: Validates that all normalized coordinates satisfy $0 \le x_c, y_c, w, h \le 1$, checks for non-zero area, and confirms class IDs match `{0: 'gun', 1: 'knife'}`.
2. **Video Decodability**: Uses OpenCV `VideoCapture` to verify stream headers, decodes the first frame of every video, and checks frame counts and framerates.
3. **Database Integrity**: Verifies operational database `campusguard.db` integrity and baseline row counts (`users: 4`, `cameras: 1`, `alerts: 67`, `incidents: 19`, `incident_logs: 12`).

---

## 7. Scaling to Full Academic Datasets

For high-performance workstation or GPU cluster training requiring the complete uncompressed datasets:

### Full Weapon Detection Dataset (~2,000+ Images)
```bash
# Query and download the full DaSCI repository
python scripts/download_datasets.py --full-weapons
```
Alternatively, download the DaSCI archive from the authors' Google Drive mirror:
[DaSCI Full Dataset Drive Link](https://drive.google.com/file/d/1Szc920DAh5kU8Qk38Doq0znEVR1QmTZS/view?usp=sharing).

### Full RWF-2000 Dataset (12 GB / 2,000 Videos)
```bash
# Using Hugging Face CLI or Python script
huggingface-cli download A1mal/RWF-2000-Dataset --local-dir data/rwf_2000_full/
```

---

## 8. Ethical Considerations and Licensing Summary

1. **Surveillance & Privacy**:
   - All dataset images and videos are sourced from approved public academic benchmarks specifically intended for security and machine perception research.
   - Datasets do not include personally identifiable biometric identity records.
2. **Model Behavior & Disclaimers**:
   - Object detection and action recognition outputs are heuristic indicators to assist human safety personnel. High-consequence interventions must always involve human operator review.
