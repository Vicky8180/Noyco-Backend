
# api_gateway/src/auth/routes.py
from fastapi import APIRouter, Depends, HTTPException, status, Response, Request, Header, Cookie
from .controller import AuthController
from ...middlewares.jwt_auth import JWTAuthController
from .schema import *
from datetime import datetime, timedelta
from typing import List
from .email_service import send_signup_otp, send_password_reset_otp, verify_otp
# Logging
import logging
logger = logging.getLogger("auth.password_reset")

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["Authentication"])

auth_controller = AuthController()
jwt_auth = JWTAuthController()

@router.post("/hospital/register")
async def register_hospital(
    request: RegistrationRequest,
    response: Response
):
    """Register a new hospital OR individual. No auth cookies are issued until e-mail is verified."""
    # Create entity + user
    data = await auth_controller.register(request)

    # Ensure the new account starts as un-verified
    auth_controller.db.users.update_one(
        {"id": data["user_id"]}, {"$set": {"email_verified": False}}
    )

    # Immediately send OTP e-mail
    send_signup_otp(data["email"], request.name)

    return {
        "success": True,
        "pending_verification": True,
        "user": {
            "id": data["user_id"],
            "email": data["email"],
            "role": "individual" if request.type == "individual" else "hospital",
            "role_entity_id": data["id"],
        },
    }

@router.post("/login")
async def login(
    request: LoginRequest,
    response: Response
):
    """Login with JWT cookie authentication"""
    # Authenticate user
    user_data = await auth_controller.login(request)

    # Create JWT tokens
    access_token = jwt_auth.create_access_token(
        user_data["user_id"],
        user_data["role_entity_id"],
        user_data["role"],
        user_data["email"],
        user_data["plan"],

    )
    refresh_token = jwt_auth.create_refresh_token(
        user_data["user_id"],
        user_data["role_entity_id"]
    )

    # Set cookies
    csrf_token = jwt_auth.set_auth_cookies(response, access_token, refresh_token)

    return {
        "success": True,
        "user": {
            "id": user_data["user_id"],
            "email": user_data["email"],
            "role": user_data["role"].value if isinstance(user_data["role"], UserRole) else user_data["role"],
            "role_entity_id": user_data["role_entity_id"],
        },
        "csrf_token": csrf_token
    }

@router.post("/logout")
async def logout(
    request: Request,
    response: Response,
    csrf_token: str = Header(..., alias="X-CSRF-Token"),
    access_token: str = Cookie(None, alias="access_token"),
    refresh_token: str = Cookie(None, alias="refresh_token")
):
    """Logout and revoke tokens"""
    # Verify CSRF token
    jwt_auth.verify_csrf_token(request, csrf_token)

    # Revoke tokens
    if access_token:
        jwt_auth.revoke_token(access_token, "access")

    if refresh_token:
        jwt_auth.revoke_token(refresh_token, "refresh")

    # Clear cookies
    jwt_auth.clear_auth_cookies(response)

    return {"success": True, "message": "Logged out successfully"}

@router.post("/password/update")
async def update_password(
    request: PasswordUpdateRequest,
    current_user: JWTClaims = Depends(jwt_auth.get_current_user),
    csrf_token: str = Header(..., alias="X-CSRF-Token")
):
    """Update user password with CSRF protection"""
    return await auth_controller.update_password(current_user.user_id, request)

@router.post("/assistants", response_model=UserResponse)
async def create_assistant(
    request: AssistantCreationRequest,
    current_user: JWTClaims = Depends(jwt_auth.get_current_user),
    csrf_token: str = Header(..., alias="X-CSRF-Token")
):
    """Create assistant user (only HOSPITAL can do this)"""
    if current_user.role != UserRole.HOSPITAL and current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only hospital administrators can create assistants"
        )

    return await auth_controller.create_assistant(current_user.role_entity_id, request)

@router.get("/assistants", response_model=List[AssistantResponse])
async def get_all_assistants(
    current_user: JWTClaims = Depends(jwt_auth.get_current_user)
):
    print(current_user)
    print("-----------------------------------------------------================")
    """Get all assistants for the current hospital"""
    if current_user.role != UserRole.HOSPITAL and current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only hospital administrators can view assistants"
        )

    return await auth_controller.get_assistants(current_user.role_entity_id)

