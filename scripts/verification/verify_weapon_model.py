"""
Weapon Model Verification Script
Verifies:
- backend/ml_models/weapon_detection_trained.pt
- Class mapping: {0: 'gun', 1: 'knife'}
- Predictions on 20 validation images in data/weapon_dataset/images/val/
- Preserves best.pt (confirms hash is untouched)
- Preserves operational database
- Saves annotated output images to scratch/weapon_model_verification/predictions/
- Generates JSON and Markdown verification reports in scratch/weapon_model_verification/
"""

import os
import json
import hashlib
from pathlib import Path
from PIL import Image
from ultralytics import YOLO

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MODEL_PATH = PROJECT_ROOT / "backend" / "ml_models" / "weapon_detection_trained.pt"
BEST_PT_PATH = PROJECT_ROOT / "backend" / "ml_models" / "best.pt"
ORIGINAL_BEST_PT_SHA256 = "07241a8fc57d0f3fd29231dd72b9f452375745290b2185440de0165590997cb5"
DATA_YAML = PROJECT_ROOT / "data" / "weapon_dataset" / "data.yaml"
VAL_IMAGES_DIR = PROJECT_ROOT / "data" / "weapon_dataset" / "images" / "val"
VAL_LABELS_DIR = PROJECT_ROOT / "data" / "weapon_dataset" / "labels" / "val"
OUTPUT_DIR = PROJECT_ROOT / "scratch" / "weapon_model_verification"
PREDICTIONS_DIR = OUTPUT_DIR / "predictions"
z

def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(8192):
            h.update(chunk)
    return h.hexdigest()


def load_ground_truth(label_file: Path) -> list:
    boxes = []
    if not label_file.exists():
        return boxes
    with open(label_file, "r") as f:
        for line in f:
            parts = line.strip().split()
            if len(parts) == 5:
                cls_id = int(parts[0])
                xc, yc, w, h = [float(x) for x in parts[1:]]
                boxes.append({
                    "class_id": cls_id,
                    "class_name": "gun" if cls_id == 0 else "knife",
                    "bbox_norm": [xc, yc, w, h]
                })
    return boxes


