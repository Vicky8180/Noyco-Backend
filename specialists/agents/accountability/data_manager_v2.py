from __future__ import annotations

"""
MongoDB DataManager for the Accountability Agent - mirrors loneliness agent pattern exactly.
Uses Pydantic models and the same data persistence approach as loneliness agent.
"""

import asyncio
import json
import logging
import time
import sys
import os
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

# Add the parent directory to Python path
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(os.path.dirname(current_dir))
sys.path.insert(0, parent_dir)

# Import required modules
from pydantic import BaseModel, Field
from uuid import uuid4
import random

# Always define the models first
class CheckIn(BaseModel):
    date: datetime = Field(default_factory=datetime.utcnow)
    response: str
    completed: bool = True
    notes: Optional[str] = None

class MoodLog(BaseModel):
    date: datetime = Field(default_factory=datetime.utcnow)
    mood_score: int = Field(ge=1, le=10)
    feelings: List[str] = Field(default_factory=list)
    notes: Optional[str] = None
    risk_level: int = 0

class ProgressEntry(BaseModel):
    date: datetime = Field(default_factory=datetime.utcnow)
    mood_score: float
    social_engagement_score: float
    affirmation: str
    emotional_trend: str = "stable"
    notes: Optional[str] = None

class AccountabilityGoal(BaseModel):
    goal_id: str = Field(default_factory=lambda: str(uuid4()))
    title: str
    description: Optional[str] = None
    due_date: Optional[datetime] = None
    status: str = "active"
    check_ins: List[CheckIn] = Field(default_factory=list)
    streak: int = 0
    max_streak: int = 0
    progress_tracking: List[ProgressEntry] = Field(default_factory=list)
    mood_trend: List[MoodLog] = Field(default_factory=list)

class AccountabilityAgent(BaseModel):
    agent_instance_id: str = Field(default_factory=lambda: str(uuid4()))
    user_profile_id: str
    accountability_goals: List[AccountabilityGoal] = Field(default_factory=list)
    last_interaction: Optional[datetime] = None
    total_conversations: int = 0
    conversations: List[Dict[str, Any]] = Field(default_factory=list)

class UserProfile(BaseModel):
    user_profile_id: str
    user_id: str = ""
    profile_name: str = "Default Profile"
    name: str = "Friend"
    interests: List[str] = []
    personality_traits: List[str] = []
    is_active: bool = True
    locale: str = "us"

# Try to import memory clients
try:
    from memory.redis_client import RedisMemory
    from memory.mongo_client import MongoMemory
    # Import from unified schema - try both relative and absolute paths
    try:
        # When running from agents folder
        from schema import (
            UserProfile as UnifiedUserProfile, BaseDBModel, 
            generate_accountability_goal_id
        )
        # Override local UserProfile with unified one
        UserProfile = UnifiedUserProfile
    except ImportError:
        # When running from root folder via run_dev.py
        try:
            from specialists.agents.schema import (
                UserProfile as UnifiedUserProfile, BaseDBModel,
                generate_accountability_goal_id
            )
            # Override local UserProfile with unified one
            UserProfile = UnifiedUserProfile
        except ImportError:
            # Fallback to local definitions if unified schema not available
            def generate_accountability_goal_id() -> str:
                return f"accountability_{random.randint(100, 999)}"
            
            class BaseDBModel(BaseModel):
                created_at: datetime = Field(default_factory=datetime.utcnow)
                updated_at: datetime = Field(default_factory=datetime.utcnow)
except ImportError as e:
    # Fallback implementations for when memory clients aren't available
    class RedisMemory:
        async def check_connection(self): 
            return True
        redis = type('Redis', (), {'get': lambda self, k: None, 'set': lambda self, k, v, ex=None: None})()
    
    class MongoMemory:
        async def initialize(self): 
            return True
        async def check_connection(self): 
            return True
        db = type('DB', (), {
            'user_profiles': type('Collection', (), {'find_one': lambda x: None, 'update_one': lambda *args, **kwargs: None})(),
            'accountability_agents': type('Collection', (), {'find_one': lambda x: None, 'update_one': lambda *args, **kwargs: None})()
        })()

logger = logging.getLogger(__name__)

class DateTimeEncoder(json.JSONEncoder):
    """Custom JSON encoder to handle datetime objects"""
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)

def safe_json_loads(data) -> dict:
    """Safely load JSON with datetime parsing"""
    if isinstance(data, str):
        return json.loads(data)
    elif isinstance(data, dict):
        return data
    return {}

