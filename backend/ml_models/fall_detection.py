import os
import cv2
import numpy as np


class FallDetection:
    """Fall detector using the trained CNN when available.

    If the optional CNN file is absent, the detector safely returns False
    instead of preventing the backend from starting.
    """

    def __init__(self):
        self.model = None
        self.img_size = (128, 128)
        candidates = [
            os.path.join("models", "fall_detection_cnn.keras"),
            os.path.join(os.path.dirname(__file__), "fall_detection_cnn.keras"),
        ]
        for path in candidates:
            if os.path.exists(path):
                try:
                    import tensorflow as tf
                    self.model = tf.keras.models.load_model(path)
                    print("Fall Detection CNN loaded successfully.")
                    break
                except Exception as exc:
                    print(f"Fall CNN could not be loaded: {exc}")
        if self.model is None:
            print("Fall Detection CNN not found; fall detection fallback is disabled.")

    def detect(self, frame, timestamp=0):
        if self.model is None or frame is None:
            return False

        image = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        image = cv2.resize(image, self.img_size)
        # Note: The loaded Keras model contains an internal layers.Rescaling(1.0/255) as Layer 0.
        # Passing [0, 255] float32 avoids double normalization.
        image = image.astype(np.float32)
        image = np.expand_dims(image, axis=0)
        prediction = float(self.model.predict(image, verbose=0)[0][0])
        # In the training dataset classes ['fall', 'normal'], label 0 is fall and label 1 is normal.
        # The sigmoid output represents P(normal), so P(fall) = 1.0 - prediction.
        fall_probability = 1.0 - prediction
        return fall_probability >= 0.5
