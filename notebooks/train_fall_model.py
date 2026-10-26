from pathlib import Path
import os
import numpy as np
import tensorflow as tf
from tensorflow.keras import layers, models
from sklearn.metrics import classification_report, confusion_matrix
import matplotlib.pyplot as plt

# Paths
PROJECT_ROOT = Path(__file__).resolve().parent.parent
BASE_DIR = PROJECT_ROOT / "data" / "fall_dataset"
TRAIN_DIR = str(BASE_DIR / "train")
TEST_DIR = str(BASE_DIR / "test")

# Settings
IMG_SIZE = (128, 128)
BATCH_SIZE = 16
EPOCHS = 10

# Load training data
train_data = tf.keras.utils.image_dataset_from_directory(
    TRAIN_DIR,
    image_size=IMG_SIZE,
    batch_size=BATCH_SIZE,
    shuffle=True,
    seed=42
)

# Load testing data
test_data = tf.keras.utils.image_dataset_from_directory(
    TEST_DIR,
    image_size=IMG_SIZE,
    batch_size=BATCH_SIZE,
    shuffle=False
)

class_names = train_data.class_names
print("Classes:", class_names)

# Normalize images
normalization = layers.Rescaling(1.0 / 255)

# CNN model
model = models.Sequential([
    normalization,

    layers.Conv2D(32, (3, 3), activation="relu"),
    layers.MaxPooling2D(),

    layers.Conv2D(64, (3, 3), activation="relu"),
    layers.MaxPooling2D(),

    layers.Conv2D(128, (3, 3), activation="relu"),
    layers.MaxPooling2D(),

    layers.Flatten(),
    layers.Dense(128, activation="relu"),
    layers.Dropout(0.5),
    layers.Dense(1, activation="sigmoid")
])

model.compile(
    optimizer="adam",
    loss="binary_crossentropy",
    metrics=["accuracy"]
)

model.summary()

# Train
history = model.fit(
    train_data,
    validation_data=test_data,
    epochs=EPOCHS
)

# Evaluate
loss, accuracy = model.evaluate(test_data)

print("\nTest Loss:", round(loss, 4))
print("Test Accuracy:", round(accuracy * 100, 2), "%")

# Predictions
y_true = []
y_pred = []

for images, labels in test_data:
    predictions = model.predict(images, verbose=0)

    y_true.extend(labels.numpy())
    y_pred.extend((predictions.ravel() >= 0.5).astype(int))

print("\nClassification Report:")
print(classification_report(
    y_true,
    y_pred,
    target_names=class_names
))

cm = confusion_matrix(y_true, y_pred)

print("Confusion Matrix:")
print(cm)

# Create results folder
RESULTS_DIR = str(PROJECT_ROOT / "docs" / "ml_results")
os.makedirs(RESULTS_DIR, exist_ok=True)

# -----------------------------
# Accuracy Graph
# -----------------------------
plt.figure(figsize=(8, 5))

plt.plot(
    history.history["accuracy"],
    label="Training Accuracy"
)

plt.plot(
    history.history["val_accuracy"],
    label="Validation Accuracy"
)

plt.xlabel("Epoch")
plt.ylabel("Accuracy")
plt.title("Fall Detection CNN - Accuracy")
plt.legend()
plt.grid(True)

plt.savefig(
    os.path.join(RESULTS_DIR, "accuracy_graph.png"),
    dpi=300,
    bbox_inches="tight"
)

plt.close()

# -----------------------------
# Loss Graph
# -----------------------------
plt.figure(figsize=(8, 5))

plt.plot(
    history.history["loss"],
    label="Training Loss"
)

plt.plot(
    history.history["val_loss"],
    label="Validation Loss"
)

plt.xlabel("Epoch")
plt.ylabel("Loss")
plt.title("Fall Detection CNN - Loss")
plt.legend()
plt.grid(True)

plt.savefig(
    os.path.join(RESULTS_DIR, "loss_graph.png"),
    dpi=300,
    bbox_inches="tight"
)

plt.close()

# -----------------------------
# Confusion Matrix
# -----------------------------
plt.figure(figsize=(6, 5))

plt.imshow(cm)

plt.title("Fall Detection CNN - Confusion Matrix")
plt.xlabel("Predicted Label")
plt.ylabel("True Label")

plt.xticks(
    range(len(class_names)),
    class_names
)

plt.yticks(
    range(len(class_names)),
    class_names
)

for i in range(len(class_names)):
    for j in range(len(class_names)):
        plt.text(
            j,
            i,
            cm[i, j],
            ha="center",
            va="center"
        )

plt.colorbar()

plt.savefig(
    os.path.join(RESULTS_DIR, "confusion_matrix.png"),
    dpi=300,
    bbox_inches="tight"
)

plt.close()

print("\nGraphs and confusion matrix saved successfully.")

# -----------------------------
# Save Model
# -----------------------------
MODEL_DIR = str(PROJECT_ROOT / "models")
os.makedirs(MODEL_DIR, exist_ok=True)

model.save(
    os.path.join(
        MODEL_DIR,
        "fall_detection_cnn.keras"
    )
)

print("Model saved successfully.")