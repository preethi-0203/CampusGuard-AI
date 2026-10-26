from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Request
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timedelta
import os
import uuid
import re

from backend.config.database import get_db
from backend.database.models.user import User
from backend.database.models.alert import Alert
from backend.database.models.incident import Incident
from backend.database.models.incident_log import IncidentLog
from backend.services.auth_service import require_role, get_current_user
from backend.services.nlp_service import nlp_service

UPLOAD_DIR = os.path.abspath(
    os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data", "uploads")
)

ALLOWED_ATTACHMENT_EXTENSIONS = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".pdf": "application/pdf",
}

router = APIRouter()


class IncidentRequest(BaseModel):
    incident_type: str
    location: str
    description: str
    attachment: Optional[str] = None


class AlertAssignRequest(BaseModel):
    assigned_to: Optional[int] = None


class SOSRequest(BaseModel):
    location: Optional[str] = None
    description: Optional[str] = None


# -------------------------
# ALERTS
# -------------------------

@router.get("/alerts")
def get_alerts(
    db: Session = Depends(get_db),
    user: dict = Depends(require_role("admin", "security"))
):
    return db.query(Alert).order_by(Alert.id.desc()).all()


@router.patch("/alerts/{alert_id}/acknowledge")
def acknowledge_alert(
    alert_id: int,
    db: Session = Depends(get_db),
    user: dict = Depends(require_role("admin", "security"))
):
    alert = db.query(Alert).filter(Alert.id == alert_id).first()

    if not alert:
        raise HTTPException(
            status_code=404,
            detail="Alert not found"
        )

    if alert.status == "resolved":
        raise HTTPException(
            status_code=400,
            detail="Cannot acknowledge a resolved alert"
        )

    alert.status = "acknowledged"
    if not alert.assigned_to:
        alert.assigned_to = user.get("user_id")

    db.commit()
    db.refresh(alert)

    return {
        "message": "Alert acknowledged successfully",
        "alert": alert
    }


@router.patch("/alerts/{alert_id}/resolve")
def resolve_alert(
    alert_id: int,
    db: Session = Depends(get_db),
    user: dict = Depends(require_role("admin", "security"))
):
    alert = db.query(Alert).filter(Alert.id == alert_id).first()

    if not alert:
        raise HTTPException(
            status_code=404,
            detail="Alert not found"
        )

    if alert.status == "resolved":
        raise HTTPException(
            status_code=400,
            detail="Alert is already resolved"
        )

    alert.status = "resolved"

    db.commit()
    db.refresh(alert)

    return {
        "message": "Alert resolved successfully",
        "alert": alert
    }


@router.patch("/alerts/{alert_id}/assign")
def assign_alert(
    alert_id: int,
    data: Optional[AlertAssignRequest] = None,
    db: Session = Depends(get_db),
    user: dict = Depends(require_role("admin", "security"))
):
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")

    if data and data.assigned_to is not None:
        target_user = db.query(User).filter(User.id == data.assigned_to).first()
        if not target_user:
            raise HTTPException(status_code=404, detail="Assigned user not found")
        if target_user.role not in ("security", "admin"):
            raise HTTPException(
                status_code=400,
                detail="Alerts can only be assigned to security or admin users"
            )
        officer_id = target_user.id
    else:
        officer_id = user.get("user_id")

    alert.assigned_to = officer_id

    db.commit()
    db.refresh(alert)

    return {
        "message": "Alert assigned successfully",
        "alert": alert,
        "assigned_to": officer_id
    }


@router.patch("/alerts/{alert_id}/escalate")
def escalate_alert(
    alert_id: int,
    db: Session = Depends(get_db),
    user: dict = Depends(require_role("admin", "security"))
):
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")

    if alert.status == "resolved":
        raise HTTPException(status_code=400, detail="Cannot escalate a resolved alert")

    alert.escalated = True
    alert.status = "escalated"
    alert.severity = "critical"

    db.commit()
    db.refresh(alert)

    return {
        "message": "Alert escalated to critical status",
        "alert": alert
    }


@router.post("/alerts/escalate-unacknowledged")
def escalate_unacknowledged_alerts(
    timeout_minutes: int = 5,
    db: Session = Depends(get_db),
    user: dict = Depends(require_role("admin", "security"))
):
    cutoff = datetime.utcnow() - timedelta(minutes=timeout_minutes)
    pending_alerts = db.query(Alert).filter(
        Alert.status == "active",
        Alert.created_at <= cutoff,
        Alert.escalated == False  # noqa: E712
    ).all()

    escalated_count = 0
    for alert in pending_alerts:
        alert.escalated = True
        alert.severity = "critical"
        escalated_count += 1

    db.commit()

    return {
        "message": f"Escalated {escalated_count} unacknowledged alert(s)",
        "escalated_count": escalated_count,
        "timeout_minutes": timeout_minutes
    }


