from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional

from backend.config.database import get_db
from backend.database.models.camera import Camera
from backend.services.auth_service import require_role

router = APIRouter(tags=["Camera Management"])


class CameraCreateRequest(BaseModel):
    name: str
    location: str
    status: bool = True


class CameraUpdateRequest(BaseModel):
    name: Optional[str] = None
    location: Optional[str] = None
    status: Optional[bool] = None


@router.get("/cameras")
def get_cameras(
    db: Session = Depends(get_db),
    user: dict = Depends(require_role("admin", "security"))
):
    cameras = db.query(Camera).order_by(Camera.id.asc()).all()
    return [
        {
            "id": c.id,
            "name": c.name,
            "location": c.location,
            "status": bool(c.status)
        }
        for c in cameras
    ]


@router.post("/cameras", status_code=201)
def create_camera(
    data: CameraCreateRequest,
    db: Session = Depends(get_db),
    admin: dict = Depends(require_role("admin"))
):
    if not data.name.strip() or not data.location.strip():
        raise HTTPException(status_code=400, detail="Camera name and location are required")

    camera = Camera(
        name=data.name.strip(),
        location=data.location.strip(),
        status=data.status
    )
    db.add(camera)
    db.commit()
    db.refresh(camera)

    return {
        "message": "Camera registered successfully",
        "camera": {
            "id": camera.id,
            "name": camera.name,
            "location": camera.location,
            "status": bool(camera.status)
        }
    }


@router.get("/cameras/{camera_id}")
def get_camera_by_id(
    camera_id: int,
    db: Session = Depends(get_db),
    user: dict = Depends(require_role("admin", "security"))
):
    camera = db.query(Camera).filter(Camera.id == camera_id).first()
    if not camera:
        raise HTTPException(status_code=404, detail="Camera not found")
    return {
        "id": camera.id,
        "name": camera.name,
        "location": camera.location,
        "status": bool(camera.status)
    }


@router.patch("/cameras/{camera_id}")
def update_camera(
    camera_id: int,
    data: CameraUpdateRequest,
    db: Session = Depends(get_db),
    admin: dict = Depends(require_role("admin"))
):
    camera = db.query(Camera).filter(Camera.id == camera_id).first()
    if not camera:
        raise HTTPException(status_code=404, detail="Camera not found")

    if data.name is not None and data.name.strip():
        camera.name = data.name.strip()
    if data.location is not None and data.location.strip():
        camera.location = data.location.strip()
    if data.status is not None:
        camera.status = data.status

    db.commit()
    db.refresh(camera)

    return {
        "message": "Camera updated successfully",
        "camera": {
            "id": camera.id,
            "name": camera.name,
            "location": camera.location,
            "status": bool(camera.status)
        }
    }


@router.delete("/cameras/{camera_id}")
def delete_camera(
    camera_id: int,
    db: Session = Depends(get_db),
    admin: dict = Depends(require_role("admin"))
):
    camera = db.query(Camera).filter(Camera.id == camera_id).first()
    if not camera:
        raise HTTPException(status_code=404, detail="Camera not found")

    db.delete(camera)
    db.commit()
    return {"message": "Camera deleted successfully", "deleted_camera_id": camera_id}
