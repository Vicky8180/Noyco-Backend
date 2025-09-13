# api_gateway/src/auth/main.py
"""
Main authentication module initialization
"""
from .controller import AuthController
from .schema import *
from .routes import router

__all__ = [
    "AuthController",
    "router",
    "HospitalRegistrationRequest",
    "LoginRequest",
    "PasswordUpdateRequest",
    "TokenResponse",
    "UserRole",
    "PlanType"
]
