"""
Data Manager for Loneliness Companion Agent
Handles caching, serialization, and database operations with proper error handling.
Updated to use unified schema design with separate user_profiles and loneliness_agents collections.
"""

import asyncio
import logging
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
import sys
import os

# Add the parent directory to Python path
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(os.path.dirname(current_dir))
sys.path.insert(0, parent_dir)

try:
    from memory.redis_client import RedisMemory
    from memory.mongo_client import MongoMemory
    # Import from unified schema
    from ..schema import (
        UserProfile, LonelinessAgent, LonelinessGoal, CheckIn, 
        MoodLog, ProgressEntry, BaseDBModel, generate_loneliness_goal_id
    )
except ImportError as e:
    logging.warning(f"Import error in data manager: {e}. Using minimal fallback implementations.")
    import random
    from pydantic import BaseModel, Field
    from datetime import datetime
    from uuid import uuid4
    
    # Minimal fallback implementations - only essential for testing
    def generate_loneliness_goal_id() -> str:
        return f"loneliness_{random.randint(100, 999)}"
    
    class UserProfile(BaseModel):
        user_profile_id: str = Field(default_factory=lambda: str(uuid4()))
        user_id: str
        profile_name: str = "Default Profile"
        name: str = "Friend"
        age: Optional[int] = None
        interests: List[str] = Field(default_factory=list)
        hobbies: List[str] = Field(default_factory=list)
        personality_traits: List[str] = Field(default_factory=list)
        preferences: Dict = Field(default_factory=dict)
        loved_ones: List = Field(default_factory=list)
        past_stories: List = Field(default_factory=list)
        is_active: bool = True
    
    class CheckIn(BaseModel):
        date: datetime
        response: str
        completed: bool = False
        notes: Optional[str] = None
    
    class MoodLog(BaseModel):
        date: datetime
        mood: str
        stress_level: Optional[int] = Field(None, ge=1, le=10)
        notes: Optional[str] = None
    
    class ProgressEntry(BaseModel):
        date: datetime
        loneliness_score: Optional[float] = Field(None, ge=0.0, le=10.0)
        social_engagement_score: Optional[float] = Field(None, ge=0.0, le=10.0)
        affirmation: Optional[str] = None
        emotional_trend: Optional[str] = None
        notes: Optional[str] = None
    
    class LonelinessGoal(BaseModel):
        goal_id: str = Field(default_factory=generate_loneliness_goal_id)
        title: str
        description: Optional[str] = None
        due_date: Optional[datetime] = None
        status: str = "active"
        check_ins: List[CheckIn] = Field(default_factory=list)
        streak: int = 0
        max_streak: int = 0
        progress_tracking: List[ProgressEntry] = Field(default_factory=list)
        mood_trend: List[MoodLog] = Field(default_factory=list)
    
    class LonelinessAgent(BaseModel):
        agent_instance_id: str = Field(default_factory=lambda: str(uuid4()))
        user_profile_id: str
        loneliness_goals: List[LonelinessGoal] = Field(default_factory=list)
        last_interaction: Optional[datetime] = None

    # Minimal fallback clients
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
            'loneliness_agents': type('Collection', (), {'find_one': lambda x: None, 'update_one': lambda *args, **kwargs: None})()
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
    # Handle bytes from Redis
    if isinstance(data, bytes):
        data = data.decode('utf-8')
    elif not isinstance(data, str):
        raise ValueError(f"Expected str or bytes, got {type(data)}")
        
    def datetime_parser(dct):
        for key, value in dct.items():
            if isinstance(value, str):
                # Try to parse ISO datetime strings
                try:
                    if 'T' in value and (value.endswith('Z') or '+' in value[-6:] or value.count(':') >= 2):
                        dct[key] = datetime.fromisoformat(value.replace('Z', '+00:00'))
                except (ValueError, AttributeError):
                    pass
        return dct
    
    return json.loads(data, object_hook=datetime_parser)