class AccountabilityDataManagerV2:
    """MongoDB-based data manager for accountability agent following loneliness agent pattern exactly"""
    
    def __init__(self, redis_client=None, mongo_client=None):
        self.redis_client = redis_client or RedisMemory()
        self.mongo_client = mongo_client or MongoMemory()
        
        # Multi-level caches
        self.user_profile_cache: Dict[str, UserProfile] = {}
        self.accountability_agent_cache: Dict[str, AccountabilityAgent] = {}
        self._session_cache: Dict[str, Dict[str, Any]] = {}
        
        # Cache TTL and stats
        self._cache_ttl = 300  # 5 minutes
        self.cache_stats = {"profile_hits": 0, "profile_misses": 0, "agent_hits": 0, "agent_misses": 0}

    async def get_user_profile(self, user_profile_id: str) -> UserProfile:
        """Fetch user profile with multi-level caching - mirrors loneliness agent exactly"""
        # Check in-memory cache first
        if user_profile_id in self.user_profile_cache:
            self.cache_stats["profile_hits"] += 1
            return self.user_profile_cache[user_profile_id]
        
        self.cache_stats["profile_misses"] += 1
        
        # Check Redis cache
        redis_key = f"user_profile:{user_profile_id}"
        try:
            cached_data = await self.redis_client.redis.get(redis_key)
            if cached_data:
                profile_dict = safe_json_loads(cached_data)
                profile = UserProfile(**profile_dict)
                self.user_profile_cache[user_profile_id] = profile
                return profile
        except Exception as e:
            logger.warning(f"Redis cache fetch failed for profile {user_profile_id}: {e}")
        
        # Fetch from MongoDB
        profile = await self._fetch_user_profile_from_db(user_profile_id)
        
        # Cache in both Redis and memory
        await self._cache_user_profile(user_profile_id, profile)
        
        return profile

    async def _fetch_user_profile_from_db(self, user_profile_id: str) -> UserProfile:
        """Fetch user profile from MongoDB user_profiles collection"""
        try:
            # Check if mongo_client and db are available
            if not self.mongo_client or not hasattr(self.mongo_client, 'db') or self.mongo_client.db is None:
                logger.warning(f"MongoDB connection not available, creating default profile for {user_profile_id}")
                return self._create_default_user_profile(user_profile_id)
                
            profile_doc = self.mongo_client.db.user_profiles.find_one(
                {"user_profile_id": user_profile_id}
            )
            
            if profile_doc:
                # Remove MongoDB's _id field
                profile_doc.pop('_id', None)
                return UserProfile(**profile_doc)
            else:
                # Create default profile
                return self._create_default_user_profile(user_profile_id)
                
        except Exception as e:
            logger.error(f"Failed to fetch user profile {user_profile_id} from DB: {e}")
            return self._create_default_user_profile(user_profile_id)
    
    def _create_default_user_profile(self, user_profile_id: str) -> UserProfile:
        """Create default user profile"""
        return UserProfile(
            user_profile_id=user_profile_id,
            user_id=user_profile_id,  # Fallback mapping
            profile_name="Default Profile",
            name="Friend",
            personality_traits=["supportive", "accountability-focused"],
            is_active=True,
            locale="us"
        )
    
    async def _cache_user_profile(self, user_profile_id: str, profile: UserProfile):
        """Cache user profile in Redis and memory"""
        try:
            # Cache in memory
            self.user_profile_cache[user_profile_id] = profile
            
            # Cache in Redis with TTL
            redis_key = f"user_profile:{user_profile_id}"
            profile_json = profile.model_dump_json()
            await self.redis_client.redis.set(redis_key, profile_json, ex=self._cache_ttl)
            
        except Exception as e:
            logger.warning(f"Failed to cache user profile {user_profile_id}: {e}")

    async def get_accountability_agent_data(self, user_profile_id: str, agent_instance_id: str) -> AccountabilityAgent:
        """Fetch accountability agent data with multi-level caching - mirrors loneliness agent exactly"""
        cache_key = f"{user_profile_id}:{agent_instance_id}"
        
        # Check in-memory cache first
        if cache_key in self.accountability_agent_cache:
            self.cache_stats["agent_hits"] += 1
            return self.accountability_agent_cache[cache_key]
        
        self.cache_stats["agent_misses"] += 1
        
        # Check Redis cache
        redis_key = f"accountability_agent:{cache_key}"
        try:
            cached_data = await self.redis_client.redis.get(redis_key)
            if cached_data:
                agent_dict = safe_json_loads(cached_data)
                agent = AccountabilityAgent(**agent_dict)
                self.accountability_agent_cache[cache_key] = agent
                return agent
        except Exception as e:
            logger.warning(f"Redis cache fetch failed for accountability agent {cache_key}: {e}")
        
        # Fetch from MongoDB
        agent = await self._fetch_agent_data_from_db(user_profile_id, agent_instance_id)
        
        # Cache in both Redis and memory
        await self._cache_agent_data(cache_key, agent)
        
        return agent
    
    async def _fetch_agent_data_from_db(self, user_profile_id: str, agent_instance_id: str) -> AccountabilityAgent:
        """Fetch accountability agent data from MongoDB accountability_agents collection"""
        try:
            # Check if mongo_client and db are available
            logger.info(f"MongoDB client check: mongo_client={self.mongo_client}, has_db={hasattr(self.mongo_client, 'db') if self.mongo_client else False}")
            if not self.mongo_client or not hasattr(self.mongo_client, 'db') or self.mongo_client.db is None:
                logger.warning(f"MongoDB connection not available, creating default agent for {user_profile_id}")
                return self._create_default_agent_data(user_profile_id, agent_instance_id)
                
            agent_doc = self.mongo_client.db.accountability_agents.find_one({
                "user_profile_id": user_profile_id
            })
            
            if agent_doc:
                # Remove MongoDB's _id field
                agent_doc.pop('_id', None)
                agent = AccountabilityAgent(**agent_doc)
                
                # Find the specific goal by agent_instance_id
                target_goal = None
                for goal in agent.accountability_goals:
                    if goal.goal_id == agent_instance_id:
                        target_goal = goal
                        break
                
                if target_goal:
                    # Return agent with only the requested goal
                    agent.accountability_goals = [target_goal]
                    return agent
                else:
                    # Goal not found, add it to existing agent
                    new_goal = AccountabilityGoal(
                        goal_id=agent_instance_id,
                        title="General Accountability",
                        description="Daily accountability tracking and goal support",
                        status="active"
                    )
                    agent.accountability_goals.append(new_goal)
                    
                    # Save updated agent back to DB
                    await self._save_agent_with_new_goal(agent)
                    
                    # Return agent with only the new goal
                    agent.accountability_goals = [new_goal]
                    return agent
            else:
                # Create default agent data (no document exists for this user)
                return self._create_default_agent_data(user_profile_id, agent_instance_id)
                
        except Exception as e:
            logger.error(f"Failed to fetch accountability agent {user_profile_id}:{agent_instance_id} from DB: {e}")
            return self._create_default_agent_data(user_profile_id, agent_instance_id)
    
    def _create_default_agent_data(self, user_profile_id: str, agent_instance_id: str) -> AccountabilityAgent:
        """Create default accountability agent data"""
        default_goal = AccountabilityGoal(
            goal_id=agent_instance_id,
            title="General Accountability",
            description="Daily accountability tracking and goal support",
            status="active"
        )
        
        return AccountabilityAgent(
            agent_instance_id=agent_instance_id,
            user_profile_id=user_profile_id,
            accountability_goals=[default_goal],
            last_interaction=datetime.utcnow(),
            total_conversations=0
        )
    
    async def _save_agent_with_new_goal(self, agent: AccountabilityAgent):
        """Save agent with new goal to MongoDB"""
        try:
            if self.mongo_client and hasattr(self.mongo_client, 'db') and self.mongo_client.db is not None:
                agent_dict = agent.model_dump()
                # Convert datetime objects to ISO strings for MongoDB
                agent_dict = json.loads(json.dumps(agent_dict, cls=DateTimeEncoder))
                
                self.mongo_client.db.accountability_agents.update_one(
                    {"user_profile_id": agent.user_profile_id},
                    {"$set": agent_dict},
                    upsert=True
                )
        except Exception as e:
            logger.error(f"Failed to save agent with new goal: {e}")
    
    async def _cache_agent_data(self, cache_key: str, agent: AccountabilityAgent):
        """Cache agent data in Redis and memory"""
        try:
            # Cache in memory
            self.accountability_agent_cache[cache_key] = agent
            
            # Cache in Redis with TTL
            redis_key = f"accountability_agent:{cache_key}"
            agent_json = agent.model_dump_json()
            await self.redis_client.redis.set(redis_key, agent_json, ex=self._cache_ttl)
            
        except Exception as e:
            logger.warning(f"Failed to cache agent data {cache_key}: {e}")

    # Session state management (mirrors loneliness agent)
    async def get_session_state(self, conversation_id: str, user_profile_id: str) -> Dict[str, Any]:
        """Get session state for conversation"""
        cache_key = f"{conversation_id}:{user_profile_id}"
        return self._session_cache.get(cache_key, {})

    async def update_session_state(self, conversation_id: str, user_profile_id: str, updates: Dict[str, Any]):
        """Update session state"""
        cache_key = f"{conversation_id}:{user_profile_id}"
        if cache_key not in self._session_cache:
            self._session_cache[cache_key] = {}
        self._session_cache[cache_key].update(updates)

    # Data persistence methods (mirror loneliness agent exactly)
    async def add_check_in(self, user_profile_id: str, agent_instance_id: str, user_query: str) -> bool:
        """Add daily check-in entry - mirrors loneliness agent exactly"""
        try:
            cache_key = f"{user_profile_id}:{agent_instance_id}"
            agent = await self.get_accountability_agent_data(user_profile_id, agent_instance_id)
            
            if agent.accountability_goals:
                today = datetime.utcnow().date()
                
                # Check if there's already a check-in for today
                existing_checkin_today = False
                for check_in in agent.accountability_goals[0].check_ins:
                    if check_in.date.date() == today:
                        existing_checkin_today = True
                        # Update the existing check-in response with latest query
                        check_in.response = user_query
                        check_in.notes = "User interaction updated"
                        logger.debug(f"Updated existing check-in for today {today}")
                        break
                
                # Only add new check-in if none exists for today
                if not existing_checkin_today:
                    check_in = CheckIn(
                        date=datetime.utcnow(),
                        response=user_query,
                        completed=True,
                        notes="User interaction recorded"
                    )
                    
                    agent.accountability_goals[0].check_ins.append(check_in)
                    
                    # Update streak only if it's a new day check-in
                    agent.accountability_goals[0].streak += 1
                    if agent.accountability_goals[0].streak > agent.accountability_goals[0].max_streak:
                        agent.accountability_goals[0].max_streak = agent.accountability_goals[0].streak
                    
                    logger.debug(f"Added new check-in for today {today}, streak: {agent.accountability_goals[0].streak}")
                
                # Update last interaction
                agent.last_interaction = datetime.utcnow()
                
                # Sync to database
                await self.sync_agent_data_to_db(user_profile_id, agent_instance_id)
                
                return True
            else:
                logger.warning(f"No accountability goals found for {user_profile_id}:{agent_instance_id}")
                return False
                
        except Exception as e:
            logger.error(f"Failed to add check-in for {user_profile_id}:{agent_instance_id}: {e}")
            return False

    async def add_mood_log(self, user_profile_id: str, agent_instance_id: str, rating: int, feelings: List[str], user_query: str, risk_level: int = 0) -> bool:
        """Add mood log entry - mirrors loneliness agent exactly"""
        try:
            cache_key = f"{user_profile_id}:{agent_instance_id}"
            agent = await self.get_accountability_agent_data(user_profile_id, agent_instance_id)
            
            if agent.accountability_goals:
                mood_entry = MoodLog(
                    date=datetime.utcnow(),
                    mood_score=max(1, min(10, rating)),  # Ensure within bounds
                    feelings=feelings or [],
                    notes=user_query[:200] if user_query else None,
                    risk_level=risk_level
                )
                
                # Always append to track mood changes throughout the day
                agent.accountability_goals[0].mood_trend.append(mood_entry)
                
                # Update last interaction
                agent.last_interaction = datetime.utcnow()
                
                # Sync to database
                await self.sync_agent_data_to_db(user_profile_id, agent_instance_id)
                
                return True
            else:
                logger.warning(f"No accountability goals found for {user_profile_id}:{agent_instance_id}")
                return False
                
        except Exception as e:
            logger.error(f"Failed to add mood log for {user_profile_id}:{agent_instance_id}: {e}")
            return False

    async def update_progress(self, user_profile_id: str, agent_instance_id: str, mood_score: float, engagement_score: float, notes: str = "") -> bool:
        """Update progress tracking - mirrors loneliness agent exactly"""
        try:
            cache_key = f"{user_profile_id}:{agent_instance_id}"
            agent = await self.get_accountability_agent_data(user_profile_id, agent_instance_id)
            
            if agent.accountability_goals:
                # Compute emotional trend versus previous mood score (if available)
                prev_mood = None
                if agent.accountability_goals[0].progress_tracking:
                    last = agent.accountability_goals[0].progress_tracking[-1]
                    try:
                        prev_mood = float(last.mood_score) if last.mood_score is not None else None
                    except Exception:
                        prev_mood = None

                trend = "stable"
                if prev_mood is not None:
                    if mood_score > prev_mood + 0.1:
                        trend = "improving"
                    elif mood_score < prev_mood - 0.1:
                        trend = "declining"
                
                # Short supportive affirmation
                affirmation = "Stay consistent. Every step counts."
                
                # Always add new progress entry to track changes throughout the day
                progress_entry = ProgressEntry(
                    date=datetime.utcnow(),
                    mood_score=mood_score,
                    social_engagement_score=engagement_score,
                    affirmation=affirmation,
                    emotional_trend=trend,
                    notes=notes
                )
                
                # Append to existing progress (don't replace)
                agent.accountability_goals[0].progress_tracking.append(progress_entry)
                logger.debug(f"Added new progress entry")
                
                # Update last interaction
                agent.last_interaction = datetime.utcnow()
                
                # Sync to database
                await self.sync_agent_data_to_db(user_profile_id, agent_instance_id)
                
                return True
            else:
                logger.warning(f"No accountability goals found for {user_profile_id}:{agent_instance_id}")
                return False
                
        except Exception as e:
            logger.error(f"Failed to update progress for {user_profile_id}:{agent_instance_id}: {e}")
            return False

    async def sync_agent_data_to_db(self, user_profile_id: str, agent_instance_id: str):
        """Sync agent data to MongoDB - mirrors loneliness agent exactly"""
        try:
            cache_key = f"{user_profile_id}:{agent_instance_id}"
            agent = self.accountability_agent_cache.get(cache_key)
            
            if agent and self.mongo_client and hasattr(self.mongo_client, 'db') and self.mongo_client.db is not None:
                # Get the full agent document to preserve other goals
                full_agent_doc = self.mongo_client.db.accountability_agents.find_one({
                    "user_profile_id": user_profile_id
                })
                
                if full_agent_doc:
                    # Update the specific goal in the existing document
                    full_agent = AccountabilityAgent(**full_agent_doc)
                    
                    # Find and update the specific goal
                    for i, goal in enumerate(full_agent.accountability_goals):
                        if goal.goal_id == agent_instance_id:
                            full_agent.accountability_goals[i] = agent.accountability_goals[0]
                            break
                    else:
                        # Goal not found, add it
                        full_agent.accountability_goals.append(agent.accountability_goals[0])
                    
                    # Update metadata
                    full_agent.last_interaction = agent.last_interaction
                    full_agent.total_conversations = getattr(agent, 'total_conversations', full_agent.total_conversations)
                    
                    # Save to database
                    agent_dict = full_agent.model_dump()
                    agent_dict = json.loads(json.dumps(agent_dict, cls=DateTimeEncoder))
                    
                    self.mongo_client.db.accountability_agents.update_one(
                        {"user_profile_id": user_profile_id},
                        {"$set": agent_dict},
                        upsert=True
                    )
                else:
                    # No existing document, create new one
                    agent_dict = agent.model_dump()
                    agent_dict = json.loads(json.dumps(agent_dict, cls=DateTimeEncoder))
                    
                    self.mongo_client.db.accountability_agents.insert_one(agent_dict)
                
                logger.debug(f"Synced accountability agent data to DB for {user_profile_id}:{agent_instance_id}")
                
        except Exception as e:
            logger.error(f"Failed to sync accountability agent data to DB: {e}")

    async def log_conversation(self, user_profile_id: str, agent_instance_id: str, conversation_id: str, user_text: str, agent_reply: str):
        """Log conversation for analytics - mirrors loneliness agent"""
        try:
            cache_key = f"{user_profile_id}:{agent_instance_id}"
            agent = self.accountability_agent_cache.get(cache_key)
            
            if agent:
                conversation_entry = {
                    "conversation_id": conversation_id,
                    "timestamp": datetime.utcnow().isoformat(),
                    "user_text": user_text[:500],  # Truncate for storage
                    "agent_reply": agent_reply[:500],  # Truncate for storage
                }
                
                agent.conversations.append(conversation_entry)
                agent.total_conversations += 1
                
                # Keep only last 50 conversations to manage storage
                if len(agent.conversations) > 50:
                    agent.conversations = agent.conversations[-50:]
                
        except Exception as e:
            logger.warning(f"Failed to log conversation: {e}")