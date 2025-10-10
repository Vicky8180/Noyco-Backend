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
from typing import Dict, Any
import sys
import os

# Add the parent directory to Python path
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(os.path.dirname(current_dir))
sys.path.insert(0, parent_dir)

try:
    from memory.redis_client import RedisMemory
    from memory.mongo_client import MongoMemory
    from common.gemini_client import get_gemini_client
    
    # Import data manager with dual pattern
    try:
        # When running from agents folder
        from loneliness.data_manager import LonelinessDataManager
    except ImportError:
        # When running as module
        from .data_manager import LonelinessDataManager
    
    # Import background tasks with dual pattern
    try:
        # When running from agents folder
        from loneliness.background_tasks import BackgroundTaskManager, MoodAnalyzer, ProgressTracker
    except ImportError:
        # When running as module
        from .background_tasks import BackgroundTaskManager, MoodAnalyzer, ProgressTracker
    
    # Import from unified schema with dual pattern
    try:
        # When running from agents folder
        from schema import UserProfile, LonelinessAgent, LonelinessGoal
    except ImportError:
        # When running as module
        from ..schema import UserProfile, LonelinessAgent, LonelinessGoal
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
            
            # Initialize regular Gemini client
            try:
                self.gemini_client = get_gemini_client()
                logger.info("Gemini client initialized")
            except Exception as gemini_error:
                logger.error(f"Gemini client failed: {gemini_error}")
                self.gemini_client = None
            
            self._initialized = True
            logger.info("Loneliness agent initialized successfully")
            
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
        session_state: Dict[str, Any],
        context: str = ""
    ) -> str:
        """Build comprehensive prompt with full user profile, agent goals, and context"""
        
        # Get essential context
        current_mood = session_state.get('current_mood', 'neutral')
        user_name = getattr(user_profile, 'name', 'Friend')
        
        # Build comprehensive user personality from profile
        user_personality = self._build_user_personality_string(user_profile)
        
        # Get agent goals and tasks
        agent_context = self._build_agent_context_string(agent_data)
        
        # Parse and format conversation context
        formatted_context = self._format_conversation_context(context)
        
        # Recent conversation memory
        conversation_memory = ""
        session_memory = session_state.get('conversation_turns', [])
        if session_memory:
            recent_turns = session_memory[-4:]  # Last 4 turns for better context
            conversation_memory = f"Recent conversation:\n{chr(10).join(recent_turns)}"

        # Determine response style based on user input
        response_style = self._determine_response_style(user_query)

        # Comprehensive prompt
        main_prompt = f"""You are a warm, empathetic loneliness companion. Your purpose is to provide gentle, proactive emotional support and help the user navigate feelings of loneliness. You are not just a listener; you are a gentle guide.

Your primary interaction model is:
1.  **Listen & Validate:** First, always acknowledge and validate the user's feelings with deep empathy.
2.  **Explore & Unpack:** Ask gentle, open-ended questions to help the user explore their feelings more deeply.
3.  **Guide & Empower:** Help the user discover new perspectives, reframe negative thoughts, and identify small, manageable steps they can take.

==== USER PROFILE ====
{user_personality}

==== AGENT GOALS & TASKS ====
{agent_context}

==== CONVERSATION CONTEXT ====
{formatted_context}

==== RECENT MEMORY ====
{conversation_memory}

==== CURRENT INTERACTION ====
User's current mood: {current_mood}
User says: "{user_query}"

==== RESPONSE GUIDELINES ====
{response_style}

Respond as their compassionate companion. Your goal is to not only make them feel heard, but to help them find a path forward, one step at a time."""

        return main_prompt

    def _build_user_personality_string(self, user_profile: UserProfile) -> str:
        """Build comprehensive user personality string from profile data"""
        
        personality_parts = []
        
        # Basic info
        basic_info = f"Name: {getattr(user_profile, 'name', 'Friend')}"
        if hasattr(user_profile, 'age') and user_profile.age:
            basic_info += f", Age: {user_profile.age}"
        if hasattr(user_profile, 'gender') and user_profile.gender:
            basic_info += f", Gender: {user_profile.gender}"
        if hasattr(user_profile, 'location') and user_profile.location:
            basic_info += f", Location: {user_profile.location}"
        personality_parts.append(basic_info)
        
        # Personality traits
        if hasattr(user_profile, 'personality_traits') and user_profile.personality_traits:
            traits = ", ".join(user_profile.personality_traits)
            personality_parts.append(f"Personality: {traits}")
        
        # Interests and hobbies
        if hasattr(user_profile, 'interests') and user_profile.interests:
            interests = ", ".join(user_profile.interests)
            personality_parts.append(f"Interests: {interests}")
        
        if hasattr(user_profile, 'hobbies') and user_profile.hobbies:
            hobbies = ", ".join(user_profile.hobbies)
            personality_parts.append(f"Hobbies: {hobbies}")
        
        # Loved ones with memories
        if hasattr(user_profile, 'loved_ones') and user_profile.loved_ones:
            loved_ones_info = []
            for person in user_profile.loved_ones:
                # Access Pydantic model attributes directly, not with .get()
                person_info = f"{getattr(person, 'name', 'Someone special')}"
                if hasattr(person, 'relation') and person.relation:
                    person_info += f" ({person.relation})"
                if hasattr(person, 'memories') and person.memories:
                    person_info += f" - {'; '.join(person.memories[:2])}"  # First 2 memories
                loved_ones_info.append(person_info)
            personality_parts.append(f"Important people: {'; '.join(loved_ones_info)}")
        
        # Health info
        if hasattr(user_profile, 'health_info') and user_profile.health_info:
            health_items = []
            # Handle health_info whether it's a dict or Pydantic model
            if hasattr(user_profile.health_info, 'get'):  # It's a dict
                if user_profile.health_info.get('allergies'):
                    health_items.append(f"Allergies: {', '.join(user_profile.health_info['allergies'])}")
                if user_profile.health_info.get('medications'):
                    health_items.append(f"Medications: {', '.join(user_profile.health_info['medications'])}")
            else:  # It's a Pydantic model or other object
                if hasattr(user_profile.health_info, 'allergies') and user_profile.health_info.allergies:
                    health_items.append(f"Allergies: {', '.join(user_profile.health_info.allergies)}")
                if hasattr(user_profile.health_info, 'medications') and user_profile.health_info.medications:
                    health_items.append(f"Medications: {', '.join(user_profile.health_info.medications)}")
            if health_items:
                personality_parts.append(f"Health considerations: {'; '.join(health_items)}")
        
        # Emotional baseline
        if hasattr(user_profile, 'emotional_baseline') and user_profile.emotional_baseline:
            personality_parts.append(f"Emotional baseline: {user_profile.emotional_baseline}")
        
        # Things they hate/dislike
        if hasattr(user_profile, 'hates') and user_profile.hates:
            hates = ", ".join(user_profile.hates)
            personality_parts.append(f"Dislikes: {hates}")
        
        return "\n".join(personality_parts)

    def _build_agent_context_string(self, agent_data: LonelinessAgent) -> str:
        """Build agent context string with goals and progress"""
        
        context_parts = []
        
        # Current goals - handle as list
        if hasattr(agent_data, 'loneliness_goals') and agent_data.loneliness_goals:
            # Check if it's a list or single object
            goals = agent_data.loneliness_goals if isinstance(agent_data.loneliness_goals, list) else [agent_data.loneliness_goals]
            
            for goal in goals:
                if goal:  # Make sure goal exists
                    goal_info = f"Current goal: {getattr(goal, 'title', 'Unnamed goal')}"
                    if hasattr(goal, 'description') and goal.description:
                        goal_info += f" - {goal.description}"
                    if hasattr(goal, 'status') and goal.status:
                        goal_info += f" (Status: {goal.status})"
                    context_parts.append(goal_info)
                    
                    # Goal progress
                    if hasattr(goal, 'check_ins') and goal.check_ins:
                        recent_checkins = goal.check_ins[-2:] if len(goal.check_ins) >= 2 else goal.check_ins
                        checkin_info = []
                        for checkin in recent_checkins:
                            if hasattr(checkin, 'date') and hasattr(checkin, 'response'):
                                checkin_info.append(f"{checkin.date.strftime('%Y-%m-%d')}: {checkin.response}")
                        if checkin_info:
                            context_parts.append(f"Recent progress: {'; '.join(checkin_info)}")
                    
                    # Progress tracking
                    if hasattr(goal, 'progress_tracking') and goal.progress_tracking:
                        recent_progress = goal.progress_tracking[-1:] if goal.progress_tracking else []
                        if recent_progress:
                            progress = recent_progress[0]
                            progress_info = f"Recent assessment - Loneliness: {getattr(progress, 'loneliness_score', 'N/A')}/10"
                            if hasattr(progress, 'social_engagement_score') and progress.social_engagement_score:
                                progress_info += f", Social engagement: {progress.social_engagement_score}/10"
                            if hasattr(progress, 'emotional_trend') and progress.emotional_trend:
                                progress_info += f", Trend: {progress.emotional_trend}"
                            context_parts.append(progress_info)
                    break  # Only process first goal for now
        
        if not context_parts:
            context_parts.append("New companion relationship - building rapport and understanding needs")
        
        return "\n".join(context_parts)

    def _format_conversation_context(self, context: str) -> str:
        """Format conversation context from orchestrator"""
        
        if not context or context == "[]" or context == "None":
            return "No previous conversation context available"
        
        try:
            # Try to parse if it's a string representation of a list
            if context.startswith("[") and context.endswith("]"):
                import ast
                context_list = ast.literal_eval(context)
                if isinstance(context_list, list):
                    formatted_items = []
                    for item in context_list:
                        if isinstance(item, dict):
                            # Format dictionary items nicely
                            formatted_items.append(f"• {item}")
                        else:
                            formatted_items.append(f"• {str(item)}")
                    return "\n".join(formatted_items)
            
            # If it's just a string, return it formatted
            return f"Previous context: {context}"
            
        except Exception:
            # If parsing fails, just return the raw context
            return f"Context: {context}"

    def _determine_response_style(self, user_query: str) -> str:
        """Determine appropriate response style based on user input"""
        
        query_lower = user_query.lower().strip()
        
        # New Guideline: Handling breakthroughs and insights
        insight_keywords = ["realize", "realization", "perspective", "makes sense", "never thought", "wow", "i see"]
        if any(keyword in query_lower for keyword in insight_keywords) and len(user_query.split()) > 5:
            return "The user had a breakthrough. First, affirm the importance of their insight. Then, ask a question to help them anchor it, like 'How does it feel to see it that way?' or 'What does that realization change for you?' Goal: Help the user integrate their new perspective."

        # Short greetings - keep response brief
        short_greetings = ["hi", "hello", "hey", "good morning", "good evening", "good afternoon", "morning", "evening"]
        if any(greeting in query_lower for greeting in short_greetings) and len(user_query.split()) <= 3:
            return "Keep response brief and warm (1-2 sentences). Match their greeting energy. Goal: Invite them to share how they are."
        
        # Questions about feelings or emotional state - more thoughtful response
        emotional_keywords = ["feel", "feeling", "emotion", "sad", "happy", "lonely", "anxious", "depressed", "mood"]
        if any(keyword in query_lower for keyword in emotional_keywords):
            return "Provide thoughtful, empathetic response (3-5 sentences). Show deep understanding and validate their feelings. Goal: Ask a gentle, open-ended question to help them explore the 'why' behind the feeling."
        
        # Seeking advice or help - detailed supportive response
        help_keywords = ["help", "advice", "what should", "how do", "can you", "need", "support"]
        if any(keyword in query_lower for keyword in help_keywords):
            return "Offer detailed, helpful guidance (4-6 sentences). Be practical while remaining emotionally supportive. Goal: Break down the problem and explore one small, manageable first step together."
        
        # Sharing stories or experiences - engaged listening response
        sharing_keywords = ["today", "yesterday", "happened", "tell you", "guess what", "story", "experience"]
        if any(keyword in query_lower for keyword in sharing_keywords):
            return "Show engaged interest (3-4 sentences). Ask follow-up questions and validate their experience. Goal: Deepen the conversation by asking about the emotional impact of the story ('How did that make you feel?')."
        
        # Short responses or one-word answers - gentle encouragement to open up
        if len(user_query.split()) <= 2:
            return "Gently encourage more sharing (2-3 sentences). Use open-ended questions like 'What's on your mind?' or 'I'm here to listen if you'd like to talk more.' Goal: Create a safe space for them to open up."
        
        # Default - balanced response
        return "Respond naturally and supportively (2-4 sentences). Match their communication style. Goal: Always end with a gentle question that invites further conversation."

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
            prompt = await self.build_gemini_prompt(
                user_query, user_profile, agent_data, session_state, context
            )
            
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
