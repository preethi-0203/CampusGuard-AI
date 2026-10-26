from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel

from backend.config.database import get_db
from backend.database.models.user import User
from backend.services.auth_service import (
    create_access_token,
    password_hash,
)

router = APIRouter()


class LoginRequest(BaseModel):
    email: str
    password: str


@router.post("/login")
def login(data: LoginRequest, db: Session = Depends(get_db)):
    email_clean = data.email.strip().lower()
    user = db.query(User).filter(
        User.email == email_clean
    ).first()

    if not user or not password_hash.verify(
        data.password, user.password
    ):
        raise HTTPException(
            status_code=401,
            detail="Invalid email or password"
        )

    token = create_access_token(user.id, user.role)

    return {
        "message": "Login successful",
        "access_token": token,
        "token_type": "bearer",
        "user_id": user.id,
        "name": user.name,
        "email": user.email,
        "role": user.role
    }


@router.post("/logout")
def logout():
    return {"message": "Logout successful"}