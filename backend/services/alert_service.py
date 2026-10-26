from datetime import datetime, timedelta
from typing import Optional
from sqlalchemy.orm import Session

from backend.database.models.alert import Alert


def create_cctv_alert(
    db: Session,
    alert_type: str,
    location: str,
    description: str,
    severity: str = "high",
    user_id: Optional[int] = None,
    operational_score: Optional[int] = None,
) -> Optional[Alert]:
    """Persists a new CCTV threat alert to the database, preventing duplicate active alerts within 30 seconds."""
    try:
        from backend.ml_models.risk_prediction import get_operational_score

        if operational_score is None and severity:
            operational_score = get_operational_score(severity)

        recent_cutoff = datetime.utcnow() - timedelta(seconds=30)
        existing = (
            db.query(Alert)
            .filter(
                Alert.alert_type == alert_type,
                Alert.location == location,
                Alert.status == "active",
                Alert.created_at >= recent_cutoff,
            )
            .first()
        )
        if existing:
            return existing

        alert = Alert(
            user_id=user_id,
            alert_type=alert_type,
            location=location,
            description=description,
            severity=severity,
            operational_score=operational_score,
            status="active",
            created_at=datetime.utcnow(),
        )
        db.add(alert)
        db.commit()
        db.refresh(alert)
        return alert
    except Exception as exc:
        db.rollback()
        print(f"Error persisting CCTV alert: {exc}")
        return None
