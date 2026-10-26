from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from datetime import datetime
from backend.config.database import Base


class IncidentLog(Base):
    __tablename__ = "incident_logs"

    id = Column(Integer, primary_key=True, index=True)
    incident_id = Column(Integer, ForeignKey("incidents.id"), nullable=False, index=True)
    action = Column(String, nullable=False)
    details = Column(String, nullable=True)
    performed_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
