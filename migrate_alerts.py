from sqlalchemy import inspect, text
from backend.config.database import engine

inspector = inspect(engine)
columns = [column["name"] for column in inspector.get_columns("alerts")]

if "user_id" not in columns:
    with engine.begin() as connection:
        connection.execute(
            text(
                "ALTER TABLE alerts "
                "ADD COLUMN user_id INTEGER REFERENCES users(id)"
            )
        )
    print("user_id column added successfully")
else:
    print("user_id column already exists")