from fastapi import Response, Request, HTTPException, status, Cookie, Header
from typing import Dict, Optional, Any
import secrets
from datetime import datetime, timedelta
import uuid
from jose import jwt, JWTError
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.backends import default_backend

if __name__ == "__main__" and __package__ is None:
    import sys
    from os import path
    sys.path.append(path.dirname(path.dirname(path.dirname(path.abspath(__file__)))))
    from api_gateway.src.auth.schema import UserRole, JWTClaims, PlanType
    from api_gateway.database.db import get_database
    from api_gateway.config import get_settings
else:
    from ..src.auth.schema import UserRole, JWTClaims, PlanType
    from ..database.db import get_database
    from ..config import get_settings

class JWTAuthController:
    """Comprehensive JWT authentication controller for handling tokens and cookies"""

    # Class-level singleton variables
    _instance = None
    _private_key = None
    _public_key = None
    _token_blocklist_global = set()

    def __new__(cls, *args, **kwargs):
        # Ensure only one instance exists (process-wide singleton)
        if cls._instance is None:
            cls._instance = super(JWTAuthController, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        # Prevent re-initialisation on subsequent instantiations
        if hasattr(self, "_initialised") and self._initialised:
            return

        # Get settings
        self.settings = get_settings()

        # Database connection
        self.db = get_database()

        # JWT settings from config
        self.algorithm = self.settings.JWT_ALGORITHM
        self.access_token_expire_minutes = self.settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES
        self.refresh_token_expire_days = self.settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS

        # Cookie settings from config
        self.secure_cookie = self.settings.COOKIE_SECURE
        self.cookie_domain = self.settings.COOKIE_DOMAIN
        self.cookie_samesite = self.settings.COOKIE_SAMESITE

        # Cookie names from config
        self.access_token_cookie = self.settings.JWT_ACCESS_TOKEN_COOKIE_NAME
        self.refresh_token_cookie = self.settings.JWT_REFRESH_TOKEN_COOKIE_NAME
        self.csrf_cookie_name = self.settings.JWT_CSRF_COOKIE_NAME

        # Token blocklist (shared across instances)
        self._token_blocklist = JWTAuthController._token_blocklist_global

        # Generate or load RSA keys (shared across instances)
        self._load_or_generate_keys()

        # Mark as initialised
        self._initialised = True

    def _load_or_generate_keys(self):
        """Load RSA keys from environment or generate new ones"""
        private_key_path = self.settings.JWT_PRIVATE_KEY_PATH
        public_key_path = self.settings.JWT_PUBLIC_KEY_PATH

        # Re-use already loaded keys if they exist
        if JWTAuthController._private_key and JWTAuthController._public_key:
            self.private_key = JWTAuthController._private_key
            self.public_key = JWTAuthController._public_key
            return

        import os
        if private_key_path and os.path.exists(private_key_path) and \
           public_key_path and os.path.exists(public_key_path):
            # Load keys from files
            with open(private_key_path, "rb") as f:
                self.private_key = serialization.load_pem_private_key(
                    f.read(),
                    password=None,
                    backend=default_backend()
                )

            with open(public_key_path, "rb") as f:
                self.public_key = serialization.load_pem_public_key(
                    f.read(),
                    backend=default_backend()
                )
        else:
            # Generate new key pair
            self.private_key = rsa.generate_private_key(
                public_exponent=65537,
                key_size=2048,
                backend=default_backend()
            )
            self.public_key = self.private_key.public_key()

            # Save keys if paths are provided
            if private_key_path and public_key_path:
                private_pem = self.private_key.private_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PrivateFormat.PKCS8,
                    encryption_algorithm=serialization.NoEncryption()
                )

                public_pem = self.public_key.public_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PublicFormat.SubjectPublicKeyInfo
                )

                import os
                os.makedirs(os.path.dirname(private_key_path), exist_ok=True)
                os.makedirs(os.path.dirname(public_key_path), exist_ok=True)

                with open(private_key_path, "wb") as f:
                    f.write(private_pem)

                with open(public_key_path, "wb") as f:
                    f.write(public_pem)

        # Cache keys at class level for future instances
        JWTAuthController._private_key = self.private_key
        JWTAuthController._public_key = self.public_key

    def create_access_token(self, user_id: str, role_entity_id: str, role: UserRole,
                          email: str, plan: Optional[Any]) -> str:
        """Create a JWT access token with minimal payload"""
        expire = datetime.utcnow() + timedelta(minutes=self.access_token_expire_minutes)

        # Minimal claims - no PHI
        claims = {
            "sub": user_id,  # Subject (user ID)
            "rid": role_entity_id,  # Role entity ID (hospital, admin, individual, etc)
            "rol": role.value if isinstance(role, UserRole) else role,  # Role
            "jti": str(uuid.uuid4()),  # JWT ID for revocation
            "exp": expire,  # Expiration
            "iat": datetime.utcnow(),  # Issued at
        }



        if email:
            claims["email"] = email

        if plan:
            claims["plan"] = plan.value if hasattr(plan, 'value') else plan

        # Sign with private key
        private_key_pem = self.private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption()
        )

        token = jwt.encode(claims, private_key_pem.decode('utf-8'), algorithm=self.algorithm)

        return token

    def create_refresh_token(self, user_id: str, role_entity_id: str) -> str:
        """Create a refresh token and store in database"""
        expire = datetime.utcnow() + timedelta(days=self.refresh_token_expire_days)
        token = secrets.token_urlsafe(32)

        # Store in database with expiry
        token_data = {
            "token": token,
            "user_id": user_id,
            "role_entity_id": role_entity_id,
            "expires_at": expire,
            "is_active": True,
            "created_at": datetime.utcnow()
        }

        self.db.refresh_tokens.insert_one(token_data)
        return token

    def verify_access_token(self, token: str) -> JWTClaims:
        """Verify JWT access token and check if it's not in blocklist"""
        try:
            # Check if token is in blocklist
            if self._is_token_revoked(token):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Token has been revoked"
                )

            # Verify token signature and expiration
            public_key_pem = self.public_key.public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo
            )

            payload = jwt.decode(
                token,
                public_key_pem.decode('utf-8'),
                algorithms=[self.algorithm]
            )

            # Map compact claims to full model
            return JWTClaims(
                user_id=payload["sub"],
                role_entity_id=payload["rid"],
                role=payload["rol"],
                email=payload.get("email", ""),
                plan=payload.get("plan"),
                exp=payload["exp"],
                iat=payload["iat"],
                jti=payload["jti"]
            )
        except JWTError as e:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Invalid token: {str(e)}"
            )

    def verify_refresh_token(self, token: str) -> Dict[str, Any]:
        """Verify refresh token from database"""
        # Find refresh token in database
        token_data = self.db.refresh_tokens.find_one({"token": token, "is_active": True})
        if not token_data:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid refresh token"
            )

        # Check if token is expired
        expires_at = token_data.get("expires_at")
        if expires_at and expires_at < datetime.utcnow():
            # Mark as inactive
            self.db.refresh_tokens.update_one(
                {"token": token},
                {"$set": {"is_active": False}}
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Refresh token expired"
            )

        return token_data

    def revoke_token(self, token: str, token_type: str = "access") -> None:
        """Add a token to the blocklist"""
        if token_type == "access":
            try:
                # Get token payload to extract jti and expiration
                public_key_pem = self.public_key.public_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PublicFormat.SubjectPublicKeyInfo
                )

                payload = jwt.decode(
                    token,
                    public_key_pem.decode('utf-8'),
                    algorithms=[self.algorithm]
                )

                jti = payload.get("jti")
                if jti:
                    self._token_blocklist.add(jti)
            except Exception:
                # Silently fail if token is invalid
                pass
        elif token_type == "refresh":
            # Mark refresh token as inactive in database
            self.db.refresh_tokens.update_one(
                {"token": token},
                {"$set": {"is_active": False}}
            )

    def _is_token_revoked(self, token: str) -> bool:
        """Check if a token is in the blocklist"""
        try:
            # Extract JTI from token
            public_key_pem = self.public_key.public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo
            )

            payload = jwt.decode(
                token,
                public_key_pem.decode('utf-8'),
                algorithms=[self.algorithm],
                options={"verify_exp": False}  # Don't check expiration here
            )

            jti = payload.get("jti")

            if not jti:
                return True  # No JTI, consider revoked

            # Check blocklist
            return jti in self._token_blocklist
        except Exception:
            return True  # Error parsing token, consider revoked

    def set_auth_cookies(self, response: Response, access_token: str, refresh_token: str) -> str:
        """Set secure httpOnly cookies for authentication and generate CSRF token"""
        csrf_token = secrets.token_urlsafe(32)

        # Access token cookie - short lived, httpOnly
        response.set_cookie(
            key=self.access_token_cookie,
            value=access_token,
            httponly=True,
            secure=self.secure_cookie,
            samesite=self.cookie_samesite,
            domain=self.cookie_domain,
            max_age=self.access_token_expire_minutes * 60,
            path="/"
        )

        # Refresh token cookie - long lived, httpOnly
        response.set_cookie(
            key=self.refresh_token_cookie,
            value=refresh_token,
            httponly=True,
            secure=self.secure_cookie,
            samesite=self.cookie_samesite,
            domain=self.cookie_domain,
            max_age=self.refresh_token_expire_days * 24 * 60 * 60,
            path="/"
        )

        # CSRF token cookie - accessible to JavaScript
        response.set_cookie(
            key=self.csrf_cookie_name,
            value=csrf_token,
            httponly=False,
            secure=self.secure_cookie,
            samesite=self.cookie_samesite,
            domain=self.cookie_domain,
            max_age=self.access_token_expire_minutes * 60,
            path="/"
        )

        return csrf_token

    def clear_auth_cookies(self, response: Response):
        """Clear all authentication cookies"""
        response.delete_cookie(
            key=self.access_token_cookie,
            path="/",
            domain=self.cookie_domain,
            secure=self.secure_cookie,
            httponly=True
        )

        response.delete_cookie(
            key=self.refresh_token_cookie,
            path="/",
            domain=self.cookie_domain,
            secure=self.secure_cookie,
            httponly=True
        )

        response.delete_cookie(
            key=self.csrf_cookie_name,
            path="/",
            domain=self.cookie_domain,
            secure=self.secure_cookie
        )

    def get_current_user(self, request: Request) -> JWTClaims:
        """Get current user from access token cookie"""
        access_token = request.cookies.get(self.access_token_cookie)

        # If not in cookie, check Authorization header
        if not access_token and "Authorization" in request.headers:
            auth_header = request.headers["Authorization"]
            if auth_header.startswith("Bearer "):
                access_token = auth_header.replace("Bearer ", "")

        if not access_token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required"
            )

        return self.verify_access_token(access_token)

    def verify_csrf_token(self, request: Request, csrf_token: str) -> bool:
        """Verify CSRF token matches the one in cookie"""
        cookie_csrf = request.cookies.get(self.csrf_cookie_name)

        if not csrf_token or not cookie_csrf or csrf_token != cookie_csrf:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="CSRF token validation failed"
            )

        return True
