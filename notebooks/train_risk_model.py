from pathlib import Path
import os
import pandas as pd
import joblib

from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_FILE = BASE_DIR / "data" / "risk_dataset.csv"
MODEL_DIR = BASE_DIR / "models"
MODEL_FILE = MODEL_DIR / "risk_prediction_model.pkl"

df = pd.read_csv(DATA_FILE)

features = [
    "fall",
    "fight",
    "weapon",
    "restricted_entry",
    "after_hours",
    "loitering"
]

X = df[features]
y = df["risk_level"]

X_train, X_test, y_train, y_test = train_test_split(
    X,
    y,
    test_size=0.2,
    random_state=42,
    stratify=y
)

model = RandomForestClassifier(
    n_estimators=100,
    random_state=42
)

model.fit(X_train, y_train)

y_pred = model.predict(X_test)

accuracy = accuracy_score(y_test, y_pred)

print("Risk Prediction Model Training Complete")
print("Training records:", len(X_train))
print("Testing records:", len(X_test))
print("Accuracy:", round(accuracy * 100, 2), "%")

print("\nClassification Report:")
print(classification_report(y_test, y_pred))

print("Confusion Matrix:")
print(confusion_matrix(y_test, y_pred))

os.makedirs(MODEL_DIR, exist_ok=True)

joblib.dump(model, MODEL_FILE)

print("\nModel saved successfully:")
print(MODEL_FILE)