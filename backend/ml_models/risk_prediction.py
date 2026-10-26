import pandas as pd
from typing import Optional

OPERATIONAL_SEVERITY_SCALE = {
    "low": 20,
    "medium": 50,
    "high": 80,
    "critical": 100,
}


def get_operational_score(severity: Optional[str]) -> Optional[int]:
    """Returns the operational severity score (Low=20, Medium=50, High=80, Critical=100).

    Returns None if severity is None or empty.
    """
    if not severity:
        return None
    return OPERATIONAL_SEVERITY_SCALE.get(str(severity).lower(), 50)



def get_contributing_factors(fall=False, fight=False, weapon=False, restricted_entry=False, after_hours=False, loitering=False):
    factors = []
    if weapon:
        factors.append({"factor": "Weapon Detection", "impact": "+50 pts", "severity": "Critical"})
    if fight:
        factors.append({"factor": "Physical Fight Detected", "impact": "+40 pts", "severity": "High"})
    if restricted_entry:
        factors.append({"factor": "Restricted Zone Entry", "impact": "+50 pts", "severity": "High"})
    if fall:
        factors.append({"factor": "Person Fall Detected", "impact": "+30 pts", "severity": "High"})
    if after_hours:
        factors.append({"factor": "After-Hours Activity", "impact": "+30 pts", "severity": "Medium"})
    if loitering:
        factors.append({"factor": "Loitering Pattern", "impact": "+30 pts", "severity": "Medium"})
    if not factors:
        factors.append({"factor": "Normal Baseline (No Active Threats)", "impact": "0 pts", "severity": "Low"})
    return factors


def predict_risk(
    model,
    fall=False,
    fight=False,
    weapon=False,
    restricted_entry=False,
    after_hours=False,
    loitering=False
):
    data = pd.DataFrame([{
        "fall": int(bool(fall)),
        "fight": int(bool(fight)),
        "weapon": int(bool(weapon)),
        "restricted_entry": int(bool(restricted_entry)),
        "after_hours": int(bool(after_hours)),
        "loitering": int(bool(loitering))
    }])

    risk_level = model.predict(data)[0]

    probabilities = model.predict_proba(data)[0]
    confidence = max(probabilities)

    # Convert ML prediction to a project risk score
    score_map = {
        "Low": 20,
        "Medium": 50,
        "High": 80
    }

    risk_score = score_map.get(risk_level, 0)
    factors = get_contributing_factors(fall, fight, weapon, restricted_entry, after_hours, loitering)

    return {
        "risk_level": risk_level,
        "risk_score": risk_score,
        "risk_score_type": "discrete_tier_score",
        "confidence": round(float(confidence), 3),
        "confidence_type": "model_class_confidence",
        "model_type": "Random Forest Classifier (Trained ML Model)",
        "factors": factors
    }