
# api_gateway/src/auth/routes.py
from fastapi import APIRouter, Depends, HTTPException, status, Response, Request, Header, Cookie
from .controller import AuthController
from ...middlewares.jwt_auth import JWTAuthController
from .schema import *
from datetime import datetime, timedelta
import uuid
from typing import List
from .email_service import send_signup_otp, send_password_reset_otp, verify_otp, test_smtp_connection, send_test_email
# Logging
import logging
logger = logging.getLogger("auth.password_reset")

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["Authentication"])

auth_controller = AuthController()
jwt_auth = JWTAuthController()
try:
    from ...config import get_settings
    _settings = get_settings()
except Exception:
    _settings = None

@router.post("/register")  # Changed from "/hospital/register" to just "/register"
async def register_user(  # Changed function name
    request: RegistrationRequest,
    response: Response
):
    """Register a new individual user. No auth cookies are issued until e-mail is verified."""
    # Only individual registration is supported now
    if request.type != RegistrationType.INDIVIDUAL:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only individual registration is supported"
        )
    
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
            "role": "individual",  # Always individual now
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

@router.post("/google/login")
async def google_login(request: Request, response: Response):
    """Login with Google ID token (Option 2: exchange for our JWT).

    Body: { id_token: string }
    Verifies Google token, upserts user as Individual if needed, issues our cookies.
    """
    try:
        body = await request.json()
        id_token_str = body.get("id_token")
        if not id_token_str:
            raise HTTPException(status_code=400, detail="Missing id_token")

        # Ensure GOOGLE_CLIENT_ID configured
        if not _settings or not _settings.GOOGLE_CLIENT_ID:
            raise HTTPException(status_code=500, detail="Google auth not configured")

        # Verify the Google ID token
        try:
            from google.oauth2 import id_token as google_id_token
            from google.auth.transport import requests as google_requests
        except ImportError as e:
            logger.error(f"Google auth library not available: {str(e)}")
            raise HTTPException(status_code=500, detail="google-auth library not installed")

        try:
            # Create request instance
            google_request = google_requests.Request()
            
            # Verify with clock skew tolerance
            g_payload = google_id_token.verify_oauth2_token(
                id_token_str,
                google_request,
                _settings.GOOGLE_CLIENT_ID,
                clock_skew_in_seconds=300  # Allow 5 minutes clock skew
            )
        except ValueError as e:
            logger.error(f"Google token verification failed: {str(e)}")
            # Return more user-friendly error messages
            error_msg = str(e)
            if "Token used too early" in error_msg:
                raise HTTPException(status_code=401, detail="Clock synchronization issue. Please try again in a moment.")
            elif "Token used too late" in error_msg:
                raise HTTPException(status_code=401, detail="Token expired. Please sign in again.")
            elif "Invalid token" in error_msg:
                raise HTTPException(status_code=401, detail="Invalid Google token. Please sign in again.")
            else:
                raise HTTPException(status_code=401, detail="Google authentication failed. Please try again.")
        except Exception as e:
            logger.error(f"Unexpected error during Google token verification: {str(e)}")
            raise HTTPException(status_code=500, detail="Authentication service temporarily unavailable.")

        issuer = g_payload.get("iss")
        if issuer not in {"accounts.google.com", "https://accounts.google.com"}:
            raise HTTPException(status_code=401, detail="Invalid token issuer")

        email_verified = g_payload.get("email_verified", False)
        if not email_verified:
            raise HTTPException(status_code=401, detail="Google email not verified")

        email = g_payload.get("email")
        name = g_payload.get("name") or (email.split("@")[0] if email else None)
        if not email:
            raise HTTPException(status_code=400, detail="Google token missing e-mail")

        # Upsert user: users + individuals
        user_doc = auth_controller.find_user_by_email(email)
        if not user_doc:
            created_at = datetime.utcnow()
            individual_id = f"individual_{uuid.uuid4().hex[:12]}"
            individual = {
                "id": individual_id,
                "name": name or email,
                "email": email,
                "password_hash": "",  # password-less account (Google)
                "phone": "Not provided",
                "created_at": created_at,
                "updated_at": created_at,
                "onboarding_completed": False,
            }
            auth_controller.db.individuals.insert_one(individual)

            user_id = f"user_{uuid.uuid4().hex[:12]}"
            user = {
                "id": user_id,
                "email": email,
                "password_hash": "",  # password-less
                "name": name or email,
                "role": UserRole.INDIVIDUAL.value,
                "role_entity_id": individual_id,
                "department": None,
                "is_active": True,
                "email_verified": True,  # Verified by Google
                "created_at": created_at,
                "updated_at": created_at,
                "last_login": created_at,
            }
            auth_controller.db.users.insert_one(user)
            user_doc = user
        else:
            # Ensure account is active and mark verified
            if not user_doc.get("is_active", True):
                raise HTTPException(status_code=401, detail="Account is deactivated")
            auth_controller.db.users.update_one(
                {"id": user_doc["id"]},
                {"$set": {"email_verified": True, "updated_at": datetime.utcnow(), "last_login": datetime.utcnow()}},
            )

        # Determine plan via role entity
        role = UserRole(user_doc["role"]) if isinstance(user_doc.get("role"), str) else user_doc.get("role")
        role_entity_id = user_doc["role_entity_id"]
        plan_type = None
        if role == UserRole.INDIVIDUAL:
            ind = auth_controller.db.individuals.find_one({"id": role_entity_id})
            plan = ind.get("plan") if ind else None
            try:
                plan_type = PlanType(plan) if plan else None
            except Exception:
                plan_type = None

        # Issue our cookies
        access_token = jwt_auth.create_access_token(
            user_doc["id"],
            role_entity_id,
            role,
            email,
            plan_type,
        )
        refresh_token = jwt_auth.create_refresh_token(user_doc["id"], role_entity_id)
        csrf_token = jwt_auth.set_auth_cookies(response, access_token, refresh_token)

        # Add CORS headers explicitly for Google auth
        origin = request.headers.get("origin")
        if origin in ["http://localhost:3000", "http://127.0.0.1:3000"]:
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Access-Control-Allow-Credentials"] = "true"

        return {
            "success": True,
            "user": {
                "id": user_doc["id"],
                "email": email,
                "role": role.value if isinstance(role, UserRole) else role,
                "role_entity_id": role_entity_id,
            },
            "csrf_token": csrf_token,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Google login failed: %s", e)
        raise HTTPException(status_code=500, detail="Google login failed")

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
    """Create assistant user (only INDIVIDUAL can do this)"""
    if current_user.role != UserRole.INDIVIDUAL and current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only individual users can create assistants"
        )

    return await auth_controller.create_assistant(current_user.role_entity_id, request)

