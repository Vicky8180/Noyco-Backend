"""Background Task Manager for Emotional Companion Agent.

This is essentially the same implementation used by the Therapy agent but
adapted for emotional support and comfort tracking.
"""

from __future__ import annotations

import asyncio
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Simple keyword-based emotional state helper – *no* external AI calls.
# ---------------------------------------------------------------------------
class EmotionalAnalyzer:
    """Ultra-cheap keyword classifier used for quick emotional state estimates."""

    DISTRESSED_KEYWORDS = {
        "sad", "lonely", "depressed", "unhappy", "bad", "terrible", "miserable", "hopeless",
        "suicidal", "down", "worried", "anxious", "scared", "afraid", "hurt", "broken",
        "devastated", "overwhelmed", "stressed", "crying", "tears", "pain", "suffering"
    }
    POSITIVE_KEYWORDS = {
        "happy", "great", "good", "fantastic", "wonderful", "excited", "content", "relaxed",
        "joyful", "peaceful", "calm", "grateful", "blessed", "loved", "supported", "better",
        "improving", "healing", "hopeful", "optimistic", "strong", "confident"
    }
    COMFORT_SEEKING_KEYWORDS = {
        "need", "help", "support", "comfort", "hug", "listen", "understand", "care",
        "alone", "nobody", "empty", "lost", "confused", "tired", "exhausted"
    }

    def quick_emotional_analysis(self, text: str) -> str:
        txt = text.lower()
        if any(w in txt for w in self.DISTRESSED_KEYWORDS):
            return "distressed"
        if any(w in txt for w in self.COMFORT_SEEKING_KEYWORDS):
            return "seeking_comfort"
        if any(w in txt for w in self.POSITIVE_KEYWORDS):
            return "positive"
        return "neutral"


class ProgressTracker:
    """Cheap heuristics to compute engagement / emotional wellness scores."""

    @staticmethod
    def calculate_engagement_score(query: str, response: str, turn_count: int = 1) -> float:
        # naive proxy: longer user query → higher engagement
        return min(10.0, max(1.0, len(query.split()) / 3 + 4))

    @staticmethod
    def calculate_emotional_wellness_score(current_emotional_state: str) -> float:
        return {
            "distressed": 2.0, 
            "seeking_comfort": 4.0, 
            "neutral": 5.0, 
            "positive": 8.0
        }.get(current_emotional_state, 5.0)


# ---------------------------------------------------------------------------
# Background task manager mirrors the therapy implementation.
# ---------------------------------------------------------------------------
class BackgroundTaskManager:
    """Runs non-blocking maintenance tasks for the emotional agent."""

    def __init__(self, max_workers: int = 4):
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        self._emotional_cache: Dict[str, str] = {}

    # ──────────────────────────────────────────────────────────────────
    # Emotional analysis (keyword-only)
    # ──────────────────────────────────────────────────────────────────
    async def schedule_emotional_analysis(self, user_id: str, text: str) -> str:
        cache_key = f"{user_id}:{hash(text)}"
        if cache_key in self._emotional_cache:
            return self._emotional_cache[cache_key]
        emotional_state = EmotionalAnalyzer().quick_emotional_analysis(text)
        self._emotional_cache[cache_key] = emotional_state
        return emotional_state

    # ──────────────────────────────────────────────────────────────────
    async def schedule_progress_update(
        self,
        user_profile_id: str,
        agent_instance_id: str,
        emotional_wellness_score: float,
        engagement_score: float,
        notes: str,
        data_manager,
    ):
        await data_manager.update_progress(
            user_profile_id, agent_instance_id, emotional_wellness_score, engagement_score, notes
        )

    # ──────────────────────────────────────────────────────────────────
    async def schedule_data_sync(self, user_profile_id: str, agent_instance_id: str, data_manager):
        await data_manager.sync_agent_data_to_db(user_profile_id, agent_instance_id)

    # ----------------------------------------------------------------
    def cleanup(self):
        self.executor.shutdown(wait=False)
