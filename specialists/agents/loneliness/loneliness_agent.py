"""
Loneliness Companion Voice Agent - Production Grade Implementation
This agent provides passive social therapy and emotional companionship.

Refactored to use unified schema design with separate user_profiles and loneliness_agents collections.
"""

import asyncio
import logging
import time
import json
from datetime import datetime
from typing import Dict, Any, AsyncGenerator
import sys
import os

# Add the parent directory to Python path
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(os.path.dirname(current_dir))
sys.path.insert(0, parent_dir)

try:
    from memory.redis_client import RedisMemory
    from memory.mongo_client import MongoMemory
    # Removed get_gemini_client import - using only streaming client
    from .data_manager import LonelinessDataManager
    from .background_tasks import BackgroundTaskManager, MoodAnalyzer, ProgressTracker
    # Import from unified schema
    from ..schema import UserProfile, LonelinessAgent, LonelinessGoal
    # Import streaming client for 100% streaming experience
    from .gemini_streaming import get_streaming_client
except ImportError as e:
    logging.warning(f"Import error: {e}. Using minimal fallback implementations.")
    
    # Minimal fallback implementations for testing only
    class RedisMemory:
        async def check_connection(self): 
            return True
        redis = type('Redis', (), {'get': lambda self, k: None, 'set': lambda self, k, v, ex=None: None})()
    
    class MongoMemory:
        async def initialize(self): 
            return True
        async def check_connection(self): 
            return True
        db = type('DB', (), {})()
    
    def get_gemini_client(model_name=None):
        return type('AsyncGeminiClient', (), {
            'generate_content': lambda self, prompt: type('Response', (), {
                'text': 'I understand you want to talk. How are you feeling today?'
            })()
        })()
    
    def get_streaming_client():
        return type('StreamingGeminiClient', (), {
            'generate_content': lambda self, prompt: type('Response', (), {
                'text': 'I understand you want to talk. How are you feeling today?'
            })(),
            'stream_generate_content': lambda self, prompt, **kwargs: iter([
                {"type": "content", "data": "I understand", "timestamp": time.time()},
                {"type": "content", "data": " you want", "timestamp": time.time()},
                {"type": "content", "data": " to talk.", "timestamp": time.time()},
                {"type": "done", "data": "I understand you want to talk.", "timestamp": time.time()}
            ])
        })()
    
    # Import fallback components
    try:
        from .data_manager import LonelinessDataManager
        from .background_tasks import BackgroundTaskManager, MoodAnalyzer, ProgressTracker
    except ImportError:
        # Minimal fallback classes
        class LonelinessDataManager:
            def __init__(self, *args): 
                pass
            async def get_user_profile(self, user_profile_id): 
                return type('UserProfile', (), {'name': 'Friend', 'personality_traits': []})()
            async def get_loneliness_agent_data(self, user_profile_id, agent_instance_id): 
                return type('LonelinessAgent', (), {'loneliness_goals': []})()
            def get_session_state(self, conv_id, user_profile_id): 
                return {"conversation_turns": [], "current_mood": "neutral"}
            def update_session_state(self, conv_id, user_profile_id, state): 
                pass
            async def add_check_in(self, *args): 
                pass
            async def add_mood_log(self, *args): 
                pass
            async def update_progress(self, *args): 
                pass
            
        class BackgroundTaskManager:
            def __init__(self, *args): 
                pass
            async def schedule_mood_analysis(self, user_id, text, client): 
                return "neutral"
            async def schedule_progress_update(self, *args): 
                pass
            async def schedule_data_sync(self, *args): 
                pass
            def schedule_daily_checkin_update(self, *args): 
                pass
            
        class MoodAnalyzer:
            def quick_mood_analysis(self, text): 
                return "neutral"
            
        class ProgressTracker:
            @staticmethod
            def calculate_loneliness_score(mood, query, history=None): 
                return 5.0
            @staticmethod
            def calculate_engagement_score(query, response, turn_count=1): 
                return 5.0
            @staticmethod
            def calculate_engagement_score(query, response, turns=1): return 7.0

    # Fallback schema classes
    class UserProfile:
        def __init__(self):
            self.name = "Friend"
            self.personality_traits = []
            self.interests = []
            self.hobbies = []
    
    class LonelinessAgent:
        def __init__(self):
            self.loneliness_goals = []
    
    class LonelinessGoal:
        def __init__(self):
            self.progress_tracking = []
            self.mood_trend = []

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class LonelinessCompanionAgent:
    """Production-grade loneliness companion agent using unified schema"""
    
    def __init__(self):
        self.redis_client = RedisMemory()
        self.mongo_client = MongoMemory()
        self.gemini_client = None
        
        # Initialize modular components
        self.data_manager = LonelinessDataManager(self.redis_client, self.mongo_client)
        self.background_tasks = BackgroundTaskManager(max_workers=8)
        self.mood_analyzer = MoodAnalyzer()
        self.progress_tracker = ProgressTracker()
        
        # Add caches for frequently accessed data
        self._profile_cache = {}
        self._agent_cache = {}
        self._session_cache = {}
        self._cache_ttl = 300  # 5 minutes cache TTL
        
        self._initialized = False
        
    async def initialize(self):
        """Initialize all connections and clients - optimized for fast startup"""
        if self._initialized:
            return
            
        try:
            # Initialize connections in parallel for faster startup
            redis_task = asyncio.create_task(self.redis_client.check_connection())
            mongo_init_task = asyncio.create_task(self.mongo_client.initialize())
            
            # Wait for both connections with timeout
            await asyncio.wait_for(
                asyncio.gather(redis_task, mongo_init_task, return_exceptions=True),
                timeout=5.0  # 5 second timeout for faster error handling
            )
            
            logger.info("Database connections established in parallel")
            
            # Initialize ONLY streaming Gemini client for 100% streaming experience
            try:
                self.gemini_client = get_streaming_client()
                logger.info("Streaming Gemini client initialized (100% streaming mode)")
            except Exception as streaming_error:
                logger.error(f"Streaming Gemini client failed: {streaming_error}")
                self.gemini_client = None
            
            self._initialized = True
            logger.info("Loneliness companion agent initialized successfully")
            
        except asyncio.TimeoutError:
            logger.warning("Database initialization timeout - continuing with fallback mode")
            self._initialized = True
        except Exception as e:
            logger.error(f"Failed to initialize loneliness companion agent: {e}")
            # Continue with fallback mode
            self._initialized = True

    async def get_cached_data(self, user_profile_id: str, agent_instance_id: str):
        """Get user profile and agent data with caching for ultra-low latency"""
        cache_key = f"{user_profile_id}_{agent_instance_id}"
        current_time = time.time()
        
        # Check local cache first
        if cache_key in self._profile_cache:
            cached_data = self._profile_cache[cache_key]
            if current_time - cached_data['timestamp'] < self._cache_ttl:
                return cached_data['profile'], cached_data['agent']
        
        # Fetch data in parallel for faster response
        profile_task = asyncio.create_task(self.data_manager.get_user_profile(user_profile_id))
        agent_task = asyncio.create_task(self.data_manager.get_loneliness_agent_data(user_profile_id, agent_instance_id))
        
        try:
            # Use timeout to prevent hanging
            user_profile, agent_data = await asyncio.wait_for(
                asyncio.gather(profile_task, agent_task),
                timeout=2.0  # 2 second timeout
            )
            
            # Cache the results
            self._profile_cache[cache_key] = {
                'profile': user_profile,
                'agent': agent_data,
                'timestamp': current_time
            }
            
            return user_profile, agent_data
            
        except asyncio.TimeoutError:
            logger.warning("Data fetch timeout - using fallback data")
            # Return minimal fallback data
            fallback_profile = type('UserProfile', (), {
                'name': 'Friend',
                'age': None,
                'interests': [],
                'personality_traits': [],
                'hobbies': []
            })()
            
            fallback_agent = type('LonelinessAgent', (), {
                'loneliness_goals': []
            })()
            
            return fallback_profile, fallback_agent

    async def get_session_state_fast(self, conversation_id: str, user_profile_id: str) -> Dict[str, Any]:
        """Fast session state retrieval with local caching"""
        cache_key = f"session_{conversation_id}_{user_profile_id}"
        current_time = time.time()
        
        # Check local cache
        if cache_key in self._session_cache:
            cached_session = self._session_cache[cache_key]
            if current_time - cached_session['timestamp'] < 30:  # 30 second cache for sessions
                return cached_session['data']
        
        # Get from data manager with fallback
        try:
            session_state = self.data_manager.get_session_state(conversation_id, user_profile_id)
            
            # Ensure it's a valid dict
            if not isinstance(session_state, dict):
                session_state = {
                    "conversation_turns": [],
                    "current_mood": "neutral",
                    "engagement_level": 5.0,
                    "last_activity": datetime.utcnow()
                }
            
            # Cache it
            self._session_cache[cache_key] = {
                'data': session_state,
                'timestamp': current_time
            }
            
            return session_state
            
        except Exception as e:
            logger.warning(f"Session state fetch error: {e}, using default")
            return {
                "conversation_turns": [],
                "current_mood": "neutral", 
                "engagement_level": 5.0,
                "last_activity": datetime.utcnow()
            }

    async def build_gemini_prompt(
        self, 
        user_query: str, 
        user_profile: UserProfile, 
        agent_data: LonelinessAgent, 
        session_state: Dict[str, Any]
    ) -> str:
        """Build optimized prompt for Gemini with reduced complexity for faster processing"""
        
        # Get essential context only
        current_mood = session_state.get('current_mood', 'neutral')
        user_name = getattr(user_profile, 'name', 'Friend')
        
        # Simplified user context for faster processing
        user_interests = getattr(user_profile, 'interests', [])
        interest_str = ', '.join(user_interests[:3]) if user_interests else 'General conversation'  # Limit to 3 interests
        
        # Recent conversation context (limit to last 2 turns for speed)
        conversation_context = ""
        session_memory = session_state.get('conversation_turns', [])
        if session_memory:
            recent_turns = session_memory[-2:]  # Reduced from 3 to 2 for faster processing
            conversation_context = f"Recent chat: {' | '.join(recent_turns[-2:])}"

        # Streamlined prompt for faster generation
        main_prompt = f"""You are a warm, empathetic loneliness companion. Be supportive and caring.

User: {user_name} | Mood: {current_mood} | Interests: {interest_str}
{conversation_context}

User says: "{user_query}"

Respond naturally and supportively in 2-3 sentences only. Focus on connection and understanding."""

        return main_prompt

    async def process_message(
        self, 
        user_query: str, 
        context: str, 
        checkpoint: str, 
        conversation_id: str, 
        user_profile_id: str,
        agent_instance_id: str,
        user_id: str  # Keep for compatibility
    ) -> Dict[str, Any]:
        """
        Optimized main processing function for ultra-low latency
        """
        
        start_time = time.time()
        
        try:
            # Fast initialization check
            if not self._initialized:
                await self.initialize()
            
            # Parallel data fetching with caching for maximum speed
            data_fetch_start = time.time()
            user_profile, agent_data = await self.get_cached_data(user_profile_id, agent_instance_id)
            session_state = await self.get_session_state_fast(conversation_id, user_profile_id)
            data_fetch_time = time.time() - data_fetch_start
            
            # Ultra-fast mood analysis (keyword-based, no AI)
            current_mood = self.mood_analyzer.quick_mood_analysis(user_query)
            session_state['current_mood'] = current_mood
            
            # Quick metric calculations (simplified for speed)
            loneliness_score = self.progress_tracker.calculate_loneliness_score(
                current_mood, user_query, []  # Empty history for faster calculation
            )
            engagement_score = 7.0  # Default good engagement score for speed
            
            # Build optimized prompt and get response
            prompt = await self.build_gemini_prompt(user_query, user_profile, agent_data, session_state)
            
            # Generate response with timeout for reliability
            response_start = time.time()
            try:
                response = await asyncio.wait_for(
                    self.gemini_client.generate_content(prompt),
                    timeout=5.0  # 5 second timeout for faster error handling
                )
                agent_response = response.text.strip()
            except (asyncio.TimeoutError, Exception) as e:
                logger.warning(f"Gemini API issue: {e}, using fast fallback")
                # Ultra-fast mood-based fallback responses
                fallback_responses = {
                    "sad": "I hear you, and I'm here with you. What's been weighing on your heart lately?",
                    "lonely": "You're not alone - I'm here to listen. Want to share what's on your mind?",
                    "anxious": "I understand you're feeling anxious. Take a breath - I'm here. What's worrying you?",
                    "happy": "It's wonderful to hear from you! What's been brightening your day?",
                    "neutral": "I'm glad you're here. How are you feeling right now?"
                }
                agent_response = fallback_responses.get(current_mood, fallback_responses["neutral"])
            
            response_time = time.time() - response_start
            
            # Fast session state update (fire and forget for next time)
            session_state['conversation_turns'].append(f"User: {user_query}")
            session_state['conversation_turns'].append(f"Assistant: {agent_response}")
            
            # Keep only last 6 turns for memory efficiency
            if len(session_state['conversation_turns']) > 6:
                session_state['conversation_turns'] = session_state['conversation_turns'][-6:]
            
            # Update cache immediately for next request
            self.data_manager.update_session_state(conversation_id, user_profile_id, session_state)
            
            # Calculate total processing time
            processing_time = time.time() - start_time
            
            # Schedule all background tasks as fire-and-forget (non-blocking)
            asyncio.create_task(self._schedule_background_tasks_async(
                user_profile_id, agent_instance_id, user_query, agent_response, 
                current_mood, loneliness_score, engagement_score, processing_time
            ))
            
            # Log performance metrics
            logger.info(f"Loneliness agent processing: {processing_time:.3f}s "
                       f"(data: {data_fetch_time:.3f}s, response: {response_time:.3f}s)")
            
            # Return optimized response
            return {
                "response": agent_response,
                "conversation_id": conversation_id,
                "checkpoint_status": "complete",
                "requires_human": False,
                "processing_time": processing_time,
                "collected_inputs": {},
                "action_required": False,
                "agent_specific_data": {
                    "current_mood": current_mood,
                    "loneliness_score": loneliness_score,
                    "engagement_score": engagement_score,
                    "user_profile_id": user_profile_id,
                    "agent_instance_id": agent_instance_id,
                    "performance": {
                        "data_fetch_time": data_fetch_time,
                        "response_time": response_time,
                        "cached_data": data_fetch_time < 0.1
                    }
                }
            }
            
        except Exception as e:
            import traceback
            logger.error(f"Error processing message: {e}")
            logger.error(f"Error traceback: {traceback.format_exc()}")
            processing_time = time.time() - start_time
            
            return {
                "response": "I'm sorry, I'm having some technical difficulties right now. Please try again in a moment. I'm here when you're ready to talk.",
                "conversation_id": conversation_id,
                "checkpoint_status": "complete",
                "requires_human": False,
                "processing_time": processing_time,
                "collected_inputs": {},
                "action_required": False,
                "agent_specific_data": {
                    "error": str(e),
                    "current_mood": "neutral",
                    "user_profile_id": user_profile_id,
                    "agent_instance_id": agent_instance_id
                }
            }

    async def _schedule_background_tasks_async(
        self, 
        user_profile_id: str,
        agent_instance_id: str,
        user_query: str, 
        agent_response: str, 
        current_mood: str,
        loneliness_score: float,
        engagement_score: float,
        processing_time: float
    ):
        """Async background tasks that don't block the main response"""
        try:
            # All tasks run concurrently in background
            tasks = [
                self.data_manager.add_check_in(user_profile_id, agent_instance_id, user_query),
                self.data_manager.add_mood_log(user_profile_id, agent_instance_id, current_mood),
                self.data_manager.update_progress(
                    user_profile_id, agent_instance_id, loneliness_score, engagement_score,
                    f"Conversation completed in {processing_time:.2f}s"
                ),
                self.background_tasks.schedule_mood_analysis(user_profile_id, user_query, self.gemini_client),
                self.background_tasks.schedule_data_sync(user_profile_id, agent_instance_id, self.data_manager)
            ]
            
            # Run all tasks concurrently with timeout
            await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=True),
                timeout=10.0  # Don't let background tasks hang
            )
            
        except asyncio.TimeoutError:
            logger.warning("Background tasks timeout - continuing")
        except Exception as e:
            logger.warning(f"Background tasks error: {e}")

    def _schedule_background_tasks(
        self, 
        user_profile_id: str,
        agent_instance_id: str,
        user_query: str, 
        agent_response: str, 
        current_mood: str,
        loneliness_score: float,
        engagement_score: float,
        processing_time: float
    ):
        """Schedule background tasks without blocking response (legacy method)"""
        # Convert to async version for better performance
        asyncio.create_task(self._schedule_background_tasks_async(
            user_profile_id, agent_instance_id, user_query, agent_response,
            current_mood, loneliness_score, engagement_score, processing_time
        ))

    def cleanup(self):
        """Clean up resources"""
        try:
            if hasattr(self.background_tasks, 'cleanup'):
                self.background_tasks.cleanup()
        except Exception as e:
            logger.warning(f"Error during cleanup: {e}")

