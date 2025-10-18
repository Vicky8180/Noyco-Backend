from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Protocol

@dataclass
class LatestConversation:
    agent_id: Optional[str] = None
    agent_name: Optional[str] = None
    excerpt: Optional[str] = None

@dataclass
class ContentPayload:
    title: str
    intro: Optional[str] = None
    metrics: Dict[str, float] = field(default_factory=dict)
    agents_used: List[str] = field(default_factory=list)
    latest_conversation: Optional[LatestConversation] = None
    extras: Dict[str, Any] = field(default_factory=dict)

class ContentProvider(Protocol):
    def get_weekly_content(self, *, user_id: str, week_start: datetime, week_end: datetime) -> ContentPayload:
        ...
