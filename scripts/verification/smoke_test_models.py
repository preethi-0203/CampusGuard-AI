import os
import sys
sys.path.insert(0, os.getcwd())
import cv2
import numpy as np

print("=== Smoke Test 1: Person Detection on Real Dataset Frame ===")
from backend.services.ml_service import MLService
ml_service = MLService()

# Find an ADL frame where a person is walking (e.g. adl-01 frame 40)
real_frame_path = os.path.join("data", "fall", "adl-01-cam0-rgb", "adl-01-cam0-rgb-040.png")
if os.path.exists(real_frame_path):
    frame = cv2.imread(real_frame_path)
    print(f"Loaded frame from {real_frame_path}, shape: {frame.shape}")
    analysis = ml_service.analyze_frame(frame)
    print(f"Person count: {analysis['person_count']}")
    print(f"People boxes: {analysis['people']}")
    print(f"Restricted entry: {analysis['restricted_entry']}")
    print(f"Fall detected: {analysis['fall_detected']}")
    print(f"Weapon detected: {analysis['weapon_detected']}")
else:
    print(f"Frame not found at {real_frame_path}")

print("\n=== Smoke Test 2: Fall Detection on Real Normal vs Fall Frames ===")
from backend.ml_models.fall_detection import FallDetection
fall_detector = FallDetection()

# Test on normal walking frame (adl-01)
if os.path.exists(real_frame_path):
    normal_pred = fall_detector.detect(frame)
    print(f"Normal walking frame (adl-01-040) fall detected: {normal_pred}")

# Test on fall frame (fall-01 frame 70 - person fallen on floor)
fall_frame_path = os.path.join("data", "fall", "fall-01-cam0-rgb", "fall-01-cam0-rgb-070.png")
if os.path.exists(fall_frame_path):
    fall_frame = cv2.imread(fall_frame_path)
    fall_pred = fall_detector.detect(fall_frame)
    print(f"Fallen person frame (fall-01-070) fall detected: {fall_pred}")

print("\n=== Smoke Test 3: Weapon Detection Inference Check ===")
from backend.ml_models.weapon_detection import WeaponDetection
weapon_detector = WeaponDetection()
print(f"Weapon detector model names: {weapon_detector.model.names}")
print(f"Weapon detector confidence threshold: {weapon_detector.confidence}")
if os.path.exists(real_frame_path):
    res = weapon_detector.detect(frame)
    print(f"Detection on clean frame (no weapon expected): {res}")
print("Note: Positive weapon detection validation remains pending due to absence of weapon sample images in local repository.")

print("\n=== Smoke Test 4: Risk Prediction Combinations ===")
from backend.services.risk_service import risk_service
test_cases = [
    {"name": "Baseline (All Clear)", "kwargs": {}},
    {"name": "Weapon Only", "kwargs": {"weapon": True}},
    {"name": "Fight Only", "kwargs": {"fight": True}},
    {"name": "Fall Only", "kwargs": {"fall": True}},
    {"name": "Restricted Zone Entry", "kwargs": {"restricted_entry": True}},
    {"name": "Loitering Only", "kwargs": {"loitering": True}},
    {"name": "After Hours Only", "kwargs": {"after_hours": True}},
    {"name": "Compound Threat (Fight + Weapon)", "kwargs": {"fight": True, "weapon": True}},
    {"name": "All Signals Active", "kwargs": {"fall": True, "fight": True, "weapon": True, "restricted_entry": True, "after_hours": True, "loitering": True}},
]

for tc in test_cases:
    result = risk_service.predict(**tc["kwargs"])
    print(f"[{tc['name']}] -> Level: {result['risk_level']}, Score: {result['risk_score']} ({result['risk_score_type']}), Conf: {result.get('confidence')} ({result.get('confidence_type')})")
