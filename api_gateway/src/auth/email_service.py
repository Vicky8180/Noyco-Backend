import ssl
import secrets
from datetime import datetime, timedelta
from email.message import EmailMessage
from typing import Optional

import smtplib
from passlib.context import CryptContext
from pymongo import MongoClient
from ...config import get_settings

# Get configuration
settings = get_settings()

# Configuration using settings instead of environment variables
SMTP_USER = settings.SMTP_GMAIL_USER
SMTP_PASS = settings.SMTP_GMAIL_PASS
OTP_TTL_MINUTES = settings.OTP_TTL

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# MongoDB client (sync)
client = MongoClient(settings.MONGODB_URI)
db = client[settings.DATABASE_NAME]
collection = db["email_otps"]


def _store_otp(email: str, otp_plain: str, *, purpose: str = "signup"):
    """Hash + store OTP for *purpose* (signup | password_reset).

    Simple abuse-protection: refuse if >5 unverified OTPs generated for the e-mail in the last hour.
    """

    cutoff = datetime.utcnow() - timedelta(hours=1)
    recent_count = collection.count_documents({
        "email": email,
        "created_at": {"$gte": cutoff},
    })
    if recent_count >= 5:
        raise RuntimeError("OTP rate limit exceeded. Please wait before requesting another code.")

    # Remove previous unverified OTPs for same purpose
    collection.delete_many({"email": email, "verified": False, "purpose": purpose})

    collection.insert_one({
        "email": email,
        "otp_hash": pwd_context.hash(otp_plain),
        "expires_at": datetime.utcnow() + timedelta(minutes=OTP_TTL_MINUTES),
        "verified": False,
        "purpose": purpose,
        "created_at": datetime.utcnow(),
    })


def _send_email(to_email: str, subject: str, body: str):
    if not SMTP_USER or not SMTP_PASS:
        raise RuntimeError("SMTP credentials not configured")
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = f"Noyco <{SMTP_USER}>"
    msg["To"] = to_email
    msg.set_content(body)

    context = ssl.create_default_context()
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context) as smtp:
        smtp.login(SMTP_USER, SMTP_PASS)
        smtp.send_message(msg)


def send_signup_otp(email: str, name: Optional[str] = ""):
    """Generate + e-mail a 6-digit OTP and persist it."""
    otp = f"{secrets.randbelow(1_000_000):06}"
    _store_otp(email, otp)

    body = (
        f"Hi {name or ''}\n\n"
        f"Your verification code (valid for {OTP_TTL_MINUTES} minutes) is:\n\n    {otp}\n\n"
        "If you didn't request this, you can ignore this e-mail.\n\n"
        "Noyco Team"
    )
    _send_email(email, "Your Noyco verification code", body)


# ──────────────────────────────────────────────────────────────
#  Password Reset – OTP generator (reuse same storage)
# ──────────────────────────────────────────────────────────────


def send_password_reset_otp(email: str, name: Optional[str] = "") -> None:
    """Generate an OTP for password-reset and e-mail it. Shares storage with signup OTPs but purpose is tracked via collection field."""

    otp = f"{secrets.randbelow(1_000_000):06}"

    # Persist with purpose flag to distinguish in logs/rate-limiting
    _store_otp(email, otp, purpose="password_reset")

    body = (
        f"Hi {name or ''}\n\n"
        f"Your password-reset code (valid for {OTP_TTL_MINUTES} minutes) is:\n\n    {otp}\n\n"
        "If you didn't request a password reset, you can safely ignore this e-mail.\n\n"
        "Noyco Team"
    )

    _send_email(email, "Reset your Noyco password", body)


def verify_otp(email: str, otp_plain: str) -> bool:
    """Return True if OTP is valid + mark verified, else False."""
    doc = collection.find_one({"email": email, "verified": False})
    if not doc:
        return False
    if doc["expires_at"] < datetime.utcnow():
        return False
    if not pwd_context.verify(otp_plain, doc["otp_hash"]):
        return False
    collection.update_one({"_id": doc["_id"]}, {"$set": {"verified": True}})
    return True
