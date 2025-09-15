"""Background Task Manager for Anxiety Support Agent.

This is essentially the same implementation used by the Therapy agent but
kept here so the Anxiety agent has *no dependency* on other packages.
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
# Simple keyword-based anxiety analyzer – *no* external AI calls.
# ---------------------------------------------------------------------------
class AnxietyAnalyzer:
    """Ultra-cheap keyword classifier used for quick anxiety level estimates."""

    PANIC_KEYWORDS = {
        "panic", "panic attack", "can't breathe", "heart racing", "chest tight", "dying",
        "losing control", "going crazy", "hyperventilating", "dizzy", "nauseous"
    }
    
    HIGH_ANXIETY_KEYWORDS = {
        "anxious", "worried", "stressed", "overwhelmed", "nervous", "scared", "fearful",
        "racing thoughts", "can't stop thinking", "restless", "on edge", "tense"
    }
    
    MODERATE_KEYWORDS = {
        "uneasy", "concerned", "bothered", "uncomfortable", "unsettled", "jittery",
        "apprehensive", "uncertain", "troubled"
    }
    
    LOW_KEYWORDS = {
        "calm", "relaxed", "peaceful", "content", "fine", "okay", "better", "good"
    }

    def quick_anxiety_analysis(self, text: str) -> str:
        txt = text.lower()
        if any(w in txt for w in self.PANIC_KEYWORDS):
            return "panic"
        if any(w in txt for w in self.HIGH_ANXIETY_KEYWORDS):
            return "high_anxiety"
        if any(w in txt for w in self.MODERATE_KEYWORDS):
            return "moderate_anxiety"
        if any(w in txt for w in self.LOW_KEYWORDS):
            return "low_anxiety"
        return "neutral"

    def extract_triggers(self, text: str) -> List[str]:
        """Extract common anxiety triggers from text"""
        txt = text.lower()
        triggers = []
        
        trigger_keywords = {
            "work": ["work", "job", "boss", "deadline", "meeting", "presentation"],
            "social": ["people", "social", "crowd", "party", "public", "judgment"],
            "health": ["health", "sick", "pain", "doctor", "medical", "symptoms"],
            "family": ["family", "parents", "relationship", "partner", "kids", "children"],
            "money": ["money", "financial", "bills", "debt", "budget", "expensive"],
            "future": ["future", "tomorrow", "next", "upcoming", "planning", "unknown"],
            "performance": ["test", "exam", "performance", "failure", "mistake", "perfect"]
        }
        
        for trigger_type, keywords in trigger_keywords.items():
            if any(keyword in txt for keyword in keywords):
                triggers.append(trigger_type)
        
        return triggers[:3]  # Limit to top 3 triggers


class ProgressTracker:
    """Cheap heuristics to compute engagement / anxiety scores."""

    @staticmethod
    def calculate_engagement_score(query: str, response: str, turn_count: int = 1) -> float:
        # naive proxy: longer user query → higher engagement
        return min(10.0, max(1.0, len(query.split()) / 3 + 4))

    @staticmethod
    def calculate_anxiety_score(current_anxiety: str) -> float:
        return {
            "panic": 9.0, 
            "high_anxiety": 7.0, 
            "moderate_anxiety": 5.0, 
            "low_anxiety": 3.0,
            "neutral": 5.0
        }.get(current_anxiety, 5.0)


# ---------------------------------------------------------------------------
# Background task manager mirrors the therapy implementation.
# ---------------------------------------------------------------------------
class BackgroundTaskManager:
    """Runs non-blocking maintenance tasks for the anxiety agent."""

    def __init__(self, max_workers: int = 4):
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        self._anxiety_cache: Dict[str, str] = {}
        self._trigger_cache: Dict[str, List[str]] = {}

    # ──────────────────────────────────────────────────────────────────
    # Anxiety analysis (keyword-only)
    # ──────────────────────────────────────────────────────────────────
    async def schedule_anxiety_analysis(self, user_id: str, text: str) -> str:
        cache_key = f"{user_id}:{hash(text)}"
        if cache_key in self._anxiety_cache:
            return self._anxiety_cache[cache_key]
        anxiety_level = AnxietyAnalyzer().quick_anxiety_analysis(text)
        self._anxiety_cache[cache_key] = anxiety_level
        return anxiety_level

    async def schedule_trigger_analysis(self, user_id: str, text: str) -> List[str]:
        cache_key = f"{user_id}:{hash(text)}"
        if cache_key in self._trigger_cache:
            return self._trigger_cache[cache_key]
        triggers = AnxietyAnalyzer().extract_triggers(text)
        self._trigger_cache[cache_key] = triggers
        return triggers

    # ──────────────────────────────────────────────────────────────────
    async def schedule_progress_update(
        self,
        user_profile_id: str,
        agent_instance_id: str,
        anxiety_score: float,
        engagement_score: float,
        notes: str,
        data_manager,
    ):
        await data_manager.update_progress(
            user_profile_id, agent_instance_id, anxiety_score, engagement_score, notes
        )

    # ──────────────────────────────────────────────────────────────────
    async def schedule_data_sync(self, user_profile_id: str, agent_instance_id: str, data_manager):
        await data_manager.sync_agent_data_to_db(user_profile_id, agent_instance_id)

    # ──────────────────────────────────────────────────────────────────
    async def schedule_coping_technique_recommendation(
        self, 
        user_profile_id: str, 
        anxiety_level: str, 
        triggers: List[str],
        data_manager
    ) -> str:
        """Recommend coping technique based on anxiety level and triggers"""
        
        # Simple rule-based recommendations
        if anxiety_level == "panic":
            return "box_breathing"  # 4-4-4-4 breathing for panic
        elif anxiety_level == "high_anxiety":
            if "social" in triggers:
                return "grounding_5_4_3_2_1"  # 5-4-3-2-1 grounding technique
            else:
                return "deep_breathing"  # Standard deep breathing
        elif anxiety_level == "moderate_anxiety":
            if "work" in triggers or "performance" in triggers:
                return "progressive_muscle_relaxation"
            else:
                return "mindful_observation"
        else:
            return "gentle_breathing"  # For low anxiety or neutral

    # ----------------------------------------------------------------
    def cleanup(self):
        self.executor.shutdown(wait=False)
