
from __future__ import annotations

"""
MongoDB DataManager for the Anxiety Support agent. 

This module follows the same architecture as the therapy agent data manager,
using MongoDB collections: user_profiles and anxiety_agents.
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
    try:
        from .schema import CheckpointState
    except ImportError:
        # Fallback for direct execution
        from schema import CheckpointState
except ImportError as e:
    logging.warning(f"Import error in anxiety data manager: {e}. Using minimal fallback implementations.")
    import random
    from pydantic import BaseModel, Field
    from datetime import datetime
    from uuid import uuid4
    
    # Minimal fallback implementations
    def generate_therapy_goal_id() -> str:
        return f"anxiety_{random.randint(100, 999)}"
    
    class UserProfile(BaseModel):
        user_profile_id: str = Field(default_factory=lambda: str(uuid4()))
        user_id: str
        profile_name: str = "Default Profile"
        name: str = "Friend"
        age: Optional[int] = None
        gender: Optional[str] = None
        location: Optional[str] = None
        language: Optional[str] = "en"
        interests: List[str] = Field(default_factory=list)
        hobbies: List[str] = Field(default_factory=list)
        hates: List[str] = Field(default_factory=list)
        personality_traits: List[str] = Field(default_factory=list)
        preferences: Dict = Field(default_factory=dict)
        loved_ones: List = Field(default_factory=list)
        past_stories: List = Field(default_factory=list)
        health_info: Dict = Field(default_factory=dict)
        emotional_baseline: Optional[str] = "neutral"
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
    
    class AnxietyLog(BaseModel):
        date: datetime
        anxiety_level: str
        anxiety_score: Optional[int] = Field(None, ge=1, le=10)
        triggers: List[str] = Field(default_factory=list)
        notes: Optional[str] = None
        
    
    class ProgressEntry(BaseModel):
        date: datetime
        anxiety_score: Optional[float] = Field(None, ge=0.0, le=10.0)
        engagement_score: Optional[float] = Field(None, ge=0.0, le=10.0)
        coping_technique: Optional[str] = None
        notes: Optional[str] = None
    
    class AnxietyGoal(BaseModel):
        goal_id: str = Field(default_factory=generate_therapy_goal_id)
        title: str
        description: Optional[str] = None
        due_date: Optional[datetime] = None
        status: str = "active"
        check_ins: List[CheckIn] = Field(default_factory=list)
        streak: int = 0
        max_streak: int = 0
        progress_tracking: List[ProgressEntry] = Field(default_factory=list)
        anxiety_trend: List[AnxietyLog] = Field(default_factory=list)
        mood_trend: List[MoodLog] = Field(default_factory=list)  # For unified schema compatibility
        last_checkpoint: str = "GREETING"  # Add checkpoint field
        # Anxiety-specific fields
        event_date: Optional[datetime] = None
        event_type: Optional[str] = None
        anxiety_level: Optional[int] = None
        nervous_thoughts: List[str] = Field(default_factory=list)
        physical_symptoms: List[str] = Field(default_factory=list)
    
    class AnxietyAgent(BaseModel):
        agent_instance_id: str = Field(default_factory=lambda: str(uuid4()))
        user_profile_id: str
        anxiety_goals: List[AnxietyGoal] = Field(default_factory=list)
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
            'anxiety_agents': type('Collection', (), {'find_one': lambda x: None, 'update_one': lambda *args, **kwargs: None})()
        })()

# Ensure Anxiety-specific models exist even when unified schema imports succeed
if 'AnxietyGoal' not in globals() or 'AnxietyAgent' not in globals():
    from pydantic import BaseModel, Field  # type: ignore
    from datetime import datetime  # type: ignore
    from uuid import uuid4  # type: ignore

    class AnxietyLog(BaseModel):
        date: datetime
        anxiety_level: str
        anxiety_score: Optional[int] = Field(None, ge=1, le=10)
        triggers: List[str] = Field(default_factory=list)
        notes: Optional[str] = None

    class ProgressEntry(BaseModel):
        date: datetime
        anxiety_score: Optional[float] = Field(None, ge=0.0, le=10.0)
        engagement_score: Optional[float] = Field(None, ge=0.0, le=10.0)
        coping_technique: Optional[str] = None
        notes: Optional[str] = None

    class AnxietyGoal(BaseModel):
        goal_id: str = Field(default_factory=lambda: generate_therapy_goal_id() if 'generate_therapy_goal_id' in globals() else f"anxiety_{int(time.time())}")
        title: str
        description: Optional[str] = None
        due_date: Optional[datetime] = None
        status: str = "active"
        check_ins: List[CheckIn] = Field(default_factory=list)
        streak: int = 0
        max_streak: int = 0
        progress_tracking: List[ProgressEntry] = Field(default_factory=list)
        anxiety_trend: List[AnxietyLog] = Field(default_factory=list)
        mood_trend: List[MoodLog] = Field(default_factory=list)  # For unified schema compatibility
        last_checkpoint: str = "GREETING"
        # Anxiety-specific fields
        event_date: Optional[datetime] = None
        event_type: Optional[str] = None
        anxiety_level: Optional[int] = None
        nervous_thoughts: List[str] = Field(default_factory=list)
        physical_symptoms: List[str] = Field(default_factory=list)

    class AnxietyAgent(BaseModel):
        agent_instance_id: str = Field(default_factory=lambda: str(uuid4()))
        user_profile_id: str
        anxiety_goals: List[AnxietyGoal] = Field(default_factory=list)
        last_interaction: Optional[datetime] = None

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

# Session and coping sessions cache (kept in memory for performance)
_session_cache: Dict[str, Dict[str, Any]] = {}
_coping_sessions: Dict[str, Dict[str, Any]] = {}


class AnxietyDataManager:
    """MongoDB-based data manager for anxiety agent following therapy agent pattern"""
    
    def __init__(self, redis_client=None, mongo_client=None):
        self.redis_client = redis_client or RedisMemory()
        self.mongo_client = mongo_client or MongoMemory()
        
        # In-memory caches for ultra-low latency
        self.user_profile_cache: Dict[str, UserProfile] = {}
        self.anxiety_agent_cache: Dict[str, Any] = {}
        
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
        """Create comprehensive default user profile for anxiety personalization"""
        return UserProfile(
            user_profile_id=user_profile_id,
            user_id=user_profile_id,  # Fallback mapping
            profile_name="Default Profile",
            name="Friend",
            age=25,
            gender="not_specified",
            location="not_specified",
            language="en",
            hobbies=["reading", "music", "walking"],
            hates=["loud noises", "crowded spaces"],
            interests=["mindfulness", "breathing exercises", "nature"],
            personality_traits=["thoughtful", "sensitive", "resilient"],
            loved_ones=[],
            past_stories=[],
            preferences={
                "communication_style": "gentle",
                "comfort_techniques": ["breathing", "grounding"],
                "preferred_time": "evening",
                "crisis_support": True
            },
            health_info={
                "anxiety_triggers": ["work", "social situations"],
                "coping_mechanisms": ["deep breathing", "meditation"],
                "previous_therapy": False,
                "medication": False,
                "panic_history": False
            },
            emotional_baseline="mild_anxiety",
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

    async def get_anxiety_agent_data(self, user_profile_id: str, agent_instance_id: str) -> Any:
        """Fetch anxiety agent data with multi-level caching"""
        cache_key = f"{user_profile_id}:{agent_instance_id}"
        
        # Check in-memory cache first
        if cache_key in self.anxiety_agent_cache:
            self.cache_stats["agent_hits"] += 1
            return self.anxiety_agent_cache[cache_key]
        
        self.cache_stats["agent_misses"] += 1
        
        # Check Redis cache
        redis_key = f"anxiety_agent:{cache_key}"
        try:
            cached_data = await self.redis_client.redis.get(redis_key)
            if cached_data:
                agent_dict = safe_json_loads(cached_data)
                agent = AnxietyAgent(**agent_dict)
                self.anxiety_agent_cache[cache_key] = agent
                return agent
        except Exception as e:
            logger.warning(f"Redis cache fetch failed for anxiety agent {cache_key}: {e}")
        
        # Fetch from MongoDB
        agent = await self._fetch_agent_data_from_db(user_profile_id, agent_instance_id)
        
        # Cache in both Redis and memory
        await self._cache_agent_data(cache_key, agent)
        
        return agent
    
    async def _fetch_agent_data_from_db(self, user_profile_id: str, agent_instance_id: str) -> Any:
        """Fetch anxiety agent data from MongoDB anxiety_agents collection"""
        try:
            # Fetch document by user_profile_id only
            # Check if mongo_client and db are available
            if not self.mongo_client or not hasattr(self.mongo_client, 'db') or self.mongo_client.db is None:
                logger.warning(f"MongoDB connection not available, creating default agent for {user_profile_id}")
                return self._create_default_agent_data(user_profile_id, agent_instance_id)
                
            agent_doc = self.mongo_client.db.anxiety_agents.find_one({
                "user_profile_id": user_profile_id
            })
            
            if agent_doc:
                # Remove MongoDB's _id field
                agent_doc.pop('_id', None)
                agent = AnxietyAgent(**agent_doc)
                
                # Find the specific goal by agent_instance_id
                target_goal = None
                for goal in agent.anxiety_goals:
                    if goal.goal_id == agent_instance_id:
                        target_goal = goal
                        break
                
                if target_goal:
                    # Return agent with only the requested goal
                    agent.anxiety_goals = [target_goal]
                    return agent
                else:
                    # Goal not found by agent_instance_id, but we have existing goals
                    # Instead of creating a new goal, use the first existing goal
                    if agent.anxiety_goals:
                        existing_goal = agent.anxiety_goals[0]
                        # Update the goal_id to match the requested agent_instance_id
                        existing_goal.goal_id = agent_instance_id
                        
                        # Return agent with only the first (updated) goal
                        agent.anxiety_goals = [existing_goal]
                        
                        # Save the updated goal_id back to DB
                        await self._save_agent_with_updated_goal_id(agent, user_profile_id)
                        
                        return agent
                    else:
                        # No goals exist at all, create the first one
                        new_goal = AnxietyGoal(
                            goal_id=agent_instance_id,
                            title="Anxiety Management",
                            description="Daily anxiety tracking and coping strategies",
                            status="active",
                            last_checkpoint="GREETING"
                        )
                        agent.anxiety_goals = [new_goal]
                        
                        # Save updated agent back to DB
                        await self._save_agent_with_new_goal(agent)
                        
                        return agent
            else:
                # Create default agent data (no document exists for this user)
                return self._create_default_agent_data(user_profile_id, agent_instance_id)
                
        except Exception as e:
            logger.error(f"Failed to fetch anxiety agent data {user_profile_id}:{agent_instance_id} from DB: {e}")
            return self._create_default_agent_data(user_profile_id, agent_instance_id)
    
    def _create_default_agent_data(self, user_profile_id: str, agent_instance_id: str) -> Any:
        """Create default anxiety agent data with initial goal"""
        default_goal = AnxietyGoal(
            goal_id=agent_instance_id,  # Use agent_instance_id as goal_id
            title="Anxiety Management",
            description="Daily anxiety tracking and coping strategies",
            status="active",
            last_checkpoint="GREETING"
        )
        
        return AnxietyAgent(
            user_profile_id=user_profile_id,
            anxiety_goals=[default_goal],
            last_interaction=datetime.utcnow()
        )
    
    async def _save_agent_with_new_goal(self, agent: Any):
        """Save agent back to DB when a new goal is added"""
        try:
            self.mongo_client.db.anxiety_agents.update_one(
                {"user_profile_id": agent.user_profile_id},
                {"$set": agent.model_dump()},
                upsert=True
            )
            logger.debug(f"Saved agent with new goal for user {agent.user_profile_id}")
        except Exception as e:
            logger.error(f"Failed to save agent with new goal: {e}")
    
    async def _cache_agent_data(self, cache_key: str, agent: Any):
        """Cache agent data in Redis and memory"""
        try:
            # Cache in memory
            self.anxiety_agent_cache[cache_key] = agent
            
            # Cache in Redis with TTL
            redis_key = f"anxiety_agent:{cache_key}"
            agent_json = agent.model_dump_json()
            await self.redis_client.redis.set(redis_key, agent_json, ex=self._cache_ttl)
            
        except Exception as e:
            logger.warning(f"Failed to cache anxiety agent {cache_key}: {e}")

    # Session state ---------------------------------------------------------
    def get_session_state(self, conversation_id: str, user_profile_id: str) -> Dict[str, Any]:
        """Get session state for conversation (kept in memory for performance)"""
        session_key = f"{conversation_id}:{user_profile_id}"
        state = _session_cache.get(session_key, {
            "conversation_turns": [],
            "current_anxiety": "neutral",
            "engagement_level": 5.0,
            "last_activity": datetime.utcnow(),
            "recent_triggers": []
        })
        
        # Defensive programming: ensure state is always a dictionary
        if not isinstance(state, dict):
            logger.warning(f"Session state for {session_key} is not a dict (type: {type(state)}), resetting to default")
            state = {
                "conversation_turns": [],
                "current_anxiety": "neutral",
                "engagement_level": 5.0,
                "last_activity": datetime.utcnow(),
                "recent_triggers": []
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
        agent = await self.get_anxiety_agent_data(user_profile_id, agent_instance_id)
        if agent.anxiety_goals:
            return agent.anxiety_goals[0].last_checkpoint
        return "GREETING"

    async def update_checkpoint(self, user_profile_id: str, agent_instance_id: str, checkpoint: str) -> None:
        """Update checkpoint state"""
        cache_key = f"{user_profile_id}:{agent_instance_id}"
        agent = await self.get_anxiety_agent_data(user_profile_id, agent_instance_id)
        
        if agent.anxiety_goals:
            # Update checkpoint directly on the goal
            agent.anxiety_goals[0].last_checkpoint = checkpoint
            agent.last_interaction = datetime.utcnow()
            
            # Update cache
            self.anxiety_agent_cache[cache_key] = agent
            
            # Sync to database
            await self.sync_agent_data_to_db(user_profile_id, agent_instance_id)

    # Check-ins / progress ---------------------------------------------------
    async def add_check_in(self, user_profile_id: str, agent_instance_id: str, user_text: str) -> bool:
        """Add daily check-in entry"""
        try:
            cache_key = f"{user_profile_id}:{agent_instance_id}"
            agent = await self.get_anxiety_agent_data(user_profile_id, agent_instance_id)
            
            if agent.anxiety_goals:
                today = datetime.utcnow().date()
                
                # Check if there's already a check-in for today
                existing_checkin_today = False
                for check_in in agent.anxiety_goals[0].check_ins:
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
                    
                    agent.anxiety_goals[0].check_ins.append(check_in)
                    
                    # Update streak only if it's a new day check-in
                    agent.anxiety_goals[0].streak += 1
                    if agent.anxiety_goals[0].streak > agent.anxiety_goals[0].max_streak:
                        agent.anxiety_goals[0].max_streak = agent.anxiety_goals[0].streak
                    
                    logger.debug(f"Added new check-in for today {today}, streak: {agent.anxiety_goals[0].streak}")
                
                # Update last interaction
                agent.last_interaction = datetime.utcnow()
                
                # Update cache
                self.anxiety_agent_cache[cache_key] = agent
                
            return True
        except Exception as e:
            logger.error(f"Failed to add check-in for {user_profile_id}:{agent_instance_id}: {e}")
            return False

    async def add_anxiety_log(
        self,
        user_profile_id: str,
        agent_instance_id: str,
        anxiety_score: int,
        anxiety_level: str,
        triggers: List[str],
        notes: str,
        stress_level: int = 0,
        panic_level: int = 0,
    ) -> bool:
        """Add anxiety log entry"""
        try:
            cache_key = f"{user_profile_id}:{agent_instance_id}"
            agent = await self.get_anxiety_agent_data(user_profile_id, agent_instance_id)
            
            if agent.anxiety_goals:
                # Ensure triggers are populated by extracting from notes if empty
                extracted_triggers: List[str] = []
                if (not triggers) and notes:
                    from .background_tasks import AnxietyAnalyzer
                    analyzer = AnxietyAnalyzer()
                    extracted_triggers = analyzer.extract_triggers(notes)
                
                final_triggers = triggers or extracted_triggers or ["general"]

                # Create both anxiety-specific log and unified mood log
                anxiety_entry = AnxietyLog(
                    date=datetime.utcnow(),
                    anxiety_level=anxiety_level,
                    anxiety_score=anxiety_score,
                    triggers=final_triggers,
                    notes=notes[:200] if notes else None
                )
                
                # Also create MoodLog entry for unified schema compatibility
                mood_entry = MoodLog(
                    date=datetime.utcnow(),
                    mood=f"Anxiety {anxiety_level}; triggers={', '.join(final_triggers)}",
                    stress_level=max(1, stress_level) if 1 <= stress_level <= 10 else None,
                    notes=notes[:200] if notes else None
                )
                
                # Always append to track anxiety changes throughout the day
                agent.anxiety_goals[0].anxiety_trend.append(anxiety_entry)
                
                # Also populate mood_trend for unified schema compatibility
                if hasattr(agent.anxiety_goals[0], 'mood_trend'):
                    agent.anxiety_goals[0].mood_trend.append(mood_entry)
                
                logger.debug(f"Added new anxiety log: level {anxiety_level}, score {anxiety_score}, stress_level: {stress_level}, triggers: {final_triggers}")
                
                # Update anxiety-specific goal fields
                await self._update_anxiety_goal_metadata(agent.anxiety_goals[0], anxiety_score, final_triggers, notes)
                
                # Update last interaction
                agent.last_interaction = datetime.utcnow()
                
                # Update cache
                self.anxiety_agent_cache[cache_key] = agent
                
                # Immediately sync to database to persist the appended data
                await self.sync_agent_data_to_db(user_profile_id, agent_instance_id)
                
            return True
        except Exception as e:
            logger.error(f"Failed to add anxiety log for {user_profile_id}:{agent_instance_id}: {e}")
            return False

    async def update_progress(
        self,
        user_profile_id: str,
        agent_instance_id: str,
        anxiety_score: float,
        engagement_score: float,
        notes: str,
        coping_technique: str = None,
    ) -> bool:
        """Update progress tracking"""
        try:
            cache_key = f"{user_profile_id}:{agent_instance_id}"
            agent = await self.get_anxiety_agent_data(user_profile_id, agent_instance_id)
            
            if agent.anxiety_goals:
                # Compute anxiety trend versus previous score (if available)
                prev_anxiety = None
                if agent.anxiety_goals[0].progress_tracking:
                    last = agent.anxiety_goals[0].progress_tracking[-1]
                    try:
                        prev_anxiety = float(last.anxiety_score) if last.anxiety_score is not None else None
                    except Exception:
                        prev_anxiety = None

                trend = "stable"
                if prev_anxiety is not None:
                    if anxiety_score < prev_anxiety - 0.5:  # Lower anxiety is better
                        trend = "improving"
                    elif anxiety_score > prev_anxiety + 0.5:
                        trend = "increasing"
                
                # Always add new progress entry to track changes throughout the day
                progress_entry = ProgressEntry(
                    date=datetime.utcnow(),
                    anxiety_score=anxiety_score,
                    engagement_score=engagement_score,
                    coping_technique=coping_technique,
                    notes=notes
                )
                
                # Append to existing progress (don't replace)
                agent.anxiety_goals[0].progress_tracking.append(progress_entry)
                logger.debug(f"Added new progress entry with trend: {trend}")
                
                # Update last interaction
                agent.last_interaction = datetime.utcnow()
                
                # Update cache
                self.anxiety_agent_cache[cache_key] = agent
                
                # Immediately sync to database to persist the appended data
                await self.sync_agent_data_to_db(user_profile_id, agent_instance_id)
                
            return True
        except Exception as e:
            logger.error(f"Failed to update progress for {user_profile_id}:{agent_instance_id}: {e}")
            return False

    async def get_anxiety_history(self, user_profile_id: str, agent_instance_id: str, days: int = 7) -> List[Dict[str, Any]]:
        """Get anxiety history for the specified number of days"""
        try:
            agent = await self.get_anxiety_agent_data(user_profile_id, agent_instance_id)
            
            if not agent.anxiety_goals:
                return []
            
            cutoff = datetime.utcnow() - timedelta(days=days)
            anxiety_history = []
            
            for anxiety_log in agent.anxiety_goals[0].anxiety_trend:
                if anxiety_log.date >= cutoff:
                    anxiety_history.append({
                        "timestampISO": anxiety_log.date.isoformat(),
                        "anxiety_level": anxiety_log.anxiety_level,
                        "anxietyScore": anxiety_log.anxiety_score or 5,  # fallback score
                        "stress_level": getattr(anxiety_log, 'stress_level', None),
                        "triggers": anxiety_log.triggers,
                        "notes": anxiety_log.notes
                    })
            
            return anxiety_history
            
        except Exception as e:
            logger.error(f"Failed to get anxiety history for {user_profile_id}:{agent_instance_id}: {e}")
            return []

    async def _update_anxiety_goal_metadata(self, goal: Any, anxiety_score: int, triggers: List[str], notes: str) -> None:
        """Update anxiety-specific fields on the goal"""
        try:
            # Set anxiety level if the field exists
            if hasattr(goal, 'anxiety_level'):
                goal.anxiety_level = int(anxiety_score)
            
            # Infer event_type from triggers and set event_date
            event_type = None
            if 'work' in triggers or 'performance' in triggers:
                event_type = 'performance'
            elif 'social' in triggers:
                event_type = 'social'
            elif 'health' in triggers:
                event_type = 'health'
            elif 'family' in triggers:
                event_type = 'family'
            elif 'money' in triggers:
                event_type = 'financial'
            
            if hasattr(goal, 'event_type'):
                goal.event_type = event_type
            
            # Set event_date if we have an event_type and it's not already set
            if event_type and hasattr(goal, 'event_date') and not getattr(goal, 'event_date', None):
                goal.event_date = datetime.utcnow()
            
            # Extract nervous thoughts and physical symptoms from notes
            if notes:
                text = notes.lower()
                
                # Extract nervous thoughts patterns
                nervous_keywords = ["what if", "can't", "won't", "always", "never", "should", "must", "fail", "embarrassed", "judge"]
                nervous_thoughts: List[str] = []
                for keyword in nervous_keywords:
                    if keyword in text:
                        nervous_thoughts.append(keyword)
                
                # Extract physical symptoms
                physical_map = {
                    'heart racing': ['heart racing', 'heart pounding', 'palpitations'],
                    'breathing': ["can't breathe", 'short of breath', 'breathless'],
                    'chest tightness': ['chest tight', 'tightness'],
                    'sweating': ['sweating', 'sweaty'],
                    'shaking': ['shaking', 'trembling'],
                    'dizziness': ['dizzy', 'lightheaded'],
                    'nausea': ['nauseous', 'nausea', 'upset stomach'],
                }
                
                physical_symptoms: List[str] = []
                for symptom, phrases in physical_map.items():
                    for phrase in phrases:
                        if phrase in text and symptom not in physical_symptoms:
                            physical_symptoms.append(symptom)
                
                # Update nervous_thoughts field if it exists
                if hasattr(goal, 'nervous_thoughts'):
                    existing_thoughts = getattr(goal, 'nervous_thoughts', []) or []
                    combined_thoughts = existing_thoughts + nervous_thoughts
                    # Keep unique and limit to 8
                    goal.nervous_thoughts = list(dict.fromkeys(combined_thoughts))[:8]
                
                # Update physical_symptoms field if it exists
                if hasattr(goal, 'physical_symptoms'):
                    existing_symptoms = getattr(goal, 'physical_symptoms', []) or []
                    combined_symptoms = existing_symptoms + physical_symptoms
                    # Keep unique and limit to 8
                    goal.physical_symptoms = list(dict.fromkeys(combined_symptoms))[:8]
                    
        except Exception as e:
            logger.warning(f"Failed to update anxiety goal metadata: {e}")

    # Coping sessions -----------------------------------------------------
    async def start_coping_session(self, user_profile_id: str, conversation_id: str, technique: str, duration_sec: int) -> str:
        """Start a coping technique session (kept in memory for performance)"""
        session_id = f"coping:{user_profile_id}:{conversation_id}:{int(time.time()*1000)}"
        _coping_sessions[session_id] = {
            "user_profile_id": user_profile_id,
            "conversation_id": conversation_id,
            "technique": technique,
            "duration_sec": duration_sec,
            "status": "active",
            "start_time": datetime.utcnow().isoformat(),
        }
        return session_id

    async def complete_coping_session(self, session_id: str) -> bool:
        """Complete a coping technique session"""
        sess = _coping_sessions.get(session_id)
        if not sess:
            return False
        sess["status"] = "completed"
        sess["end_time"] = datetime.utcnow().isoformat()
        return True

    # MongoDB sync methods ---------------------------------------------------

    async def _save_agent_with_updated_goal_id(self, agent: Any, user_profile_id: str):
        """Save agent with updated goal_id to prevent duplicates"""
        try:
            if self.mongo_client and hasattr(self.mongo_client, 'db') and self.mongo_client.db is not None:
                # Update the goal_id in the database
                result = self.mongo_client.db.anxiety_agents.update_one(
                    {"user_profile_id": user_profile_id},
                    {
                        "$set": {
                            "anxiety_goals.0.goal_id": agent.anxiety_goals[0].goal_id,
                            "last_interaction": datetime.utcnow(),
                            "updated_at": datetime.utcnow()
                        }
                    }
                )
                logger.debug(f"Updated goal_id for user {user_profile_id}: {result.modified_count} documents modified")
        except Exception as e:
            logger.error(f"Failed to save updated goal_id for {user_profile_id}: {e}")

    async def sync_agent_data_to_db(self, user_profile_id: str, agent_instance_id: str):
        """Sync agent data to MongoDB - updates specific goal within the user's document"""
        try:
            cache_key = f"{user_profile_id}:{agent_instance_id}"
            if cache_key in self.anxiety_agent_cache:
                cached_agent = self.anxiety_agent_cache[cache_key]
                cached_agent.last_interaction = datetime.utcnow()
                
                # Get the specific goal to update
                if cached_agent.anxiety_goals:
                    goal_to_update = cached_agent.anxiety_goals[0]
                    
                    # First, fetch the full document from DB
                    existing_doc = self.mongo_client.db.anxiety_agents.find_one({
                        "user_profile_id": user_profile_id
                    })
                    
                    if existing_doc:
                        # Update the specific goal in the existing document
                        existing_doc.pop('_id', None)
                        full_agent = AnxietyAgent(**existing_doc)
                        
                        # Find and update the specific goal
                        goal_updated = False
                        for i, goal in enumerate(full_agent.anxiety_goals):
                            if goal.goal_id == agent_instance_id:
                                full_agent.anxiety_goals[i] = goal_to_update
                                goal_updated = True
                                break
                        
                        # If goal not found, add it
                        if not goal_updated:
                            full_agent.anxiety_goals.append(goal_to_update)
                        
                        # Update last interaction for the full document
                        full_agent.last_interaction = datetime.utcnow()
                        
                        # Save the full updated document
                        self.mongo_client.db.anxiety_agents.update_one(
                            {"user_profile_id": user_profile_id},
                            {"$set": full_agent.model_dump()},
                            upsert=True
                        )
                    else:
                        # No existing document, create new one
                        self.mongo_client.db.anxiety_agents.update_one(
                            {"user_profile_id": user_profile_id},
                            {"$set": cached_agent.model_dump()},
                            upsert=True
                        )
                    
                    logger.debug(f"Synced anxiety agent data to DB: {user_profile_id}:{agent_instance_id}")
                
        except Exception as e:
            logger.error(f"Failed to sync anxiety agent data to DB: {e}")

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
                "anxiety_agents": len(self.anxiety_agent_cache),
                "sessions": len(_session_cache),
                "coping_sessions": len(_coping_sessions)
            }
        }


# Convenience singleton (optional)
anxiety_data_manager_singleton = AnxietyDataManager()