class PromoteAlertRequest(BaseModel):
    notes: Optional[str] = None
    incident_type: Optional[str] = None


@router.post("/alerts/{alert_id}/promote-to-incident")
@router.post("/alerts/{alert_id}/promote")
def promote_alert_to_incident(
    alert_id: int,
    data: Optional[PromoteAlertRequest] = None,
    db: Session = Depends(get_db),
    user: dict = Depends(require_role("admin", "security"))
):
    # 1. Validate alert existence
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if not alert:
        raise HTTPException(
            status_code=404,
            detail=f"Alert #{alert_id} not found"
        )

    # 2. Prevent duplicate promotions of the same alert
    existing_incident = db.query(Incident).filter(Incident.alert_id == alert_id).first()
    if existing_incident:
        return {
            "message": f"Alert #{alert_id} has already been promoted to Incident #{existing_incident.id}",
            "incident_id": existing_incident.id,
            "alert_id": alert_id,
            "status": existing_incident.status,
            "is_duplicate": True,
            "incident": {
                "id": existing_incident.id,
                "alert_id": existing_incident.alert_id,
                "incident_type": existing_incident.incident_type,
                "location": existing_incident.location,
                "description": existing_incident.description,
                "status": existing_incident.status,
                "nlp_category": existing_incident.nlp_category,
                "nlp_urgency": existing_incident.nlp_urgency,
                "created_at": existing_incident.created_at,
            }
        }

    # 3. Reuse alert fields and analyze with NLP
    inc_type = (data.incident_type.strip() if (data and data.incident_type and data.incident_type.strip()) else alert.alert_type)
    desc = alert.description or f"CCTV Alert #{alert.id} ({alert.alert_type}) reported at {alert.location}"
    if data and data.notes and data.notes.strip():
        desc = f"{desc}\nOfficer Notes: {data.notes.strip()}"

    nlp_result = nlp_service.analyze_report(desc, inc_type)

    # 4. Map severity to NLP urgency
    raw_urgency = nlp_result.get("urgency", "Normal")
    if (alert.severity or "").lower() == "critical" or (raw_urgency or "").lower() == "high":
        urgency = "High"
    else:
        urgency = "Normal"

    officer_id = user.get("user_id")

    incident = Incident(
        alert_id=alert.id,
        user_id=officer_id,
        incident_type=inc_type,
        location=alert.location,
        description=desc,
        nlp_category=nlp_result.get("category", "General Security"),
        nlp_urgency=urgency,
        attachment=None,
        status="acknowledged" if alert.status in ("acknowledged", "escalated") else "submitted"
    )

    db.add(incident)
    db.commit()
    db.refresh(incident)

    # 5. Record chronological audit trail in incident_logs
    log_promoted = IncidentLog(
        incident_id=incident.id,
        action="promoted_from_cctv",
        details=f"Promoted from CCTV Alert #{alert.id} ({alert.alert_type}, severity: {alert.severity}) by officer #{officer_id}",
        performed_by=officer_id
    )
    log_nlp = IncidentLog(
        incident_id=incident.id,
        action="nlp_analyzed",
        details=f"Classified as {incident.nlp_category} with {incident.nlp_urgency} urgency",
        performed_by=None
    )
    db.add(log_promoted)
    db.add(log_nlp)

    # 6. Acknowledge and assign alert if currently active
    if alert.status == "active":
        alert.status = "acknowledged"
    if not alert.assigned_to and officer_id:
        alert.assigned_to = officer_id

    db.commit()
    db.refresh(alert)

    return {
        "message": f"Alert #{alert.id} successfully promoted to Incident #{incident.id}",
        "incident_id": incident.id,
        "alert_id": alert.id,
        "status": incident.status,
        "is_duplicate": False,
        "incident": {
            "id": incident.id,
            "alert_id": incident.alert_id,
            "incident_type": incident.incident_type,
            "location": incident.location,
            "description": incident.description,
            "status": incident.status,
            "nlp_category": incident.nlp_category,
            "nlp_urgency": incident.nlp_urgency,
            "created_at": incident.created_at,
        }
    }


# -------------------------
# INCIDENTS
# -------------------------