@router.get("/assistants", response_model=List[AssistantResponse])
async def get_all_assistants(
    current_user: JWTClaims = Depends(jwt_auth.get_current_user)
):
    print(current_user)
    print("-----------------------------------------------------================")
    """Get all assistants for the current individual"""
    if current_user.role != UserRole.INDIVIDUAL and current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only individual users can view assistants"
        )

    return await auth_controller.get_assistants(current_user.role_entity_id)

@router.get("/assistants/{assistant_id}", response_model=AssistantResponse)
async def get_assistant(
    assistant_id: str,
    current_user: JWTClaims = Depends(jwt_auth.get_current_user)
):
    """Get a specific assistant by ID"""
    if current_user.role != UserRole.INDIVIDUAL and current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only individual users can view assistants"
        )

    return await auth_controller.get_assistant(assistant_id, current_user.role_entity_id)

@router.put("/assistants/{assistant_id}", response_model=AssistantResponse)
async def update_assistant(
    assistant_id: str,
    request: AssistantUpdateRequest,
    current_user: JWTClaims = Depends(jwt_auth.get_current_user),
    csrf_token: str = Header(..., alias="X-CSRF-Token")
):
    """Update assistant details"""
    if current_user.role != UserRole.INDIVIDUAL and current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only individual users can update assistants"
        )

    return await auth_controller.update_assistant(assistant_id, current_user.role_entity_id, request)

