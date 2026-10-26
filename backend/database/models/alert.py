from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Boolean
from datetime import datetime
from backend.config.database import Base


class Alert(Base):
    __tablename__ = "alerts"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    alert_type = Column(String, nullable=False)
    location = Column(String, nullable=False)
    description = Column(String)
    severity = Column(String, default="medium")
    status = Column(String, default="active")
    assigned_to = Column(Integer, ForeignKey("users.id"), nullable=True)
    escalated = Column(Boolean, default=False)
    operational_score = Column(Integer, nullable=True, default=None)
    created_at = Column(DateTime, default=datetime.utcnow)