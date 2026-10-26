from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pwdlib import PasswordHash
from sqlalchemy.orm import Session

from backend.config.database import get_db
from backend.database.models.user import User
from backend.config.settings import (
    SECRET_KEY,
    ALGORITHM,
    ACCESS_TOKEN_EXPIRE_MINUTES,
)

password_hash = PasswordHash.recommended()
security = HTTPBearer(auto_error=True)


def create_access_token(user_id: int, role: str):
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {"sub": str(user_id), "role": role, "exp": expire}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
):
    try:
        payload = jwt.decode(
            credentials.credentials,
            SECRET_KEY,
            algorithms=[ALGORITHM],
        )
        user_id_raw = payload.get("sub")
        if user_id_raw is None:
            raise HTTPException(status_code=401, detail="Invalid authentication token")
        user_id = int(user_id_raw)
    except (jwt.InvalidTokenError, ValueError, TypeError):
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found or account deactivated")

    return {
        "user_id": user.id,
        "name": user.name,
        "email": user.email,
        "role": user.role,
    }


def require_role(*allowed_roles):
    def check_role(current_user: dict = Depends(get_current_user)):
        if current_user["role"] not in allowed_roles:
            raise HTTPException(status_code=403, detail="Access forbidden")
        return current_user
    return check_role
