# api_gateway/utils/helperFunctions.py
import uuid
import secrets
from datetime import datetime
from typing import Dict, Any

def generate_unique_id(prefix: str = "") -> str:
    """Generate unique ID with optional prefix"""
    unique_id = str(uuid.uuid4()).replace("-", "")[:12]
    return f"{prefix}_{unique_id}" if prefix else unique_id

def generate_api_key() -> str:
    """Generate secure API key"""
    return secrets.token_urlsafe(32)

def sanitize_input(data: Dict[str, Any]) -> Dict[str, Any]:
    """Sanitize input data"""
    if isinstance(data, dict):
        return {k: sanitize_input(v) if isinstance(v, (dict, list)) else str(v).strip()
                for k, v in data.items()}
    elif isinstance(data, list):
        return [sanitize_input(item) for item in data]
    return data

def format_datetime(dt: datetime) -> str:
    """Format datetime to ISO string"""
    return dt.isoformat()



# def validate_plan_permissions(plan_type: str, requested_services: list) -> bool:
#     """Validate if requested services are allowed for the plan"""
#     from ..src.auth.schema import PlanType
#     from ..src.auth.schema import BASE_PLAN_CONFIGS

#     plan_config = BASE_PLAN_CONFIGS.get(PlanType(plan_type))
#     if not plan_config:
#         return False

#     return all(service in plan_config.available_services for service in requested_services)


# -----------------------------------------
# Admin bootstrap helper
# -----------------------------------------

def ensure_default_admin():
    """Create a default platform admin account if none exists.

    The credentials are sourced from the environment once, then stored **only**
    in MongoDB (password hashed). Subsequent application runs will skip creation
    if an admin already exists.  This lets the single platform administrator
    log in through the standard /auth/login endpoint and access the admin
    dashboard, without having to hard-code credentials in the codebase or rely
    on environment look-ups at runtime.
    """
    from datetime import datetime
    # Local imports placed inside the function to avoid potential circular refs
    from api_gateway.database.db import get_database
    from api_gateway.src.auth.controller import AuthController
    from api_gateway.src.auth.schema import User, Hospital, HospitalStatus, UserRole
    from api_gateway.config import get_settings

    settings = get_settings()
    db = get_database()

    # Abort early if an admin account already exists
    if db.users.find_one({"role": UserRole.ADMIN.value}):
        return

    # Pull initial credentials from settings
    admin_email = settings.DEFAULT_ADMIN_EMAIL
    admin_password = settings.DEFAULT_ADMIN_PASSWORD

    auth = AuthController()

    # ------------------------------------------------------------------
    # Create a placeholder "system" entity for admin
    # ------------------------------------------------------------------
    system_id = generate_unique_id("system")

    system_entity = {
        "id": system_id,
        "name": "System",
        "email": admin_email,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
    }
    db.system_entities.insert_one(system_entity)

    # ------------------------------------------------------------------
    # Create the admin user linked to the system entity
    # ------------------------------------------------------------------
    admin_user_id = generate_unique_id("user")

    admin_user = User(
        id=admin_user_id,
        email=admin_email,
        password_hash=auth.hash_password(admin_password),
        name="Platform Admin",
        role=UserRole.ADMIN,
        role_entity_id=system_id,
        department="Administration",
        is_active=True,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.users.insert_one(admin_user.dict())

    # Log to console so operators know the credentials (only logged once)
    print(
        "[INIT] Created default admin user.\n"
        f"Email: {admin_email}\n"
        "Please log in immediately and change the password via the UI or an API call."
    )

# -----------------------------------------

