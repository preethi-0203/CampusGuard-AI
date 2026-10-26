"""
Weapon Detection Training Pipeline for CampusGuard AI
Trains YOLO11n on the DaSCI weapon benchmark dataset (data/weapon_dataset/).

Safety requirements strictly enforced:
- Existing backend/ml_models/best.pt is NEVER deleted or overwritten.
- Trained weights are exported to models/weapon_detection_trained.pt
  and backend/ml_models/weapon_detection_trained.pt.
- No modifications are made to database or operational files.
"""

import argparse
import os
import shutil
import sys
from pathlib import Path
from ultralytics import YOLO


def get_project_root() -> Path:
    """Find repository root by looking for marker files."""
    current = Path(__file__).resolve().parent
    for parent in [current] + list(current.parents):
        if (parent / "backend").is_dir() and (parent / "data").is_dir():
            return parent
    return Path.cwd()


def verify_dataset(data_yaml_path: Path) -> dict:
    """Verify that dataset configuration and directories exist."""
    if not data_yaml_path.exists():
        raise FileNotFoundError(f"data.yaml not found at: {data_yaml_path}")

    from ultralytics.data.utils import check_det_dataset
    dataset_info = check_det_dataset(str(data_yaml_path))
    return dataset_info


def parse_args():
    project_root = get_project_root()
    default_data = project_root / "data" / "weapon_dataset" / "data.yaml"
    default_base_model = project_root / "backend" / "ml_models" / "best.pt"

    parser = argparse.ArgumentParser(
        description="Train/Fine-tune YOLO model for CampusGuard AI weapon detection."
    )
    parser.add_argument(
        "--data",
        type=str,
        default=str(default_data),
        help="Path to dataset data.yaml file.",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=str(default_base_model),
        help="Base model checkpoint or architecture (e.g. backend/ml_models/best.pt or yolo11n.pt).",
    )
    parser.add_argument(
        "--epochs",
        type=int,
        default=15,
        help="Number of training epochs (default: 15).",
    )
    parser.add_argument(
        "--batch",
        type=int,
        default=8,
        help="Batch size (default: 8).",
    )
    parser.add_argument(
        "--imgsz",
        type=int,
        default=640,
        help="Input image resolution (default: 640).",
    )
    parser.add_argument(
        "--device",
        type=str,
        default=None,
        help="Device to use ('cpu', '0', etc.). Auto-detects if omitted.",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=0,
        help="Number of dataloader workers (0 recommended for Windows CPU).",
    )
    parser.add_argument(
        "--output-name",
        type=str,
        default="weapon_detection_trained.pt",
        help="Filename for the newly saved trained model (must NOT be best.pt).",
    )
    return parser.parse_args()


def train_pipeline(args):
    project_root = get_project_root()
    data_yaml = Path(args.data).resolve()
    base_model_path = args.model
    output_name = args.output_name

    # STRICT SAFETY CHECK: Never overwrite best.pt
    if output_name.strip().lower() == "best.pt":
        raise ValueError(
            "CRITICAL SAFETY VIOLATION: Output model filename cannot be 'best.pt'. "
            "Existing best.pt must be preserved. Use 'weapon_detection_trained.pt'."
        )

    print("=" * 60)
    print("CAMPUSGUARD AI - WEAPON DETECTION TRAINING PIPELINE")
    print("=" * 60)
    print(f"Project root:       {project_root}")
    print(f"Dataset config:     {data_yaml}")
    print(f"Base model:         {base_model_path}")
    print(f"Epochs:             {args.epochs}")
    print(f"Batch size:         {args.batch}")
    print(f"Image size:         {args.imgsz}")
    print(f"Output model name:  {output_name}")

    # Verify dataset integrity
    print("\n[1/4] Verifying dataset configuration...")
    dataset_info = verify_dataset(data_yaml)
    print(f"  Classes: {dataset_info.get('names')}")
    print(f"  Train path: {dataset_info.get('train')}")
    print(f"  Val path:   {dataset_info.get('val')}")

    # Initialize model
    print(f"\n[2/4] Loading base model ({base_model_path})...")
    model = YOLO(base_model_path)

    # Train
    print(f"\n[3/4] Starting training for {args.epochs} epochs...")
    train_kwargs = {
        "data": str(data_yaml),
        "epochs": args.epochs,
        "batch": args.batch,
        "imgsz": args.imgsz,
        "workers": args.workers,
        "project": str(project_root / "runs" / "detect"),
        "name": "weapon_train",
        "exist_ok": True,
        "plots": True,
    }
    if args.device:
        train_kwargs["device"] = args.device

    train_results = model.train(**train_kwargs)

    # Export & Save model under new filename
    print("\n[4/4] Saving newly trained model safely...")
    trained_weights = Path(train_results.save_dir) / "weights" / "best.pt"
    if not trained_weights.exists():
        trained_weights = Path(train_results.save_dir) / "weights" / "last.pt"

    if not trained_weights.exists():
        raise FileNotFoundError(f"Trained weights not found in {train_results.save_dir}")

    # Target destinations
    dest_models_dir = project_root / "models"
    dest_backend_dir = project_root / "backend" / "ml_models"

    dest_models_dir.mkdir(parents=True, exist_ok=True)
    dest_backend_dir.mkdir(parents=True, exist_ok=True)

    dest_primary = dest_models_dir / output_name
    dest_backend = dest_backend_dir / output_name

    shutil.copy2(trained_weights, dest_primary)
    shutil.copy2(trained_weights, dest_backend)

    print(f"  Successfully copied trained model to:")
    print(f"    - {dest_primary}")
    print(f"    - {dest_backend}")
    print(f"  Existing best.pt remains untouched at {dest_backend_dir / 'best.pt'}")

    # Validation evaluation
    print("\nEvaluating trained model on validation set...")
    val_model = YOLO(str(dest_primary))
    metrics = val_model.val(data=str(data_yaml), split="val", verbose=True)

    print("\n" + "=" * 60)
    print("TRAINING PIPELINE COMPLETE")
    print("=" * 60)
    print(f"mAP50:     {metrics.box.map50:.4f}")
    print(f"mAP50-95:  {metrics.box.map:.4f}")
    print(f"Precision: {metrics.box.mp:.4f}")
    print(f"Recall:    {metrics.box.mr:.4f}")
    print(f"Output checkpoint: {dest_primary}")


if __name__ == "__main__":
    args = parse_args()
    train_pipeline(args)
