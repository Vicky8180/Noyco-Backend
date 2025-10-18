from __future__ import annotations

import hashlib
import hmac
import base64
import json
import logging
from typing import Any, Dict

from fastapi import APIRouter, Header, HTTPException, Request

from api_gateway.config import get_settings
from api_gateway.database.db import get_database

router = APIRouter()
logger = logging.getLogger("webhooks.mailersend")


def _verify_signature(secret: str | None, body: bytes, signature_header: str | None) -> bool:
    if not secret:
        # In absence of secret, allow but warn (useful for local dev)
        logger.warning("mailersend_webhook_no_secret_configured")
        return True
    if not signature_header:
        return False
    try:
        mac = hmac.new(secret.encode("utf-8"), body, hashlib.sha256)
        hex_sig = mac.hexdigest().lower()
        candidate = signature_header.strip()
        # Accept either exact hex match or base64 of raw digest
        if hmac.compare_digest(hex_sig, candidate.lower()):
            return True
        try:
            b64_sig = base64.b64encode(mac.digest()).decode("ascii")
            if hmac.compare_digest(b64_sig, candidate):
                return True
        except Exception:
            pass
        return False
    except Exception:
        return False


def _event_kind(payload: Dict[str, Any]) -> str:
    # Try common fields: 'type', 'event', 'status'
    for key in ("type", "event", "status"):
        val = payload.get(key)
        if isinstance(val, str):
            return val.lower()
    return "unknown"


def _recipient_email(payload: Dict[str, Any]) -> str | None:
    # Try typical shapes: data[recipient], data[email], recipient, to[0].email
    data = payload.get("data") if isinstance(payload, dict) else None
    if isinstance(data, dict):
        for key in ("recipient", "email"):
            v = data.get(key)
            if isinstance(v, str):
                return v
    # Fallbacks
    for key in ("recipient", "email"):
        v = payload.get(key)
        if isinstance(v, str):
            return v
    to_list = payload.get("to")
    if isinstance(to_list, list) and to_list:
        first = to_list[0]
        if isinstance(first, dict):
            v = first.get("email")
            if isinstance(v, str):
                return v
    return None


def _message_id(payload: Dict[str, Any]) -> str | None:
    # Try headers then body fields
    mid = payload.get("message_id") or payload.get("id")
    if isinstance(mid, str):
        return mid
    data = payload.get("data")
    if isinstance(data, dict):
        for k in ("message_id", "id"):
            v = data.get(k)
            if isinstance(v, str):
                return v
    return None


def _is_suppression(kind: str) -> bool:
    return any(x in kind for x in ["bounce", "complaint", "spam", "blocked", "hard_bounce", "soft_bounce"])  # conservative


@router.post("/public/webhooks/mailersend")
async def mailersend_webhook(
    request: Request,
    x_mailersend_signature: str | None = Header(default=None, alias="X-MailerSend-Signature"),
    x_mailersend_signature_alt: str | None = Header(default=None, alias="X-Mailersend-Signature"),
    x_signature: str | None = Header(default=None, alias="X-Signature"),
):
    settings = get_settings()
    secret = getattr(settings, "MAILERSEND_WEBHOOK_SECRET", None)

    body = await request.body()
    signature = x_mailersend_signature or x_mailersend_signature_alt or x_signature
    if not _verify_signature(secret, body, signature):
        raise HTTPException(status_code=400, detail="invalid signature")

    try:
        payload = json.loads(body.decode("utf-8") or "{}")
    except Exception:
        raise HTTPException(status_code=400, detail="invalid json")

    # MailerSend may POST a single event or an array of events. Normalize to list.
    events: list[dict] = []
    if isinstance(payload, list):
        events = [e for e in payload if isinstance(e, dict)]
    elif isinstance(payload, dict):
        # Some payloads include 'events' array
        if isinstance(payload.get("events"), list):
            events = [e for e in payload["events"] if isinstance(e, dict)]
        else:
            events = [payload]

    db = get_database()
    processed = 0
    for ev in events:
        kind = _event_kind(ev)
        email = _recipient_email(ev)
        message_id = _message_id(ev)

        log_extra = {"event": kind, "email": email, "message_id": message_id}

        if not email:
            logger.info("mailersend_webhook_event_no_email", extra=log_extra)
            continue

        if _is_suppression(kind):
            # Set suppression flags and disable weekly digest for individuals
            user = db.users.find_one({"email": email}) or {}
            if user:
                db.users.update_one({"id": user.get("id")}, {"$set": {"email_suppressed": True}})
                if user.get("role") == "individual" and user.get("role_entity_id"):
                    db.individuals.update_one(
                        {"id": user["role_entity_id"]},
                        {"$set": {"email_suppressed": True, "weekly_digest_enabled": False}},
                    )
            else:
                # Try to update any individual with this email directly
                db.individuals.update_one(
                    {"email": email},
                    {"$set": {"email_suppressed": True, "weekly_digest_enabled": False}},
                )

            logger.warning("mailersend_webhook_suppressed", extra=log_extra)
        else:
            # Delivered/open/click etc.
            logger.info("mailersend_webhook_event", extra=log_extra)
        processed += 1

    return {"ok": True, "processed": processed}
