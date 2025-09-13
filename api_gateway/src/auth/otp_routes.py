from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, EmailStr
from typing import Any, Dict

from .email_service import send_signup_otp, verify_otp  # local file imports
from .controller import AuthController

router = APIRouter(prefix="/auth/otp", tags=["otp"])

auth_controller = AuthController()


class OTPRequest(BaseModel):
    email: EmailStr


class OTPVerifyRequest(BaseModel):
    email: EmailStr
    otp: str


@router.post("/send", status_code=status.HTTP_202_ACCEPTED)
async def send_otp(body: OTPRequest):
    user = auth_controller.db.users.find_one({"email": body.email})
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    send_signup_otp(body.email, user.get("name"))
    return {"status": "otp_sent"}


@router.post("/verify", status_code=status.HTTP_200_OK)
async def verify_user_otp(body: OTPVerifyRequest):
    if not verify_otp(body.email, body.otp):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired OTP")

    # mark email verified on user profile
    auth_controller.db.users.update_one({"email": body.email}, {"$set": {"email_verified": True}})
    return {"status": "verified"}
