from backend.config.database import Base, engine
from backend.database.models import user, camera, alert, incident, incident_log

def create_tables():
    Base.metadata.create_all(bind=engine)
