import os
import joblib

from backend.ml_models.risk_prediction import predict_risk, get_contributing_factors, get_operational_score
from backend.services.alert_service import create_cctv_alert


candidates = [
    os.path.join("models", "risk_prediction_model.pkl"),
    os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "models", "risk_prediction_model.pkl"),
]
MODEL_PATH = next((p for p in candidates if os.path.exists(p)), candidates[0])


class RiskService:
    def __init__(self):
        self.model = None
        self.model_load_error = None
        if os.path.exists(MODEL_PATH):
            try:
                self.model = joblib.load(MODEL_PATH)
                print("Risk Prediction ML model loaded successfully.")
            except Exception as exc:
                self.model_load_error = str(exc)
                print(f"Risk model could not be loaded: {exc}")
        else:
            self.model_load_error = "Model file not found"
            print("Risk Prediction model not found; rule-based fallback enabled.")

    def predict(self, fall=False, fight=False, weapon=False,
                restricted_entry=False, after_hours=False, loitering=False):
        inference_error = None
        if self.model is not None:
            try:
                return predict_risk(
                    self.model,
                    fall=fall,
                    fight=fight,
                    weapon=weapon,
                    restricted_entry=restricted_entry,
                    after_hours=after_hours,
                    loitering=loitering,
                )
            except Exception as exc:
                inference_error = str(exc)
                print(f"Risk model inference failed, falling back to rule-based heuristic: {exc}")

        score = min(
            int(fall) * 30
            + int(fight) * 40
            + int(weapon) * 50
            + int(restricted_entry) * 50
            + int(after_hours) * 30
            + int(loitering) * 30,
            100,
        )
        if score >= 70:
            level = "High"
        elif score >= 30:
            level = "Medium"
        else:
            level = "Low"

        factors = get_contributing_factors(fall, fight, weapon, restricted_entry, after_hours, loitering)

        if inference_error:
            model_type = f"Rule-based Fallback Heuristic (Inference error: {inference_error})"
        elif self.model_load_error:
            model_type = f"Rule-based Fallback Heuristic (Model load error: {self.model_load_error})"
        else:
            model_type = "Rule-based Fallback Heuristic"

        result = {
            "risk_level": level,
            "risk_score": score,
            "risk_score_type": "rule_based_additive_points",
            "confidence": None,  # Not calibrated from ML model; avoid hardcoded 1.0
            "confidence_type": "uncalibrated_heuristic",
            "model_type": model_type,
            "factors": factors,
        }
        if inference_error:
            result["inference_error"] = inference_error
        elif self.model_load_error:
            result["model_load_error"] = self.model_load_error

        return result

    def calculate_campus_overview(self, db):
        from backend.database.models.alert import Alert
        from backend.database.models.incident import Incident
        from backend.database.models.camera import Camera
        from backend.services.after_hours_service import AfterHoursService

        active_alerts = (
            db.query(Alert).filter(Alert.status.in_(["active", "escalated"])).all()
            if db
            else []
        )
        critical_alerts = [a for a in active_alerts if (a.severity or "").lower() in ("critical", "high")]
        sos_alerts = [a for a in active_alerts if a.alert_type == "SOS"]

        recent_incidents = db.query(Incident).filter(Incident.status != "resolved").all() if db else []
        urgent_incidents = [i for i in recent_incidents if (i.nlp_urgency or "").lower() == "high"]

        total_cameras = db.query(Camera).count() if db else 0
        active_cameras = db.query(Camera).filter(Camera.status == True).count() if db else 0  # noqa: E712

        after_hours_info = AfterHoursService().check_after_hours()
        is_after_hours = after_hours_info["after_hours"]

        # Composite Multi-Signal Safety Score
        score = 0
        signals = []

        if sos_alerts:
            score += min(len(sos_alerts) * 35, 70)
            signals.append(f"{len(sos_alerts)} Active SOS Emergency Alert(s)")

        if critical_alerts:
            score += min(len(critical_alerts) * 20, 50)
            signals.append(f"{len(critical_alerts)} Critical/High Severity Alert(s)")

        if urgent_incidents:
            score += min(len(urgent_incidents) * 15, 30)
            signals.append(f"{len(urgent_incidents)} High Urgency Incident(s)")

        if is_after_hours:
            score += 15
            signals.append("Campus in After-Hours Window")

        # Clamp between 0 and 100
        risk_score = min(score, 100)
        if risk_score >= 65:
            risk_level = "High"
        elif risk_score >= 25:
            risk_level = "Medium"
        else:
            risk_level = "Low"

        if not signals:
            signals.append("All campus zones within safe baseline parameters")

        return {
            "risk_score": risk_score,
            "risk_level": risk_level,
            "safety_index": 100 - risk_score,
            "active_sos_count": len(sos_alerts),
            "critical_alerts_count": len(critical_alerts),
            "open_incidents_count": len(recent_incidents),
            "urgent_incidents_count": len(urgent_incidents),
            "active_cameras": active_cameras,
            "total_cameras": total_cameras,
            "after_hours": is_after_hours,
            "contributing_signals": signals
        }


