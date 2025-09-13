# auth_utils.py
from fastapi import HTTPException, status, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError
from typing import Any
from datetime import datetime
import os

# Define the roles if needed (basic setup)
class UserRole:
    ADMIN = "admin"
    HOSPITAL_ADMIN = "hospital_admin"
    DOCTOR = "doctor"
    NURSE = "nurse"
    STAFF = "staff"

# JWT Secret and Algorithm (make sure it's same as API Gateway)
SECRET_KEY = os.getenv("JWT_SECRET_KEY", "your-secret-key-change-in-production")
ALGORITHM = "HS256"

# Optional: JWT Claims Model (you can simplify if needed)
class JWTClaims:
    def __init__(self, payload: dict):
        self.user_id: str = payload.get("user_id")
        self.hospital_id: str = payload.get("hospital_id")
        self.hospital_unique_identity: str = payload.get("hospital_unique_identity")
        self.email: str = payload.get("email")
        self.role: str = payload.get("role")
        self.plan: str = payload.get("plan")
        self.exp: int = payload.get("exp")
        self.iat: int = payload.get("iat")
        self.jti: str = payload.get("jti")

def verify_token(token: str) -> JWTClaims:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return JWTClaims(payload)
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token"
        )

# FastAPI dependency
security = HTTPBearer()

def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> JWTClaims:
    return verify_token(credentials.credentials)
