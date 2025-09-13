"""
Database Manager for Accountability Buddy Agent

This manager provides focused CRUD helpers that operate ONLY on the
`accountability_agents` collection (created/managed by the user profile
service) and ONLY update allowed goal fields:
  - accountability_goals.$.check_ins (append)
  - accountability_goals.$.streak (set)
  - accountability_goals.$.max_streak (set)
  - accountability_goals.$.progress_tracking (append)
  - accountability_goals.$.mood_trend (append)

Agent/goal CREATION is intentionally not handled here. If there is no agent
document or no goal for a user, the caller should create it via the
user-profile endpoint (kept in api_gateway).
"""

import logging
import uuid
from typing import Dict, List, Optional, Any
from datetime import datetime, date, timedelta
from pymongo.errors import DuplicateKeyError

# Import shared memory client
from memory.mongo_client import MongoMemory

from .schema import (
    AccountabilityGoal,
)

logger = logging.getLogger(__name__)

class AccountabilityDatabaseManager:
    """Database manager for accountability agent (no instance creation here)"""
    
    def __init__(self):
        self.mongo_memory = MongoMemory()
        self.initialized = False
        
    async def initialize(self):
        """Initialize database connection"""
        try:
            await self.mongo_memory.initialize()
            self.initialized = True
            logger.info("✅ Accountability database manager initialized successfully")
        except Exception as e:
            logger.error(f"❌ Failed to initialize accountability database manager: {e}")
            raise
            
    # === NEW: Helpers targeting accountability_agents collection ===

    async def get_user_profile(self, user_profile_id: str) -> Optional[Dict[str, Any]]:
        """Fetch user profile for personalization."""
        try:
            doc = self.mongo_memory.db["user_profiles"].find_one({"user_profile_id": user_profile_id})
            if doc:
                doc.pop("_id", None)
            return doc
        except Exception as e:
            logger.error(f"❌ Error fetching user profile {user_profile_id}: {e}")
            return None

    async def get_accountability_agent_doc(self, user_profile_id: str) -> Optional[Dict[str, Any]]:
        """Return the agent document from accountability_agents (no creation)."""
        try:
            doc = self.mongo_memory.db["accountability_agents"].find_one({"user_profile_id": user_profile_id})
            if doc:
                doc.pop("_id", None)
            return doc
        except Exception as e:
            logger.error(f"❌ Error fetching accountability agent for {user_profile_id}: {e}")
            return None

    @staticmethod
    def _select_active_goal(agent_doc: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        goals = (agent_doc or {}).get("accountability_goals", [])
        if not goals:
            return None
        # Prefer status=="active"; else last goal
        for g in goals:
            if g.get("status") == "active":
                return g
        return goals[-1]

    async def append_checkin(self, user_profile_id: str, goal_id: str, checkin: Dict[str, Any]) -> bool:
        try:
            res = self.mongo_memory.db["accountability_agents"].update_one(
                {"user_profile_id": user_profile_id, "accountability_goals.goal_id": goal_id},
                {"$push": {"accountability_goals.$.check_ins": checkin}}
            )
            return res.modified_count > 0
        except Exception as e:
            logger.error(f"❌ append_checkin failed: {e}")
            return False

    async def set_streaks(self, user_profile_id: str, goal_id: str, streak: int, max_streak: int) -> bool:
        try:
            res = self.mongo_memory.db["accountability_agents"].update_one(
                {"user_profile_id": user_profile_id, "accountability_goals.goal_id": goal_id},
                {"$set": {"accountability_goals.$.streak": streak, "accountability_goals.$.max_streak": max_streak}}
            )
            return res.modified_count > 0
        except Exception as e:
            logger.error(f"❌ set_streaks failed: {e}")
            return False

    async def append_progress_tracking(self, user_profile_id: str, goal_id: str, entry: Dict[str, Any]) -> bool:
        try:
            res = self.mongo_memory.db["accountability_agents"].update_one(
                {"user_profile_id": user_profile_id, "accountability_goals.goal_id": goal_id},
                {"$push": {"accountability_goals.$.progress_tracking": entry}}
            )
            return res.modified_count > 0
        except Exception as e:
            logger.error(f"❌ append_progress_tracking failed: {e}")
            return False

    async def append_mood_trend(self, user_profile_id: str, goal_id: str, mood_log: Dict[str, Any]) -> bool:
        try:
            res = self.mongo_memory.db["accountability_agents"].update_one(
                {"user_profile_id": user_profile_id, "accountability_goals.goal_id": goal_id},
                {"$push": {"accountability_goals.$.mood_trend": mood_log}}
            )
            return res.modified_count > 0
        except Exception as e:
            logger.error(f"❌ append_mood_trend failed: {e}")
            return False
