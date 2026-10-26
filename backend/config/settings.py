import os
from dotenv import load_dotenv

load_dotenv()

PROJECT_NAME = "CampusGuard AI"
API_VERSION = "1.0.0"

SECRET_KEY = os.getenv("CAMPUSGUARD_SECRET_KEY")

if not SECRET_KEY:
    raise RuntimeError(
        "CAMPUSGUARD_SECRET_KEY is missing. Set it in your environment or .env file."
    )

if SECRET_KEY == "change-this-to-a-random-secret-before-deployment":
    raise RuntimeError(
        "The default JWT secret is insecure. Configure a secure secret."
    )

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30