from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional

from backend.config.database import get_db
from backend.database.models.user import User
from backend.database.models.alert import Alert
from backend.database.models.incident import Incident
from backend.database.models.incident_log import IncidentLog
from backend.services.auth_service import require_role, password_hash

router = APIRouter(tags=["User Management"])


class UserCreateRequest(BaseModel):
    name: str
    email: str
    password: str
    role: str = "student"


class UserUpdateRequest(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    role: Optional[str] = None
    password: Optional[str] = None


@router.get("/users")
def get_users(
    db: Session = Depends(get_db),
    admin: dict = Depends(require_role("admin"))
):
    users = db.query(User).order_by(User.id.asc()).all()
    return [
        {
            "id": u.id,
            "name": u.name,
            "email": u.email,
            "role": u.role
        }
        for u in users
    ]


@router.post("/users", status_code=201)
def create_user(
    data: UserCreateRequest,
    db: Session = Depends(get_db),
    admin: dict = Depends(require_role("admin"))
):
    if "@" not in data.email or "." not in data.email:
        raise HTTPException(status_code=400, detail="Invalid email format")

    valid_roles = ["student", "security", "admin", "user"]
    role_normalized = data.role.lower().strip()
    if role_normalized not in valid_roles:
        raise HTTPException(status_code=400, detail=f"Invalid role. Must be one of {valid_roles}")

    existing = db.query(User).filter(User.email == data.email.strip().lower()).first()
    if existing:
        raise HTTPException(status_code=400, detail="User with this email already exists")

    new_user = User(
        name=data.name.strip(),
        email=data.email.strip().lower(),
        password=password_hash.hash(data.password),
        role=role_normalized
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    return {
        "message": "User created successfully",
        "user": {
            "id": new_user.id,
            "name": new_user.name,
            "email": new_user.email,
            "role": new_user.role
        }
    }


@router.get("/users/{user_id}")
def get_user_by_id(
    user_id: int,
    db: Session = Depends(get_db),
    admin: dict = Depends(require_role("admin"))
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return {
        "id": user.id,
        "name": user.name,
        "email": user.email,
        "role": user.role
    }


@router.patch("/users/{user_id}")
def update_user(
    user_id: int,
    data: UserUpdateRequest,
    db: Session = Depends(get_db),
    admin: dict = Depends(require_role("admin"))
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if data.name is not None and data.name.strip():
        user.name = data.name.strip()
    if data.email is not None and data.email.strip():
        if "@" not in data.email or "." not in data.email:
            raise HTTPException(status_code=400, detail="Invalid email format")
        conflict = db.query(User).filter(User.email == data.email.strip().lower(), User.id != user_id).first()
        if conflict:
            raise HTTPException(status_code=400, detail="Email is already in use by another user")
        user.email = data.email.strip().lower()
    if data.role is not None:
        valid_roles = ["student", "security", "admin", "user"]
        role_norm = data.role.lower().strip()
        if role_norm not in valid_roles:
            raise HTTPException(status_code=400, detail=f"Invalid role. Must be one of {valid_roles}")
        if user.role == "admin" and role_norm != "admin":
            admin_count = db.query(User).filter(User.role == "admin").count()
            if admin_count <= 1:
                raise HTTPException(status_code=400, detail="Cannot demote the last remaining administrator account")
        user.role = role_norm
    if data.password is not None and data.password.strip():
        user.password = password_hash.hash(data.password.strip())

    db.commit()
    db.refresh(user)
    return {
        "message": "User updated successfully",
        "user": {
            "id": user.id,
            "name": user.name,
            "email": user.email,
            "role": user.role
        }
    }


@router.delete("/users/{user_id}")
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    admin: dict = Depends(require_role("admin"))
):
    if admin.get("user_id") == user_id:
        raise HTTPException(status_code=400, detail="Cannot delete your own administrator account")

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if user.role == "admin":
        admin_count = db.query(User).filter(User.role == "admin").count()
        if admin_count <= 1:
            raise HTTPException(status_code=400, detail="Cannot delete the last remaining administrator account")

    try:
        # Nullify historical references in alerts, incidents, and audit logs before row deletion
        db.query(Alert).filter(Alert.user_id == user_id).update(
            {Alert.user_id: None}, synchronize_session=False
        )
        db.query(Alert).filter(Alert.assigned_to == user_id).update(
            {Alert.assigned_to: None}, synchronize_session=False
        )
        db.query(Incident).filter(Incident.user_id == user_id).update(
            {Incident.user_id: None}, synchronize_session=False
        )
        db.query(IncidentLog).filter(IncidentLog.performed_by == user_id).update(
            {IncidentLog.performed_by: None}, synchronize_session=False
        )

        db.delete(user)
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Failed to delete user and reassign historical records safely."
        )

    return {"message": "User deleted successfully", "deleted_user_id": user_id}