risk_service = RiskService()


def create_risk_alert(
    db=None,
    location=None,
    fall=False,
    fight=False,
    weapon=False,
    restricted_zone=False,
    restricted_entry=False,
    after_hours=False,
    loitering=False,
    detected_weapons=None,
    user_id=None,
):
    if restricted_zone:
        restricted_entry = True

    risk = risk_service.predict(
        fall=fall,
        fight=fight,
        weapon=weapon,
        restricted_entry=restricted_entry,
        after_hours=after_hours,
        loitering=loitering,
    )

    # Determine if this image or video analysis contains a qualifying threat
    has_threat = (
        bool(weapon)
        or bool(fight)
        or bool(fall)
        or bool(restricted_entry)
        or bool(loitering)
        or (risk.get("risk_level") == "High")
    )

    if has_threat:
        # Determine primary alert type based on threat hierarchy
        if weapon:
            alert_type = "Weapon Detection"
            severity = "critical"
        elif fight:
            alert_type = "Fight Detection"
            severity = "high"
        elif restricted_entry:
            alert_type = "Restricted Entry"
            severity = "high"
        elif fall:
            alert_type = "Fall Detection"
            severity = "high"
        elif loitering:
            alert_type = "Loitering Detection"
            severity = "medium"
        elif after_hours:
            alert_type = "After-Hours Activity"
            severity = "medium"
        else:
            alert_type = "Critical CCTV Threat"
            severity = "high"

        if risk.get("risk_score", 0) >= 70:
            severity = "critical"

        operational_score = get_operational_score(severity)
        operational_severity = severity.capitalize()
    else:
        alert_type = None
        severity = "low"
        operational_score = 20
        operational_severity = "Low"

    risk["operational_severity"] = operational_severity
    risk["operational_score"] = operational_score
    risk["operational_score_scale"] = "Low=20, Medium=50, High=80, Critical=100"

    if has_threat and db is not None:
        # Resolve location details
        if restricted_zone and isinstance(restricted_zone, str):
            resolved_location = f"{restricted_zone} ({location or 'Main Campus'})"
        else:
            resolved_location = location or "Main Campus"

        # Build informative threat description with detection details
        details = []
        if weapon:
            if detected_weapons and isinstance(detected_weapons, list):
                weapon_names = []
                for item in detected_weapons:
                    if isinstance(item, str):
                        weapon_names.append(item)
                    elif isinstance(item, dict):
                        weapon_names.append(
                            item.get("weapon")
                            or item.get("name")
                            or item.get("class")
                            or "weapon"
                        )
                details.append(
                    f"Weapons detected: {', '.join(weapon_names) if weapon_names else 'unidentified weapon'}"
                )
            else:
                details.append("Weapon detected")
        if fight:
            details.append("Physical fight detected")
        if fall:
            details.append("Person fall detected")
        if restricted_entry:
            zone_name = restricted_zone if isinstance(restricted_zone, str) else "Restricted Area"
            details.append(f"Unauthorized intrusion in {zone_name}")
        if loitering:
            details.append("Loitering pattern detected")
        if after_hours:
            details.append("After-hours activity")

        details_str = "; ".join(details) if details else "Critical threat detected by CCTV intelligence"
        description = (
            f"CCTV Threat Alert: {details_str}. "
            f"Operational Threat Severity: {severity.upper()} (Operational Severity Score: {operational_score}/100) | "
            f"ML Risk Score: {risk.get('risk_score', 0)}/100 (Level: {risk.get('risk_level', 'Unknown')})."
        )

        alert = create_cctv_alert(
            db=db,
            alert_type=alert_type,
            location=resolved_location,
            description=description,
            severity=severity,
            user_id=user_id,
            operational_score=operational_score,
        )

        risk["alert_id"] = alert.id if alert else None
    else:
        risk["alert_id"] = None

    return risk
