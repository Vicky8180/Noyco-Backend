from pydantic import BaseModel, EmailStr, HttpUrl, validator, Field
from typing import Optional, List, Literal
from enum import Enum
from datetime import datetime


# ----- Enums -----
class PlanType(str, Enum):
    LITE = "lite"
    PRO = "pro"
    PREMIUM = "premium"

class UserRole(str, Enum):
    ADMIN = "admin"
    HOSPITAL = "hospital"
    ASSISTANT = "assistant"
    INDIVIDUAL = "individual"
class RegistrationType(str, Enum):
    ORGANIZATION = "organization"
    INDIVIDUAL = "individual"
class HospitalStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    SUSPENDED = "suspended"
    PENDING = "pending"

# ----- Validators -----
def password_validator(v: str) -> str:
    if len(v) < 8:
        raise ValueError('Password must be at least 8 characters long')
    if not any(c.isupper() for c in v):
        raise ValueError('Password must contain at least one uppercase letter')
    if not any(c.islower() for c in v):
        raise ValueError('Password must contain at least one lowercase letter')
    if not any(c.isdigit() for c in v):
        raise ValueError('Password must contain at least one digit')
    return v

# ----- Request Models -----
class RegistrationRequest(BaseModel):
    email: EmailStr
    password: str
    name: str
    phone: Optional[str] = None
    website_link: Optional[HttpUrl] = None
    plan: Optional[PlanType] = None
    admin_name: Optional[str] = None
    type: RegistrationType

    _validate_password = validator('password', allow_reuse=True)(password_validator)

class AssistantCreationRequest(BaseModel):
    email: EmailStr
    password: str
    name: str
    department: Optional[str] = None
    phone: Optional[str] = None

    _validate_password = validator('password', allow_reuse=True)(password_validator)

class IndividualRegistrationRequest(BaseModel):
    email: EmailStr
    password: str
    name: str
    phone: Optional[str] = None
    plan: Optional[PlanType] = None
    type: Literal["individual"] = "individual"

    _validate_password = validator('password', allow_reuse=True)(password_validator)

class LoginRequest(BaseModel):
    email: str
    password: str

    @validator("email")
    def validate_email_basic(cls, v: str) -> str:
        if "@" not in v or v.startswith("@") or v.endswith("@"):  # basic guard
            raise ValueError("Invalid email address")
        return v.strip()

# ──────────────────────────────────────────────
#  Forgot-password models
# ──────────────────────────────────────────────


class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordResetConfirm(BaseModel):
    email: EmailStr
    otp: str = Field(..., min_length=6, max_length=6)
    new_password: str

    _validate_pwd = validator("new_password", allow_reuse=True)(password_validator)

class PasswordUpdateRequest(BaseModel):
    current_password: str
    new_password: str

    _validate_new_password = validator('new_password', allow_reuse=True)(password_validator)

class UserCreationRequest(BaseModel):
    email: EmailStr
    password: str
    name: str
    role: UserRole
    role_entity_id: str  # links to Admin/Hospital/Assistant/Individual
    department: Optional[str] = None

    _validate_password = validator('password', allow_reuse=True)(password_validator)

# ----- Request Models for Updates -----
class AssistantUpdateRequest(BaseModel):
    email: EmailStr
    name: str
    department: Optional[str] = None
    phone: Optional[str] = None
    password: Optional[str] = None  # Optional – only send when changing

    @validator('password')
    def validate_password_optional(cls, v):
        if v is None or v == "":
            return v  # Skip validation if not provided
        return password_validator(v)

class UpdateProfileRequest(BaseModel):
    """Request model for updating basic profile details of an individual user"""
    name: Optional[str] = None
    phone: Optional[str] = None

    @validator("phone")
    def validate_phone(cls, v):
        if v is None:
            return v
        import re
        phone_pattern = re.compile(r"^\+?[0-9]{10,15}$")
        if not phone_pattern.match(v):
            raise ValueError("Invalid phone number format. Expecting 10-15 digits, optional leading '+'.")
        return v

# ----- Response Models -----
class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int

class HospitalResponse(BaseModel):
    id: str
    hospital_name: str
    email: EmailStr
    phone: Optional[str]
    website_link: Optional[HttpUrl]
    plan: PlanType
    status: HospitalStatus
    created_at: datetime
    updated_at: datetime

class IndividualResponse(BaseModel):
    id: str
    name: str
    email: EmailStr
    phone: Optional[str]
    plan: Optional[PlanType]
    status: HospitalStatus
    created_at: datetime
    updated_at: datetime

class UserResponse(BaseModel):
    id: str
    email: EmailStr
    name: str
    role: UserRole
    role_entity_id: str  # Links to Hospital, Assistant, Individual, etc.
    department: Optional[str]
    is_active: bool
    created_at: datetime
    updated_at: datetime

class AssistantResponse(BaseModel):
    id: str
    email: EmailStr
    name: str
    phone: Optional[str]
    department: Optional[str]
    hospital_id: str
    is_active: bool
    created_at: datetime
    updated_at: datetime




# ----- Database Models -----
class Hospital(BaseModel):
    id: str
    name: str
    email: EmailStr
    password_hash: str
    phone: Optional[str]
    website_link: Optional[HttpUrl]
    plan: Optional[PlanType] = None
    status: HospitalStatus = HospitalStatus.ACTIVE
    onboarding_completed: bool = False  # Indicates if onboarding flow is finished
    created_at: datetime
    updated_at: datetime

class Individual(BaseModel):
    id: str
    name: str
    email: EmailStr
    password_hash: str
    phone: Optional[str]
    plan: Optional[PlanType] = None
    status: HospitalStatus = HospitalStatus.ACTIVE
    onboarding_completed: bool = False
    created_at: datetime
    updated_at: datetime

class User(BaseModel):
    id: str
    email: EmailStr
    password_hash: str
    name: str
    role: UserRole
    role_entity_id: str
    department: Optional[str]
    is_active: bool = True
    onboarding_completed: bool = False
    created_at: datetime
    updated_at: datetime
    last_login: Optional[datetime] = None

class Assistant(BaseModel):
    id: str
    name: str
    email: EmailStr
    phone: Optional[str]
    department: Optional[str]
    hospital_id: str
    is_active: bool = True
    created_at: datetime
    updated_at: datetime

class RefreshToken(BaseModel):
    token: str
    user_id: str
    role_entity_id: str
    expires_at: datetime
    is_active: bool = True





# ----- Permissions -----
Resource = Literal[
    "hospital", "assistant", "individual", "user", "plan", "token"
]
Action = Literal[
    "create", "read", "update", "delete", "list"
]

class Permission(BaseModel):
    resource: Resource
    action: Action

class RolePermissions(BaseModel):
    role: UserRole
    permissions: List[Permission]

# ----- JWT Claims -----
class JWTClaims(BaseModel):
    user_id: str
    role_entity_id: str
    role: UserRole
    email: EmailStr
    plan: Optional[PlanType] = None
    exp: int
    iat: int
    jti: str