class LonelinessDataManager:
    """Manages data operations for loneliness companion agent using unified schema"""
    
    def __init__(self, redis_client=None, mongo_client=None):
        self.redis_client = redis_client or RedisMemory()
        self.mongo_client = mongo_client or MongoMemory()
        
        # In-memory caches for ultra-low latency
        self.user_profile_cache: Dict[str, UserProfile] = {}
        self.loneliness_agent_cache: Dict[str, LonelinessAgent] = {}
        self.session_state_cache: Dict[str, Dict[str, Any]] = {}
        
        # Cache statistics
        self.cache_stats = {
            "profile_hits": 0,
            "profile_misses": 0,
            "agent_hits": 0,
            "agent_misses": 0
        }
    
    async def get_user_profile(self, user_profile_id: str) -> UserProfile:
        """Fetch user profile with multi-level caching"""
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
            logger.warning(f"Redis cache fetch failed for user profile {user_profile_id}: {e}")
        
        # Fetch from MongoDB
        profile = await self._fetch_profile_from_db(user_profile_id)
        
        # Cache in both Redis and memory
        await self._cache_user_profile(user_profile_id, profile)
        
        return profile
    
    async def _fetch_profile_from_db(self, user_profile_id: str) -> UserProfile:
        """Fetch user profile from MongoDB user_profiles collection"""
        try:
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
            personality_traits=["supportive", "friendly"],
            is_active=True
        )
    
    async def _cache_user_profile(self, user_profile_id: str, profile: UserProfile):
        """Cache user profile in Redis and memory"""
        try:
            # Cache in memory
            self.user_profile_cache[user_profile_id] = profile
            
            # Cache in Redis with TTL
            redis_key = f"user_profile:{user_profile_id}"
            profile_json = profile.model_dump_json()
            await self.redis_client.redis.set(redis_key, profile_json, ex=1800)  # 30 min TTL
            
        except Exception as e:
            logger.warning(f"Failed to cache user profile {user_profile_id}: {e}")
    
    async def get_loneliness_agent_data(self, user_profile_id: str, agent_instance_id: str) -> LonelinessAgent:
        """Fetch loneliness agent data with multi-level caching"""
        cache_key = f"{user_profile_id}:{agent_instance_id}"
        
        # Check in-memory cache first
        if cache_key in self.loneliness_agent_cache:
            self.cache_stats["agent_hits"] += 1
            return self.loneliness_agent_cache[cache_key]
        
        self.cache_stats["agent_misses"] += 1
        
        # Check Redis cache
        redis_key = f"loneliness_agent:{cache_key}"
        try:
            cached_data = await self.redis_client.redis.get(redis_key)
            if cached_data:
                agent_dict = safe_json_loads(cached_data)
                agent = LonelinessAgent(**agent_dict)
                self.loneliness_agent_cache[cache_key] = agent
                return agent
        except Exception as e:
            logger.warning(f"Redis cache fetch failed for loneliness agent {cache_key}: {e}")
        
        # Fetch from MongoDB
        agent = await self._fetch_agent_data_from_db(user_profile_id, agent_instance_id)
        
        # Cache in both Redis and memory
        await self._cache_agent_data(cache_key, agent)
        
        return agent
    
    async def _fetch_agent_data_from_db(self, user_profile_id: str, agent_instance_id: str) -> LonelinessAgent:
        """Fetch loneliness agent data from MongoDB loneliness_agents collection"""
        try:
            # Fetch document by user_profile_id only
            agent_doc = self.mongo_client.db.loneliness_agents.find_one({
                "user_profile_id": user_profile_id
            })
            
            if agent_doc:
                # Remove MongoDB's _id field
                agent_doc.pop('_id', None)
                agent = LonelinessAgent(**agent_doc)
                
                # Find the specific goal by agent_instance_id
                target_goal = None
                for goal in agent.loneliness_goals:
                    if goal.goal_id == agent_instance_id:
                        target_goal = goal
                        break
                
                if target_goal:
                    # Return agent with only the requested goal
                    agent.loneliness_goals = [target_goal]
                    return agent
                else:
                    # Goal not found, add it to existing agent
                    new_goal = LonelinessGoal(
                        goal_id=agent_instance_id,
                        title="Social Connection Building",
                        description="Gradually increase social interactions and reduce feelings of loneliness",
                        status="active"
                    )
                    agent.loneliness_goals.append(new_goal)
                    
                    # Save updated agent back to DB
                    await self._save_agent_with_new_goal(agent)
                    
                    # Return agent with only the new goal
                    agent.loneliness_goals = [new_goal]
                    return agent
            else:
                # Create default agent data (no document exists for this user)
                return self._create_default_agent_data(user_profile_id, agent_instance_id)
                
        except Exception as e:
            logger.error(f"Failed to fetch loneliness agent data {user_profile_id}:{agent_instance_id} from DB: {e}")
            return self._create_default_agent_data(user_profile_id, agent_instance_id)
    
    def _create_default_agent_data(self, user_profile_id: str, agent_instance_id: str) -> LonelinessAgent:
        """Create default loneliness agent data with initial goal"""
        default_goal = LonelinessGoal(
            goal_id=agent_instance_id,  # Use agent_instance_id as goal_id
            title="Social Connection Building",
            description="Gradually increase social interactions and reduce feelings of loneliness",
            status="active"
        )
        
        return LonelinessAgent(
            user_profile_id=user_profile_id,
            loneliness_goals=[default_goal],
            last_interaction=datetime.utcnow()
        )
    
    async def _save_agent_with_new_goal(self, agent: LonelinessAgent):
        """Save agent back to DB when a new goal is added"""
        try:
            self.mongo_client.db.loneliness_agents.update_one(
                {"user_profile_id": agent.user_profile_id},
                {"$set": agent.model_dump()},
                upsert=True
            )
            logger.debug(f"Saved agent with new goal for user {agent.user_profile_id}")
        except Exception as e:
            logger.error(f"Failed to save agent with new goal: {e}")
    
    async def _cache_agent_data(self, cache_key: str, agent: LonelinessAgent):
        """Cache agent data in Redis and memory"""
        try:
            # Cache in memory
            self.loneliness_agent_cache[cache_key] = agent
            
            # Cache in Redis with TTL
            redis_key = f"loneliness_agent:{cache_key}"
            agent_json = agent.model_dump_json()
            await self.redis_client.redis.set(redis_key, agent_json, ex=1800)  # 30 min TTL
            
        except Exception as e:
            logger.warning(f"Failed to cache loneliness agent {cache_key}: {e}")
    
    async def update_progress(self, user_profile_id: str, agent_instance_id: str, 
                            loneliness_score: float, engagement_score: float, notes: str = ""):
        """Update progress tracking for a specific goal (appends new progress entry for each query)"""
        try:
            cache_key = f"{user_profile_id}:{agent_instance_id}"
            agent = await self.get_loneliness_agent_data(user_profile_id, agent_instance_id)
            
            if agent.loneliness_goals:
                # Always add new progress entry to track changes throughout the day
                progress_entry = ProgressEntry(
                    date=datetime.utcnow(),
                    loneliness_score=loneliness_score,
                    social_engagement_score=engagement_score,
                    notes=notes,
                    emotional_trend="improving" if loneliness_score < 5.0 else "stable"
                )
                
                # Append to existing progress (don't replace)
                agent.loneliness_goals[0].progress_tracking.append(progress_entry)
                logger.debug(f"Added new progress entry")
                
                # Update last interaction
                agent.last_interaction = datetime.utcnow()
                
                # Update cache
                self.loneliness_agent_cache[cache_key] = agent
                
                # Immediately sync to database to persist the appended data
                await self.sync_agent_data_to_db(user_profile_id, agent_instance_id)
                
                logger.debug(f"Progress updated and synced for {user_profile_id}:{agent_instance_id}")
                
        except Exception as e:
            logger.error(f"Failed to update progress for {user_profile_id}:{agent_instance_id}: {e}")
            raise
    
    async def add_mood_log(self, user_profile_id: str, agent_instance_id: str, mood: str, stress_level: int = None):
        """Add mood log entry (appends to existing mood trend for each query)"""
        try:
            cache_key = f"{user_profile_id}:{agent_instance_id}"
            agent = await self.get_loneliness_agent_data(user_profile_id, agent_instance_id)
            
            if agent.loneliness_goals:
                mood_entry = MoodLog(
                    date=datetime.utcnow(),
                    mood=mood,
                    stress_level=stress_level,
                    notes=f"Mood detected during conversation"
                )
                
                # Always append to track mood changes throughout the day
                agent.loneliness_goals[0].mood_trend.append(mood_entry)
                logger.debug(f"Added new mood log: {mood}")
                
                # Update last interaction
                agent.last_interaction = datetime.utcnow()
                
                # Update cache
                self.loneliness_agent_cache[cache_key] = agent
                
                # Immediately sync to database to persist the appended data
                await self.sync_agent_data_to_db(user_profile_id, agent_instance_id)
                
                logger.debug(f"Mood log processed and synced for {user_profile_id}:{agent_instance_id}")
                
        except Exception as e:
            logger.error(f"Failed to add mood log for {user_profile_id}:{agent_instance_id}: {e}")
            raise
    
    async def add_check_in(self, user_profile_id: str, agent_instance_id: str, user_query: str):
        """Add daily check-in entry - only one per day"""
        try:
            cache_key = f"{user_profile_id}:{agent_instance_id}"
            agent = await self.get_loneliness_agent_data(user_profile_id, agent_instance_id)
            
            if agent.loneliness_goals:
                today = datetime.utcnow().date()
                
                # Check if there's already a check-in for today
                existing_checkin_today = False
                for check_in in agent.loneliness_goals[0].check_ins:
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
                    
                    agent.loneliness_goals[0].check_ins.append(check_in)
                    
                    # Update streak only if it's a new day check-in
                    agent.loneliness_goals[0].streak += 1
                    if agent.loneliness_goals[0].streak > agent.loneliness_goals[0].max_streak:
                        agent.loneliness_goals[0].max_streak = agent.loneliness_goals[0].streak
                    
                    logger.debug(f"Added new check-in for today {today}, streak: {agent.loneliness_goals[0].streak}")
                
                # Update last interaction
                agent.last_interaction = datetime.utcnow()
                
                # Update cache
                self.loneliness_agent_cache[cache_key] = agent
                
        except Exception as e:
            logger.error(f"Failed to add check-in for {user_profile_id}:{agent_instance_id}: {e}")
    
    async def sync_agent_data_to_db(self, user_profile_id: str, agent_instance_id: str):
        """Sync agent data to MongoDB - updates specific goal within the user's document"""
        try:
            cache_key = f"{user_profile_id}:{agent_instance_id}"
            if cache_key in self.loneliness_agent_cache:
                cached_agent = self.loneliness_agent_cache[cache_key]
                cached_agent.last_interaction = datetime.utcnow()
                
                # Get the specific goal to update
                if cached_agent.loneliness_goals:
                    goal_to_update = cached_agent.loneliness_goals[0]
                    
                    # First, fetch the full document from DB
                    existing_doc = self.mongo_client.db.loneliness_agents.find_one({
                        "user_profile_id": user_profile_id
                    })
                    
                    if existing_doc:
                        # Update the specific goal in the existing document
                        existing_doc.pop('_id', None)
                        full_agent = LonelinessAgent(**existing_doc)
                        
                        # Find and update the specific goal
                        goal_updated = False
                        for i, goal in enumerate(full_agent.loneliness_goals):
                            if goal.goal_id == agent_instance_id:
                                full_agent.loneliness_goals[i] = goal_to_update
                                goal_updated = True
                                break
                        
                        # If goal not found, add it
                        if not goal_updated:
                            full_agent.loneliness_goals.append(goal_to_update)
                        
                        # Update last interaction for the full document
                        full_agent.last_interaction = datetime.utcnow()
                        
                        # Save the full updated document
                        self.mongo_client.db.loneliness_agents.update_one(
                            {"user_profile_id": user_profile_id},
                            {"$set": full_agent.model_dump()},
                            upsert=True
                        )
                    else:
                        # No existing document, create new one
                        self.mongo_client.db.loneliness_agents.update_one(
                            {"user_profile_id": user_profile_id},
                            {"$set": cached_agent.model_dump()},
                            upsert=True
                        )
                    
                    logger.debug(f"Synced loneliness agent data to DB: {user_profile_id}:{agent_instance_id}")
                
        except Exception as e:
            logger.error(f"Failed to sync loneliness agent data to DB: {e}")
    
    async def save_user_profile(self, profile: UserProfile):
        """Save user profile to MongoDB"""
        try:
            self.mongo_client.db.user_profiles.update_one(
                {"user_profile_id": profile.user_profile_id},
                {"$set": profile.model_dump()},
                upsert=True
            )
            
            # Update cache
            self.user_profile_cache[profile.user_profile_id] = profile
            
        except Exception as e:
            logger.error(f"Failed to save user profile {profile.user_profile_id}: {e}")
    
    def get_session_state(self, conversation_id: str, user_profile_id: str) -> Dict[str, Any]:
        """Get session state for conversation"""
        session_key = f"{conversation_id}:{user_profile_id}"
        state = self.session_state_cache.get(session_key, {
            "conversation_turns": [],
            "current_mood": "neutral",
            "engagement_level": 5.0,
            "last_activity": datetime.utcnow()
        })
        
        # Defensive programming: ensure state is always a dictionary
        if not isinstance(state, dict):
            logger.warning(f"Session state for {session_key} is not a dict (type: {type(state)}), resetting to default")
            state = {
                "conversation_turns": [],
                "current_mood": "neutral",
                "engagement_level": 5.0,
                "last_activity": datetime.utcnow()
            }
            self.session_state_cache[session_key] = state
        
        return state
    
    def update_session_state(self, conversation_id: str, user_profile_id: str, state: Dict[str, Any]):
        """Update session state"""
        session_key = f"{conversation_id}:{user_profile_id}"
        state["last_activity"] = datetime.utcnow()
        self.session_state_cache[session_key] = state
        
        # Clean up old sessions periodically
        if len(self.session_state_cache) > 1000:
            self._cleanup_old_sessions()
    
    def _cleanup_old_sessions(self):
        """Clean up old session states"""
        cutoff_time = datetime.utcnow() - timedelta(hours=24)
        keys_to_remove = []
        
        for key, state in self.session_state_cache.items():
            if state.get("last_activity", datetime.min) < cutoff_time:
                keys_to_remove.append(key)
        
        for key in keys_to_remove:
            self.session_state_cache.pop(key, None)
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache performance statistics"""
        return {
            **self.cache_stats,
            "memory_cache_sizes": {
                "user_profiles": len(self.user_profile_cache),
                "loneliness_agents": len(self.loneliness_agent_cache),
                "sessions": len(self.session_state_cache)
            }
        }