@router.get("/uploads/{filename:path}")
def get_uploaded_attachment(
    filename: str,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user)
):
    if (
        not filename
        or os.path.basename(filename) != filename
        or ".." in filename
        or "/" in filename
        or "\\" in filename
    ):
        raise HTTPException(status_code=404, detail="File not found")

    ext = os.path.splitext(filename)[1].lower()
    if ext not in ALLOWED_ATTACHMENT_EXTENSIONS:
        raise HTTPException(status_code=404, detail="File not found")

    file_path = os.path.abspath(os.path.join(UPLOAD_DIR, filename))
    if not file_path.startswith(UPLOAD_DIR + os.sep) and file_path != UPLOAD_DIR:
        raise HTTPException(status_code=404, detail="File not found")

    if not os.path.isfile(file_path):
        raise HTTPException(status_code=404, detail="File not found")

    # Evidence authorization:
    # Admins and security officers can view any uploaded evidence.
    # Students can only view evidence attached to their own incidents.
    user_role = user.get("role") if isinstance(user, dict) else None
    if user_role == "student":
        attachment_path = f"/uploads/{filename}"
        incident = db.query(Incident).filter(Incident.attachment == attachment_path).first()
        if incident and incident.user_id != user.get("user_id"):
            raise HTTPException(
                status_code=403,
                detail="Access denied: You are not authorized to view evidence for this incident"
            )

    media_type = ALLOWED_ATTACHMENT_EXTENSIONS[ext]
    return FileResponse(file_path, media_type=media_type)


@router.post("/incidents/upload")
def upload_incident_attachment(
    file: UploadFile = File(...),
    request: Request = None,
    user: dict = Depends(require_role("admin", "security", "student"))
):
    allowed_exts = set(ALLOWED_ATTACHMENT_EXTENSIONS.keys())
    raw_filename = os.path.basename(file.filename or "upload")
    ext = os.path.splitext(raw_filename)[1].lower()
    if ext not in allowed_exts:
        raise HTTPException(status_code=400, detail="Allowed attachment formats: JPG, PNG, WEBP, PDF")

    max_size = 10 * 1024 * 1024  # 10 MB

    if request:
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                if int(content_length) > max_size:
                    raise HTTPException(status_code=413, detail="File size exceeds maximum allowed limit (10 MB)")
            except (ValueError, TypeError):
                pass

    os.makedirs(UPLOAD_DIR, exist_ok=True)

    sanitized_name = re.sub(r"[^A-Za-z0-9._-]", "_", raw_filename)
    safe_filename = f"{uuid.uuid4().hex[:12]}_{sanitized_name}"
    file_path = os.path.abspath(os.path.join(UPLOAD_DIR, safe_filename))
    if not file_path.startswith(os.path.abspath(UPLOAD_DIR) + os.sep):
        raise HTTPException(status_code=400, detail="Invalid filename")

    chunk_size = 1024 * 1024  # 1 MB
    total_bytes = 0
    try:
        with open(file_path, "wb") as f:
            while True:
                chunk = file.file.read(chunk_size)
                if not chunk:
                    break
                total_bytes += len(chunk)
                if total_bytes > max_size:
                    raise HTTPException(status_code=413, detail="File size exceeds maximum allowed limit (10 MB)")
                f.write(chunk)
    except HTTPException:
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except Exception:
                pass
        raise

    return {
        "message": "File uploaded successfully",
        "attachment_url": f"/uploads/{safe_filename}",
        "filename": safe_filename
    }


@router.post("/incidents")
def report_incident(
    data: IncidentRequest,
    db: Session = Depends(get_db),
    user: dict = Depends(
        require_role("admin", "security", "student")
    )
):
    if data.attachment is not None:
        att = data.attachment
        if (
            not att.startswith("/uploads/")
            or "://" in att
            or "//" in att
            or ".." in att
            or "\\" in att
            or "%" in att
            or ":" in att
        ):
            raise HTTPException(
                status_code=400,
                detail="Invalid attachment path. Must be a relative path starting with /uploads/"
            )

    nlp_result = nlp_service.analyze_report(
        data.description,
        data.incident_type
    )

    incident = Incident(
        user_id=user["user_id"],
        incident_type=data.incident_type,
        location=data.location,
        description=data.description,
        nlp_category=nlp_result["category"],
        nlp_urgency=nlp_result["urgency"],
        attachment=data.attachment
    )

    db.add(incident)
    db.commit()
    db.refresh(incident)

    # Record initial audit timeline logs
    log_created = IncidentLog(
        incident_id=incident.id,
        action="submitted",
        details="Incident report submitted by user",
        performed_by=user["user_id"]
    )
    log_nlp = IncidentLog(
        incident_id=incident.id,
        action="nlp_analyzed",
        details=f"Classified as {nlp_result['category']} with {nlp_result['urgency']} urgency",
        performed_by=None
    )
    db.add(log_created)
    db.add(log_nlp)
    db.commit()

    return {
        "message": "Incident reported successfully",
        "incident_id": incident.id,
        "status": incident.status,
        "attachment": incident.attachment,
        "nlp_analysis": {
            "category": nlp_result["category"],
            "urgency": nlp_result["urgency"]
        }
    }