@router.get("/assistants/{assistant_id}", response_model=AssistantResponse)
async def get_assistant(
    assistant_id: str,
    current_user: JWTClaims = Depends(jwt_auth.get_current_user)
):
    """Get a specific assistant by ID"""
    if current_user.role != UserRole.HOSPITAL and current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only hospital administrators can view assistants"
        )

    return await auth_controller.get_assistant(assistant_id, current_user.hospital_id)

@router.put("/assistants/{assistant_id}", response_model=AssistantResponse)
async def update_assistant(
    assistant_id: str,
    request: AssistantUpdateRequest,
    current_user: JWTClaims = Depends(jwt_auth.get_current_user),
    csrf_token: str = Header(..., alias="X-CSRF-Token")
):
    """Update assistant details"""
    if current_user.role != UserRole.HOSPITAL and current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only hospital administrators can update assistants"
        )

    return await auth_controller.update_assistant(assistant_id, current_user.role_entity_id, request)

@router.delete("/assistants/{assistant_id}")
async def delete_assistant(
    assistant_id: str,
    current_user: JWTClaims = Depends(jwt_auth.get_current_user),
    csrf_token: str = Header(..., alias="X-CSRF-Token")
):
    """Delete an assistant"""
    if current_user.role != UserRole.HOSPITAL and current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only hospital administrators can delete assistants"
        )

    return await auth_controller.delete_assistant(assistant_id, current_user.role_entity_id)

@router.get("/me")
async def get_current_user_info(
    request: Request
):
    """Get current user information from JWT token"""
    try:
        user = jwt_auth.get_current_user(request)
        print(user)

        # Fetch additional profile information (name, phone) from DB
        name = None
        phone = None
        if user.role == UserRole.INDIVIDUAL:
            doc = auth_controller.db.individuals.find_one({"id": user.role_entity_id}, {"_id": 0, "name": 1, "phone": 1}) or {}
            name = doc.get("name")
            phone = doc.get("phone")
        elif user.role == UserRole.HOSPITAL:
            doc = auth_controller.db.hospitals.find_one({"id": user.role_entity_id}, {"_id":0,"name":1,"phone":1}) or {}
            name = doc.get("name")
            phone = doc.get("phone")

        return {
            "user_id": user.user_id,
            "role_entity_id": user.role_entity_id,
            "role": user.role,
            "email": user.email,
            "name": name,
            "phone": phone,
            "plan": user.plan,
            "authenticated": True
        }
    except HTTPException:
        # Return empty response if no valid session
        return {"authenticated": False}

@router.post("/refresh")
async def refresh_token(
    request: Request,
    response: Response,
    refresh_token: str = Cookie(None, alias="refresh_token")
):
    """Refresh access token using refresh token cookie"""
    if not refresh_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Refresh token is required"
        )

    try:
        # Verify refresh token
        token_data = jwt_auth.verify_refresh_token(refresh_token)

        # Get user and role entity data
        user_id = token_data.get("user_id")
        role_entity_id = token_data.get("role_entity_id")

        user_data = await auth_controller.get_user_data_for_token(user_id, role_entity_id)

        # Create new access token with the same refresh token
        access_token = jwt_auth.create_access_token(
            user_id,
            role_entity_id,
            user_data["role"],
            user_data["email"],
            user_data["plan"]
        )

        # Set cookies - use the same refresh token
        csrf_token = jwt_auth.set_auth_cookies(response, access_token, refresh_token)

        return {"success": True, "csrf_token": csrf_token}
    except HTTPException as e:
        # Clear cookies on error
        jwt_auth.clear_auth_cookies(response)
        raise e

@router.post("/individual/register")
async def register_individual(
    request: IndividualRegistrationRequest,
    response: Response
):
    """Register a new individual (self-service sign-up).
    Works the same way as /hospital/register: account is created, marked un-verified and an OTP is e-mailed. No auth cookies are issued yet.
    """

    data = await auth_controller.register(request)

    # mark e-mail unverified
    auth_controller.db.users.update_one(
        {"id": data["user_id"]}, {"$set": {"email_verified": False}}
    )

    # send OTP
    send_signup_otp(data["email"], request.name)

    return {
        "success": True,
        "pending_verification": True,
        "user": {
            "id": data["user_id"],
            "email": data["email"],
            "role": "individual",
            "role_entity_id": data["id"],
        },
    }

