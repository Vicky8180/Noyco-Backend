from __future__ import annotations
from datetime import datetime
from typing import Any, Dict, List, Optional

from api_gateway.database.db import get_database
from api_gateway.config import get_settings
from .content_provider import ContentProvider, ContentPayload, LatestConversation

class MetricsContentProviderExisting(ContentProvider):
    """Reads from the existing metrics collection and maps fields to ContentPayload.

    This provider intentionally makes minimal assumptions about the schema. It attempts to
    extract numeric metrics, agents used, and a latest conversation snippet if available.
    """

    def __init__(self) -> None:
        settings = get_settings()
        self.collection_name = settings.METRICS_COLLECTION_NAME

    def _extract_numeric_metrics(self, doc: Dict[str, Any]) -> Dict[str, float]:
        metrics: Dict[str, float] = {}
        for k, v in doc.items():
            if isinstance(v, (int, float)):
                metrics[k] = float(v)
            elif isinstance(v, dict) and all(isinstance(x, (int, float)) for x in v.values()):
                # flatten one level if it's a simple numeric dict
                for sk, sv in v.items():
                    metrics[f"{k}.{sk}"] = float(sv)
        return metrics

    def _extract_agents(self, doc: Dict[str, Any]) -> List[str]:
        agents: List[str] = []
        # common patterns: 'agent', 'agent_name', 'agents', 'agents_used'
        for key in ("agent", "agent_name"):
            if isinstance(doc.get(key), str):
                agents.append(doc[key])
        for key in ("agents", "agents_used"):
            v = doc.get(key)
            if isinstance(v, list):
                for a in v:
                    if isinstance(a, str):
                        agents.append(a)
                    elif isinstance(a, dict) and isinstance(a.get("name"), str):
                        agents.append(a["name"])
        # de-duplicate preserving order
        seen = set()
        ordered: List[str] = []
        for a in agents:
            if a not in seen:
                seen.add(a)
                ordered.append(a)
        return ordered

    def _extract_latest_conversation(self, doc: Dict[str, Any]) -> Optional[LatestConversation]:
        conv = doc.get("latest_conversation") or doc.get("last_conversation")
        if isinstance(conv, dict):
            return LatestConversation(
                agent_id=conv.get("agent_id") or conv.get("agent"),
                agent_name=conv.get("agent_name"),
                excerpt=conv.get("excerpt") or conv.get("summary") or conv.get("text"),
            )
        return None

    def get_weekly_content(self, *, user_id: str, week_start: datetime, week_end: datetime) -> ContentPayload:
        db = get_database()
        coll = db[self.collection_name]
        # Try a few common patterns for date range filtering
        query = {
            "user_id": user_id,
            "$or": [
                {"week_start": {"$gte": week_start}, "week_end": {"$lte": week_end}},
                {"timestamp": {"$gte": week_start, "$lte": week_end}},
                {"date": {"$gte": week_start, "$lte": week_end}},
            ]
        }
        doc = coll.find_one(query, sort=[("timestamp", -1)]) or coll.find_one({"user_id": user_id}, sort=[("timestamp", -1)])

        metrics: Dict[str, float] = {}
        agents_used: List[str] = []
        latest_conversation: Optional[LatestConversation] = None

        if doc:
            metrics = self._extract_numeric_metrics(doc)
            agents_used = self._extract_agents(doc)
            latest_conversation = self._extract_latest_conversation(doc)

        title = "Your weekly summary"
        intro = "Here are your highlights for the week."
        return ContentPayload(
            title=title,
            intro=intro,
            metrics=metrics,
            agents_used=agents_used,
            latest_conversation=latest_conversation,
            extras={
                "week_start": week_start.isoformat(),
                "week_end": week_end.isoformat(),
            },
        )
