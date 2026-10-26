from sqlalchemy import inspect, text
from backend.config.database import engine, Base
from backend.database.models.user import User  # noqa: F401
from backend.database.models.incident import Incident  # noqa: F401
from backend.database.models.alert import Alert  # noqa: F401
from backend.database.models.camera import Camera  # noqa: F401
from backend.database.models.incident_log import IncidentLog  # noqa: F401


def run_migrations():
    # Create any newly defined tables (e.g. incident_logs)
    Base.metadata.create_all(bind=engine)

    inspector = inspect(engine)

    # 1. Check alerts table for assigned_to and escalated
    alert_cols = [c["name"] for c in inspector.get_columns("alerts")]
    with engine.begin() as conn:
        if "assigned_to" not in alert_cols:
            conn.execute(text("ALTER TABLE alerts ADD COLUMN assigned_to INTEGER REFERENCES users(id)"))
            print("Added assigned_to to alerts")
        if "escalated" not in alert_cols:
            conn.execute(text("ALTER TABLE alerts ADD COLUMN escalated BOOLEAN DEFAULT 0"))
            print("Added escalated to alerts")
        if "operational_score" not in alert_cols:
            conn.execute(text("ALTER TABLE alerts ADD COLUMN operational_score INTEGER DEFAULT NULL"))
            print("Added operational_score to alerts")

    # 2. Check incidents table for attachment and alert_id
    incident_cols = [c["name"] for c in inspector.get_columns("incidents")]
    with engine.begin() as conn:
        if "attachment" not in incident_cols:
            conn.execute(text("ALTER TABLE incidents ADD COLUMN attachment TEXT"))
            print("Added attachment to incidents")
        if "alert_id" not in incident_cols:
            conn.execute(text("ALTER TABLE incidents ADD COLUMN alert_id INTEGER REFERENCES alerts(id)"))
            print("Added alert_id to incidents")

    print("Schema migration check completed successfully.")


if __name__ == "__main__":
    run_migrations()
