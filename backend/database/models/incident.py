from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from datetime import datetime
from backend.config.database import Base


class Incident(Base):
    __tablename__ = "incidents"

    id = Column(Integer, primary_key=True, index=True)
    alert_id = Column(
        Integer,
        ForeignKey("alerts.id"),
        nullable=True,
        index=True
    )
    user_id = Column(
        Integer,
        ForeignKey("users.id"),
        nullable=True
    )
    incident_type = Column(String, nullable=False)
    location = Column(String, nullable=False)
    description = Column(String, nullable=False)
    nlp_category = Column(String, nullable=True)
    nlp_urgency = Column(String, nullable=True)
    attachment = Column(String, nullable=True)
    status = Column(String, default="submitted")
    created_at = Column(DateTime, default=datetime.utcnow)