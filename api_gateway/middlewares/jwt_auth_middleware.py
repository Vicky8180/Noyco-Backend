from fastapi import Request, HTTPException, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from .jwt_auth import JWTAuthController
from ..src.auth.schema import UserRole

class JWTAuthMiddleware(BaseHTTPMiddleware):
    """Middleware for JWT authentication with httpOnly cookies"""

    def __init__(self, app):
        super().__init__(app)
        self.jwt_auth = JWTAuthController()

        # Routes that don't require authentication (use prefix matching)
        self.public_routes = {
            "/",
            # "/api/call",
            # "/api/calls/active",
            # "/auth/hospital/register",
            "/auth/individual/register",
            "/auth/login",
            "/auth/me",
            "/auth/refresh",
            "/docs",
            "/redoc",
            "/openapi.json",
            "/health",
            "/marketing",
            "/marketing/about",
            "/marketing/features",
            "/marketing/pricing",
            "/marketing/blog",
            "/marketing/contact",
            "/marketing/privacy",
            "/static",
            # "/patients",
            # "/phone/generate",
            # "/phone/config/{hospital_id}",
            # "/phone/call",
            # "/phone/voice",
            # "/phone/forward-webhook",
            # "/phone/status",
            # "/phone/stream",
            # "/phone/gather-response",  # Twilio gather endpoint without query params
            # "/phone/orchestrator-response",
            # "/schedule/create",
            # "/schedule/stats",
            "/billing/plans",
            "/orchestrate",
            # "/api/patients",
            "/stripe/webhook",  # allow Stripe to POST webhooks without auth
            "/voice-widget",  # allow voice widget endpoints (embed/js/iframe/session)
            "/.well-known",  # chrome devtools fetches
            "/individual/mediscan/patients",  # allow fetching patients without auth
            # "/api/fhir/upload-csv",
            "/auth/otp" , # ← add this to allow all OTP endpoints without auth
            "/chat",
            "/initial/chat",
            "/user-profile",  # Allow all user profile endpoints without authentication
            # "/phone/test-verification",
            "/user-profile/goals",  # Allow all goal endpoints without authentication
            "/auth/password/reset/request",
            "/auth/password/reset/confirm",
            "/api/v1/livekit",  # Allow LiveKit voice assistant endpoints without authentication
            "/api/v1/voice"     # Allow professional voice assistant endpoints without authentication
        }

        self.csrf_protected_routes = {
            "/auth/logout",
            "/auth/password/update",
            "/auth/users",
            "/auth/assistants",
            "/billing/plan/select",
            "/billing/services/select",
            "/individual/mediscan/ocr",
                #   "/phone/config"
            # "/billing/plan/current",  # Removed CSRF requirement for GET endpoint
        }

        self.service_routes = {
            "/orchestrator": "orchestrator",
            "/memory": "memory",
            "/detector": "detector",
            "/checkpoint": "checkpoint",
            "/billing": "billing",
            "/individual/mediscan": "mediscan"  # Add MediScan route
        }
        self.service_routes["/stripe"] = "stripe"

    async def dispatch(self, request: Request, call_next):
        if request.method == "OPTIONS":
            return await call_next(request)

        path = request.url.path
        
        # ✅ Allow public routes via exact or prefix match
        # For Twilio webhooks like gather-response, we need to match the base path ignoring query params
        if any(path == route or path.startswith(route + "/") for route in self.public_routes):
            return await call_next(request)

        access_token = request.cookies.get(self.jwt_auth.access_token_cookie)
        if not access_token:
            if request.headers.get("Authorization"):
                return await call_next(request)

            refresh_token = request.cookies.get(self.jwt_auth.refresh_token_cookie)
            if refresh_token and path != "/auth/refresh":
                # 🛠️ Attempt silent refresh when access token is missing but refresh token exists
                try:
                    token_data = self.jwt_auth.verify_refresh_token(refresh_token)
                    from api_gateway.src.auth.controller import AuthController
                    auth_controller = AuthController()
                    user_id = token_data.get("user_id")
                    role_entity_id = token_data.get("role_entity_id")
                    user_data = await auth_controller.get_user_data_for_token(user_id, role_entity_id)

                    new_access_token = self.jwt_auth.create_access_token(
                        user_id,
                        role_entity_id,
                        user_data["role"],
                        user_data["email"],
                        user_data.get("plan")
                    )

                    # 🔥 CRITICAL: Set user context for downstream handlers
                    new_user = self.jwt_auth.verify_access_token(new_access_token)
                    request.state.user = new_user

                    # Handle CSRF token validation if required
                    if path in self.csrf_protected_routes or request.method in ["POST", "PUT", "DELETE", "PATCH"]:
                        csrf_token = request.headers.get("X-CSRF-Token")
                        if not csrf_token:
                            return JSONResponse(
                                status_code=status.HTTP_403_FORBIDDEN,
                                content={"detail": "CSRF token required"}
                            )
                        # Note: CSRF validation will happen after refresh, using new token in cookies

                    # Check permissions before proceeding
                    if not await self.check_service_permission(request, new_user):
                        return JSONResponse(
                            status_code=status.HTTP_403_FORBIDDEN,
                            content={"detail": "Insufficient permissions for this service"}
                        )

                    # Proceed with original request and set fresh cookies
                    response = await call_next(request)
                    self.jwt_auth.set_auth_cookies(response, new_access_token, refresh_token)

                    return response
                except HTTPException:
                    # Fall through and return 401 below
                    pass

            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"detail": "Authentication required"}
            )

        try:
            user = self.jwt_auth.verify_access_token(access_token)

            if path in self.csrf_protected_routes or request.method in ["POST", "PUT", "DELETE", "PATCH"]:
                csrf_token = request.headers.get("X-CSRF-Token")
                if not csrf_token:
                    return JSONResponse(
                        status_code=status.HTTP_403_FORBIDDEN,
                        content={"detail": "CSRF token required"}
                    )

                try:
                    self.jwt_auth.verify_csrf_token(request, csrf_token)
                except HTTPException as e:
                    return JSONResponse(
                        status_code=e.status_code,
                        content={"detail2": e.detail}
                    )

            request.state.user = user

            if not await self.check_service_permission(request, user):
                return JSONResponse(
                    status_code=status.HTTP_403_FORBIDDEN,
                    content={"detail": "Insufficient permissions for this service"}
                )

            return await call_next(request)

        except HTTPException as e:
            # 🚀 Automatic access token refresh using refresh token cookie
            if (
                e.status_code == status.HTTP_401_UNAUTHORIZED
                and request.cookies.get(self.jwt_auth.refresh_token_cookie)
            ):
                refresh_token = request.cookies.get(self.jwt_auth.refresh_token_cookie)

                try:
                    # 1️⃣ Verify refresh token (raises if invalid / expired)
                    token_data = self.jwt_auth.verify_refresh_token(refresh_token)

                    # 2️⃣ Fetch latest user data (role / email / plan) on-the-fly
                    from api_gateway.src.auth.controller import AuthController  # Local import to avoid circular deps

                    auth_controller = AuthController()
                    user_id = token_data.get("user_id")
                    role_entity_id = token_data.get("role_entity_id")

                    user_data = await auth_controller.get_user_data_for_token(
                        user_id, role_entity_id
                    )

                    # 3️⃣ Issue new access token and attach refreshed cookies
                    new_access_token = self.jwt_auth.create_access_token(
                        user_id,
                        role_entity_id,
                        user_data["role"],
                        user_data["email"],
                        user_data.get("plan"),
                    )

                    # Re-verify to obtain claims & attach to request for downstream handlers
                    new_user = self.jwt_auth.verify_access_token(new_access_token)
                    request.state.user = new_user

                    # Proceed with original request and set fresh cookies on outgoing response
                    response = await call_next(request)
                    self.jwt_auth.set_auth_cookies(response, new_access_token, refresh_token)

                    return response

                except HTTPException:
                    # Fall through to standard 401 handling below
                    pass

            # This block is now redundant - the refresh logic above handles this case
            # Keeping for any edge cases not covered above

            return JSONResponse(
                status_code=e.status_code,
                content={"detail1": e.detail}
            )

        except Exception as e:
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content={"detail": f"Internal server error: {str(e)}"}
            )

    async def check_service_permission(self, request: Request, user) -> bool:
        path = request.url.path

        service = None
        for route_prefix, service_name in self.service_routes.items():
            if path.startswith(route_prefix):
                service = service_name
                break

        if not service:
            return True

        if user.role == UserRole.ADMIN:
            return True

        # if user.role == UserRole.HOSPITAL:
        #     return True

        if user.role == UserRole.INDIVIDUAL:
            # Allow individuals to access billing and mediscan services
            if service in ["billing", "mediscan"]:
               return True

        if service == "billing":
            return user.role in [UserRole.ADMIN, UserRole.INDIVIDUAL]

        if service in ["orchestrator", "detector", "checkpoint", "memory"]:
            return user.role in [UserRole.ADMIN, UserRole.ASSISTANT]
            
        if service == "mediscan":
            return user.role == UserRole.INDIVIDUAL

        if service == "stripe":
            return user.role in [UserRole.ADMIN, UserRole.INDIVIDUAL]

        return False