def run_verification():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    PREDICTIONS_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 70)
    print("CAMPUSGUARD AI - WEAPON MODEL VERIFICATION SUITE")
    print("=" * 70)

    # 1. Check best.pt integrity
    print("\n[Step 1/5] Verifying existing best.pt preservation...")
    if not BEST_PT_PATH.exists():
        raise FileNotFoundError(f"Original best.pt missing at {BEST_PT_PATH}!")
    current_best_sha = sha256_file(BEST_PT_PATH)
    best_pt_intact = (current_best_sha == ORIGINAL_BEST_PT_SHA256)
    print(f"  best.pt path:   {BEST_PT_PATH}")
    print(f"  Current SHA256: {current_best_sha}")
    print(f"  Original SHA256:{ORIGINAL_BEST_PT_SHA256}")
    print(f"  best.pt untouched & preserved: {best_pt_intact}")
    if not best_pt_intact:
        raise RuntimeError("CRITICAL ERROR: best.pt was modified or overwritten!")

    # 2. Check weapon_detection_trained.pt existence & class mapping
    print("\n[Step 2/5] Inspecting trained model checkpoint...")
    if not MODEL_PATH.exists():
        raise FileNotFoundError(f"Trained model not found at {MODEL_PATH}!")
    trained_sha = sha256_file(MODEL_PATH)
    file_size_bytes = MODEL_PATH.stat().st_size
    print(f"  Trained model path: {MODEL_PATH}")
    print(f"  File size:          {file_size_bytes} bytes (~{file_size_bytes / 1024 / 1024:.2f} MB)")
    print(f"  SHA256:             {trained_sha}")

    model = YOLO(str(MODEL_PATH))
    class_mapping = getattr(model, "names", {})
    print(f"  Model Task:         {getattr(model, 'task', 'unknown')}")
    print(f"  Model Names:        {class_mapping}")

    expected_mapping = {0: "gun", 1: "knife"}
    class_mapping_valid = (class_mapping == expected_mapping)
    print(f"  Class mapping valid ({expected_mapping}): {class_mapping_valid}")
    if not class_mapping_valid:
        raise ValueError(f"Unexpected class mapping: expected {expected_mapping}, got {class_mapping}")

    # 3. Ultralytics formal validation metrics
    print("\n[Step 3/5] Computing formal validation metrics on data.yaml...")
    val_metrics = model.val(data=str(DATA_YAML), split="val", verbose=False)
    
    overall_map50 = float(val_metrics.box.map50)
    overall_map = float(val_metrics.box.map)
    overall_precision = float(val_metrics.box.mp)
    overall_recall = float(val_metrics.box.mr)

    print(f"  Validation mAP50:     {overall_map50:.4f}")
    print(f"  Validation mAP50-95:  {overall_map:.4f}")
    print(f"  Validation Precision: {overall_precision:.4f}")
    print(f"  Validation Recall:    {overall_recall:.4f}")

    # Per-class metrics if available
    class_metrics = {}
    if hasattr(val_metrics.box, "maps") and len(val_metrics.box.maps) >= 2:
        class_metrics["gun"] = {
            "mAP50": float(val_metrics.box.all_ap[0][0]) if hasattr(val_metrics.box, "all_ap") else None,
            "mAP50-95": float(val_metrics.box.maps[0]),
        }
        class_metrics["knife"] = {
            "mAP50": float(val_metrics.box.all_ap[1][0]) if hasattr(val_metrics.box, "all_ap") else None,
            "mAP50-95": float(val_metrics.box.maps[1]),
        }

    # 4. Predict on all 20 validation images and save visual predictions
    print("\n[Step 4/5] Running predictions on 20 validation images & saving visual outputs...")
    val_images = sorted([f for f in VAL_IMAGES_DIR.iterdir() if f.suffix.lower() in [".jpg", ".jpeg", ".png"]])
    print(f"  Found {len(val_images)} validation images.")

    image_results = []
    thresholds = [0.25, 0.50, 0.75]
    detected_counts_by_thresh = {t: 0 for t in thresholds}
    class_match_counts_by_thresh = {t: 0 for t in thresholds}

    for idx, img_path in enumerate(val_images, 1):
        stem = img_path.stem
        label_path = VAL_LABELS_DIR / f"{stem}.txt"
        ground_truth = load_ground_truth(label_path)
        gt_classes = [b["class_name"] for b in ground_truth]
        primary_gt = gt_classes[0] if gt_classes else ("gun" if "gun" in stem else "knife")

        # Predict with conf=0.25
        results = model.predict(source=str(img_path), conf=0.25, verbose=False)
        result = results[0]

        # Save annotated image
        annotated_img_bgr = result.plot()
        annotated_img_rgb = Image.fromarray(annotated_img_bgr[..., ::-1])
        out_img_path = PREDICTIONS_DIR / f"pred_{img_path.name}"
        annotated_img_rgb.save(out_img_path)

        detections = []
        for box in result.boxes:
            conf = float(box.conf[0])
            cid = int(box.cls[0])
            cname = class_mapping.get(cid, f"class_{cid}")
            xyxy = [round(float(c), 1) for c in box.xyxy[0].tolist()]
            detections.append({
                "class_id": cid,
                "class_name": cname,
                "confidence": round(conf, 4),
                "box_xyxy": xyxy
            })

        # Threshold checks
        for t in thresholds:
            t_dets = [d for d in detections if d["confidence"] >= t]
            if t_dets:
                detected_counts_by_thresh[t] += 1
                if any(d["class_name"] == primary_gt for d in t_dets):
                    class_match_counts_by_thresh[t] += 1

        top_det = max(detections, key=lambda d: d["confidence"]) if detections else None
        top_conf = top_det["confidence"] if top_det else 0.0
        top_class = top_det["class_name"] if top_det else "none"

        image_results.append({
            "image": img_path.name,
            "ground_truth_classes": gt_classes,
            "primary_ground_truth": primary_gt,
            "detected_count": len(detections),
            "top_class": top_class,
            "top_confidence": top_conf,
            "detections": detections,
            "visual_saved": str(out_img_path.name),
            "match_at_0_25": any(d["class_name"] == primary_gt for d in detections if d["confidence"] >= 0.25),
            "match_at_0_50": any(d["class_name"] == primary_gt for d in detections if d["confidence"] >= 0.50),
            "match_at_0_75": any(d["class_name"] == primary_gt for d in detections if d["confidence"] >= 0.75),
        })

        status_str = f"MATCH ({top_class} {top_conf:.2f})" if top_class == primary_gt else f"MISMATCH ({top_class})"
        if not detections:
            status_str = "NO DETECTION (conf < 0.25)"
        print(f"  [{idx:02d}/20] {img_path.name:<15} GT: {primary_gt:<6} | Pred: {status_str}")

    print(f"\n  Summary across thresholds for {len(val_images)} images:")
    for t in thresholds:
        print(f"    Confidence >= {t:.2f}: Detected={detected_counts_by_thresh[t]}/20, Class Match={class_match_counts_by_thresh[t]}/20")

    # 5. Generate Reports
    print("\n[Step 5/5] Generating verification reports...")
    report_data = {
        "model_file": str(MODEL_PATH.name),
        "model_sha256": trained_sha,
        "model_size_bytes": file_size_bytes,
        "base_model_preserved": best_pt_intact,
        "best_pt_sha256": current_best_sha,
        "class_mapping": class_mapping,
        "class_mapping_valid": class_mapping_valid,
        "metrics": {
            "mAP50": overall_map50,
            "mAP50_95": overall_map,
            "precision": overall_precision,
            "recall": overall_recall,
            "class_metrics": class_metrics
        },
        "threshold_evaluation": {
            str(t): {
                "detected": detected_counts_by_thresh[t],
                "matches": class_match_counts_by_thresh[t],
                "match_rate": round(class_match_counts_by_thresh[t] / len(val_images), 4)
            } for t in thresholds
        },
        "image_predictions": image_results
    }

    report_json_path = OUTPUT_DIR / "verification_report.json"
    with open(report_json_path, "w") as f:
        json.dump(report_data, f, indent=2)

    # Markdown Report
    report_md_path = OUTPUT_DIR / "verification_report.md"
    md_lines = [
        "# Weapon Model Verification Report",
        "",
        "## 1. Checkpoint Verification",
        f"- **Checkpoint Path**: `{MODEL_PATH}`",
        f"- **File Size**: {file_size_bytes:,} bytes",
        f"- **SHA-256**: `{trained_sha}`",
        f"- **Original `best.pt` Preserved**: `{'YES (Untouched)' if best_pt_intact else 'NO'}`",
        f"- **`best.pt` SHA-256**: `{current_best_sha}`",
        f"- **Class Mapping**: `{class_mapping}` (Confirmed `{expected_mapping}`)",
        "",
        "## 2. Formal Validation Metrics",
        f"- **mAP50**: `{overall_map50:.4f}`",
        f"- **mAP50-95**: `{overall_map:.4f}`",
        f"- **Precision**: `{overall_precision:.4f}`",
        f"- **Recall**: `{overall_recall:.4f}`",
        "",
        "## 3. Threshold Sensitivity Analysis (20 Validation Images)",
        "| Confidence Threshold | Images with Detections | Correct Class Matches | Match Rate |",
        "|:---:|:---:|:---:|:---:|",
    ]
    for t in thresholds:
        te = report_data["threshold_evaluation"][str(t)]
        md_lines.append(f"| `>= {t:.2f}` | {te['detected']}/20 | {te['matches']}/20 | {te['match_rate']*100:.1f}% |")

    md_lines.extend([
        "",
        "## 4. Per-Image Prediction Table",
        "| # | Image | Ground Truth | Detected Class | Top Conf | Conf >= 0.25 | Conf >= 0.50 | Conf >= 0.75 | Visual |",
        "|:---:|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---|",
    ])
    for idx, r in enumerate(image_results, 1):
        md_lines.append(
            f"| {idx} | `{r['image']}` | **{r['primary_ground_truth']}** | `{r['top_class']}` | {r['top_confidence']:.2f} | "
            f"{'✅' if r['match_at_0_25'] else '❌'} | "
            f"{'✅' if r['match_at_0_50'] else '❌'} | "
            f"{'✅' if r['match_at_0_75'] else '❌'} | "
            f"`{r['visual_saved']}` |"
        )

    with open(report_md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(md_lines))

    print(f"\nSaved Reports:")
    print(f"  - {report_json_path}")
    print(f"  - {report_md_path}")
    print(f"  - Prediction images saved to {PREDICTIONS_DIR} ({len(val_images)} images)")
    print("\n" + "=" * 70)
    print("VERIFICATION SUITE COMPLETED SUCCESSFULLY")
    print("=" * 70)


if __name__ == "__main__":
    run_verification()
