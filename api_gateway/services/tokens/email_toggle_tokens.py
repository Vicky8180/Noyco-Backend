from __future__ import annotations
from datetime import datetime, timedelta, timezone
from typing import Dict, Tuple
import jwt

from api_gateway.config import get_settings

ALGO = "HS256"

class InvalidToken(Exception):
    pass

class ExpiredToken(Exception):
    pass


def _settings_secret() -> str:
    settings = get_settings()
    if not settings.EMAIL_TOGGLE_SECRET:
        # Fall back to JWT_SECRET_KEY to avoid hard failure in dev, but recommend setting dedicated secret
        if getattr(settings, "JWT_SECRET_KEY", None):
            return settings.JWT_SECRET_KEY
        raise InvalidToken("EMAIL_TOGGLE_SECRET is not configured")
    return settings.EMAIL_TOGGLE_SECRET


def _encode(payload: Dict) -> str:
    secret = _settings_secret()
    return jwt.encode(payload, secret, algorithm=ALGO)


def _decode(token: str) -> Dict:
    secret = _settings_secret()
    try:
        return jwt.decode(token, secret, algorithms=[ALGO])
    except jwt.ExpiredSignatureError:
        raise ExpiredToken("Token expired")
    except Exception as e:
        raise InvalidToken(str(e))


def create_opt_in_token(user_id: str, exp: datetime | None = None) -> str:
    if exp is None:
        exp = datetime.now(timezone.utc) + timedelta(days=7)
    payload = {"sub": user_id, "act": "opt_in", "exp": int(exp.timestamp())}
    return _encode(payload)


def create_opt_out_token(user_id: str, exp: datetime | None = None) -> str:
    if exp is None:
        exp = datetime.now(timezone.utc) + timedelta(days=90)
    payload = {"sub": user_id, "act": "opt_out", "exp": int(exp.timestamp())}
    return _encode(payload)


def validate_token(token: str) -> Tuple[str, str]:
    """Returns (user_id, action) where action in {opt_in, opt_out}."""
    data = _decode(token)
    user_id = data.get("sub")
    action = data.get("act")
    if not user_id or action not in {"opt_in", "opt_out"}:
        raise InvalidToken("Invalid payload")
    return user_id, action
