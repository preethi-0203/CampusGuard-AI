"""
Unit tests for WeaponDetection class:
- Model-path selection (prefer trained model)
- Fallback behavior (to best.pt when trained model missing)
- Confidence validation (0.0 to 1.0 bounds)
- Detection output format and filtering compatibility
- Mock YOLO for fast, camera-independent testing
- Checkpoint integrity verification
"""

import os
import sys
import hashlib
import unittest
from unittest.mock import MagicMock, patch
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend.ml_models.weapon_detection import WeaponDetection


class TestWeaponDetection(unittest.TestCase):
    BEST_PT_SHA256 = "07241a8fc57d0f3fd29231dd72b9f452375745290b2185440de0165590997cb5"

    def test_01_default_initialization_prefers_trained_model(self):
        """When weapon_detection_trained.pt exists, WeaponDetection() must load it by default."""
        detector = WeaponDetection()
        self.assertEqual(detector.confidence, 0.50)
        self.assertTrue(os.path.exists(detector.model_path))
        self.assertIn("weapon_detection_trained.pt", detector.model_path)
        self.assertEqual(detector.model.names[0], "gun")
        self.assertEqual(detector.model.names[1], "knife")

    @patch("backend.ml_models.weapon_detection.YOLO")
    @patch("os.path.exists")
    def test_02_fallback_to_best_pt_when_trained_missing(self, mock_exists, mock_yolo):
        """When weapon_detection_trained.pt is missing, it must fall back to best.pt."""
        def fake_exists(path):
            norm_path = path.replace("\\", "/")
            if "weapon_detection_trained.pt" in norm_path:
                return False
            if "best.pt" in norm_path:
                return True
            return False

        mock_exists.side_effect = fake_exists
        mock_instance = MagicMock()
        mock_instance.names = {0: "gun", 1: "knife"}
        mock_yolo.return_value = mock_instance

        detector = WeaponDetection()
        self.assertIn("best.pt", detector.model_path)
        mock_yolo.assert_called_once()
        called_arg = mock_yolo.call_args[0][0].replace("\\", "/")
        self.assertTrue(called_arg.endswith("best.pt"))

    @patch("backend.ml_models.weapon_detection.YOLO")
    def test_03_explicit_model_path_selection(self, mock_yolo):
        """Explicit model_path parameter overrides auto-selection."""
        mock_instance = MagicMock()
        mock_instance.names = {0: "gun", 1: "knife"}
        mock_yolo.return_value = mock_instance

        custom_path = "custom/path/experimental_weapon.pt"
        detector = WeaponDetection(model_path=custom_path, confidence=0.60)
        self.assertEqual(detector.model_path, custom_path)
        self.assertEqual(detector.confidence, 0.60)
        mock_yolo.assert_called_once_with(custom_path)

    def test_04_confidence_validation_valid_ranges(self):
        """Valid confidence thresholds within [0.0, 1.0] must be accepted."""
        with patch("backend.ml_models.weapon_detection.YOLO"):
            for valid_conf in [0.0, 0.1, 0.5, 0.75, 0.99, 1.0, 0, 1]:
                detector = WeaponDetection(confidence=valid_conf)
                self.assertEqual(detector.confidence, float(valid_conf))

    def test_05_confidence_validation_invalid_ranges_raise_value_error(self):
        """Invalid confidence thresholds (<0, >1, or non-numeric) must raise ValueError."""
        with patch("backend.ml_models.weapon_detection.YOLO"):
            for invalid_conf in [-0.01, -1.0, 1.01, 2.5, "high", None, []]:
                with self.assertRaises(ValueError, msg=f"Should raise ValueError for {invalid_conf}"):
                    WeaponDetection(confidence=invalid_conf)

    @patch("backend.ml_models.weapon_detection.YOLO")
    def test_06_detection_output_format_and_filtering(self, mock_yolo):
        """Verifies output format matches [{'weapon': ..., 'confidence': ...}] and applies threshold."""
        mock_instance = MagicMock()
        mock_instance.names = {0: "gun", 1: "knife", 2: "cellphone"}
        mock_yolo.return_value = mock_instance

        # Simulate 3 boxes:
        # Box 1: gun with conf 0.82 (>= 0.50) -> KEEP
        # Box 2: knife with conf 0.35 (< 0.50) -> FILTER OUT
        # Box 3: cellphone with conf 0.95 (not gun/knife) -> FILTER OUT
        box1 = MagicMock()
        box1.conf = [0.82]
        box1.cls = [0]

        box2 = MagicMock()
        box2.conf = [0.35]
        box2.cls = [1]

        box3 = MagicMock()
        box3.conf = [0.95]
        box3.cls = [2]

        result = MagicMock()
        result.boxes = [box1, box2, box3]
        mock_instance.return_value = [result]

        detector = WeaponDetection(confidence=0.50)
        fake_frame = MagicMock()
        detections = detector.detect(fake_frame)

        self.assertEqual(len(detections), 1)
        self.assertEqual(detections[0], {"weapon": "gun", "confidence": 0.82})

    @patch("backend.ml_models.weapon_detection.YOLO")
    def test_07_custom_threshold_detects_lower_confidence(self, mock_yolo):
        """Configuring lower threshold (e.g. 0.30) includes weapons that meet that threshold."""
        mock_instance = MagicMock()
        mock_instance.names = {0: "gun", 1: "knife"}
        mock_yolo.return_value = mock_instance

        box = MagicMock()
        box.conf = [0.38]
        box.cls = [1]

        result = MagicMock()
        result.boxes = [box]
        mock_instance.return_value = [result]

        detector = WeaponDetection(confidence=0.30)
        fake_frame = MagicMock()
        detections = detector.detect(fake_frame)

        self.assertEqual(len(detections), 1)
        self.assertEqual(detections[0], {"weapon": "knife", "confidence": 0.38})

    @patch("backend.ml_models.weapon_detection.YOLO")
    def test_08_detect_none_frame_safe_fallback(self, mock_yolo):
        """detect(None) must return empty list without crashing."""
        detector = WeaponDetection()
        self.assertEqual(detector.detect(None), [])

    @patch("backend.ml_models.weapon_detection.YOLO")
    def test_09_detect_empty_boxes_safe_handling(self, mock_yolo):
        """detect() with empty results or boxes=None must return empty list."""
        mock_instance = MagicMock()
        mock_yolo.return_value = mock_instance
        result = MagicMock()
        result.boxes = None
        mock_instance.return_value = [result]

        detector = WeaponDetection()
        self.assertEqual(detector.detect(MagicMock()), [])

    def test_10_original_best_pt_checkpoint_remains_untouched(self):
        """Verifies backend/ml_models/best.pt has not been modified or overwritten."""
        best_pt_path = ROOT_DIR / "backend" / "ml_models" / "best.pt"
        self.assertTrue(best_pt_path.exists(), "best.pt must exist")
        h = hashlib.sha256()
        with open(best_pt_path, "rb") as f:
            while chunk := f.read(8192):
                h.update(chunk)
        self.assertEqual(h.hexdigest(), self.BEST_PT_SHA256, "best.pt SHA-256 must match original")


if __name__ == "__main__":
    unittest.main()