@router.get("/incidents")
def get_incidents(
    db: Session = Depends(get_db),
    user: dict = Depends(
        require_role("admin", "security", "student")
    )
):
    query = db.query(Incident)

    if user["role"] == "student":
        query = query.filter(
            Incident.user_id == user["user_id"]
        )

    return query.order_by(Incident.id.desc()).all()


@router.get("/incidents/{incident_id}/logs")
def get_incident_logs(
    incident_id: int,
    db: Session = Depends(get_db),
    user: dict = Depends(require_role("admin", "security", "student"))
):
    incident = db.query(Incident).filter(Incident.id == incident_id).first()
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")

    if user["role"] == "student" and incident.user_id != user["user_id"]:
        raise HTTPException(status_code=403, detail="Cannot access logs for other users' incidents")

    logs = db.query(IncidentLog).filter(
        IncidentLog.incident_id == incident_id
    ).order_by(IncidentLog.id.asc()).all()

    return [
        {
            "id": l.id,
            "incident_id": l.incident_id,
            "action": l.action,
            "details": l.details,
            "performed_by": l.performed_by,
            "created_at": l.created_at
        }
        for l in logs
    ]


@router.post("/incidents/analyze-existing")
def analyze_existing_incidents(
    db: Session = Depends(get_db),
    user: dict = Depends(
        require_role("admin", "security")
    )
):
    incidents = db.query(Incident).all()

    analyzed_count = 0

    for incident in incidents:
        nlp_result = nlp_service.analyze_report(
            incident.description or "",
            incident.incident_type or ""
        )

        incident.nlp_category = nlp_result["category"]
        incident.nlp_urgency = nlp_result["urgency"]

        analyzed_count += 1

    db.commit()

    return {
        "message": "Existing incidents reanalyzed successfully",
        "analyzed_count": analyzed_count
    }


@router.patch("/incidents/{incident_id}/status")
def update_incident_status(
    incident_id: int,
    status: str,
    db: Session = Depends(get_db),
    user: dict = Depends(
        require_role("admin", "security")
    )
):
    incident = db.query(Incident).filter(
        Incident.id == incident_id
    ).first()

    if not incident:
        raise HTTPException(
            status_code=404,
            detail="Incident not found"
        )

    if status not in [
        "submitted",
        "acknowledged",
        "resolved"
    ]:
        raise HTTPException(
            status_code=400,
            detail="Invalid incident status"
        )

    old_status = incident.status
    incident.status = status

    # Record status transition in audit log
    log = IncidentLog(
        incident_id=incident.id,
        action=status,
        details=f"Status changed from {old_status} to {status}",
        performed_by=user.get("user_id")
    )
    db.add(log)

    db.commit()
    db.refresh(incident)

    return {
        "message": "Incident status updated",
        "incident_id": incident.id,
        "status": incident.status
    }


# -------------------------
# SOS
# -------------------------

@router.post("/sos")
def send_sos(
    data: Optional[SOSRequest] = None,
    db: Session = Depends(get_db),
    user: dict = Depends(require_role("student"))
):
    loc = (data.location.strip() if data and data.location and data.location.strip() else "Student Location")
    desc = (data.description.strip() if data and data.description and data.description.strip() else "Emergency SOS alert sent by a student")

    alert = Alert(
        user_id=user["user_id"],
        alert_type="SOS",
        location=loc,
        description=desc,
        severity="high",
        status="active"
    )

    db.add(alert)
    db.commit()
    db.refresh(alert)

    return {
        "message": "SOS alert sent successfully",
        "alert_id": alert.id,
        "status": alert.status,
        "location": alert.location
    }


@router.get("/sos")
def get_sos_alerts(
    db: Session = Depends(get_db),
    user: dict = Depends(
        require_role("admin", "security", "student")
    )
):
    query = db.query(Alert).filter(
        Alert.alert_type == "SOS"
    )

    if user["role"] == "student":
        query = query.filter(
            Alert.user_id == user["user_id"]
        )

    return query.order_by(Alert.id.desc()).all()