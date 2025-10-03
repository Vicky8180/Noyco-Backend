from datetime import datetime
from ...database.db import get_database

db = get_database()
COLL = db.stripe_audit

def log(event_type: str, payload: dict, status: str = "ok", note: str = ""):
    """Generic audit logger.

    payload can include identifiers like:
    - plan_type
    - intro_price_id / recurring_price_id
    - subscription_id / schedule_id
    - role / role_entity_id
    """
    doc = {
        "event_type": event_type,
        "payload": payload,
        "status": status,
        "note": note,
        "created_at": datetime.utcnow(),
    }
    try:
        COLL.insert_one(doc)
    except Exception:
        # No-op on audit failures to avoid impacting webhooks
        pass

def log_schedule_created(plan_type: str, intro_price_id: str, recurring_price_id: str, subscription_id: str, schedule_id: str, role: str, role_entity_id: str):
    """Convenience helper for subscription schedule creation events."""
    log(
        "subscription_schedule_create",
        {
            "plan_type": plan_type,
            "intro_price_id": intro_price_id,
            "recurring_price_id": recurring_price_id,
            "subscription_id": subscription_id,
            "schedule_id": schedule_id,
            "role": role,
            "role_entity_id": role_entity_id,
        },
        "ok",
        "created",
    )
