from __future__ import annotations

"""
MongoDB DataManager for the Emotional Companion agent. 

This module follows the same architecture as the therapy agent data manager,
using MongoDB collections: user_profiles and emotional_companion_agents.
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
# Go up to the conversionalEngine root directory
root_dir = os.path.dirname(os.path.dirname(os.path.dirname(current_dir)))
sys.path.insert(0, root_dir)

try:
    from memory.redis_client import RedisMemory
    from memory.mongo_client import MongoMemory
    # Import from unified schema - try both relative and absolute paths
    try:
        # When running from agents folder
        from schema import (
            UserProfile, EmotionalCompanionAgent, EmotionalGoal, CheckIn, 
            MoodLog, ProgressEntry, BaseDBModel, generate_emotional_goal_id
        )
    except ImportError:
        # When running from root folder via run_dev.py
        from specialists.agents.schema import (
            UserProfile, EmotionalCompanionAgent, EmotionalGoal, CheckIn, 
            MoodLog, ProgressEntry, BaseDBModel, generate_emotional_goal_id
        )
    
    # Import CheckpointState from local schema
    try:
        from emotional.schema import CheckpointState
    except ImportError:
        from specialists.agents.emotional.schema import CheckpointState
except ImportError as e:
    logging.warning(f"Import error in emotional data manager: {e}. Using minimal fallback implementations.")
    import random
    from pydantic import BaseModel, Field
    from datetime import datetime
    from uuid import uuid4
    
    # Minimal fallback implementations
    def generate_emotional_goal_id() -> str:
        return f"emotional_{random.randint(100, 999)}"
    
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
        emotional_wellness_score: Optional[float] = Field(None, ge=0.0, le=10.0)
        engagement_score: Optional[float] = Field(None, ge=0.0, le=10.0)
        notes: Optional[str] = None
    
    class EmotionalGoal(BaseModel):
        goal_id: str = Field(default_factory=generate_emotional_goal_id)
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
            'emotional_companion_agents': type('Collection', (), {'find_one': lambda *_, **__: None, 'update_one': lambda *_, **__: None})()
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

# Session and comfort sessions cache (kept in memory for performance)
_session_cache: Dict[str, Dict[str, Any]] = {}
_comfort_sessions: Dict[str, Dict[str, Any]] = {}

# Collection used for storing emotional companion agent docs
_COLL_NAME = "emotional_companion_agents"

class EmotionalDataManager:
    """MongoDB-based data manager for emotional agent following therapy agent pattern"""
    
    def __init__(self, redis_client=None, mongo_client=None):
        self.redis_client = redis_client or RedisMemory()
        self.mongo_client = mongo_client or MongoMemory()
        
        # In-memory caches for ultra-low latency
        self.user_profile_cache: Dict[str, UserProfile] = {}
        self.emotional_agent_cache: Dict[str, EmotionalCompanionAgent] = {}
        
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
        """Create comprehensive default user profile for emotional support personalization"""
        return UserProfile(
            user_profile_id=user_profile_id,
            user_id=user_profile_id,  # Fallback mapping
            profile_name="Default Profile",
            name="Friend",
            age=None,
            gender=None,
            interests=["emotional wellbeing", "self-care", "mindfulness"],
            hobbies=["reading", "journaling", "listening to music"],
            hates=[],  # Important for avoiding emotional triggers
            personality_traits=["empathetic", "caring", "resilient"],
            loved_ones=[],
            past_stories=[],
            preferences={"communication_style": "nurturing", "comfort_pace": "gentle"},
            health_info={},
            emotional_baseline="balanced",
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

    async def get_emotional_agent_data(self, user_profile_id: str, agent_instance_id: str) -> EmotionalCompanionAgent:
        """Fetch emotional agent data with multi-level caching"""
        cache_key = f"{user_profile_id}:{agent_instance_id}"
        
        # Check in-memory cache first
        if cache_key in self.emotional_agent_cache:
            self.cache_stats["agent_hits"] += 1
            return self.emotional_agent_cache[cache_key]
        
        self.cache_stats["agent_misses"] += 1
        
        # Check Redis cache
        redis_key = f"emotional_agent:{cache_key}"
        try:
            cached_data = await self.redis_client.redis.get(redis_key)
            if cached_data:
                agent_dict = safe_json_loads(cached_data)
                agent = EmotionalCompanionAgent(**agent_dict)
                self.emotional_agent_cache[cache_key] = agent
                return agent
        except Exception as e:
            logger.warning(f"Redis cache fetch failed for emotional agent {cache_key}: {e}")
        
        # Fetch from MongoDB
        agent = await self._fetch_agent_data_from_db(user_profile_id, agent_instance_id)
        
        # Cache in both Redis and memory
        await self._cache_agent_data(cache_key, agent)
        
        return agent
    
    async def _fetch_agent_data_from_db(self, user_profile_id: str, agent_instance_id: str) -> EmotionalCompanionAgent:
        """Fetch emotional agent data from MongoDB emotional_companion_agents collection"""
        try:
            # Fetch document by user_profile_id only
            # Check if mongo_client and db are available
            if not self.mongo_client or not hasattr(self.mongo_client, 'db') or self.mongo_client.db is None:
                logger.warning(f"MongoDB connection not available, creating default agent for {user_profile_id}")
                return self._create_default_agent_data(user_profile_id, agent_instance_id)
                
            agent_doc = self.mongo_client.db[_COLL_NAME].find_one({
                "user_profile_id": user_profile_id
            })
            
            if agent_doc:
                # Remove MongoDB's _id field
                agent_doc.pop('_id', None)
                agent = EmotionalCompanionAgent(**agent_doc)
                
                # Find the specific goal by agent_instance_id
                target_goal = None
                for goal in agent.emotional_goals:
                    if goal.goal_id == agent_instance_id:
                        target_goal = goal
                        break
                
                if target_goal:
                    # Return agent with only the requested goal
                    agent.emotional_goals = [target_goal]
                    return agent
                else:
                    # Goal not found, add it to existing agent
                    new_goal = EmotionalGoal(
                        goal_id=agent_instance_id,
                        title="Emotional Support Journey",
                        description="Daily emotional check-ins and comfort support",
                        status="active",
                        last_checkpoint="GREETING"
                    )
                    agent.emotional_goals.append(new_goal)
                    
                    # Save updated agent back to DB
                    await self._save_agent_with_new_goal(agent)
                    
                    # Return agent with only the new goal
                    agent.emotional_goals = [new_goal]
                    return agent
            else:
                # Create default agent data (no document exists for this user)
                return self._create_default_agent_data(user_profile_id, agent_instance_id)
                
        except Exception as e:
            logger.error(f"Failed to fetch emotional agent data {user_profile_id}:{agent_instance_id} from DB: {e}")
            return self._create_default_agent_data(user_profile_id, agent_instance_id)
    
    def _create_default_agent_data(self, user_profile_id: str, agent_instance_id: str) -> EmotionalCompanionAgent:
        """Create default emotional agent data with initial goal"""
        default_goal = EmotionalGoal(
            goal_id=agent_instance_id,  # Use agent_instance_id as goal_id
            title="Emotional Support Journey",
            description="Daily emotional check-ins and comfort support",
            status="active"
        )
        
        return EmotionalCompanionAgent(
            user_profile_id=user_profile_id,
            emotional_goals=[default_goal],
            memory_stack=["I'm here to listen and support you through whatever you're going through."],
            comfort_tips=[
                "Take deep breaths when feeling overwhelmed",
                "It's okay to feel what you're feeling",
                "You don't have to go through this alone",
                "One moment at a time is enough"
            ],
            last_interaction=datetime.utcnow()
        )
    
    async def _save_agent_with_new_goal(self, agent: EmotionalCompanionAgent):
        """Save agent back to DB when a new goal is added"""
        try:
            self.mongo_client.db[_COLL_NAME].update_one(
                {"user_profile_id": agent.user_profile_id},
                {"$set": agent.model_dump()},
                upsert=True
            )
            logger.debug(f"Saved agent with new goal for user {agent.user_profile_id}")
        except Exception as e:
            logger.error(f"Failed to save agent with new goal: {e}")
    
    async def _cache_agent_data(self, cache_key: str, agent: EmotionalCompanionAgent):
        """Cache agent data in Redis and memory"""
        try:
            # Cache in memory
            self.emotional_agent_cache[cache_key] = agent
            
            # Cache in Redis with TTL
            redis_key = f"emotional_agent:{cache_key}"
            agent_json = agent.model_dump_json()
            await self.redis_client.redis.set(redis_key, agent_json, ex=self._cache_ttl)
            
        except Exception as e:
            logger.warning(f"Failed to cache emotional agent {cache_key}: {e}")

    # Session state ---------------------------------------------------------
    def get_session_state(self, conversation_id: str, user_profile_id: str) -> Dict[str, Any]:
        """Get session state for conversation (kept in memory for performance)"""
        session_key = f"{conversation_id}:{user_profile_id}"
        state = _session_cache.get(session_key, {
            "conversation_turns": [],
            "current_emotional_state": "neutral",
            "comfort_level": 5.0,
            "last_activity": datetime.utcnow()
        })
        
        # Defensive programming: ensure state is always a dictionary
        if not isinstance(state, dict):
            logger.warning(f"Session state for {session_key} is not a dict (type: {type(state)}), resetting to default")
            state = {
                "conversation_turns": [],
                "current_emotional_state": "neutral",
                "comfort_level": 5.0,
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
        agent = await self.get_emotional_agent_data(user_profile_id, agent_instance_id)
        if agent.emotional_goals:
            return agent.emotional_goals[0].last_checkpoint
        return "GREETING"

    async def update_checkpoint(self, user_profile_id: str, agent_instance_id: str, checkpoint: str) -> None:
        """Update checkpoint state"""
        cache_key = f"{user_profile_id}:{agent_instance_id}"
        agent = await self.get_emotional_agent_data(user_profile_id, agent_instance_id)
        
        if agent.emotional_goals:
            # Update checkpoint directly on the goal
            agent.emotional_goals[0].last_checkpoint = checkpoint
            agent.last_interaction = datetime.utcnow()
            
            # Update cache
            self.emotional_agent_cache[cache_key] = agent
            
            # Sync to database
            await self.sync_agent_data_to_db(user_profile_id, agent_instance_id)

    # Check-ins / progress ---------------------------------------------------
    async def add_check_in(self, user_profile_id: str, agent_instance_id: str, user_text: str) -> bool:
        """Add daily check-in entry"""
        try:
            cache_key = f"{user_profile_id}:{agent_instance_id}"
            agent = await self.get_emotional_agent_data(user_profile_id, agent_instance_id)
            
            if agent.emotional_goals:
                today = datetime.utcnow().date()
                
                # Check if there's already a check-in for today
                existing_checkin_today = False
                for check_in in agent.emotional_goals[0].check_ins:
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
                    
                    agent.emotional_goals[0].check_ins.append(check_in)
                    
                    # Update streak only if it's a new day check-in
                    agent.emotional_goals[0].streak += 1
                    if agent.emotional_goals[0].streak > agent.emotional_goals[0].max_streak:
                        agent.emotional_goals[0].max_streak = agent.emotional_goals[0].streak
                    
                    logger.debug(f"Added new check-in for today {today}, streak: {agent.emotional_goals[0].streak}")
                
                # Update last interaction
                agent.last_interaction = datetime.utcnow()
                
                # Update cache
                self.emotional_agent_cache[cache_key] = agent
                
            return True
        except Exception as e:
            logger.error(f"Failed to add check-in for {user_profile_id}:{agent_instance_id}: {e}")
            return False

    async def add_emotional_log(
        self,
        user_profile_id: str,
        agent_instance_id: str,
        feelings: List[str],
        notes: str,
        stress_level: int = 0,
    ) -> bool:
        """Add emotional state log entry"""
        try:
            cache_key = f"{user_profile_id}:{agent_instance_id}"
            agent = await self.get_emotional_agent_data(user_profile_id, agent_instance_id)
            
            if agent.emotional_goals:
                # Ensure feelings are populated by extracting from notes if empty
                extracted: List[str] = []
                if (not feelings) and notes:
                    tokens = [w.strip(".,!? ").lower() for w in (notes or "").split()]
                    vocab = {
                        "sad", "anxious", "angry", "tired", "lonely", "overwhelmed", "numb", "stressed",
                        "worried", "scared", "fearful", "hopeless", "frustrated", "upset", "confused",
                        "happy", "peaceful", "calm", "grateful", "loved", "supported", "hopeful", "content"
                    }
                    for w in tokens:
                        if w in vocab and w not in extracted:
                            extracted.append(w)
                        if len(extracted) >= 5:
                            break
                final_feelings = feelings or extracted or ["seeking_comfort"]

                emotional_entry = MoodLog(
                    date=datetime.utcnow(),
                    mood=', '.join(final_feelings) if final_feelings else "emotional_support",
                    stress_level=max(1, stress_level) if 1 <= stress_level <= 10 else None,
                    notes=notes[:200] if notes else None
                )
                
                # Always append to track emotional changes throughout the day
                agent.emotional_goals[0].mood_trend.append(emotional_entry)
                logger.debug(f"Added new emotional log: feelings: {final_feelings}, stress_level: {stress_level}")
                
                # Update last interaction
                agent.last_interaction = datetime.utcnow()
                
                # Update cache
                self.emotional_agent_cache[cache_key] = agent
                
                # Immediately sync to database to persist the appended data
                await self.sync_agent_data_to_db(user_profile_id, agent_instance_id)
                
            return True
        except Exception as e:
            logger.error(f"Failed to add emotional log for {user_profile_id}:{agent_instance_id}: {e}")
            return False

    async def update_progress(
        self,
        user_profile_id: str,
        agent_instance_id: str,
        emotional_wellness_score: float,
        engagement_score: float,
        notes: str,
    ) -> bool:
        """Update progress tracking"""
        try:
            cache_key = f"{user_profile_id}:{agent_instance_id}"
            agent = await self.get_emotional_agent_data(user_profile_id, agent_instance_id)
            
            if agent.emotional_goals:
                # Compute emotional trend versus previous wellness score (if available)
                prev_wellness = None
                if agent.emotional_goals[0].progress_tracking:
                    last = agent.emotional_goals[0].progress_tracking[-1]
                    try:
                        prev_wellness = float(last.loneliness_score) if last.loneliness_score is not None else None
                    except Exception:
                        prev_wellness = None

                trend = "stable"
                if prev_wellness is not None:
                    if emotional_wellness_score > prev_wellness + 0.1:
                        trend = "improving"
                    elif emotional_wellness_score < prev_wellness - 0.1:
                        trend = "declining"
                
                # Supportive affirmation
                affirmation = "You're doing great by reaching out. I'm here with you."

                # Always add new progress entry to track changes throughout the day
                progress_entry = ProgressEntry(
                    date=datetime.utcnow(),
                    loneliness_score=emotional_wellness_score,  # Map emotional_wellness_score to loneliness_score
                    social_engagement_score=engagement_score,
                    affirmation=affirmation,
                    emotional_trend=trend,
                    notes=notes
                )
                
                # Append to existing progress (don't replace)
                agent.emotional_goals[0].progress_tracking.append(progress_entry)
                logger.debug(f"Added new progress entry")
                
                # Update last interaction
                agent.last_interaction = datetime.utcnow()
                
                # Update cache
                self.emotional_agent_cache[cache_key] = agent
                
                # Immediately sync to database to persist the appended data
                await self.sync_agent_data_to_db(user_profile_id, agent_instance_id)
                
            return True
        except Exception as e:
            logger.error(f"Failed to update progress for {user_profile_id}:{agent_instance_id}: {e}")
            return False

    async def get_emotional_history(self, user_profile_id: str, agent_instance_id: str, days: int = 7) -> List[Dict[str, Any]]:
        """Get emotional history for the specified number of days"""
        try:
            agent = await self.get_emotional_agent_data(user_profile_id, agent_instance_id)
            
            if not agent.emotional_goals:
                return []
            
            cutoff = datetime.utcnow() - timedelta(days=days)
            emotional_history = []
            
            for emotional_log in agent.emotional_goals[0].mood_trend:
                if emotional_log.date >= cutoff:
                    emotional_history.append({
                        "timestampISO": emotional_log.date.isoformat(),
                        "emotional_state": emotional_log.mood,
                        "stress_level": emotional_log.stress_level,
                        "notes": emotional_log.notes
                    })
            
            return emotional_history
            
        except Exception as e:
            logger.error(f"Failed to get emotional history for {user_profile_id}:{agent_instance_id}: {e}")
            return []

    # Comfort sessions -----------------------------------------------------
    async def start_comfort_session(self, user_profile_id: str, conversation_id: str, session_type: str = "general") -> str:
        """Start a comfort session (kept in memory for performance)"""
        session_id = f"comfort:{user_profile_id}:{conversation_id}:{int(time.time()*1000)}"
        _comfort_sessions[session_id] = {
            "user_profile_id": user_profile_id,
            "conversation_id": conversation_id,
            "session_type": session_type,
            "status": "active",
            "start_time": datetime.utcnow().isoformat(),
        }
        return session_id

    async def complete_comfort_session(self, session_id: str) -> bool:
        """Complete a comfort session"""
        sess = _comfort_sessions.get(session_id)
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
            if cache_key in self.emotional_agent_cache:
                cached_agent = self.emotional_agent_cache[cache_key]
                cached_agent.last_interaction = datetime.utcnow()
                
                # Get the specific goal to update
                if cached_agent.emotional_goals:
                    goal_to_update = cached_agent.emotional_goals[0]
                    
                    # First, fetch the full document from DB
                    existing_doc = self.mongo_client.db[_COLL_NAME].find_one({
                        "user_profile_id": user_profile_id
                    })
                    
                    if existing_doc:
                        # Update the specific goal in the existing document
                        existing_doc.pop('_id', None)
                        full_agent = EmotionalCompanionAgent(**existing_doc)
                        
                        # Find and update the specific goal
                        goal_updated = False
                        for i, goal in enumerate(full_agent.emotional_goals):
                            if goal.goal_id == agent_instance_id:
                                full_agent.emotional_goals[i] = goal_to_update
                                goal_updated = True
                                break
                        
                        # If goal not found, add it
                        if not goal_updated:
                            full_agent.emotional_goals.append(goal_to_update)
                        
                        # Update last interaction for the full document
                        full_agent.last_interaction = datetime.utcnow()
                        
                        # Save the full updated document
                        self.mongo_client.db[_COLL_NAME].update_one(
                            {"user_profile_id": user_profile_id},
                            {"$set": full_agent.model_dump()},
                            upsert=True
                        )
                    else:
                        # No existing document, create new one
                        self.mongo_client.db[_COLL_NAME].update_one(
                            {"user_profile_id": user_profile_id},
                            {"$set": cached_agent.model_dump()},
                            upsert=True
                        )
                    
                    logger.debug(f"Synced emotional agent data to DB: {user_profile_id}:{agent_instance_id}")
                
        except Exception as e:
            logger.error(f"Failed to sync emotional agent data to DB: {e}")

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
                "emotional_companion_agents": len(self.emotional_agent_cache),
                "sessions": len(_session_cache),
                "comfort_sessions": len(_comfort_sessions)
            }
        }


# Convenience singleton (optional)
emotional_data_manager_singleton = EmotionalDataManager()
