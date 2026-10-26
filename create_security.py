from backend.config.database import SessionLocal
from backend.database.models.user import User
from backend.services.auth_service import password_hash

db = SessionLocal()

email = "security@campusguard.com"

existing_user = db.query(User).filter(
    User.email == email
).first()

if existing_user:
    print("Security account already exists.")
else:
    user = User(
        name="Security Officer",
        email=email,
        password=password_hash.hash("Security@123"),
        role="security"
    )

    db.add(user)
    db.commit()

    print("Security account created successfully!")

db.close()