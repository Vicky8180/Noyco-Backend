from datetime import datetime, time, timedelta
from typing import Any, Dict, List, Optional
import re

from fastapi import HTTPException


PII_REGEXES = [
    re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),  # emails
    re.compile(r"\b\+?\d[\d\s().-]{7,}\b"),  # phone-like numbers
]


def _redact(text: str) -> str:
    if not isinstance(text, str):
        return text
    redacted = text
    for rx in PII_REGEXES:
        redacted = rx.sub("[REDACTED]", redacted)
    return redacted


def _compute_sentiment(messages: List[Dict[str, Any]]) -> str:
    """Very simple heuristic sentiment; placeholder for future ML integration."""
    content = " ".join([m.get("content", "") for m in messages]).lower()
    positive = any(w in content for w in ["thank you", "great", "helpful", "good", "awesome", "love"])
    negative = any(w in content for w in ["angry", "bad", "terrible", "hate", "upset", "refund", "complaint"])
    if positive and not negative:
        return "positive"
    if negative and not positive:
        return "negative"
    return "neutral"


def _detect_flags(messages: List[Dict[str, Any]]) -> List[str]:
    content = " ".join([m.get("content", "") for m in messages]).lower()
    flags = []
    keywords = {
        "self_harm": ["suicide", "kill myself", "self-harm", "self harm"],
        "abuse": ["abuse", "violence", "assault"],
        "refund": ["refund", "chargeback"],
        "escalation": ["manager", "supervisor", "escalate"],
    }
    for tag, words in keywords.items():
        if any(w in content for w in words):
            flags.append(tag)
    return flags


async def list_conversations_controller(
    db,
    *,
    page: int,
    per_page: int,
    agent_type: Optional[str],
    status: Optional[str],  # active|paused
    user: Optional[str],  # email, name, or user_id
) -> Dict[str, Any]:
    filt: Dict[str, Any] = {}

    if agent_type:
        filt["detected_agent"] = agent_type

    if status:
        if status not in {"active", "paused"}:
            raise HTTPException(status_code=400, detail="Invalid status filter")
        # conversations have is_paused flag
        filt["is_paused"] = (status == "paused")

    # Filter by user (email, name, or user id)
    if user:
        # Build a list of individual_ids from users that match the input
        # Match by exact id, or regex on email/name
        user_ids: List[str] = []
        query = {"$or": [
            {"id": user},
            {"email": {"$regex": user, "$options": "i"}},
            {"name": {"$regex": user, "$options": "i"}},
        ]}
        for udoc in db.users.find(query, {"role_entity_id": 1}):
            rid = udoc.get("role_entity_id")
            if rid:
                user_ids.append(rid)
        if user_ids:
            filt["individual_id"] = {"$in": user_ids}
        else:
            # No matching users, return empty result fast
            return {"page": page, "per_page": per_page, "total": 0, "data": []}

    skip = (page - 1) * per_page

    # Use aggregation so we can add computed fields before pagination
    pipeline = [
        {"$match": filt},
        {"$addFields": {
            "message_count": {"$size": {"$ifNull": ["$context", []]}}
        }},
        {"$sort": {"updated_at": -1}},  # Default sort by most recent activity
        {"$skip": skip},
        {"$limit": per_page},
        {"$project": {
            "_id": 0,
            "conversation_id": 1,
            "individual_id": 1,
            "detected_agent": 1,
            "created_at": 1,
            "updated_at": 1,
            "is_paused": 1,
            "message_count": 1,
            "context": 1,
        }}
    ]

    rows_raw = list(db.conversations.aggregate(pipeline))

    # Enrich with user email/name and derived fields
    results: List[Dict[str, Any]] = []
    for doc in rows_raw:
        individual_id = doc.get("individual_id")
        
        # First, try to get name from the individuals collection
        individual_doc = db.individuals.find_one({"id": individual_id}) or {}
        name = individual_doc.get("name") or ""
        email = individual_doc.get("email") or ""
        
        # If not found in individuals, fallback to users collection
        if not name and not email:
            user_doc = db.users.find_one({"$or": [{"role_entity_id": individual_id}, {"individual_id": individual_id}]}) or {}
            name = user_doc.get("name") or user_doc.get("full_name") or ""
            email = user_doc.get("email") or user_doc.get("user_email") or ""

        msgs: List[Dict[str, Any]] = doc.get("context", [])
        message_count = int(doc.get("message_count", len(msgs)))
        last_preview = msgs[-1].get("content") if msgs else "No messages"
        created_at = doc.get("created_at")
        updated_at = doc.get("updated_at") or created_at
        duration_seconds = None
        if created_at and updated_at:
            try:
                duration_seconds = int((updated_at - created_at).total_seconds())
            except Exception:
                duration_seconds = None

        results.append({
            "conversation_id": doc.get("conversation_id"),
            "user": {"email": email, "name": name, "individual_id": individual_id},
            "agent_type": doc.get("detected_agent"),
            "started_at": created_at,
            "updated_at": updated_at,
            "duration_seconds": duration_seconds,
            "message_count": message_count,
            "last_message_preview": last_preview[:100] + ("..." if last_preview and len(last_preview) > 100 else ""),
            "status": "paused" if doc.get("is_paused") else "active",
        })

    # Compute total count for pagination
    try:
        total = db.conversations.count_documents({k: v for k, v in filt.items() if k != "_no_match"}) if not filt.get("_no_match") else 0
    except Exception:
        total = len(results)

    return {
        "page": page,
        "per_page": per_page,
        "total": total,
        "data": results,
    }


