from ultralytics import YOLO
import os


class WeaponDetection:
    """
    Weapon Detection model for CampusGuard AI (detects 'gun' and 'knife').

    NOTE: Trained on a small benchmark dataset (60 training, 20 validation images).
    This model should be treated as experimental and does not claim production-grade
    accuracy under all operational CCTV conditions.
    """

    def __init__(self, model_path: str = None, confidence: float = 0.50):
        # Validate confidence threshold
        if not isinstance(confidence, (int, float)) or not (0.0 <= float(confidence) <= 1.0):
            raise ValueError(f"Confidence threshold must be a float between 0.0 and 1.0, got: {confidence}")
        self.confidence = float(confidence)

        # Resolve model path: prefer weapon_detection_trained.pt, fall back to best.pt
        if model_path is None:
            dir_path = os.path.dirname(__file__)
            trained_path = os.path.join(dir_path, "weapon_detection_trained.pt")
            fallback_path = os.path.join(dir_path, "best.pt")

            if os.path.exists(trained_path):
                model_path = trained_path
            elif os.path.exists(fallback_path):
                model_path = fallback_path
            elif os.path.exists("backend/ml_models/weapon_detection_trained.pt"):
                model_path = "backend/ml_models/weapon_detection_trained.pt"
            elif os.path.exists("backend/ml_models/best.pt"):
                model_path = "backend/ml_models/best.pt"
            else:
                model_path = trained_path

        self.model_path = model_path
        self.model = None
        if model_path:
            try:
                self.model = YOLO(model_path)
            except Exception as exc:
                print(f"Weapon model could not be loaded from {model_path}: {exc}")
                self.model = None
        else:
            self.model = None

    @property
    def is_available(self) -> bool:
        return self.model is not None

    def detect(self, frame):
        if self.model is None or frame is None:
            return []

        results = self.model(frame, verbose=False)
        detected_weapons = []

        for result in results:
            if getattr(result, "boxes", None) is None:
                continue
            for box in result.boxes:
                confidence = float(box.conf[0])
                class_id = int(box.cls[0])
                weapon = self.model.names[class_id]

                if weapon in ["gun", "knife"] and confidence >= self.confidence:
                    detected_weapons.append({
                        "weapon": weapon,
                        "confidence": round(confidence, 2)
                    })

        return detected_weapons