from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel

from backend.config.database import get_db
from backend.services.risk_service import risk_service
from backend.services.auth_service import get_current_user, require_role

router = APIRouter(tags=["Risk Prediction"])


class RiskInput(BaseModel):
    fall: bool = False
    fight: bool = False
    weapon: bool = False
    restricted_entry: bool = False
    after_hours: bool = False
    loitering: bool = False


@router.post("/risk")
def get_risk(data: RiskInput, user: dict = Depends(get_current_user)):
    return risk_service.predict(
        fall=data.fall,
        fight=data.fight,
        weapon=data.weapon,
        restricted_entry=data.restricted_entry,
        after_hours=data.after_hours,
        loitering=data.loitering,
    )


@router.get("/risk/campus-overview")
def get_campus_risk_overview(
    db: Session = Depends(get_db),
    user: dict = Depends(require_role("admin", "security"))
):
    return risk_service.calculate_campus_overview(db)