# Global agent instance
loneliness_agent = LonelinessCompanionAgent()

async def process_message(
    user_query: str, 
    context: str, 
    checkpoint: str, 
    conversation_id: str, 
    user_profile_id: str,
    agent_instance_id: str,
    user_id: str
) -> Dict[str, Any]:
    """
    Main entry point for loneliness companion agent processing
    Updated to use unified schema with user_profile_id and agent_instance_id
    """
    
    # Initialize agent if not already done
    if not loneliness_agent._initialized:
        await loneliness_agent.initialize()
    
    return await loneliness_agent.process_message(
        user_query, context, checkpoint, conversation_id, 
        user_profile_id, agent_instance_id, user_id
    )

async def stream_loneliness_response(
    user_query: str,
    context: str,
    checkpoint: str,
    conversation_id: str,
    user_profile_id: str,
    agent_instance_id: str,
    user_id: str = ""
) -> AsyncGenerator[Dict[str, Any], None]:
    """
    DIRECT STREAMING FUNCTION for loneliness companion responses.
    This function can be imported directly by the orchestrator for zero-latency streaming.
    
    Yields chunks in the format:
    {
        "type": "start" | "content" | "done" | "error",
        "data": str,
        "conversation_id": str,
        "timestamp": float
    }
    """
    try:
        # Initialize agent if needed
        if not loneliness_agent._initialized:
            await loneliness_agent.initialize()
        
        # Send start signal
        yield {
            "type": "start",
            "conversation_id": conversation_id,
            "timestamp": time.time()
        }
        
        # Get user data for prompt building
        try:
            user_profile, agent_data = await loneliness_agent.get_cached_data(
                user_profile_id, agent_instance_id
            )
            session_state = await loneliness_agent.get_session_state_fast(
                conversation_id, user_profile_id
            )
        except Exception as e:
            logger.warning(f"Data fetch error: {e}, using defaults")
            # Use minimal defaults
            user_profile = type('Profile', (), {'name': 'Friend', 'interests': []})()
            agent_data = type('Agent', (), {'loneliness_goals': []})()
            session_state = {'current_mood': 'neutral', 'conversation_turns': []}
        
        # Build prompt
        prompt = await loneliness_agent.build_gemini_prompt(
            user_query, user_profile, agent_data, session_state
        )
        
        # REAL STREAMING: Stream directly from Gemini
        streaming_client = get_streaming_client()
        full_response = ""
        
        # Stream chunks directly from Gemini
        async for chunk in streaming_client.stream_generate_content(
            prompt, max_tokens=200, temperature=0.7, chunk_size=2
        ):
            # Add conversation_id and forward chunk
            chunk["conversation_id"] = conversation_id
            yield chunk
            
            # Collect full response for background tasks
            if chunk.get("type") == "content":
                full_response += chunk.get("data", "")
            elif chunk.get("type") == "done":
                full_response = chunk.get("data", full_response)
                break
        
        # Send final completion
        yield {
            "type": "complete",
            "conversation_id": conversation_id,
            "response_length": len(full_response),
            "timestamp": time.time()
        }
        
        # Schedule background tasks (non-blocking)
        if full_response:
            asyncio.create_task(loneliness_agent._schedule_background_tasks_async(
                user_profile_id, agent_instance_id,
                user_query, full_response, "neutral", 5.0, 7.0, 0.5
            ))
            
    except Exception as e:
        logger.error(f"Error in streaming loneliness response: {e}")
        yield {
            "type": "error",
            "data": f"Streaming error: {str(e)}",
            "conversation_id": conversation_id,
            "timestamp": time.time()
        }
