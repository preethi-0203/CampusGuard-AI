from backend.config.database import SessionLocal
from backend.database.models.user import User
from backend.services.auth_service import password_hash

DEFAULT_USERS = [
    ("Student User", "student@campusguard.com", "Student@123", "student"),
    ("Security User", "security@campusguard.com", "Security@123", "security"),
    ("Admin User", "admin@campusguard.com", "Admin@123", "admin"),
]


def seed_users():
    db = SessionLocal()
    try:
        for name, email, password, role in DEFAULT_USERS:
            if not db.query(User).filter(User.email == email).first():
                db.add(User(name=name, email=email, password=password_hash.hash(password), role=role))
        db.commit()
    finally:
        db.close()
