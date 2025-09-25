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
SMTP_USER = settings.SMTP_ZOHO_USER
SMTP_PASS = settings.SMTP_ZOHO_PASS
SMTP_HOST = getattr(settings, "SMTP_HOST", "smtp.zoho.com")
SMTP_PORT = int(getattr(settings, "SMTP_PORT", 465))
OTP_TTL_MINUTES = settings.OTP_TTL

# Debug: Print configuration status at startup
print(f"SMTP CONFIG DEBUG: SMTP_USER loaded: {'YES' if SMTP_USER else 'NO'}")
print(f"SMTP CONFIG DEBUG: SMTP_PASS loaded: {'YES' if SMTP_PASS else 'NO'}")
if SMTP_USER:
    print(f"SMTP CONFIG DEBUG: SMTP_USER value: {SMTP_USER}")
if SMTP_PASS:
    print(f"SMTP CONFIG DEBUG: SMTP_PASS length: {len(SMTP_PASS)}")

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
        raise RuntimeError(f"SMTP credentials not configured. SMTP_USER: {'SET' if SMTP_USER else 'NOT SET'}, SMTP_PASS: {'SET' if SMTP_PASS else 'NOT SET'}")
    
    print(f"DEBUG: Attempting to send email with SMTP_USER: {SMTP_USER}")
    print(f"DEBUG: SMTP_PASS length: {len(SMTP_PASS) if SMTP_PASS else 0}")
    
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = f"Noyco <{SMTP_USER}>"
    msg["To"] = to_email
    msg.set_content(body)

    context = ssl.create_default_context()
    try:
        if SMTP_PORT == 465:
            with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, context=context) as smtp:
                print(f"DEBUG: Connected to {SMTP_HOST}:{SMTP_PORT} (SSL)")
                smtp.login(SMTP_USER, SMTP_PASS)
                print("DEBUG: SMTP login successful")
                smtp.send_message(msg)
                print("DEBUG: Email sent successfully")
        else:
            # STARTTLS flow for ports like 587
            with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as smtp:
                print(f"DEBUG: Connected to {SMTP_HOST}:{SMTP_PORT} (STARTTLS)")
                smtp.ehlo()
                smtp.starttls(context=context)
                smtp.ehlo()
                smtp.login(SMTP_USER, SMTP_PASS)
                print("DEBUG: SMTP login successful")
                smtp.send_message(msg)
                print("DEBUG: Email sent successfully")
    except smtplib.SMTPAuthenticationError as e:
        print(f"DEBUG: SMTP Authentication failed: {e}")
        error_msg = f"""
SMTP Authentication failed for user {SMTP_USER}. Error: {e}

TROUBLESHOOTING STEPS:
1. Generate app-specific password at: https://accounts.zoho.com/home → Security → App Passwords
2. Enable IMAP access at: https://mail.zoho.com → Settings → Mail → POP/IMAP Access
3. Update SMTP_ZOHO_PASS with the app-specific password (not regular password)
4. Restart the application after updating credentials

See ZOHO_SMTP_TROUBLESHOOTING.md for detailed instructions.
        """.strip()
        raise RuntimeError(error_msg)
    except smtplib.SMTPServerDisconnected as e:
        print(f"DEBUG: SMTP Server disconnected: {e}")
        raise RuntimeError(f"Could not connect to Zoho SMTP server: {e}")
    except Exception as e:
        print(f"DEBUG: Unexpected SMTP error: {e}")
        raise RuntimeError(f"SMTP error: {e}")


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


def test_smtp_connection() -> dict:
    """Test SMTP connection to Zoho Mail server and return status."""
    try:
        if not SMTP_USER or not SMTP_PASS:
            return {
                "success": False,
                "error": "SMTP credentials not configured. Please set SMTP_ZOHO_USER and SMTP_ZOHO_PASS environment variables."
            }
        
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL("smtp.zoho.com", 465, context=context) as smtp:
            smtp.login(SMTP_USER, SMTP_PASS)
            return {
                "success": True,
                "message": f"Successfully connected to Zoho SMTP server with user: {SMTP_USER}"
            }
    except smtplib.SMTPAuthenticationError:
        return {
            "success": False,
            "error": "SMTP Authentication failed. Please check your Zoho Mail credentials and ensure app-specific password is used."
        }
    except smtplib.SMTPServerDisconnected:
        return {
            "success": False,
            "error": "Could not connect to Zoho SMTP server. Please check your internet connection."
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"SMTP connection error: {str(e)}"
        }


def send_test_email(to_email: str) -> dict:
    """Send a test email to verify SMTP configuration."""
    try:
        subject = "Noyco SMTP Test - Zoho Mail Migration"
        body = (
            "Hello!\n\n"
            "This is a test email to verify that the Zoho Mail SMTP configuration is working correctly.\n\n"
            "If you receive this email, the migration from Gmail to Zoho Mail was successful!\n\n"
            "Best regards,\n"
            "Noyco Team"
        )
        
        _send_email(to_email, subject, body)
        return {
            "success": True,
            "message": f"Test email sent successfully to {to_email}"
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Failed to send test email: {str(e)}"
        }
