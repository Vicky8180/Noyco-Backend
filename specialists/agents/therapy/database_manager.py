"""
Database helpers for Therapy Agent (goal-scoped updates only).

Targets the `therapy_agents` collection created/managed by the user profile
service, and updates ONLY fields inside a single goal document:
  - therapy_goals.$.check_ins (append)
  - therapy_goals.$.streak (set)
  - therapy_goals.$.max_streak (set)
  - therapy_goals.$.progress_tracking (append)
  - therapy_goals.$.mood_trend (append)

Creation of agents/goals is explicitly not handled here.
"""

from typing import Dict, Any, Optional
import logging

from memory.mongo_client import MongoMemory


logger = logging.getLogger(__name__)


class TherapyDatabaseManager:
    def __init__(self) -> None:
        self.mongo_memory = MongoMemory()
        self.initialized = False

    async def initialize(self) -> None:
        try:
            await self.mongo_memory.initialize()
            self.initialized = True
            logger.info("✅ Therapy database manager initialized")
        except Exception as e:
            logger.error(f"❌ Failed to initialize therapy database manager: {e}")
            raise

    async def get_user_profile(self, user_profile_id: str) -> Optional[Dict[str, Any]]:
        try:
            doc = self.mongo_memory.db["user_profiles"].find_one({"user_profile_id": user_profile_id})
            if doc:
                doc.pop("_id", None)
            return doc
        except Exception as e:
            logger.error(f"❌ Error fetching user profile {user_profile_id}: {e}")
            return None

    async def get_therapy_agent_doc(self, user_profile_id: str) -> Optional[Dict[str, Any]]:
        try:
            doc = self.mongo_memory.db["therapy_agents"].find_one({"user_profile_id": user_profile_id})
            if doc:
                doc.pop("_id", None)
            return doc
        except Exception as e:
            logger.error(f"❌ Error fetching therapy agent for {user_profile_id}: {e}")
            return None

    @staticmethod
    def _select_active_goal(agent_doc: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        goals = (agent_doc or {}).get("therapy_goals", [])
        if not goals:
            return None
        for g in goals:
            if g.get("status") == "active":
                return g
        return goals[-1]

    async def append_checkin(self, user_profile_id: str, goal_id: str, checkin: Dict[str, Any]) -> bool:
        try:
            res = self.mongo_memory.db["therapy_agents"].update_one(
                {"user_profile_id": user_profile_id, "therapy_goals.goal_id": goal_id},
                {"$push": {"therapy_goals.$.check_ins": checkin}}
            )
            return res.modified_count > 0
        except Exception as e:
            logger.error(f"❌ therapy append_checkin failed: {e}")
            return False

    async def set_streaks(self, user_profile_id: str, goal_id: str, streak: int, max_streak: int) -> bool:
        try:
            res = self.mongo_memory.db["therapy_agents"].update_one(
                {"user_profile_id": user_profile_id, "therapy_goals.goal_id": goal_id},
                {"$set": {"therapy_goals.$.streak": streak, "therapy_goals.$.max_streak": max_streak}}
            )
            return res.modified_count > 0
        except Exception as e:
            logger.error(f"❌ therapy set_streaks failed: {e}")
            return False

    async def append_progress_tracking(self, user_profile_id: str, goal_id: str, entry: Dict[str, Any]) -> bool:
        try:
            res = self.mongo_memory.db["therapy_agents"].update_one(
                {"user_profile_id": user_profile_id, "therapy_goals.goal_id": goal_id},
                {"$push": {"therapy_goals.$.progress_tracking": entry}}
            )
            return res.modified_count > 0
        except Exception as e:
            logger.error(f"❌ therapy append_progress_tracking failed: {e}")
            return False

    async def append_mood_trend(self, user_profile_id: str, goal_id: str, mood_log: Dict[str, Any]) -> bool:
        try:
            res = self.mongo_memory.db["therapy_agents"].update_one(
                {"user_profile_id": user_profile_id, "therapy_goals.goal_id": goal_id},
                {"$push": {"therapy_goals.$.mood_trend": mood_log}}
            )
            return res.modified_count > 0
        except Exception as e:
            logger.error(f"❌ therapy append_mood_trend failed: {e}")
            return False


