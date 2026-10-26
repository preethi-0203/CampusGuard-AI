from pwdlib import PasswordHash
from backend.config.database import SessionLocal
from backend.database.models.user import User

password_hash = PasswordHash.recommended()

db = SessionLocal()

try:
    users = db.query(User).all()
    count = 0

    for user in users:
        if not user.password.startswith("$argon2"):
            user.password = password_hash.hash(user.password)
            count += 1

    db.commit()
    print(f"Successfully hashed passwords for {count} users.")

except Exception as e:
    db.rollback()
    print("Migration failed:", e)

finally:
    db.close()