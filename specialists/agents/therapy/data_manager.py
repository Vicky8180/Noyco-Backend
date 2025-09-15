from __future__ import annotations

"""
MongoDB DataManager for the Therapy Support agent. 

This module follows the same architecture as the loneliness agent data manager,
using MongoDB collections: user_profiles and therapy_agents.
Updated to use real MongoDB persistence instead of in-memory storage.
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

try:
    from memory.redis_client import RedisMemory
    from memory.mongo_client import MongoMemory
    # Import from unified schema
    from ..schema import (
        UserProfile, TherapyAgent, TherapyGoal, CheckIn, 
        MoodLog, ProgressEntry, BaseDBModel, generate_therapy_goal_id
    )
    # Import CheckpointState from local schema
    from .schema import CheckpointState
except ImportError as e:
    logging.warning(f"Import error in therapy data manager: {e}. Using minimal fallback implementations.")
    import random
    from pydantic import BaseModel, Field
    from datetime import datetime
    from uuid import uuid4
    
    # Minimal fallback implementations
    def generate_therapy_goal_id() -> str:
        return f"therapy_{random.randint(100, 999)}"
    
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
        locale: str = "us"
    
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
        mood_score: Optional[float] = Field(None, ge=0.0, le=10.0)
        engagement_score: Optional[float] = Field(None, ge=0.0, le=10.0)
        notes: Optional[str] = None
    
    class TherapyGoal(BaseModel):
        goal_id: str = Field(default_factory=generate_therapy_goal_id)
        title: str
        description: Optional[str] = None
        due_date: Optional[datetime] = None
        status: str = "active"
        check_ins: List[CheckIn] = Field(default_factory=list)
        streak: int = 0
        max_streak: int = 0
        progress_tracking: List[ProgressEntry] = Field(default_factory=list)
        mood_trend: List[MoodLog] = Field(default_factory=list)
        last_checkpoint: str = "GREETING"  # Add checkpoint field
    
    class TherapyAgent(BaseModel):
        agent_instance_id: str = Field(default_factory=lambda: str(uuid4()))
        user_profile_id: str
        therapy_goals: List[TherapyGoal] = Field(default_factory=list)
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
            'therapy_agents': type('Collection', (), {'find_one': lambda x: None, 'update_one': lambda *args, **kwargs: None})()
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

# Session and breathing sessions cache (kept in memory for performance)
_session_cache: Dict[str, Dict[str, Any]] = {}
_breathing_sessions: Dict[str, Dict[str, Any]] = {}


class TherapyDataManager:
    """MongoDB-based data manager for therapy agent following loneliness agent pattern"""
    
    def __init__(self, redis_client=None, mongo_client=None):
        self.redis_client = redis_client or RedisMemory()
        self.mongo_client = mongo_client or MongoMemory()
        
        # In-memory caches for ultra-low latency
        self.user_profile_cache: Dict[str, UserProfile] = {}
        self.therapy_agent_cache: Dict[str, TherapyAgent] = {}
        
        # Cache statistics
        self.cache_stats = {
            "profile_hits": 0,
            "profile_misses": 0,
            "agent_hits": 0,
            "agent_misses": 0
        }
        self._cache_ttl = 1800  # 30 minutes

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
        """Create default user profile with comprehensive fields for therapy personalization"""
        return UserProfile(
            user_profile_id=user_profile_id,
            user_id=user_profile_id,  # Fallback mapping
            profile_name="Default Profile",
            name="Friend",
            age=None,
            gender=None,
            interests=["general wellbeing", "self-care"],
            hobbies=["reading", "walking"],
            hates=[],  # Important for avoiding triggers
            personality_traits=["thoughtful", "resilient"],
            loved_ones=[],
            past_stories=[],
            preferences={"communication_style": "supportive", "session_pace": "comfortable"},
            health_info={},
            emotional_baseline="neutral",
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

    async def get_therapy_agent_data(self, user_profile_id: str, agent_instance_id: str) -> TherapyAgent:
        """Fetch therapy agent data with multi-level caching"""
        cache_key = f"{user_profile_id}:{agent_instance_id}"
        
        # Check in-memory cache first
        if cache_key in self.therapy_agent_cache:
            self.cache_stats["agent_hits"] += 1
            return self.therapy_agent_cache[cache_key]
        
        self.cache_stats["agent_misses"] += 1
        
        # Check Redis cache
        redis_key = f"therapy_agent:{cache_key}"
        try:
            cached_data = await self.redis_client.redis.get(redis_key)
            if cached_data:
                agent_dict = safe_json_loads(cached_data)
                agent = TherapyAgent(**agent_dict)
                self.therapy_agent_cache[cache_key] = agent
                return agent
        except Exception as e:
            logger.warning(f"Redis cache fetch failed for therapy agent {cache_key}: {e}")
        
        # Fetch from MongoDB
        agent = await self._fetch_agent_data_from_db(user_profile_id, agent_instance_id)
        
        # Cache in both Redis and memory
        await self._cache_agent_data(cache_key, agent)
        
        return agent
    
    async def _fetch_agent_data_from_db(self, user_profile_id: str, agent_instance_id: str) -> TherapyAgent:
        """Fetch therapy agent data from MongoDB therapy_agents collection"""
        try:
            # Fetch document by user_profile_id only
            # Check if mongo_client and db are available
            if not self.mongo_client or not hasattr(self.mongo_client, 'db') or self.mongo_client.db is None:
                logger.warning(f"MongoDB connection not available, creating default agent for {user_profile_id}")
                return self._create_default_agent_data(user_profile_id, agent_instance_id)
                
            agent_doc = self.mongo_client.db.therapy_agents.find_one({
                "user_profile_id": user_profile_id
            })
            
            if agent_doc:
                # Remove MongoDB's _id field
                agent_doc.pop('_id', None)
                agent = TherapyAgent(**agent_doc)
                
                # Find the specific goal by agent_instance_id
                target_goal = None
                for goal in agent.therapy_goals:
                    if goal.goal_id == agent_instance_id:
                        target_goal = goal
                        break
                
                if target_goal:
                    # Return agent with only the requested goal
                    agent.therapy_goals = [target_goal]
                    return agent
                else:
                    # Goal not found, add it to existing agent
                    new_goal = TherapyGoal(
                        goal_id=agent_instance_id,
                        title="Mental Health Check-in",
                        description="Daily mood tracking and mental wellness support",
                        status="active",
                        last_checkpoint="GREETING"
                    )
                    agent.therapy_goals.append(new_goal)
                    
                    # Save updated agent back to DB
                    await self._save_agent_with_new_goal(agent)
                    
                    # Return agent with only the new goal
                    agent.therapy_goals = [new_goal]
                    return agent
            else:
                # Create default agent data (no document exists for this user)
                return self._create_default_agent_data(user_profile_id, agent_instance_id)
                
        except Exception as e:
            logger.error(f"Failed to fetch therapy agent data {user_profile_id}:{agent_instance_id} from DB: {e}")
            return self._create_default_agent_data(user_profile_id, agent_instance_id)
    
    def _create_default_agent_data(self, user_profile_id: str, agent_instance_id: str) -> TherapyAgent:
        """Create default therapy agent data with initial goal"""
        default_goal = TherapyGoal(
            goal_id=agent_instance_id,  # Use agent_instance_id as goal_id
            title="Mental Health Check-in",
            description="Daily mood tracking and mental wellness support",
            status="active",
            last_checkpoint="GREETING"
        )
        
        return TherapyAgent(
            user_profile_id=user_profile_id,
            therapy_goals=[default_goal],
            last_interaction=datetime.utcnow()
        )
    
    async def _save_agent_with_new_goal(self, agent: TherapyAgent):
        """Save agent back to DB when a new goal is added"""
        try:
            self.mongo_client.db.therapy_agents.update_one(
                {"user_profile_id": agent.user_profile_id},
                {"$set": agent.model_dump()},
                upsert=True
            )
            logger.debug(f"Saved agent with new goal for user {agent.user_profile_id}")
        except Exception as e:
            logger.error(f"Failed to save agent with new goal: {e}")
    
    async def _cache_agent_data(self, cache_key: str, agent: TherapyAgent):
        """Cache agent data in Redis and memory"""
        try:
            # Cache in memory
            self.therapy_agent_cache[cache_key] = agent
            
            # Cache in Redis with TTL
            redis_key = f"therapy_agent:{cache_key}"
            agent_json = agent.model_dump_json()
            await self.redis_client.redis.set(redis_key, agent_json, ex=self._cache_ttl)
            
        except Exception as e:
            logger.warning(f"Failed to cache therapy agent {cache_key}: {e}")

    # Session state ---------------------------------------------------------
    def get_session_state(self, conversation_id: str, user_profile_id: str) -> Dict[str, Any]:
        """Get session state for conversation (kept in memory for performance)"""
        session_key = f"{conversation_id}:{user_profile_id}"
        state = _session_cache.get(session_key, {
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
            _session_cache[session_key] = state
        
        return state

    def update_session_state(self, conversation_id: str, user_profile_id: str, state: Dict[str, Any]) -> None:
        """Update session state"""
        session_key = f"{conversation_id}:{user_profile_id}"
        state["last_activity"] = datetime.utcnow()
        _session_cache[session_key] = state
        
        # Clean up old sessions periodically
        if len(_session_cache) > 1000:
            self._cleanup_old_sessions()

    def _cleanup_old_sessions(self):
        """Clean up old session states"""
        cutoff_time = datetime.utcnow() - timedelta(hours=24)
        keys_to_remove = []
        
        for key, state in _session_cache.items():
            if state.get("last_activity", datetime.min) < cutoff_time:
                keys_to_remove.append(key)
        
        for key in keys_to_remove:
            _session_cache.pop(key, None)

    # Checkpoint helpers -----------------------------------------------------
    async def get_checkpoint(self, user_profile_id: str, agent_instance_id: str) -> str:
        """Get current checkpoint state"""
        agent = await self.get_therapy_agent_data(user_profile_id, agent_instance_id)
        if agent.therapy_goals:
            return agent.therapy_goals[0].last_checkpoint
        return "GREETING"

    async def update_checkpoint(self, user_profile_id: str, agent_instance_id: str, checkpoint: str) -> None:
        """Update checkpoint state"""
        cache_key = f"{user_profile_id}:{agent_instance_id}"
        agent = await self.get_therapy_agent_data(user_profile_id, agent_instance_id)
        
        if agent.therapy_goals:
            # Update checkpoint directly on the goal
            agent.therapy_goals[0].last_checkpoint = checkpoint
            agent.last_interaction = datetime.utcnow()
            
            # Update cache
            self.therapy_agent_cache[cache_key] = agent
            
            # Sync to database
            await self.sync_agent_data_to_db(user_profile_id, agent_instance_id)

    # Check-ins / progress ---------------------------------------------------
    async def add_check_in(self, user_profile_id: str, agent_instance_id: str, user_text: str) -> bool:
        """Add daily check-in entry"""
        try:
            cache_key = f"{user_profile_id}:{agent_instance_id}"
            agent = await self.get_therapy_agent_data(user_profile_id, agent_instance_id)
            
            if agent.therapy_goals:
                today = datetime.utcnow().date()
                
                # Check if there's already a check-in for today
                existing_checkin_today = False
                for check_in in agent.therapy_goals[0].check_ins:
                    if check_in.date.date() == today:
                        existing_checkin_today = True
                        # Update the existing check-in response with latest query
                        check_in.response = user_text
                        check_in.notes = "User interaction updated"
                        logger.debug(f"Updated existing check-in for today {today}")
                        break
                
                # Only add new check-in if none exists for today
                if not existing_checkin_today:
                    check_in = CheckIn(
                        date=datetime.utcnow(),
                        response=user_text,
                        completed=True,
                        notes="User interaction recorded"
                    )
                    
                    agent.therapy_goals[0].check_ins.append(check_in)
                    
                    # Update streak only if it's a new day check-in
                    agent.therapy_goals[0].streak += 1
                    if agent.therapy_goals[0].streak > agent.therapy_goals[0].max_streak:
                        agent.therapy_goals[0].max_streak = agent.therapy_goals[0].streak
                    
                    logger.debug(f"Added new check-in for today {today}, streak: {agent.therapy_goals[0].streak}")
                
                # Update last interaction
                agent.last_interaction = datetime.utcnow()
                
                # Update cache
                self.therapy_agent_cache[cache_key] = agent
                
            return True
        except Exception as e:
            logger.error(f"Failed to add check-in for {user_profile_id}:{agent_instance_id}: {e}")
            return False

    async def add_mood_log(
        self,
        user_profile_id: str,
        agent_instance_id: str,
        feelings: List[str],
        notes: str,
        risk_level: int = 0,
    ) -> bool:
        """Add mood log entry"""
        try:
            cache_key = f"{user_profile_id}:{agent_instance_id}"
            agent = await self.get_therapy_agent_data(user_profile_id, agent_instance_id)
            
            if agent.therapy_goals:
                # Ensure feelings are populated by extracting from notes if empty
                extracted: List[str] = []
                if (not feelings) and notes:
                    tokens = [w.strip(".,!? ").lower() for w in (notes or "").split()]
                    vocab = {
                        "sad", "anxious", "angry", "tired", "lonely", "overwhelmed", "numb", "stressed",
                        "worried", "scared", "fearful", "hopeless", "frustrated", "upset", "confused",
                    }
                    for w in tokens:
                        if w in vocab and w not in extracted:
                            extracted.append(w)
                        if len(extracted) >= 5:
                            break
                final_feelings = feelings or extracted or ["anxious"]

                mood_entry = MoodLog(
                    date=datetime.utcnow(),
                    mood=', '.join(final_feelings),
                    stress_level=max(1, risk_level) if risk_level <= 10 else None,
                    notes=notes[:200] if notes else None
                )
                
                # Always append to track mood changes throughout the day
                agent.therapy_goals[0].mood_trend.append(mood_entry)
                logger.debug(f"Added new mood log: feelings: {feelings}, stress_level: {risk_level}")
                
                # Update last interaction
                agent.last_interaction = datetime.utcnow()
                
                # Update cache
                self.therapy_agent_cache[cache_key] = agent
                
                # Immediately sync to database to persist the appended data
                await self.sync_agent_data_to_db(user_profile_id, agent_instance_id)
                
            return True
        except Exception as e:
            logger.error(f"Failed to add mood log for {user_profile_id}:{agent_instance_id}: {e}")
            return False

    async def update_progress(
        self,
        user_profile_id: str,
        agent_instance_id: str,
        mood_score: float,
        engagement_score: float,
        notes: str,
    ) -> bool:
        """Update progress tracking"""
        try:
            cache_key = f"{user_profile_id}:{agent_instance_id}"
            agent = await self.get_therapy_agent_data(user_profile_id, agent_instance_id)
            
            if agent.therapy_goals:
                # Compute emotional trend versus previous mood score (if available)
                prev_mood = None
                if agent.therapy_goals[0].progress_tracking:
                    last = agent.therapy_goals[0].progress_tracking[-1]
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
                affirmation = "You’re not alone. One small step at a time."

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
                agent.therapy_goals[0].progress_tracking.append(progress_entry)
                logger.debug(f"Added new progress entry")
                
                # Update last interaction
                agent.last_interaction = datetime.utcnow()
                
                # Update cache
                self.therapy_agent_cache[cache_key] = agent
                
                # Immediately sync to database to persist the appended data
                await self.sync_agent_data_to_db(user_profile_id, agent_instance_id)
                
            return True
        except Exception as e:
            logger.error(f"Failed to update progress for {user_profile_id}:{agent_instance_id}: {e}")
            return False

    async def get_mood_history(self, user_profile_id: str, agent_instance_id: str, days: int = 7) -> List[Dict[str, Any]]:
        """Get mood history for the specified number of days"""
        try:
            agent = await self.get_therapy_agent_data(user_profile_id, agent_instance_id)
            
            if not agent.therapy_goals:
                return []
            
            cutoff = datetime.utcnow() - timedelta(days=days)
            mood_history = []
            
            for mood_log in agent.therapy_goals[0].mood_trend:
                if mood_log.date >= cutoff:
                    mood_history.append({
                        "timestampISO": mood_log.date.isoformat(),
                        "mood": mood_log.mood,
                        "moodScore": mood_log.stress_level or 5,  # fallback score
                        "notes": mood_log.notes
                    })
            
            return mood_history
            
        except Exception as e:
            logger.error(f"Failed to get mood history for {user_profile_id}:{agent_instance_id}: {e}")
            return []

    # Breathing sessions -----------------------------------------------------
    async def start_breathing_session(self, user_profile_id: str, conversation_id: str, duration_sec: int) -> str:
        """Start a breathing session (kept in memory for performance)"""
        session_id = f"breathing:{user_profile_id}:{conversation_id}:{int(time.time()*1000)}"
        _breathing_sessions[session_id] = {
            "user_profile_id": user_profile_id,
            "conversation_id": conversation_id,
            "duration_sec": duration_sec,
            "status": "active",
            "start_time": datetime.utcnow().isoformat(),
        }
        return session_id

    async def complete_breathing_session(self, session_id: str) -> bool:
        """Complete a breathing session"""
        sess = _breathing_sessions.get(session_id)
        if not sess:
            return False
        sess["status"] = "completed"
        sess["end_time"] = datetime.utcnow().isoformat()
        return True

    # MongoDB sync methods ---------------------------------------------------
    async def sync_agent_data_to_db(self, user_profile_id: str, agent_instance_id: str):
        """Sync agent data to MongoDB - updates specific goal within the user's document"""
        try:
            cache_key = f"{user_profile_id}:{agent_instance_id}"
            if cache_key in self.therapy_agent_cache:
                cached_agent = self.therapy_agent_cache[cache_key]
                cached_agent.last_interaction = datetime.utcnow()
                
                # Get the specific goal to update
                if cached_agent.therapy_goals:
                    goal_to_update = cached_agent.therapy_goals[0]
                    
                    # First, fetch the full document from DB
                    existing_doc = self.mongo_client.db.therapy_agents.find_one({
                        "user_profile_id": user_profile_id
                    })
                    
                    if existing_doc:
                        # Update the specific goal in the existing document
                        existing_doc.pop('_id', None)
                        full_agent = TherapyAgent(**existing_doc)
                        
                        # Find and update the specific goal
                        goal_updated = False
                        for i, goal in enumerate(full_agent.therapy_goals):
                            if goal.goal_id == agent_instance_id:
                                full_agent.therapy_goals[i] = goal_to_update
                                goal_updated = True
                                break
                        
                        # If goal not found, add it
                        if not goal_updated:
                            full_agent.therapy_goals.append(goal_to_update)
                        
                        # Update last interaction for the full document
                        full_agent.last_interaction = datetime.utcnow()
                        
                        # Save the full updated document
                        self.mongo_client.db.therapy_agents.update_one(
                            {"user_profile_id": user_profile_id},
                            {"$set": full_agent.model_dump()},
                            upsert=True
                        )
                    else:
                        # No existing document, create new one
                        self.mongo_client.db.therapy_agents.update_one(
                            {"user_profile_id": user_profile_id},
                            {"$set": cached_agent.model_dump()},
                            upsert=True
                        )
                    
                    logger.debug(f"Synced therapy agent data to DB: {user_profile_id}:{agent_instance_id}")
                
        except Exception as e:
            logger.error(f"Failed to sync therapy agent data to DB: {e}")

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

    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache performance statistics"""
        return {
            **self.cache_stats,
            "memory_cache_sizes": {
                "user_profiles": len(self.user_profile_cache),
                "therapy_agents": len(self.therapy_agent_cache),
                "sessions": len(_session_cache),
                "breathing_sessions": len(_breathing_sessions)
            }
        }


# Convenience singleton (optional)
therapy_data_manager_singleton = TherapyDataManager()
