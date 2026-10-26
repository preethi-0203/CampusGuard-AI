from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import os

from backend.config.settings import PROJECT_NAME, API_VERSION
from backend.config.database import Base, engine
from backend.database.models.user import User  # noqa: F401
from backend.database.models.incident import Incident  # noqa: F401
from backend.database.models.alert import Alert  # noqa: F401
from backend.database.models.camera import Camera  # noqa: F401
from backend.database.models.incident_log import IncidentLog  # noqa: F401
from backend.database.migrate_schema import run_migrations
from backend.routes.auth import router as auth_router
from backend.routes.assistant import router as assistant_router
from backend.routes.users import router as users_router
from backend.routes.camera import router as camera_router
from backend.routes.cameras import router as cameras_router
from backend.routes.alerts import router as alerts_router
from backend.routes.risk import router as risk_router
from backend.seed import seed_users

app = FastAPI(title=PROJECT_NAME, version=API_VERSION)

cors_origins_env = os.getenv("CORS_ORIGINS")
if cors_origins_env:
    allowed_origins = [orig.strip() for orig in cors_origins_env.split(",") if orig.strip()]
    if not allowed_origins:
        allowed_origins = ["http://localhost:5173", "http://127.0.0.1:5173"]
else:
    allowed_origins = ["http://localhost:5173", "http://127.0.0.1:5173"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

Base.metadata.create_all(bind=engine)
run_migrations()
seed_users()



app.include_router(users_router)
app.include_router(cameras_router)
app.include_router(camera_router)
app.include_router(alerts_router)
app.include_router(risk_router)
app.include_router(auth_router)
app.include_router(assistant_router)


@app.get("/")
def home():
    return {"message": "CampusGuard AI Backend is Running", "version": API_VERSION}


@app.get("/health")
def health():
    return {"status": "ok", "service": PROJECT_NAME, "version": API_VERSION}
