from datetime import datetime
from api_gateway.database.db import get_database

db = get_database()
COLL = db.stripe_audit

def log(event_type: str, payload: dict, status: str = "ok", note: str = ""):
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
        pass  # do not crash webhook 
