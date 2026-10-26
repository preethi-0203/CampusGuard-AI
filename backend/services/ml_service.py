from ultralytics import YOLO
import os

from backend.ml_models.fall_detection import FallDetection
from backend.ml_models.fight_detection import FightDetection
from backend.ml_models.weapon_detection import WeaponDetection
from backend.services.restricted_zone_service import RestrictedZoneService
from backend.services.after_hours_service import AfterHoursService


class MLService:
    def __init__(self):
        self.fall_detector = FallDetection()
        self.fight_detector = FightDetection()
        self.weapon_detector = WeaponDetection()

        person_model_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "ml_models",
            "person_detection.pt"
        )
        if not os.path.exists(person_model_path):
            person_model_path = "backend/ml_models/person_detection.pt"

        self.person_model = None
        if os.path.exists(person_model_path):
            try:
                self.person_model = YOLO(person_model_path)
            except Exception as exc:
                print(f"Person detection model could not be loaded: {exc}")
                self.person_model = None
        else:
            print(f"Person detection model not found at {person_model_path}")

        self.zone_service = RestrictedZoneService()
        self.after_hours_service = AfterHoursService()

    def test_person_detection(self, frame):
        if self.person_model is None or frame is None:
            return []

        results = self.person_model.predict(
            source=frame,
            conf=0.1,
            verbose=False
        )

        for result in results:
            if result.boxes is not None:
                print(
                    "Detected classes:",
                    result.boxes.cls.cpu().numpy()
                )
                print(
                    "Detected count:",
                    len(result.boxes)
                )

        return results

    def analyze_frame(self, frame):
        if (
            frame is None
            or not hasattr(frame, "shape")
            or len(frame.shape) < 2
            or frame.shape[0] <= 0
            or frame.shape[1] <= 0
            or (hasattr(frame, "size") and frame.size == 0)
        ):
            after_hours_result = self.after_hours_service.check_after_hours()
            return {
                "fall_detected": False,
                "fight_detected": False,
                "weapon_detected": False,
                "detected_weapons": [],
                "person_count": 0,
                "people": [],
                "restricted_entry": False,
                "restricted_zone": None,
                "after_hours": False,
                "after_hours_message": after_hours_result.get("message", "Within campus hours"),
                "detector_errors": {},
            }

        frame_height, frame_width = int(frame.shape[0]), int(frame.shape[1])

        detector_errors = {}

        fall = False
        fall_available = self.fall_detector is not None and getattr(self.fall_detector, "model", None) is not None
        if fall_available:
            try:
                fall = self.fall_detector.detect(frame, 0)
            except Exception as exc:
                detector_errors["fall_detection"] = str(exc)
                print(f"Fall detection failed on image frame: {exc}")
        else:
            detector_errors["fall_detection"] = "unavailable"

        fight = False
        fight_available = self.fight_detector is not None and getattr(self.fight_detector, "detector", None) is not None
        if fight_available:
            try:
                fight = self.fight_detector.detect(frame)
            except Exception as exc:
                detector_errors["fight_detection"] = str(exc)
                print(f"Fight detection failed on image frame: {exc}")
        else:
            detector_errors["fight_detection"] = "unavailable"

        weapons = []
        weapon_available = self.weapon_detector is not None and getattr(self.weapon_detector, "model", None) is not None
        if weapon_available:
            try:
                weapons = self.weapon_detector.detect(frame)
            except Exception as exc:
                detector_errors["weapon_detection"] = str(exc)
                print(f"Weapon detection failed on image frame: {exc}")
        else:
            detector_errors["weapon_detection"] = "unavailable"

        people = []
        restricted_entry = False
        restricted_zone = None
        person_available = self.person_model is not None
        if person_available:
            try:
                results = self.person_model.predict(
                    source=frame,
                    classes=[0],
                    conf=0.5,
                    verbose=False
                )

                for result in results:
                    if result.boxes is None:
                        continue

                    for box in result.boxes.xyxy.cpu().numpy():
                        x1, y1, x2, y2 = map(int, box)

                        x = (x1 + x2) // 2
                        y = y2

                        people.append({
                            "x1": x1,
                            "y1": y1,
                            "x2": x2,
                            "y2": y2
                        })

                        zone_result = self.zone_service.check_person(
                            x, y, frame_width=frame_width, frame_height=frame_height
                        )

                        if zone_result.get("restricted_entry"):
                            restricted_entry = True
                            restricted_zone = zone_result.get("zone")
            except Exception as exc:
                detector_errors["person_detection"] = str(exc)
        else:
            detector_errors["person_detection"] = "unavailable"
            detector_errors["restricted_zone"] = "unavailable"

        after_hours_result = (
            self.after_hours_service.check_after_hours()
        )

        resolved_weapon_detected = True if weapons else (None if not weapon_available or "weapon_detection" in detector_errors else False)
        resolved_fall_detected = True if fall else (None if not fall_available or "fall_detection" in detector_errors else False)
        resolved_restricted_entry = True if restricted_entry else (None if not person_available or "restricted_zone" in detector_errors else False)

        return {
            "fall_detected": resolved_fall_detected,
            "fight_detected": bool(fight),
            "fight_proximity": bool(fight),
            "weapon_detected": resolved_weapon_detected,
            "detected_weapons": weapons,
            "person_count": len(people),
            "people": people,
            "restricted_entry": resolved_restricted_entry,
            "restricted_zone": restricted_zone,
            "after_hours": (
                len(people) > 0
                and after_hours_result["after_hours"]
            ),
            "after_hours_message": after_hours_result["message"],
            "detector_errors": detector_errors,
        }

    def analyze_video_frame(
        self, frame, loitering_service, elapsed_time
    ):
        if (
            frame is None
            or not hasattr(frame, "shape")
            or len(frame.shape) < 2
            or frame.shape[0] <= 0
            or frame.shape[1] <= 0
            or (hasattr(frame, "size") and frame.size == 0)
        ):
            return {
                "person_count": 0,
                "tracked_ids": [],
                "loitering_detected": False,
                "loitering_people": [],
                "weapon_detected": False,
                "detected_weapons": [],
                "fall_detected": False,
                "fight_proximity": False,
                "restricted_entry": False,
                "restricted_zone": None,
                "detector_errors": {"frame": "Invalid or empty video frame"},
            }

        frame_height, frame_width = int(frame.shape[0]), int(frame.shape[1])
        detector_errors = {}
        loitering_people = []
        person_count = 0
        tracked_ids = []
        restricted_entry = False
        restricted_zone = None

        person_available = self.person_model is not None
        if person_available:
            try:
                results = self.person_model.track(
                    source=frame,
                    classes=[0],
                    conf=0.1,
                    persist=True,
                    tracker="bytetrack.yaml",
                    verbose=False
                )

                for result in results:
                    if result.boxes is None:
                        continue

                    if result.boxes.id is None:
                        continue

                    boxes = result.boxes.xyxy.cpu().numpy()
                    track_ids = (
                        result.boxes.id.cpu().numpy().astype(int)
                    )
                    tracked_ids.extend([int(pid) for pid in track_ids])

                    for box, person_id in zip(boxes, track_ids):
                        x1, y1, x2, y2 = map(int, box)

                        x = (x1 + x2) // 2
                        y = y2
                        person_count += 1

                        is_loitering = loitering_service.check_person(
                            int(person_id),
                            x,
                            y,
                            elapsed_time
                        )

                        if is_loitering:
                            loitering_people.append({
                                "person_id": int(person_id),
                                "x1": x1,
                                "y1": y1,
                                "x2": x2,
                                "y2": y2,
                                "loitering": True
                            })

                        # Check restricted zone for each tracked person
                        zone_result = self.zone_service.check_person(
                            x, y, frame_width=frame_width, frame_height=frame_height
                        )
                        if zone_result.get("restricted_entry"):
                            restricted_entry = True
                            restricted_zone = zone_result.get("zone")
            except Exception as exc:
                detector_errors["person_tracking"] = str(exc)
        else:
            detector_errors["person_tracking"] = "unavailable"
            detector_errors["restricted_zone"] = "unavailable"

        # Weapon detection on video frame
        weapons = []
        weapon_available = self.weapon_detector is not None and getattr(self.weapon_detector, "model", None) is not None
        if weapon_available:
            try:
                weapons = self.weapon_detector.detect(frame)
            except Exception as exc:
                detector_errors["weapon_detection"] = str(exc)
                print(f"Weapon detection failed on video frame: {exc}")
        else:
            detector_errors["weapon_detection"] = "unavailable"

        # Fall detection on video frame
        fall = False
        fall_available = self.fall_detector is not None and getattr(self.fall_detector, "model", None) is not None
        if fall_available:
            try:
                fall = self.fall_detector.detect(frame, elapsed_time)
            except Exception as exc:
                detector_errors["fall_detection"] = str(exc)
                print(f"Fall detection failed on video frame: {exc}")
        else:
            detector_errors["fall_detection"] = "unavailable"

        # Fight detection (2D centroid proximity heuristic) on video frame
        fight_proximity = False
        fight_available = self.fight_detector is not None and getattr(self.fight_detector, "detector", None) is not None
        if fight_available:
            try:
                fight_proximity = self.fight_detector.detect(frame)
            except Exception as exc:
                detector_errors["fight_detection"] = str(exc)
                print(f"Fight detection failed on video frame: {exc}")
        else:
            detector_errors["fight_detection"] = "unavailable"

        resolved_weapon_detected = True if weapons else (None if not weapon_available or "weapon_detection" in detector_errors else False)
        resolved_fall_detected = True if fall else (None if not fall_available or "fall_detection" in detector_errors else False)

        return {
            "person_count": person_count,
            "tracked_ids": tracked_ids,
            "loitering_detected": len(loitering_people) > 0,
            "loitering_people": loitering_people,
            "weapon_detected": resolved_weapon_detected,
            "detected_weapons": weapons,
            "fall_detected": resolved_fall_detected,
            "fight_proximity": bool(fight_proximity),
            "restricted_entry": restricted_entry,
            "restricted_zone": restricted_zone,
            "detector_errors": detector_errors,
        }

    def get_detector_statuses(self):
        person_active = self.person_model is not None
        weapon_active = (self.weapon_detector is not None and getattr(self.weapon_detector, "model", None) is not None)
        fall_active = (self.fall_detector is not None and getattr(self.fall_detector, "model", None) is not None)
        fight_active = (self.fight_detector is not None and getattr(self.fight_detector, "detector", None) is not None)

        return {
            "person_detection": "active" if person_active else "unavailable",
            "weapon_detection": "active" if weapon_active else "unavailable",
            "fall_detection": "active" if fall_active else "unavailable",
            "fight_detection": "experimental_heuristic_proximity_only" if fight_active else "unavailable",
            "loitering_detection": "active" if person_active else "unavailable",
            "restricted_zone": "active" if person_active else "unavailable",
        }

    def reset_tracker(self):
        """Reset ByteTrack tracker state to prevent track leaks between video analyses."""
        try:
            if hasattr(self, "person_model") and self.person_model is not None:
                predictor = getattr(self.person_model, "predictor", None)
                if predictor is not None and hasattr(predictor, "trackers"):
                    if predictor.trackers:
                        for tracker in predictor.trackers:
                            if hasattr(tracker, "reset"):
                                tracker.reset()
                    delattr(predictor, "trackers")
        except Exception as exc:
            print(f"Warning: Failed to reset tracker state: {exc}")