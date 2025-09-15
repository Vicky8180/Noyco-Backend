"""Background Task Manager for Therapy Companion Agent.

This is essentially the same implementation used by the Loneliness agent but
kept here so the Therapy agent has *no dependency* on the Loneliness package.
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
# Simple keyword-based sentiment helper – *no* external AI calls.
# ---------------------------------------------------------------------------
class MoodAnalyzer:
    """Ultra-cheap keyword classifier used for quick mood estimates."""

    LOW_KEYWORDS = {
        "sad", "lonely", "depressed", "unhappy", "bad", "terrible", "miserable", "hopeless",
        "suicidal", "down", "worried", "anxious",
    }
    HIGH_KEYWORDS = {
        "happy", "great", "good", "fantastic", "wonderful", "excited", "content", "relaxed",
    }

    def quick_mood_analysis(self, text: str) -> str:
        txt = text.lower()
        if any(w in txt for w in self.LOW_KEYWORDS):
            return "sad"
        if any(w in txt for w in self.HIGH_KEYWORDS):
            return "happy"
        return "neutral"


class ProgressTracker:
    """Cheap heuristics to compute engagement / mood scores."""

    @staticmethod
    def calculate_engagement_score(query: str, response: str, turn_count: int = 1) -> float:
        # naive proxy: longer user query → higher engagement
        return min(10.0, max(1.0, len(query.split()) / 3 + 4))

    @staticmethod
    def calculate_mood_score(current_mood: str) -> float:
        return {"sad": 3.0, "neutral": 5.0, "happy": 8.0}.get(current_mood, 5.0)


# ---------------------------------------------------------------------------
# Background task manager mirrors the loneliness implementation.
# ---------------------------------------------------------------------------
class BackgroundTaskManager:
    """Runs non-blocking maintenance tasks for the agent."""

    def __init__(self, max_workers: int = 4):
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        self._mood_cache: Dict[str, str] = {}

    # ──────────────────────────────────────────────────────────────────
    # Mood analysis (keyword-only)
    # ──────────────────────────────────────────────────────────────────
    async def schedule_mood_analysis(self, user_id: str, text: str) -> str:
        cache_key = f"{user_id}:{hash(text)}"
        if cache_key in self._mood_cache:
            return self._mood_cache[cache_key]
        mood = MoodAnalyzer().quick_mood_analysis(text)
        self._mood_cache[cache_key] = mood
        return mood

    # ──────────────────────────────────────────────────────────────────
    async def schedule_progress_update(
        self,
        user_profile_id: str,
        agent_instance_id: str,
        mood_score: float,
        engagement_score: float,
        notes: str,
        data_manager,
    ):
        await data_manager.update_progress(
            user_profile_id, agent_instance_id, mood_score, engagement_score, notes
        )

    # ──────────────────────────────────────────────────────────────────
    async def schedule_data_sync(self, user_profile_id: str, agent_instance_id: str, data_manager):
        await data_manager.sync_agent_data_to_db(user_profile_id, agent_instance_id)

    # ----------------------------------------------------------------
    def cleanup(self):
        self.executor.shutdown(wait=False)