async def get_agent_types_controller(db) -> List[Dict[str, Any]]:
    """Return list of agent types across all conversations with counts and last activity."""
    pipeline = [
        {"$match": {"detected_agent": {"$ne": None}}},
        {"$group": {"_id": "$detected_agent", "count": {"$sum": 1}, "last_activity": {"$max": "$updated_at"}}},
        {"$sort": {"count": -1}},
    ]
    result = list(db.conversations.aggregate(pipeline))
    if result:
        return [{"agent_type": r.get("_id"), "count": r.get("count"), "last_activity": r.get("last_activity")} for r in result]
    # Fallback to distinct if pipeline returns none (e.g. missing counts in some envs)
    try:
        distinct = db.conversations.distinct("detected_agent")
        return [{"agent_type": a, "count": None, "last_activity": None} for a in distinct if a]
    except Exception:
        return []


async def get_conversation_detail_controller(
    db,
    *,
    conversation_id: str,
    redact: bool,
) -> Dict[str, Any]:
    conv = db.conversations.find_one({"conversation_id": conversation_id})
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    individual_id = conv.get("individual_id")
    
    # First, try to get name from the individuals collection
    individual_doc = db.individuals.find_one({"id": individual_id}) or {}
    name = individual_doc.get("name") or ""
    email = individual_doc.get("email") or ""
    
    # If not found in individuals, fallback to users collection
    if not name and not email:
        user_doc = db.users.find_one({"role_entity_id": individual_id}) or {}
        name = user_doc.get("name") or user_doc.get("full_name") or ""
        email = user_doc.get("email") or user_doc.get("user_email") or ""

    messages: List[Dict[str, Any]] = conv.get("context", [])
    transcript = []
    for m in messages:
        content = m.get("content", "")
        if redact:
            content = _redact(content)
        transcript.append({
            "role": m.get("role", ""),
            "content": content,
            "timestamp": m.get("timestamp"),
        })

    sentiment = _compute_sentiment(messages)
    flags = _detect_flags(messages)

    # Placeholder for feedback if present in conversation doc
    feedback = conv.get("feedback") or []

    return {
        "conversation_id": conv.get("conversation_id"),
        "user": {
            "email": email,
            "name": name,
            "individual_id": individual_id,
        },
        "agent_type": conv.get("detected_agent"),
        "created_at": conv.get("created_at"),
        "updated_at": conv.get("updated_at"),
        "is_active": not conv.get("is_paused", False),
        "transcript": transcript,
        "sentiment": sentiment,
        "flags": flags,
        "user_feedback": feedback,
        "summary": conv.get("summary"),
    }
