import os
import sys
from pathlib import Path
import unittest
import numpy as np
import cv2

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

os.environ["DATABASE_URL"] = "sqlite:///:memory:"


class TestModelVerification(unittest.TestCase):
    # 1. Person Model Verification
    def test_01_person_model_class_mapping(self):
        """Verifies person detection model loads and class 0 corresponds to 'person'."""
        from ultralytics import YOLO
        model_path = os.path.join("backend", "ml_models", "person_detection.pt")
        self.assertTrue(os.path.exists(model_path), f"Missing model at {model_path}")

        model = YOLO(model_path)
        self.assertIn(0, model.names)
        self.assertEqual(model.names[0], "person")
        self.assertEqual(len(model.names), 80)

    # 2. Weapon Model Verification
    def test_02_weapon_model_classes_and_threshold(self):
        """Verifies weapon model has gun and knife classes and WeaponDetection applies configurable threshold defaulting to 0.50."""
        from backend.ml_models.weapon_detection import WeaponDetection
        weapon_detector = WeaponDetection()

        self.assertEqual(weapon_detector.confidence, 0.50)
        self.assertTrue(os.path.exists(weapon_detector.model_path))
        self.assertIn("weapon_detection_trained.pt", weapon_detector.model_path)
        self.assertIn(0, weapon_detector.model.names)
        self.assertIn(1, weapon_detector.model.names)
        self.assertEqual(weapon_detector.model.names[0], "gun")
        self.assertEqual(weapon_detector.model.names[1], "knife")
        self.assertEqual(len(weapon_detector.model.names), 2)

        # Configurable confidence
        custom_detector = WeaponDetection(confidence=0.75)
        self.assertEqual(custom_detector.confidence, 0.75)

    # 3. Fall Model Architecture and Output Interpretation
    def test_03_fall_cnn_architecture_and_probability(self):
        """Verifies fall CNN input shape (128,128,3), output shape (None, 1), and output layer activation."""
        import tensorflow as tf
        from backend.ml_models.fall_detection import FallDetection

        detector = FallDetection()
        self.assertIsNotNone(detector.model)
        self.assertEqual(detector.img_size, (128, 128))
        self.assertEqual(detector.model.input_shape, (None, 128, 128, 3))
        self.assertEqual(detector.model.output_shape, (None, 1))

        # First layer is Rescaling and last layer is Dense with sigmoid activation
        self.assertIn("rescaling", detector.model.layers[0].name.lower())
        self.assertEqual(detector.model.layers[-1].activation.__name__, "sigmoid")

        # Monochromatic synthetic frame produces out-of-distribution sigmoid response
        # The training set class order ['fall', 'normal'] maps label 0 to fall and label 1 to normal,
        # so sigmoid output represents P(normal), and P(fall) = 1.0 - sigmoid.
        black_frame = np.zeros((128, 128, 3), dtype=np.uint8)
        is_fall_black = detector.detect(black_frame)
        self.assertTrue(is_fall_black, "Out-of-distribution synthetic zero frame produces fall probability >= 0.5")

    # 4. Fall Model Evaluation on Real Dataset Frames
    def test_04_fall_detection_real_dataset_frames(self):
        """Evaluates fall detector on real normal (ADL) and fall frames from UR Fall Detection Dataset."""
        from backend.ml_models.fall_detection import FallDetection
        detector = FallDetection()

        normal_frame_path = os.path.join("data", "fall", "adl-01-cam0-rgb", "adl-01-cam0-rgb-040.png")
        fall_frame_path = os.path.join("data", "fall", "fall-01-cam0-rgb", "fall-01-cam0-rgb-070.png")

        if os.path.exists(normal_frame_path) and os.path.exists(fall_frame_path):
            normal_frame = cv2.imread(normal_frame_path)
            fall_frame = cv2.imread(fall_frame_path)

            pred_normal = detector.detect(normal_frame)
            pred_fall = detector.detect(fall_frame)

            self.assertFalse(pred_normal, "Expected normal walking frame to not trigger fall detection")
            self.assertTrue(pred_fall, "Expected fallen person frame to trigger fall detection")

    # 5. Risk Model Features, Input Shape, and Class Mapping
    def test_05_risk_model_features_and_predictions(self):
        """Verifies Random Forest feature order, input shape, and prediction mapping."""
        import joblib
        import pandas as pd
        from backend.services.risk_service import risk_service

        model_path = os.path.join("models", "risk_prediction_model.pkl")
        self.assertTrue(os.path.exists(model_path))

        model = joblib.load(model_path)
        expected_features = ["fall", "fight", "weapon", "restricted_entry", "after_hours", "loitering"]
        self.assertEqual(list(model.feature_names_in_), expected_features)
        self.assertEqual(set(model.classes_), {"Low", "Medium", "High"})

        # Baseline: All 0s -> Low
        res_low = risk_service.predict()
        self.assertEqual(res_low["risk_level"], "Low")
        self.assertEqual(res_low["risk_score"], 20)
        self.assertEqual(res_low["confidence"], 1.0)

        # Compound Threat: Fight + Weapon -> High
        res_high = risk_service.predict(fight=True, weapon=True)
        self.assertEqual(res_high["risk_level"], "High")
        self.assertEqual(res_high["risk_score"], 80)
        self.assertEqual(res_high["confidence"], 1.0)

    # 6. Person Detection on Real Dataset Frame
    def test_06_person_detection_real_frame(self):
        """Verifies YOLO person detector identifies walking person in real dataset frame."""
        from backend.services.ml_service import MLService
        ml_service = MLService()

        sample_path = os.path.join("data", "fall", "adl-01-cam0-rgb", "adl-01-cam0-rgb-040.png")
        if os.path.exists(sample_path):
            frame = cv2.imread(sample_path)
            result = ml_service.analyze_frame(frame)
            self.assertGreaterEqual(result["person_count"], 1)
            self.assertGreater(len(result["people"]), 0)
            person = result["people"][0]
            self.assertIn("x1", person)
            self.assertIn("y1", person)
            self.assertIn("x2", person)
            self.assertIn("y2", person)

    # 7. Weapon Detector Clean Frame False-Positive Check
    def test_07_weapon_detector_clean_frame(self):
        """Verifies weapon detector does not fire false alarms on clean everyday frame."""
        from backend.ml_models.weapon_detection import WeaponDetection
        detector = WeaponDetection()

        sample_path = os.path.join("data", "fall", "adl-01-cam0-rgb", "adl-01-cam0-rgb-040.png")
        if os.path.exists(sample_path):
            frame = cv2.imread(sample_path)
            weapons = detector.detect(frame)
            self.assertEqual(weapons, [], "Clean everyday frame should not detect weapons")


if __name__ == "__main__":
    unittest.main()