@router.delete("/assistants/{assistant_id}")
async def delete_assistant(
    assistant_id: str,
    current_user: JWTClaims = Depends(jwt_auth.get_current_user),
    csrf_token: str = Header(..., alias="X-CSRF-Token")
):
    """Delete an assistant"""
    if current_user.role != UserRole.INDIVIDUAL and current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only individual users can delete assistants"
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

        # Fetch additional profile information (name, phone, password status) from DB
        name = None
        phone = None
        has_password = False
        if user.role == UserRole.INDIVIDUAL:
            doc = auth_controller.db.individuals.find_one({"id": user.role_entity_id}, {"_id": 0, "name": 1, "phone": 1}) or {}
            name = doc.get("name")
            phone = doc.get("phone")
            
            # Check if user has a password (non-OAuth user)
            user_doc = auth_controller.db.users.find_one({"id": user.user_id}, {"_id": 0, "password_hash": 1})
            has_password = bool(user_doc and user_doc.get("password_hash", "").strip())
        # Hospital role removed - no longer supported

        return {
            "user_id": user.user_id,
            "role_entity_id": user.role_entity_id,
            "role": user.role,
            "email": user.email,
            "name": name,
            "phone": phone,
            "plan": user.plan,
            "authenticated": True,
            "has_password": has_password
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
    Works the same way as /register: account is created, marked un-verified and an OTP is e-mailed. No auth cookies are issued yet.
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
    if user_doc["role"] == UserRole.INDIVIDUAL:
        coll = "individuals"
    else:
        coll = None  # HOSPITAL role no longer supported
    if coll:
        auth_controller.db[coll].update_one({"email": body.email}, {"$set": {"password_hash": new_hash}})

    logger.info(f"Password reset completed for {body.email}")
    return {"success": True}


# ──────────────────────────────────────────────────────────────
#  SMTP Testing Routes (for Zoho Mail migration)
# ──────────────────────────────────────────────────────────────

@router.get("/smtp/test-connection")
async def test_smtp_connection_route():
    """Test SMTP connection to Zoho Mail server."""
    result = test_smtp_connection()
    if result["success"]:
        return {"status": "success", "message": result["message"]}
    else:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=result["error"]
        )

# ──────────────────────────────────────────────
#  Combined: Verify OTP + set password + issue cookies (public)
# ──────────────────────────────────────────────

class VerifyAndSetPasswordBody(BaseModel):
    email: EmailStr
    otp: str = Field(..., min_length=6, max_length=6)
    password: str

    _validate_pwd = validator("password", allow_reuse=True)(password_validator)


@router.post("/verify-otp-and-set-password")
async def verify_otp_and_set_password(
    body: VerifyAndSetPasswordBody,
    response: Response
):
    """Public endpoint for funnel: verify OTP, set password, mark verified, and issue JWT cookies for auto-login."""
    # Verify OTP first
    if not verify_otp(body.email, body.otp):
        raise HTTPException(status_code=400, detail="Invalid or expired OTP")

    # Find user
    user_doc = auth_controller.find_user_by_email(body.email)
    if not user_doc:
        raise HTTPException(status_code=400, detail="Account not found")

    # Set password
    new_hash = auth_controller.hash_password(body.password)
    auth_controller.db.users.update_one({"email": body.email}, {"$set": {"password_hash": new_hash, "email_verified": True, "updated_at": datetime.utcnow()}})

    # Also update role collection mirror
    role = user_doc.get("role")
    role_entity_id = user_doc.get("role_entity_id")
    if role == UserRole.INDIVIDUAL.value:
        auth_controller.db.individuals.update_one({"email": body.email}, {"$set": {"password_hash": new_hash, "updated_at": datetime.utcnow()}})

    # Issue cookies for auto-login
    plan_type = None
    if role == UserRole.INDIVIDUAL.value and role_entity_id:
        ind = auth_controller.db.individuals.find_one({"id": role_entity_id})
        plan = ind.get("plan") if ind else None
        try:
            plan_type = PlanType(plan) if plan else None
        except Exception:
            plan_type = None

    access_token = jwt_auth.create_access_token(
        user_doc["id"],
        role_entity_id,
        UserRole(role) if isinstance(role, str) else role,
        body.email,
        plan_type,
    )
    refresh_token = jwt_auth.create_refresh_token(user_doc["id"], role_entity_id)
    csrf_token = jwt_auth.set_auth_cookies(response, access_token, refresh_token)

    return {
        "success": True,
        "user": {
            "id": user_doc["id"],
            "email": body.email,
            "role": role,
            "role_entity_id": role_entity_id,
        },
        "csrf_token": csrf_token,
    }


@router.post("/smtp/send-test-email")
async def send_test_email_route(
    request: Request,
    current_user: JWTClaims = Depends(jwt_auth.get_current_user),
    csrf_token: str = Header(..., alias="X-CSRF-Token")
):
    """Send a test email to verify SMTP configuration. Requires authentication."""
    body = await request.json()
    to_email = body.get("email")
    
    if not to_email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email address is required"
        )
    
    result = send_test_email(to_email)
    if result["success"]:
        return {"status": "success", "message": result["message"]}
    else:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=result["error"]
        )
