import os
import cv2
import mediapipe as mp
from mediapipe.tasks import python
from mediapipe.tasks.python import vision


class FightDetection:
    def __init__(self):
        asset_path = os.path.join(os.path.dirname(__file__), "pose_landmarker_lite.task")
        if not os.path.exists(asset_path):
            asset_path = "backend/ml_models/pose_landmarker_lite.task"

        self.detector = None
        try:
            options = vision.PoseLandmarkerOptions(
                base_options=python.BaseOptions(
                    model_asset_path=asset_path
                ),
                running_mode=vision.RunningMode.IMAGE,
                num_poses=5
            )

            self.detector = vision.PoseLandmarker.create_from_options(
                options
            )
        except Exception:
            self.detector = None

    def detect(self, frame):
        if self.detector is None or frame is None:
            return False

        try:
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

            image = mp.Image(
                image_format=mp.ImageFormat.SRGB,
                data=rgb
            )

            results = self.detector.detect(image)
            poses = results.pose_landmarks

            if len(poses) < 2:
                return False

            centers = []

            for landmarks in poses:
                x = sum(point.x for point in landmarks) / len(landmarks)
                y = sum(point.y for point in landmarks) / len(landmarks)
                centers.append((x, y))

            for i in range(len(centers)):
                for j in range(i + 1, len(centers)):
                    distance = (
                        (centers[i][0] - centers[j][0]) ** 2
                        + (centers[i][1] - centers[j][1]) ** 2
                    ) ** 0.5

                    if distance < 0.25:
                        return True

            return False
        except Exception:
            return False

    def close(self):
        if self.detector is not None:
            try:
                self.detector.close()
            except Exception:
                pass