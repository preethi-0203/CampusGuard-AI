import threading
from typing import Optional
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends, Request, Query
from sqlalchemy.orm import Session
import cv2
import numpy as np
import tempfile
import os
from datetime import datetime, timedelta

from backend.services.ml_service import MLService
from backend.services.loitering_service import LoiteringService
from backend.services.risk_service import create_risk_alert
from backend.config.database import get_db
from backend.services.auth_service import require_role
from backend.database.models.alert import Alert

router = APIRouter()
ml_service = MLService()

ANALYSIS_LOCK = threading.Lock()
CHUNK_SIZE = 1024 * 1024  # 1 MB
MAX_IMAGE_SIZE = 20 * 1024 * 1024  # 20 MB
MAX_VIDEO_SIZE = 100 * 1024 * 1024  # 100 MB


# Analyze an image
@router.post("/camera/analyze")
def analyze_camera(
    request: Request = None,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: dict = Depends(require_role("admin", "security"))
):
    # Check Content-Length first when present
    if request:
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                if int(content_length) > MAX_IMAGE_SIZE:
                    raise HTTPException(
                        status_code=413,
                        detail="Image must be smaller than 20 MB"
                    )
            except (ValueError, TypeError):
                pass

    # Read with file.file in 1 MB chunks (not await file.read())
    chunks = []
    total_bytes = 0
    while True:
        chunk = file.file.read(CHUNK_SIZE)
        if not chunk:
            break
        total_bytes += len(chunk)
        if total_bytes > MAX_IMAGE_SIZE:
            raise HTTPException(
                status_code=413,
                detail="Image must be smaller than 20 MB"
            )
        chunks.append(chunk)

    contents = b"".join(chunks)

    image = cv2.imdecode(
        np.frombuffer(contents, np.uint8),
        cv2.IMREAD_COLOR
    )

    if image is None:
        raise HTTPException(
            status_code=400,
            detail="Invalid image"
        )

    # Hold the lock only while analysing, not while reading the upload
    with ANALYSIS_LOCK:
        detections = ml_service.analyze_frame(image)

    # Note: 2D centroid distance heuristic is an experimental proximity signal, NOT a confirmed fight.
    # Pass fight=False to create_risk_alert to prevent unvalidated proximity from generating confirmed fight alerts.
    fight_proximity_detected = bool(detections.get("fight_detected") or detections.get("fight_proximity"))

    risk = create_risk_alert(
        db=db,
        fall=bool(detections.get("fall_detected")),
        fight=False,
        weapon=bool(detections.get("weapon_detected")),
        detected_weapons=detections.get("detected_weapons"),
        location="Main Campus",
        restricted_entry=bool(detections.get("restricted_entry")),
        restricted_zone=detections.get("restricted_zone"),
        after_hours=detections.get("after_hours", False),
        loitering=False,
        user_id=user.get("user_id") if isinstance(user, dict) else None,
    )

    return {
        **detections,
        "fight_detected": False,  # Proximity alone does not confirm fighting
        "fight_proximity_detected": fight_proximity_detected,
        "experimental_signals": {
            "fight_proximity_detected": fight_proximity_detected,
            "status": "experimental_heuristic_proximity_only",
            "note": "2D centroid distance < 0.25 is an experimental proximity heuristic; unconfirmed as fight."
        },
        "risk": risk,
        "operational_severity": risk.get("operational_severity") if isinstance(risk, dict) else None,
        "operational_score": risk.get("operational_score") if isinstance(risk, dict) else None,
        "alert_id": risk.get("alert_id"),
    }


