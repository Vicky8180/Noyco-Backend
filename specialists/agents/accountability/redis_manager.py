"""
Redis Manager for Accountability Buddy Agent
Handles Redis operations for session state, reminders, and quick access cache
"""

import logging
import json
import asyncio
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta, date
from redis.asyncio import Redis
from redis.exceptions import RedisError
from urllib.parse import urlparse

from .schema import AccountabilitySession, DailyCheckIn, AccountabilityGoal
from ..config import get_settings

logger = logging.getLogger(__name__)

class AccountabilityRedis:
    """Redis manager for accountability agent data"""
    
    def __init__(self, redis_url: Optional[str] = None, db: int = 1):
        settings = get_settings()
        redis_url = redis_url or settings.REDIS_URL
        
        # Parse Redis URL
        parsed = urlparse(redis_url)
        host = parsed.hostname or 'localhost'
        port = parsed.port or 6379
        
        # Use db=1 to separate from main Redis
        # Reduce connection timeouts so API doesn't hang if Redis is down
        self.redis = Redis(
            host=host,
            port=port,
            db=db,
            socket_connect_timeout=1,  # seconds
            socket_timeout=2
        )
        self.initialized = False
        
    async def initialize(self):
        """Initialize Redis connection"""
        try:
            await self.redis.ping()
            self.initialized = True
            logger.info("✅ Accountability Redis initialized successfully")
        except RedisError as e:
            logger.error(f"⚠️ Redis unavailable for accountability agent (continuing without cache): {str(e)}")
            self.initialized = False  # Disable Redis usage instead of crashing
            
    async def check_connection(self):
        """Check Redis connection"""
        try:
            await self.redis.ping()
            return True
        except RedisError as e:
            logger.error(f"❌ Accountability Redis connection failed: {str(e)}")
            raise
            
    # === SESSION MANAGEMENT ===
    
    async def save_session(self, session: AccountabilitySession, ttl: int = 3600) -> bool:
        """Save accountability session with TTL"""
        try:
            key = f"accountability:session:{session.session_id}"
            session_data = session.dict()
            
            # Convert datetime objects to ISO strings
            for field in ['started_at', 'last_activity']:
                if field in session_data and isinstance(session_data[field], datetime):
                    session_data[field] = session_data[field].isoformat()
                    
            await self.redis.setex(key, ttl, json.dumps(session_data, default=str))
            
            # Also maintain a user session index
            user_key = f"accountability:user_sessions:{session.user_id}"
            await self.redis.sadd(user_key, session.session_id)
            await self.redis.expire(user_key, ttl)
            
            logger.info(f"✅ Saved accountability session {session.session_id}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error saving session to Redis: {e}")
            return False
            
    async def get_session(self, session_id: str) -> Optional[AccountabilitySession]:
        """Get accountability session from Redis"""
        try:
            key = f"accountability:session:{session_id}"
            data = await self.redis.get(key)
            
            if data:
                session_data = json.loads(data)
                
                # Convert ISO strings back to datetime objects
                for field in ['started_at', 'last_activity']:
                    if field in session_data and isinstance(session_data[field], str):
                        session_data[field] = datetime.fromisoformat(session_data[field])
                        
                return AccountabilitySession(**session_data)
                
        except Exception as e:
            logger.error(f"❌ Error getting session from Redis: {e}")
            
        return None
        
    async def update_session_activity(self, session_id: str) -> bool:
        """Update last activity timestamp for a session"""
        try:
            session = await self.get_session(session_id)
            if session:
                session.last_activity = datetime.utcnow()
                await self.save_session(session)
                return True
                
        except Exception as e:
            logger.error(f"❌ Error updating session activity: {e}")
            
        return False
        
    async def end_session(self, session_id: str) -> bool:
        """Remove session from Redis"""
        try:
            key = f"accountability:session:{session_id}"
            result = await self.redis.delete(key)
            
            if result:
                logger.info(f"✅ Ended accountability session {session_id}")
                return True
                
        except Exception as e:
            logger.error(f"❌ Error ending session: {e}")
            
        return False
        
    # === REMINDER MANAGEMENT ===
    
    async def schedule_reminder(self, user_id: str, goal_id: str, reminder_time: str, 
                              message: str, reminder_date: date = None) -> bool:
        """Schedule a reminder for a user"""
        try:
            if reminder_date is None:
                reminder_date = date.today()
                
            # Create reminder key with timestamp
            reminder_datetime = datetime.combine(reminder_date, 
                                               datetime.strptime(reminder_time, "%H:%M").time())
            timestamp = int(reminder_datetime.timestamp())
            
            reminder_data = {
                'user_id': user_id,
                'goal_id': goal_id,
                'message': message,
                'reminder_time': reminder_time,
                'reminder_date': reminder_date.isoformat(),
                'created_at': datetime.utcnow().isoformat()
            }
            
            # Store reminder with score as timestamp for sorted set
            await self.redis.zadd(
                "accountability:reminders", 
                {json.dumps(reminder_data): timestamp}
            )
            
            # Also store user-specific reminders
            user_key = f"accountability:user_reminders:{user_id}"
            await self.redis.zadd(user_key, {json.dumps(reminder_data): timestamp})
            await self.redis.expire(user_key, 86400 * 7)  # Expire after 7 days
            
            logger.info(f"✅ Scheduled reminder for user {user_id} at {reminder_time}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error scheduling reminder: {e}")
            return False
            
    async def get_due_reminders(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get reminders that are due now"""
        try:
            current_timestamp = int(datetime.utcnow().timestamp())
            
            # Get reminders with score <= current timestamp
            results = await self.redis.zrangebyscore(
                "accountability:reminders", 
                0, 
                current_timestamp, 
                start=0, 
                num=limit,
                withscores=True
            )
            
            due_reminders = []
            for reminder_json, score in results:
                try:
                    reminder_data = json.loads(reminder_json)
                    reminder_data['scheduled_timestamp'] = score
                    due_reminders.append(reminder_data)
                    
                    # Remove processed reminder
                    await self.redis.zrem("accountability:reminders", reminder_json)
                    
                except json.JSONDecodeError:
                    logger.error(f"❌ Invalid reminder data: {reminder_json}")
                    
            return due_reminders
            
        except Exception as e:
            logger.error(f"❌ Error getting due reminders: {e}")
            return []
            
    async def get_user_reminders(self, user_id: str, days: int = 1) -> List[Dict[str, Any]]:
        """Get upcoming reminders for a user"""
        try:
            user_key = f"accountability:user_reminders:{user_id}"
            current_timestamp = int(datetime.utcnow().timestamp())
            end_timestamp = current_timestamp + (days * 86400)
            
            results = await self.redis.zrangebyscore(
                user_key, 
                current_timestamp, 
                end_timestamp,
                withscores=True
            )
            
            reminders = []
            for reminder_json, score in results:
                try:
                    reminder_data = json.loads(reminder_json)
                    reminder_data['scheduled_timestamp'] = score
                    reminders.append(reminder_data)
                except json.JSONDecodeError:
                    logger.error(f"❌ Invalid reminder data: {reminder_json}")
                    
            return reminders
            
        except Exception as e:
            logger.error(f"❌ Error getting user reminders: {e}")
            return []
            
    # === QUICK ACCESS CACHE ===
    
    async def cache_user_goals(self, user_id: str, goals: List[AccountabilityGoal], ttl: int = 1800) -> bool:
        """Cache user's active goals for quick access"""
        try:
            key = f"accountability:goals:{user_id}"
            goals_data = [goal.dict() for goal in goals]
            
            # Convert date objects to ISO strings for JSON serialization
            for goal_data in goals_data:
                for field in ['start_date', 'target_end_date']:
                    if field in goal_data and isinstance(goal_data[field], date):
                        goal_data[field] = goal_data[field].isoformat()
                        
            await self.redis.setex(key, ttl, json.dumps(goals_data, default=str))
            logger.info(f"✅ Cached {len(goals)} goals for user {user_id}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error caching user goals: {e}")
            return False
            
    async def get_cached_goals(self, user_id: str) -> Optional[List[AccountabilityGoal]]:
        """Get cached user goals"""
        try:
            key = f"accountability:goals:{user_id}"
            data = await self.redis.get(key)
            
            if data:
                goals_data = json.loads(data)
                goals = []
                
                for goal_data in goals_data:
                    # Convert ISO strings back to date objects
                    for field in ['start_date', 'target_end_date']:
                        if field in goal_data and isinstance(goal_data[field], str):
                            try:
                                goal_data[field] = datetime.fromisoformat(goal_data[field]).date()
                            except (ValueError, TypeError):
                                goal_data[field] = None
                                
                    goals.append(AccountabilityGoal(**goal_data))
                    
                return goals
                
        except Exception as e:
            logger.error(f"❌ Error getting cached goals: {e}")
            
        return None
        
    async def invalidate_user_cache(self, user_id: str) -> bool:
        """Invalidate all cached data for a user"""
        try:
            keys_to_delete = [
                f"accountability:goals:{user_id}",
                f"accountability:checkins:{user_id}",
                f"accountability:streak:{user_id}:*"
            ]
            
            # Get all keys matching patterns
            all_keys = []
            for pattern in keys_to_delete:
                if '*' in pattern:
                    matching_keys = await self.redis.keys(pattern)
                    all_keys.extend(matching_keys)
                else:
                    all_keys.append(pattern)
                    
            if all_keys:
                deleted = await self.redis.delete(*all_keys)
                logger.info(f"✅ Invalidated {deleted} cache keys for user {user_id}")
                
            return True
            
        except Exception as e:
            logger.error(f"❌ Error invalidating user cache: {e}")
            return False
            
    # === DAILY CHECK-IN TRACKING ===
    
    async def mark_checkin_completed(self, user_id: str, goal_id: str, checkin_date: date = None) -> bool:
        """Mark that a check-in has been completed for today"""
        try:
            if checkin_date is None:
                checkin_date = date.today()
                
            key = f"accountability:completed_checkins:{checkin_date.isoformat()}"
            checkin_key = f"{user_id}:{goal_id}"
            
            await self.redis.sadd(key, checkin_key)
            await self.redis.expire(key, 86400 * 2)  # Keep for 2 days
            
            logger.info(f"✅ Marked check-in completed for user {user_id}, goal {goal_id}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error marking check-in completed: {e}")
            return False
            
    async def is_checkin_completed(self, user_id: str, goal_id: str, checkin_date: date = None) -> bool:
        """Check if user has completed check-in for a goal today"""
        try:
            if checkin_date is None:
                checkin_date = date.today()
                
            key = f"accountability:completed_checkins:{checkin_date.isoformat()}"
            checkin_key = f"{user_id}:{goal_id}"
            
            result = await self.redis.sismember(key, checkin_key)
            return bool(result)
            
        except Exception as e:
            logger.error(f"❌ Error checking if check-in completed: {e}")
            return False
            
    # === ANALYTICS CACHE ===
    
    async def cache_analytics(self, user_id: str, goal_id: str, analytics: Dict[str, Any], ttl: int = 3600) -> bool:
        """Cache goal analytics"""
        try:
            key = f"accountability:analytics:{user_id}:{goal_id}"
            await self.redis.setex(key, ttl, json.dumps(analytics, default=str))
            return True
            
        except Exception as e:
            logger.error(f"❌ Error caching analytics: {e}")
            return False
            
    async def get_cached_analytics(self, user_id: str, goal_id: str) -> Optional[Dict[str, Any]]:
        """Get cached analytics"""
        try:
            key = f"accountability:analytics:{user_id}:{goal_id}"
            data = await self.redis.get(key)
            
            if data:
                return json.loads(data)
                
        except Exception as e:
            logger.error(f"❌ Error getting cached analytics: {e}")
            
        return None
        
    # === CONVERSATION STATE ===
    
    async def save_conversation_state(self, conversation_id: str, state: Dict[str, Any], ttl: int = 1800) -> bool:
        """Save conversation state for accountability agent"""
        try:
            key = f"accountability:conversation:{conversation_id}"
            await self.redis.setex(key, ttl, json.dumps(state, default=str))
            return True
            
        except Exception as e:
            logger.error(f"❌ Error saving conversation state: {e}")
            return False
            
    async def get_conversation_state(self, conversation_id: str) -> Optional[Dict[str, Any]]:
        """Get conversation state"""
        try:
            key = f"accountability:conversation:{conversation_id}"
            data = await self.redis.get(key)
            
            if data:
                return json.loads(data)
                
        except Exception as e:
            logger.error(f"❌ Error getting conversation state: {e}")
            
        return None
        
    async def clear_conversation_state(self, conversation_id: str) -> bool:
        """Clear conversation state"""
        try:
            key = f"accountability:conversation:{conversation_id}"
            result = await self.redis.delete(key)
            return bool(result)
            
        except Exception as e:
            logger.error(f"❌ Error clearing conversation state: {e}")
            return False