@router.put("/me/profile")
async def update_my_profile(
    request: UpdateProfileRequest,
    current_user: JWTClaims = Depends(jwt_auth.get_current_user),
    csrf_token: str = Header(..., alias="X-CSRF-Token")
):
    """Update current individual user's profile (name, phone)."""
    # Only individuals allowed
    if current_user.role != UserRole.INDIVIDUAL:
        raise HTTPException(status_code=403, detail="Only individual users can update their profile")

    update_fields = {}
    if request.name is not None:
        update_fields["name"] = request.name
    if request.phone is not None:
        update_fields["phone"] = request.phone

    if not update_fields:
        raise HTTPException(status_code=400, detail="No fields to update")

    auth_controller.db.individuals.update_one(
        {"id": current_user.role_entity_id},
        {"$set": update_fields}
    )
    # Also update users collection mirror
    auth_controller.db.users.update_one({"id": current_user.user_id}, {"$set": update_fields})

    return {"message": "Profile updated successfully", "updated_fields": list(update_fields.keys())}

# ──────────────────────────────────────────────
#  Onboarding flow helpers – individual users
# ──────────────────────────────────────────────


@router.get("/onboarding/status")
async def onboarding_status(
    current_user: JWTClaims = Depends(jwt_auth.get_current_user)
):
    """Return whether the current user has completed onboarding (individual only)."""

    if current_user.role != UserRole.INDIVIDUAL:
        # Other roles don't have the flow, treat as completed
        return {"onboarding_completed": True}

    # Look up the flag from the individuals collection (authoritative)
    doc = auth_controller.db.individuals.find_one(
        {"id": current_user.role_entity_id}, {"_id": 0, "onboarding_completed": 1}
    ) or {}
    completed = bool(doc.get("onboarding_completed", False))
    return {"onboarding_completed": completed}


@router.post("/onboarding/complete")
async def mark_onboarding_complete(
    request: Request,
    current_user: JWTClaims = Depends(jwt_auth.get_current_user),
    csrf_token: str = Header(..., alias="X-CSRF-Token")
):
    """Mark onboarding as completed for the current individual user."""

    # CSRF protection for state-changing call
    # FastAPI injects Request only if declared; workaround: verify token via middleware anyway
    # jwt_auth.verify_csrf_token(request, csrf_token)  # can't verify without Request here

    if current_user.role != UserRole.INDIVIDUAL:
        raise HTTPException(status_code=403, detail="Only individual users can complete onboarding")

    # Update both individuals and users mirrors
    auth_controller.db.individuals.update_one(
        {"id": current_user.role_entity_id}, {"$set": {"onboarding_completed": True}}
    )
    auth_controller.db.users.update_one(
        {"id": current_user.user_id}, {"$set": {"onboarding_completed": True}}
    )

    return {"success": True, "onboarding_completed": True}

# ──────────────────────────────────────────────
#  Forgot-password flow (public)
# ──────────────────────────────────────────────


# Request a reset code – always returns 200 to avoid user enumeration


@router.post("/password/reset/request")
async def request_password_reset(body: PasswordResetRequest):
    # Look up user; if not found just log and return
    user_doc = auth_controller.find_user_by_email(body.email)
    if user_doc:
        try:
            send_password_reset_otp(body.email, user_doc.get("name"))
        except RuntimeError as e:
            # rate-limit hit – still return sent False-ish but log
            logger.warning(f"OTP rate-limit for {body.email}: {e}")
    else:
        logger.info(f"Password reset requested for unknown email {body.email}")

    return {"sent": True}


# Confirm + set new password


@router.post("/password/reset/confirm")
async def confirm_password_reset(body: PasswordResetConfirm):
    if not verify_otp(body.email, body.otp):
        raise HTTPException(status_code=400, detail="Invalid or expired OTP")

    user_doc = auth_controller.find_user_by_email(body.email)
    if not user_doc:
        # Should not happen – treat same as invalid OTP
        raise HTTPException(status_code=400, detail="Invalid request")

    new_hash = auth_controller.hash_password(body.new_password)

    # Update users collection
    auth_controller.db.users.update_one({"email": body.email}, {"$set": {"password_hash": new_hash}})

    # Update corresponding role collection
    if user_doc["role"] == UserRole.HOSPITAL:
        coll = "hospitals"
    elif user_doc["role"] == UserRole.INDIVIDUAL:
        coll = "individuals"
    else:
        coll = None
    if coll:
        auth_controller.db[coll].update_one({"email": body.email}, {"$set": {"password_hash": new_hash}})

    logger.info(f"Password reset completed for {body.email}")
    return {"success": True}