# Analyze a video for loitering
@router.post("/camera/analyze-video")
def analyze_video(
    request: Request = None,
    file: UploadFile = File(...),
    threshold_seconds: Optional[int] = Query(default=5),
    db: Session = Depends(get_db),
    user: dict = Depends(require_role("admin", "security"))
):
    if threshold_seconds is None:
        threshold = 5
    elif threshold_seconds < 1 or threshold_seconds > 600:
        raise HTTPException(
            status_code=400,
            detail="threshold_seconds must be between 1 and 600"
        )
    else:
        threshold = threshold_seconds

    if not file.filename or not file.filename.lower().endswith(
        (".mp4", ".avi", ".mov", ".mkv")
    ):
        raise HTTPException(
            status_code=400,
            detail="Upload an MP4, AVI, MOV, or MKV video"
        )

    # Check Content-Length first when present
    if request:
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                if int(content_length) > MAX_VIDEO_SIZE:
                    raise HTTPException(
                        status_code=413,
                        detail="Video must be smaller than 100 MB"
                    )
            except (ValueError, TypeError):
                pass

    temp_path = None
    capture = None

    try:
        # Save uploaded video in 1 MB chunks
        with tempfile.NamedTemporaryFile(
            suffix=os.path.splitext(file.filename)[1],
            delete=False
        ) as temp_file:
            temp_path = temp_file.name
            total_bytes = 0
            while True:
                chunk = file.file.read(CHUNK_SIZE)
                if not chunk:
                    break
                total_bytes += len(chunk)
                if total_bytes > MAX_VIDEO_SIZE:
                    raise HTTPException(
                        status_code=413,
                        detail="Video must be smaller than 100 MB"
                    )
                temp_file.write(chunk)

        if total_bytes == 0:
            raise HTTPException(
                status_code=400,
                detail="Empty video"
            )

        capture = cv2.VideoCapture(temp_path)

        if not capture.isOpened():
            raise HTTPException(
                status_code=400,
                detail="Could not open video"
            )

        fps = capture.get(cv2.CAP_PROP_FPS)

        if not fps or fps <= 0:
            raise HTTPException(
                status_code=400,
                detail="Invalid video frame rate"
            )

        # Hold the lock only while analysing (tracker reset and the frame loop)
        with ANALYSIS_LOCK:
            # Reset ByteTrack state for a clean video analysis session
            ml_service.reset_tracker()

            # Initialize loitering detection
            loitering_service = LoiteringService(
                threshold=threshold
            )

            frame_count = capture.get(cv2.CAP_PROP_FRAME_COUNT)
            duration_seconds = (
                round(float(frame_count / fps), 2)
                if (fps and fps > 0 and frame_count and frame_count > 0)
                else None
            )

            frame_index = 0
            total_frames = 0
            loitering_frames = 0
            loitering_ids = set()
            all_person_ids = set()
            max_people_in_frame = 0

            weapon_detected = False
            weapon_frames = 0
            all_detected_weapons = []

            fall_detected = False
            fall_frames = 0

            fight_proximity_detected = False
            fight_proximity_frames = 0

            restricted_entry_detected = False
            restricted_zone_name = None
            restricted_entry_frames = 0
            processing_errors = {}

            # Process every fifth frame
            while True:
                success, frame = capture.read()

                if not success:
                    break

                if frame_index % 5 == 0:
                    elapsed_time = frame_index / fps

                    result = ml_service.analyze_video_frame(
                        frame,
                        loitering_service,
                        elapsed_time
                    )

                    total_frames += 1

                    # Track any detector exceptions rather than silently swallowing as negative detections
                    if result.get("detector_errors"):
                        for det, err in result["detector_errors"].items():
                            if det not in processing_errors:
                                processing_errors[det] = err

                    # Person tracking aggregation
                    all_person_ids.update(result.get("tracked_ids", []))
                    person_count_in_frame = result.get("person_count", 0)
                    if person_count_in_frame > max_people_in_frame:
                        max_people_in_frame = person_count_in_frame

                    # Loitering aggregation
                    if result.get("loitering_detected"):
                        loitering_frames += 1
                        for person in result.get("loitering_people", []):
                            loitering_ids.add(person["person_id"])

                    # Weapon detection aggregation
                    if result.get("weapon_detected"):
                        weapon_detected = True
                        weapon_frames += 1
                        for w in result.get("detected_weapons", []):
                            if w not in all_detected_weapons:
                                all_detected_weapons.append(w)

                    # Fall detection aggregation
                    if result.get("fall_detected"):
                        fall_detected = True
                        fall_frames += 1

                    # Restricted zone aggregation
                    if result.get("restricted_entry"):
                        restricted_entry_detected = True
                        restricted_entry_frames += 1
                        if not restricted_zone_name and result.get("restricted_zone"):
                            restricted_zone_name = result["restricted_zone"]

                    # Fight proximity aggregation (heuristic signal only)
                    if result.get("fight_proximity"):
                        fight_proximity_detected = True
                        fight_proximity_frames += 1

                frame_index += 1

        if total_frames == 0:
            raise HTTPException(
                status_code=400,
                detail="Could not decode frames from video"
            )

        loitering_detected = len(loitering_ids) > 0
        person_count = len(all_person_ids) if all_person_ids else max_people_in_frame

        # After-hours activity check
        after_hours_result = ml_service.after_hours_service.check_after_hours()
        after_hours_detected = bool(
            person_count > 0 and after_hours_result.get("after_hours")
        )

        # Composite video risk assessment and alert persistence
        # Note: Unvalidated 2D centroid distance heuristic is NOT treated as confirmed fight
        risk = create_risk_alert(
            db=db,
            location="Main Campus",
            fall=fall_detected,
            fight=False,
            weapon=weapon_detected,
            detected_weapons=all_detected_weapons,
            restricted_entry=restricted_entry_detected,
            restricted_zone=restricted_zone_name,
            after_hours=after_hours_detected,
            loitering=loitering_detected,
            user_id=user.get("user_id") if isinstance(user, dict) else None,
        )

        detector_statuses = ml_service.get_detector_statuses()
        for det, err in processing_errors.items():
            if err == "unavailable":
                detector_statuses[det] = "unavailable"
            else:
                detector_statuses[det] = f"error: {err}"

        total_vision_detectors = 5
        if not processing_errors:
            analysis_status = "success"
        elif len(processing_errors) >= total_vision_detectors:
            analysis_status = "failed"
        else:
            analysis_status = "partial"

        # Ensure a detector error or unavailable detector is not represented as a verified negative detection
        def resolve_flag(detected: bool, det_key: str, status_key: str = None) -> Optional[bool]:
            if detected:
                return True
            s_key = status_key or det_key
            if detector_statuses.get(s_key) == "unavailable" or processing_errors.get(det_key) == "unavailable":
                return None
            if det_key in processing_errors:
                return None
            return False

        resolved_weapon_detected = resolve_flag(weapon_detected, "weapon_detection")
        resolved_fall_detected = resolve_flag(fall_detected, "fall_detection")
        resolved_restricted_entry = resolve_flag(restricted_entry_detected, "restricted_zone")

        def resolve_analysis(detected: bool, det_key: str, status_key: str = None, detected_label: str = "detected") -> str:
            if detected:
                return detected_label
            s_key = status_key or det_key
            if detector_statuses.get(s_key) == "unavailable" or processing_errors.get(det_key) == "unavailable":
                return "unavailable"
            if det_key in processing_errors:
                return "error"
            return "clear"

        detector_analysis = {
            "weapon_detection": resolve_analysis(weapon_detected, "weapon_detection"),
            "fall_detection": resolve_analysis(fall_detected, "fall_detection"),
            "fight_detection": resolve_analysis(fight_proximity_detected, "fight_detection", detected_label="proximity_flagged"),
            "restricted_zone": resolve_analysis(restricted_entry_detected, "restricted_zone"),
            "loitering_detection": resolve_analysis(loitering_detected, "person_tracking", status_key="loitering_detection"),
        }

        return {
            "message": "Video analysis completed",
            "analysis_status": analysis_status,
            "detector_analysis": detector_analysis,
            "frames_analyzed": total_frames,
            "video_duration_seconds": duration_seconds,
            "person_count": person_count,
            "loitering_detected": loitering_detected,
            "loitering_person_ids": sorted(loitering_ids),
            "loitering_frames": loitering_frames,
            "loitering_threshold_seconds": threshold,
            "weapon_detected": resolved_weapon_detected,
            "detected_weapons": all_detected_weapons,
            "weapon_frames": weapon_frames,
            "fall_detected": resolved_fall_detected,
            "fall_frames": fall_frames,
            "fight_detected": False,
            "fight_proximity_detected": fight_proximity_detected,
            "fight_proximity_frames": fight_proximity_frames,
            "restricted_entry": resolved_restricted_entry,
            "restricted_zone": restricted_zone_name,
            "restricted_entry_frames": restricted_entry_frames,
            "after_hours": after_hours_detected,
            "risk": risk,
            "operational_severity": risk.get("operational_severity") if isinstance(risk, dict) else None,
            "operational_score": risk.get("operational_score") if isinstance(risk, dict) else None,
            "alert_id": risk.get("alert_id") if risk else None,
            "detector_statuses": detector_statuses,
            "processing_errors": processing_errors,
            "experimental_signals": {
                "fight_proximity_detected": fight_proximity_detected,
                "note": (
                    "Proximity heuristic only (pose distance < 0.25). "
                    "Temporal action recognition not implemented; unvalidated proximity "
                    "alone does not trigger critical alerts."
                ),
            },
        }

    finally:
        # Release video capture and remove temporary file safely
        if capture is not None:
            try:
                capture.release()
            except Exception:
                pass

        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass