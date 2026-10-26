from pathlib import Path
import os
import random
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = PROJECT_ROOT / "data"
OUTPUT_FILE = OUTPUT_DIR / "risk_dataset.csv"

os.makedirs(OUTPUT_DIR, exist_ok=True)

rows = []

for _ in range(2000):
    fall = random.randint(0, 1)
    fight = random.randint(0, 1)
    weapon = random.randint(0, 1)
    restricted_entry = random.randint(0, 1)
    after_hours = random.randint(0, 1)
    loitering = random.randint(0, 1)

    risk_score = (
        fall * 30
        + fight * 40
        + weapon * 50
        + restricted_entry * 50
        + after_hours * 30
        + loitering * 30
    )

    risk_score = min(risk_score, 100)

    if risk_score >= 70:
        risk_level = "High"
    elif risk_score >= 30:
        risk_level = "Medium"
    else:
        risk_level = "Low"

    rows.append({
        "fall": fall,
        "fight": fight,
        "weapon": weapon,
        "restricted_entry": restricted_entry,
        "after_hours": after_hours,
        "loitering": loitering,
        "risk_score": risk_score,
        "risk_level": risk_level
    })

df = pd.DataFrame(rows)

df.to_csv(OUTPUT_FILE, index=False)

print("Risk dataset created successfully.")
print("Total records:", len(df))
print("\nClass distribution:")
print(df["risk_level"].value_counts())

print("\nDataset saved to:")
print(OUTPUT_FILE)