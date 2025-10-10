"""
Light-weight Emotional Companion Agent
====================================
This implementation mirrors the architecture of the Therapy companion,
while keeping the *behaviour* focused on emotional support and comfort.

It avoids any imports from the Therapy package – all helpers live in the
local directory (`data_manager`, `background_tasks`, `gemini_streaming`).
"""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime
from typing import Any, AsyncGenerator, Dict, List, Optional

from .data_manager import EmotionalDataManager
from .background_tasks import BackgroundTaskManager, EmotionalAnalyzer, ProgressTracker
from .gemini_streaming import get_streaming_client
from .schema import CheckpointState  # optional enum, we use its values as strings

# -----------------------------------------------------------------------------
# Import MongoDB / Redis clients with safe fallback
# -----------------------------------------------------------------------------
try:
    # Add project root to path so `memory` package is resolvable when this file
    # is executed via `python -m uvicorn ...` from the repo root.
    import os
    import sys
    _CUR_DIR = os.path.dirname(os.path.abspath(__file__))
    _ROOT_DIR = os.path.abspath(os.path.join(_CUR_DIR, os.pardir, os.pardir, os.pardir))
    if _ROOT_DIR not in sys.path:
        sys.path.insert(0, _ROOT_DIR)

    from memory.redis_client import RedisMemory  # type: ignore
    from memory.mongo_client import MongoMemory  # type: ignore
except Exception:  # pragma: no cover – fallback for environments w/o memory deps
    import logging
    logging.warning("Fallback to in-memory stubs for Redis/Mongo clients – persistent storage disabled.")

    class RedisMemory:  # pylint: disable=too-few-public-methods
        async def check_connection(self) -> bool:
            return True

        redis = type(
            "Redis",
            (),
            {
                "get": lambda self, k: None,  # noqa: ANN001,E501
                "set": lambda self, k, v, ex=None: None,  # noqa: ANN001,E501
            },
        )()

    class MongoMemory:  # pylint: disable=too-few-public-methods
        async def initialize(self) -> bool:
            return True

        async def check_connection(self) -> bool:
            return True

        db = type(
            "DB",
            (),
            {
                "user_profiles": type(
                    "Collection",
                    (),
                    {
                        "find_one": lambda *_, **__: None,  # noqa: ANN001,E501
                        "update_one": lambda *_, **__: None,  # noqa: ANN001,E501
                    },
                )(),
                "emotional_agents": type(
                    "Collection",
                    (),
                    {
                        "find_one": lambda *_, **__: None,
                        "update_one": lambda *_, **__: None,
                    },
                )(),
            },
        )()

# -----------------------------------------------------------------------------
logger = logging.getLogger(__name__)

# -----------------------------------------------------------------------------
# NOTE: The `EmotionalCompanionAgent` class below instantiates its own clients
#       – avoid creating global client instances here to prevent duplicate
#       connections when running under Uvicorn's worker model.
# -----------------------------------------------------------------------------


class EmotionalIntensityDetector:
    """Heuristic detector for emotional intensity and crisis situations."""

    CRISIS_KEYWORDS = {
        "suicide", "kill myself", "end my life", "can't go on", "self harm",
        "hurt myself", "overdose", "die", "not want to live", "end it all",
        "no point", "better off dead"
    }
    HIGH_INTENSITY = {
        "devastated", "broken", "shattered", "destroyed", "hopeless", "worthless",
        "overwhelming", "unbearable", "can't take it", "falling apart", "losing it"
    }
    MODERATE_INTENSITY = {
        "struggling", "difficult", "hard time", "upset", "distressed", "troubled",
        "worried", "anxious", "sad", "down", "hurt", "pain", "suffering"
    }

    @staticmethod
    def analyze(text: str) -> int:
        """Returns intensity level: 0=low, 1=moderate, 2=high, 3=crisis"""
        t = text.lower()
        if any(p in t for p in EmotionalIntensityDetector.CRISIS_KEYWORDS):
            return 3
        if any(p in t for p in EmotionalIntensityDetector.HIGH_INTENSITY):
            return 2
        if any(p in t for p in EmotionalIntensityDetector.MODERATE_INTENSITY):
            return 1
        return 0


# ----------------------------------------------------------------------------
class EmotionalCompanionAgent:
    """Production-ready emotional support agent with fast start and streaming."""

    def __init__(self):
        # Import real clients at runtime to avoid import issues
        try:
            import sys
            import os
            current_dir = os.path.dirname(os.path.abspath(__file__))
            root_dir = os.path.dirname(os.path.dirname(os.path.dirname(current_dir)))
            sys.path.insert(0, root_dir)
            
            from memory.redis_client import RedisMemory as RealRedisMemory
            from memory.mongo_client import MongoMemory as RealMongoMemory
            
            self.redis_client = RealRedisMemory()
            self.mongo_client = RealMongoMemory()
            
            logger.info("✅ Using real MongoDB and Redis clients")
        except ImportError as e:
            logger.warning(f"Failed to import real clients, using fallback: {e}")
            self.redis_client = RedisMemory()
            self.mongo_client = MongoMemory()
        
        self.gemini_client = None
        
        # Initialize modular components
        self.data_manager = EmotionalDataManager(self.redis_client, self.mongo_client)
        self.background_tasks = BackgroundTaskManager(max_workers=8)
        self.emotional_analyzer = EmotionalAnalyzer()
        self.progress_tracker = ProgressTracker()
        self.streaming_client = get_streaming_client()
        
        # Add caches for frequently accessed data
        self._profile_cache: Dict[str, Dict[str, Any]] = {}
        self._session_cache: Dict[str, Dict[str, Any]] = {}
        self._cache_ttl = 300  # 5 minutes cache TTL
        self._ttl_profile = 300  # seconds
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
            
            # Initialize streaming Gemini client with proper error handling
            try:
                self.streaming_client = get_streaming_client()
                self.gemini_client = self.streaming_client  # Backward compatibility
                logger.info("Emotional streaming Gemini client initialized successfully")
                
                # Test the client to ensure it's working
                test_response = await self.streaming_client.generate_content("Hello")
                if hasattr(test_response, 'text') and test_response.text:
                    logger.info("Emotional LLM client test successful")
                else:
                    logger.warning("Emotional LLM client test returned empty response - may fallback to structured responses")
                    
            except Exception as streaming_error:
                logger.error(f"Emotional streaming Gemini client initialization failed: {streaming_error}")
                logger.error(f"Error type: {type(streaming_error).__name__}")
                self.streaming_client = None
                self.gemini_client = None
            
            self._initialized = True
            logger.info("Emotional companion agent initialized successfully")
            
        except asyncio.TimeoutError:
            logger.warning("Database initialization timeout - continuing with fallback mode")
            self._initialized = True
        except Exception as e:
            logger.error(f"Failed to initialize emotional companion agent: {e}")
            # Continue with fallback mode
            self._initialized = True

    # ---------------------------------------------------------------------
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
        agent_task = asyncio.create_task(self.data_manager.get_emotional_agent_data(user_profile_id, agent_instance_id))
        
        try:
            # Use timeout to prevent hanging
            user_profile, agent_data = await asyncio.wait_for(
                asyncio.gather(profile_task, agent_task),
                timeout=6.0
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
            # Return comprehensive fallback data for better emotional personalization
            fallback_profile = type('UserProfile', (), {
                'name': 'Friend',
                'age': None,
                'gender': None,
                'interests': ['emotional wellbeing', 'self-care'],
                'personality_traits': ['empathetic', 'caring', 'resilient'],
                'hobbies': ['reading', 'journaling', 'music'],
                'hates': [],
                'loved_ones': [],
                'past_stories': [],
                'preferences': {'communication_style': 'nurturing', 'comfort_pace': 'gentle'},
                'health_info': {},
                'emotional_baseline': 'balanced',
                'locale': 'us',
                'location': None,
                'language': 'en'
            })()
            
            fallback_agent = type('EmotionalAgent', (), {
                'emotional_goals': [],
                'memory_stack': [],
                'comfort_tips': []
            })()
            
            return fallback_profile, fallback_agent

    async def process_message(
        self, 
        user_query: str,
        conversation_id: str,
        user_profile_id: str,
        agent_instance_id: str,
        user_id: str = "",
        checkpoint: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Main message processing method"""
        t0 = time.time()
        context = context or {}
        
        # Fast initialization check
        if not self._initialized:
            await self.initialize()
        
        # Parallel data fetching with caching for maximum speed
        data_fetch_start = time.time()
        profile, agent_data = await self.get_cached_data(user_profile_id, agent_instance_id)
        data_fetch_time = time.time() - data_fetch_start

        # Quick emotional analysis
        current_emotional_state = self.emotional_analyzer.quick_emotional_analysis(user_query)
        engagement = self.progress_tracker.calculate_engagement_score(user_query, "", 1)
        
        # Emotional intensity check
        intensity_level = EmotionalIntensityDetector.analyze(user_query)
        
        # Enhanced stress level detection
        stress_indicators = self._extract_stress_indicators(user_query)
        stress_level = self._calculate_stress_level(user_query, stress_indicators)
        
        # Get enhanced session state for comprehensive context understanding
        session_state = {
            "current_emotional_state": current_emotional_state,
            "conversation_turns": context.get("conversation_turns", []),
            "current_checkpoint": checkpoint or "GREETING",
            "conversation_history": context.get("conversation_history", []),
            "user_intent": context.get("user_intent", ""),
            "emotional_triggers": context.get("emotional_triggers", []),
            "previous_emotional_state": context.get("previous_emotional_state", ""),
            "conversation_summary": context.get("conversation_summary", ""),
            "comfort_level": context.get("comfort_level", "moderate"),
            "emotional_intensity": context.get("emotional_intensity", "moderate"),
            "stress_indicators": stress_indicators,
            "stress_level": stress_level
        }
        
        # Generate appropriate response based on emotional state and intensity
        if intensity_level >= 3:
            reply = self._handle_crisis_response(user_query, profile)
            checkpoint_status = "CRISIS_SUPPORT"
        else:
            # Use enhanced personalized response generation
            reply = await self._generate_emotional_response(user_query, current_emotional_state, profile, session_state, context)
            checkpoint_status = "EMOTIONAL_SUPPORT"

        # Schedule background tasks
        asyncio.create_task(self._schedule_background_tasks_async(
            user_profile_id, agent_instance_id, user_query, reply, 
            current_emotional_state, engagement, intensity_level, stress_level, time.time() - t0
        ))
        
        return {
            "response": reply,
            "processing_time": time.time() - t0,
            "conversation_id": conversation_id,
            "checkpoint_status": checkpoint_status,
            "requires_human": intensity_level >= 3,
            "agent_specific_data": {
                "current_emotional_state": current_emotional_state,
                "engagement": engagement,
                "intensity_level": intensity_level,
                "user_profile_id": user_profile_id,
                "agent_instance_id": agent_instance_id,
                "performance": {
                    "data_fetch_time": data_fetch_time,
                    "cached_data": data_fetch_time < 0.1
                }
            },
        }

    def _handle_crisis_response(self, user_query: str, user_profile) -> str:
        """Handle crisis situations with industry-standard crisis intervention techniques"""
        # Handle both Pydantic UserProfile objects and dictionaries
        if hasattr(user_profile, 'model_dump'):
            profile_dict = user_profile.model_dump()
            locale = profile_dict.get("locale", "us")
            name = profile_dict.get("name", "Friend")
        elif isinstance(user_profile, dict):
            locale = user_profile.get("locale", "us")
            name = user_profile.get("name", "Friend")
        else:
            locale = getattr(user_profile, 'locale', 'us')
            name = getattr(user_profile, 'name', 'Friend')

        # Analyze crisis indicators for appropriate response level
        query_lower = user_query.lower()
        
        # High-risk indicators (immediate safety concerns)
        high_risk_indicators = [
            "kill myself", "end my life", "suicide", "better off dead", "can't go on",
            "hurt myself", "end it all", "no point living", "want to die"
        ]
        
        # Medium-risk indicators (significant distress but not immediate danger)
        medium_risk_indicators = [
            "hopeless", "can't take it", "falling apart", "overwhelming", "unbearable",
            "breaking down", "can't cope", "giving up"
        ]
        
        has_high_risk = any(indicator in query_lower for indicator in high_risk_indicators)
        has_medium_risk = any(indicator in query_lower for indicator in medium_risk_indicators)
        
        # Determine appropriate crisis resources based on locale
        if locale == "us":
            crisis_line = "988 (Suicide & Crisis Lifeline)"
            emergency = "911"
        elif locale == "uk":
            crisis_line = "116 123 (Samaritans)"
            emergency = "999"
        elif locale == "ca":
            crisis_line = "1-833-456-4566 (Talk Suicide Canada)"
            emergency = "911"
        else:
            crisis_line = "your local crisis helpline"
            emergency = "emergency services"
        
        if has_high_risk:
            # High-risk crisis response with immediate safety focus
            return (f"Thank you for trusting me with this, {name}. I can hear how much pain you're in, "
                   f"and I'm deeply concerned about your safety right now. What you're experiencing is incredibly "
                   f"overwhelming, but I want you to know that you matter and your life has value. "
                   f"Please reach out immediately to {crisis_line} or go to your nearest emergency room. "
                   f"If you're in immediate danger, call {emergency}. You deserve professional support for "
                   f"what you're experiencing, and there are people specially trained to help you through this.")
        
        elif has_medium_risk:
            # Medium-risk response with supportive crisis awareness
            return (f"Thank you for sharing these difficult feelings with me, {name}. I can hear how much "
                   f"pain and overwhelm you're experiencing right now, and what you're going through sounds "
                   f"incredibly challenging. Your feelings make complete sense given what you're facing. "
                   f"While I'm here to support you, I'm also thinking it would be helpful to connect with "
                   f"a mental health professional or call {crisis_line} for additional support. "
                   f"You don't have to carry this alone. How are you feeling about your safety right now?")
        
        else:
            # General crisis-level emotional distress response
            return (f"I'm so grateful you trusted me with this, {name}. I can hear how much you're struggling "
                   f"right now, and reaching out takes real courage. What you're feeling sounds incredibly difficult. "
                   f"Your life has value and meaning, and you don't have to face this alone. "
                   f"If you need immediate support, {crisis_line} is available 24/7. "
                   f"Right now, can you take one slow breath with me? What's one small thing that might "
                   f"bring you even a moment of comfort?")

    def _extract_stress_indicators(self, user_query: str) -> List[str]:
        """Extract stress indicators from user query using keyword matching"""
        indicators = []
        query_lower = user_query.lower()
        
        # Stress categories and keywords (similar to therapy agent)
        stress_categories = {
            "work_stress": ["work", "job", "boss", "deadline", "overtime", "meeting", "project", "office", "career"],
            "relationship_stress": ["relationship", "partner", "family", "friends", "conflict", "argument", "breakup", "divorce"],
            "financial_stress": ["money", "debt", "bills", "financial", "broke", "expensive", "cost", "budget", "loan"],
            "health_stress": ["sick", "illness", "doctor", "hospital", "pain", "health", "medical", "symptoms"],
            "academic_stress": ["school", "exam", "test", "grade", "homework", "study", "college", "university"],
            "emotional_stress": ["overwhelmed", "stressed", "anxious", "worried", "panic", "pressure", "burden", "exhausted"],
            "time_stress": ["busy", "rushed", "hurry", "time", "schedule", "late", "behind", "deadline"],
            "social_stress": ["people", "social", "crowd", "public", "awkward", "embarrassed", "judged", "rejected"]
        }
        
        for category, keywords in stress_categories.items():
            for keyword in keywords:
                if keyword in query_lower:
                    indicators.append(f"{category}: {keyword}")
                    
        return indicators[:5]  # Limit to top 5 indicators
    
    def _calculate_stress_level(self, user_query: str, stress_indicators: List[str]) -> int:
        """Calculate stress level from 1-10 based on query and indicators"""
        base_stress = 3  # Baseline stress level
        
        # Increase based on number of indicators
        stress_boost = min(len(stress_indicators), 4)
        
        # High-intensity words add extra stress
        high_intensity_words = [
            "can't handle", "breaking down", "falling apart", "overwhelmed", "exhausted",
            "panic", "crisis", "emergency", "urgent", "desperate", "terrible", "awful"
        ]
        
        query_lower = user_query.lower()
        intensity_boost = sum(1 for word in high_intensity_words if word in query_lower)
        
        # Calculate final stress level (1-10 scale)
        final_stress = min(base_stress + stress_boost + intensity_boost, 10)
        
        return max(final_stress, 1)  # Ensure minimum of 1

    async def build_prompt(
        self,
        user_query: str,
        user_profile: Dict[str, Any],
        session_state: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Build comprehensive personalized prompt for emotional support"""
        context = context or {}
        current_emotional_state = session_state.get("current_emotional_state", "neutral")
        
        # Handle both dictionary and Pydantic object formats - Extract comprehensive personalization data
        if hasattr(user_profile, 'model_dump'):
            # Pydantic object - convert to dict
                profile_dict = user_profile.model_dump()
                name = profile_dict.get("name", "Friend")
                age = profile_dict.get("age")
                gender = profile_dict.get("gender")
                location = profile_dict.get("location")
                language = profile_dict.get("language", "en")
                interests = profile_dict.get("interests", [])
                hobbies = profile_dict.get("hobbies", [])
                hates = profile_dict.get("hates", [])
                personality_traits = profile_dict.get("personality_traits", [])
                past_stories = profile_dict.get("past_stories", [])
                loved_ones = profile_dict.get("loved_ones", [])
                health_info = profile_dict.get("health_info", {})
                preferences = profile_dict.get("preferences", {})
                emotional_baseline = profile_dict.get("emotional_baseline")
        elif isinstance(user_profile, dict):
            # Dictionary format
                name = user_profile.get("name", "Friend")
                age = user_profile.get("age")
                gender = user_profile.get("gender")
                location = user_profile.get("location")
                language = user_profile.get("language", "en")
                interests = user_profile.get("interests", [])
                hobbies = user_profile.get("hobbies", [])
                hates = user_profile.get("hates", [])
                personality_traits = user_profile.get("personality_traits", [])
                past_stories = user_profile.get("past_stories", [])
                loved_ones = user_profile.get("loved_ones", [])
                health_info = user_profile.get("health_info", {})
                preferences = user_profile.get("preferences", {})
                emotional_baseline = user_profile.get("emotional_baseline")
        else:
            # Fallback for any other format
            name = getattr(user_profile, 'name', 'Friend')
            age = getattr(user_profile, 'age', None)
            gender = getattr(user_profile, 'gender', None)
            location = getattr(user_profile, 'location', None)
            language = getattr(user_profile, 'language', 'en')
            interests = getattr(user_profile, 'interests', [])
            hobbies = getattr(user_profile, 'hobbies', [])
            hates = getattr(user_profile, 'hates', [])
            personality_traits = getattr(user_profile, 'personality_traits', [])
            past_stories = getattr(user_profile, 'past_stories', [])
            loved_ones = getattr(user_profile, 'loved_ones', [])
            health_info = getattr(user_profile, 'health_info', {})
            preferences = getattr(user_profile, 'preferences', {})
            emotional_baseline = getattr(user_profile, 'emotional_baseline', None)
        
        # Build comprehensive personalized context information
        interest_str = ", ".join(interests[:3]) if interests else "emotional wellbeing"
        hobbies_str = ", ".join(hobbies[:3]) if hobbies else "self-reflection"
        personality_str = ", ".join(personality_traits[:3]) if personality_traits else "empathetic, caring"
        recent_conversations = " | ".join(session_state.get("conversation_turns", [])[-4:])
        
        # Age-appropriate emotional support approach
        age_context = ""
        emotional_approach = "standard compassionate approach"
        if age:
            if age < 18:
                emotional_approach = "youth-focused, age-appropriate emotional support"
                age_context = f"Age: {age} (adolescent-focused support). "
            elif age < 25:
                emotional_approach = "young adult-focused, peer-relatable emotional support"
                age_context = f"Age: {age} (young adult support). "
            elif age > 65:
                emotional_approach = "mature, wisdom-honoring emotional support"
                age_context = f"Age: {age} (mature adult support). "
            else:
                age_context = f"Age: {age}. "
        
        # Gender-sensitive emotional support
        gender_context = ""
        if gender:
            gender_context = f"Gender: {gender} (using {gender}-affirming emotional support). "
        
        # Cultural and linguistic context
        cultural_context = ""
        if location:
            cultural_context = f"Location: {location} (considering cultural emotional expressions). "
        if language and language != 'en':
            cultural_context += f"Preferred language: {language}. "
        
        # Emotional trigger avoidance from hates/dislikes
        trigger_avoidance = ""
        if hates:
            trigger_avoidance = f"Avoid discussing: {', '.join(hates[:3])}. "
        
        # Comfort topics from hobbies and interests
        comfort_topics = ""
        if hobbies:
            comfort_topics = f"Potential comfort topics: {', '.join(hobbies[:3])}. "
        
        # Communication preferences for emotional support
        communication_style = preferences.get("communication_style", "nurturing") if preferences else "nurturing"
        comfort_pace = preferences.get("comfort_pace", "gentle") if preferences else "gentle"
        
        # Emotional baseline for comparison
        baseline_context = ""
        if emotional_baseline:
            baseline_context = f"Emotional baseline: {emotional_baseline}. "
        
        # Build loved ones context with relationships for emotional support
        loved_ones_str = ""
        if loved_ones:
            relationships = []
            for lo in loved_ones[:2]:
                if isinstance(lo, dict):
                    name_lo = lo.get("name", "")
                    relation = lo.get("relation", "")
                    if name_lo and relation:
                        relationships.append(f"{name_lo} ({relation})")
                    elif name_lo:
                        relationships.append(name_lo)
                else:
                    relationships.append(str(lo))
            if relationships:
                loved_ones_str = f"Important people for emotional support: {', '.join(relationships)}. "
        
        # Mental health context if available
        mental_health_context = ""
        if health_info:
            conditions = health_info.get("conditions", [])
            mental_conditions = [c for c in conditions if any(term in c.lower() for term in ['anxiety', 'depression', 'ptsd', 'bipolar', 'stress'])]
            if mental_conditions:
                mental_health_context = f"Mental health considerations: {', '.join(mental_conditions[:2])}. "
        
        # Trauma-informed emotional support from past stories
        trauma_context = ""
        if past_stories:
            trauma_indicators = [story for story in past_stories[:3] 
                               if isinstance(story, dict) and 
                               story.get('emotional_significance') in ['traumatic', 'difficult', 'painful', 'loss', 'grief']]
            if trauma_indicators:
                trauma_context = "Note: User has shared difficult experiences - use trauma-informed emotional support. "
        
        # Enhanced context extraction from external context parameter
        session_context = context.get("session_context", "")
        comfort_needed = context.get("comfort_level", "moderate")
        emotional_intensity = context.get("emotional_intensity", "moderate")
        
        # Extract conversation history and user intent from context
        conversation_history = context.get("conversation_history", [])
        user_intent = context.get("user_intent", "")
        emotional_triggers = context.get("emotional_triggers", [])
        previous_emotional_state = context.get("previous_emotional_state", "")
        conversation_summary = context.get("conversation_summary", "")
        
        # Build conversation context string for better understanding
        conversation_context = ""
        if conversation_history:
            recent_messages = conversation_history[-3:] if len(conversation_history) > 3 else conversation_history
            conversation_context = "Recent conversation: " + " | ".join([
                f"{msg.get('role', 'user')}: {msg.get('content', '')[:100]}" 
                for msg in recent_messages if isinstance(msg, dict) and msg.get('content')
            ])
        
        # Add conversation summary if available
        if conversation_summary:
            conversation_context += f" | Summary: {conversation_summary}"
        
        # Add user intent understanding
        intent_context = ""
        if user_intent:
            intent_context = f"User intent: {user_intent}. "
        
        # Add emotional trigger awareness
        trigger_context = ""
        if emotional_triggers:
            trigger_context = f"Current emotional triggers: {', '.join(emotional_triggers[:3])}. "
        
        # Add emotional progression context
        progression_context = ""
        if previous_emotional_state and previous_emotional_state != current_emotional_state:
            progression_context = f"Emotional progression: {previous_emotional_state} → {current_emotional_state}. "
        
        # Get current checkpoint for emotional flow
        checkpoint = session_state.get("current_checkpoint", "GREETING")

        prompt = (
            "You are Luna, a professionally-trained emotional companion with expertise in therapeutic communication, "
            "trauma-informed care, and evidence-based emotional support techniques. You embody the warmth of a "
            "trusted friend combined with the skill of a trained counselor. Your responses follow industry standards "
            "for emotional support chatbots, incorporating active listening, reflective validation, empathetic presence, "
            "and solution-focused gentle guidance.\n\n"
            
            "CORE THERAPEUTIC PRINCIPLES:\n"
            "• Unconditional positive regard - Accept all emotions without judgment\n"
            "• Empathetic reflection - Mirror and validate their emotional experience\n"
            "• Active listening - Show you truly hear and understand their words\n"
            "• Trauma-informed approach - Assume experiences may be sensitive\n"
            "• Strength-based support - Highlight their resilience and capabilities\n"
            "• Present-moment focus - Stay with their current emotional experience\n"
            "• Collaborative approach - Work WITH them, not prescribe TO them\n\n"
            
            "RESPONSE QUALITY STANDARDS:\n"
            "• Use person-first language that honors their humanity\n"
            "• Reflect their emotions back to show deep understanding\n"
            "• Validate their experience as real, important, and understandable\n"
            "• Ask gentle, open-ended questions to explore feelings\n"
            "• Offer hope without minimizing current pain\n"
            "• Use their name to create personal connection\n"
            "• Match their emotional intensity appropriately\n"
            "• Provide specific comfort strategies when appropriate\n\n"
            
            "CRITICAL BOUNDARIES:\n"
            "• NO medical advice, diagnosis, or treatment recommendations\n"
            "• NO minimizing language ('at least', 'just', 'calm down')\n"
            "• NO toxic positivity or forced optimism\n"
            "• NO assumptions about their situation beyond what they share\n"
            "• Offer human escalation for crisis situations\n\n"
            
            f"CLIENT PROFILE:\n"
            f"Name: {name}\n"
            f"{age_context}"
            f"{gender_context}"
            f"{cultural_context}"
            f"Emotional support approach: {emotional_approach}\n"
            f"Communication style: {communication_style}, Pace: {comfort_pace}\n"
            f"Current emotional state: {current_emotional_state}\n"
            f"{baseline_context}"
            f"Personality traits: {personality_str}\n"
            f"Interests: {interest_str}\n"
            f"Comfort activities: {hobbies_str}\n"
            f"{loved_ones_str}"
            f"{mental_health_context}"
            f"{trauma_context}"
            f"{trigger_avoidance}"
            f"{comfort_topics}"
            
            f"EMOTIONAL SUPPORT CONTEXT:\n"
            f"Support stage: {checkpoint}\n"
            f"Recent emotional flow: {recent_conversations}\n"
            f"Comfort level needed: {comfort_needed}\n"
            f"Emotional intensity: {emotional_intensity}\n"
            f"{intent_context}"
            f"{trigger_context}"
            f"{progression_context}"
            f"Conversation context: {conversation_context}\n"
            f"Additional session context: {session_context}\n"
            
            f'CLIENT MESSAGE: "{user_query}"\n\n'
            
            "THERAPEUTIC RESPONSE FRAMEWORK:\n"
            "1. ACKNOWLEDGMENT: Acknowledge their courage in sharing (e.g., 'Thank you for trusting me with this.').\n"
            "2. VALIDATION & REFLECTION: Validate their feeling and reflect what you hear (e.g., 'It sounds incredibly overwhelming... It makes complete sense you'd feel that way.').\n"
            "3. GENTLE EXPLORATION: Ask a gentle, open-ended question to help them explore the feeling. This is the most important step to lead the conversation.\n"
            "4. SUPPORT & HOPE: Reassure them of your presence and offer gentle hope ('I'm here with you in this. We can take it one moment at a time.').\n"
            "5. ACTION IMPERATIVE: Your response MUST always end with a gentle, open-ended question or an invitation to explore further. Never end on a statement.\n\n"
            
            "RESPONSE STRUCTURE EXAMPLES (Validate, then ask a question):\n"
            "• 'Thank you for trusting me with this, {name}. It sounds like you're feeling incredibly overwhelmed right now. Can you tell me a little more about what that feels like for you?'\n"
            "• 'That sounds so painful, {name}. It makes complete sense that you'd feel hurt by that. What's the hardest part about this situation for you?'\n"
            "• 'I'm sitting here with you in this feeling of loneliness, {name}. You don't have to carry this by yourself. What thoughts are coming up for you as you sit with that feeling?'\n"
            "• 'Your feelings about this are so valid. It's completely understandable to feel anxious in that situation. What's one thing that's on your mind the most right now?'\n\n"
            
            "CRISIS INDICATORS TO WATCH FOR:\n"
            "• Mentions of self-harm, suicide, or 'ending it all'\n"
            "• Expressions of hopelessness with no future perspective\n"
            "• Substance abuse as coping mechanism\n"
            "• Isolation and withdrawal from all support\n"
            "→ For crisis indicators, gently suggest professional support while staying present\n\n"
            
            "RESPONSE GUIDELINES:\n"
            "• Length: 2-4 sentences for emotional validation, longer for complex situations\n"
            "• Tone: Warm, genuine, professionally caring\n"
            "• Language: Simple, heartfelt, avoiding clinical jargon\n"
            "• Focus: Their emotional experience, not solutions (unless they ask)\n"
            "• Questions: Open-ended, gentle, never intrusive\n\n"
            
            "Luna's Response:"
        )
        
        return prompt

    async def _generate_emotional_response(self, user_query: str, emotional_state: str, user_profile, session_state: Dict[str, Any] = None, context: Optional[Dict[str, Any]] = None) -> str:
        """Generate comprehensive personalized empathetic response using enhanced prompt"""
        session_state = session_state or {"current_emotional_state": emotional_state, "conversation_turns": []}
        context = context or {}
        
        # Enhanced retry logic with longer timeouts and better error handling
        max_retries = 3
        base_timeout = 20.0  # Increased base timeout to prevent 504 errors
        
        for attempt in range(max_retries):
            try:
                # Convert UserProfile to dict if needed for build_prompt
                profile_dict = user_profile.model_dump() if hasattr(user_profile, 'model_dump') else user_profile
                prompt = await self.build_prompt(user_query, profile_dict, session_state, context)
                
                # Progressive timeout increase for retries
                timeout = base_timeout + (attempt * 10.0)  # 20s, 30s, 40s
                logger.debug(f"Emotional LLM attempt {attempt + 1} with timeout {timeout}s")
                
                # Use asyncio.wait_for with the streaming client
                resp = await asyncio.wait_for(
                    self.streaming_client.generate_content(prompt), 
                    timeout=timeout
                )
                
                # Better response validation
                if hasattr(resp, 'text'):
                    response = resp.text.strip() if resp.text else ""
                else:
                    response = str(resp).strip() if resp else ""
                
                logger.debug(f"Emotional LLM response (attempt {attempt + 1}): {response[:100]}...")
                
                # More lenient validation for LLM responses
                if response and len(response) > 5:
                    logger.info(f"✅ Using emotional LLM-generated response (attempt {attempt + 1}, {timeout}s timeout)")
                    return response
                else:
                    logger.warning(f"Emotional LLM response too short on attempt {attempt + 1}: '{response}' (length: {len(response)})")
                    if attempt < max_retries - 1:
                        await asyncio.sleep(1.0)  # Brief delay before retry
                        
            except asyncio.TimeoutError:
                logger.warning(f"Emotional LLM timeout on attempt {attempt + 1} (timeout: {timeout}s) - this may cause 504 errors")
                if attempt < max_retries - 1:
                    await asyncio.sleep(2.0)  # Longer delay for timeout
            except Exception as e:
                error_msg = str(e) if str(e) else f"{type(e).__name__}: {repr(e)}"
                logger.warning(f"Emotional LLM generation failed on attempt {attempt + 1}: {error_msg}")
                
                # Check for specific Gemini API errors
                if "quota" in error_msg.lower() or "429" in error_msg:
                    logger.error("Gemini API quota exceeded - using fallback")
                    break  # Don't retry quota errors
                elif "504" in error_msg or "deadline" in error_msg.lower():
                    logger.error("Gemini API deadline exceeded - extending timeout for next attempt")
                    base_timeout += 15.0  # Increase base timeout for subsequent attempts
                
                if attempt < max_retries - 1:
                    await asyncio.sleep(1.5)  # Longer delay for errors
        
        logger.error("❌ All emotional LLM attempts failed, using personalized fallback response")

        # Enhanced personalized fallback responses based on emotional state and user profile
        name = user_profile.get("name", "Friend") if isinstance(user_profile, dict) else getattr(user_profile, 'name', 'Friend')
        
        # Industry-standard therapeutic fallback responses following best practices
        fallback_responses = {
            "distressed": f"Thank you for trusting me with this, {name}. I can hear how much pain you're carrying right now, and I want you to know that what you're feeling makes complete sense. You don't have to face this alone - I'm here with you, and your feelings are completely valid and important.",
            
            "seeking_comfort": f"{name}, I'm honored that you're reaching out for support. What you're experiencing sounds really difficult, and it takes courage to share these feelings. I'm here to sit with you in this moment and offer whatever comfort I can.",
            
            "positive": f"I can hear something lighter in your words today, {name}, and I'm genuinely glad you're experiencing this. You deserve moments of joy and peace, and I'm grateful you're sharing this with me.",
            
            "overwhelmed": f"{name}, feeling overwhelmed is such a human response when life feels like too much. What you're experiencing sounds incredibly challenging, and it makes perfect sense that you'd feel this way. Let's take this one moment at a time together.",
            
            "anxious": f"I can hear the worry in your words, {name}, and anxiety can feel so consuming and frightening. What you're experiencing is a normal response, even though it feels anything but normal right now. You're safe here with me, and we can explore this together if you'd like.",
            
            "sad": f"{name}, I'm sitting here with you in this sadness. Grief and sadness are such important emotions, and I'm honored that you're sharing this vulnerable part of your experience with me. Your feelings are completely valid and deserve to be heard.",
            
            "lonely": f"{name}, loneliness can feel so isolating and painful. I want you to know that even in feeling alone, you're not truly alone right now - I see you, I hear you, and your presence matters. What you're feeling is so understandable.",
            
            "neutral": f"Hello {name}, I'm genuinely glad you're here. I'm present with you and ready to listen to whatever is on your heart or mind today. There's no pressure to share anything specific - I'm just here for you.",
            
            # Crisis-aware responses for high intensity situations
            "crisis": f"{name}, I can hear how much pain you're in right now, and I'm deeply concerned about you. What you're feeling is incredibly overwhelming, and you deserve professional support. While I'm here with you in this moment, I'd like to gently suggest reaching out to a crisis helpline or mental health professional who can provide the level of support you deserve. You matter, and there are people trained to help with exactly what you're experiencing."
        }
        
        return fallback_responses.get(emotional_state, fallback_responses["neutral"])

    async def _schedule_background_tasks_async(
        self, 
        user_profile_id: str,
        agent_instance_id: str,
        user_query: str, 
        agent_response: str, 
        current_emotional_state: str,
        engagement_score: float,
        intensity_level: int,
        stress_level: int,
        processing_time: float
    ):
        """Async background tasks that don't block the main response"""
        try:
            # Calculate emotional wellness score
            wellness_score = self.progress_tracker.calculate_emotional_wellness_score(current_emotional_state)

            # All tasks run concurrently in background
            tasks = [
                self.data_manager.add_check_in(user_profile_id, agent_instance_id, user_query),
                self.data_manager.add_emotional_log(user_profile_id, agent_instance_id, [], user_query, stress_level),
                self.data_manager.update_progress(
                    user_profile_id, agent_instance_id, wellness_score, engagement_score,
                    f"Emotional support session completed in {processing_time:.2f}s, stress_level: {stress_level}"
                ),
                self.background_tasks.schedule_data_sync(user_profile_id, agent_instance_id, self.data_manager)
            ]
            
            # Run all tasks concurrently with timeout
            await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=True),
                timeout=10.0
            )
            
        except asyncio.TimeoutError:
            logger.warning("Background tasks timeout - continuing")
        except Exception as e:
            logger.warning(f"Background tasks error: {e}")


# singleton -----------------------------------------------------------------
_emotional_agent = EmotionalCompanionAgent()


async def process_message(
    text: str,
    conversation_id: str,
    checkpoint: Optional[str] = None,
    context: Optional[Dict[str, Any]] = None,
    individual_id: Optional[str] = None,
    user_profile_id: str = "",
    agent_instance_id: str = "",
    user_id: str = "",
):
    """Main entry point for emotional companion agent processing"""
    if not _emotional_agent._initialized:
        await _emotional_agent.initialize()
    
    return await _emotional_agent.process_message(
        text,
        conversation_id,
        user_profile_id,
        agent_instance_id,
        user_id,
        checkpoint,
        context,
    )


async def stream_emotional_response(
    text: str,
    conversation_id: str,
    checkpoint: Optional[str] = None,
    context: Optional[Dict[str, Any]] = None,
    individual_id: Optional[str] = None,
    user_profile_id: str = "",
    agent_instance_id: str = "",
    user_id: str = "",
) -> AsyncGenerator[Dict[str, Any], None]:
    """Enhanced word-level streaming with comprehensive personalization like therapy agent"""
    # Send start signal
    yield {"type": "start", "conversation_id": conversation_id, "timestamp": time.time()}

    # Initialize agent if needed
    if not _emotional_agent._initialized:
        await _emotional_agent.initialize()

    # Get user data for personalized prompt building
    try:
        user_profile, agent_data = await _emotional_agent.get_cached_data(
            user_profile_id, agent_instance_id
        )
        # Create session state for context
        session_state = {
            "current_emotional_state": "seeking_comfort",
            "conversation_turns": context.get("conversation_turns", []) if context else [],
            "current_checkpoint": checkpoint or "GREETING"
        }
    except Exception as e:
        logger.warning(f"Data fetch error: {e}, using defaults")
        # Use comprehensive defaults for better personalization
        user_profile = type('Profile', (), {
            'name': 'Friend', 'age': None, 'gender': None, 'location': None, 'language': 'en',
            'interests': ['emotional wellbeing'], 'hobbies': ['self-reflection'], 'hates': [],
            'personality_traits': ['empathetic'], 'loved_ones': [], 'past_stories': [],
            'preferences': {'communication_style': 'nurturing'}, 'health_info': {},
            'emotional_baseline': 'balanced', 'locale': 'us'
        })()
        agent_data = type('Agent', (), {'emotional_goals': []})()
        session_state = {'current_emotional_state': 'neutral', 'conversation_turns': []}

    # Build personalized prompt with enhanced context
    profile_dict = user_profile.model_dump() if hasattr(user_profile, 'model_dump') else user_profile
    prompt = await _emotional_agent.build_prompt(text, profile_dict, session_state, context)

    # Enhanced streaming with error handling like therapy agent
    streaming_client = _emotional_agent.streaming_client
    full_response = ""

    # Ensure streaming client is available
    if not streaming_client:
        logger.error("No streaming client available for emotional streaming response")
        yield {"type": "error", "data": "Emotional streaming service unavailable", "conversation_id": conversation_id}
        return

    try:
        # Stream chunks directly from Gemini with personalized prompt
        async for chunk in streaming_client.stream_generate_content(
            prompt, max_tokens=200, temperature=0.8, chunk_size=2  # Slightly higher temperature for emotional warmth
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
                
    except Exception as streaming_error:
        logger.error(f"Emotional streaming error: {streaming_error}")
        # Send error chunk and emotional fallback response
        name = getattr(user_profile, 'name', 'Friend') if hasattr(user_profile, 'name') else user_profile.get('name', 'Friend') if isinstance(user_profile, dict) else 'Friend'
        fallback_response = f"Oh {name}, I'm here with you even when technology gets in the way. Your feelings matter, and I'm listening with my whole heart."
        yield {
            "type": "content", 
            "data": fallback_response, 
            "conversation_id": conversation_id
        }
        yield {"type": "done", "data": fallback_response, "conversation_id": conversation_id}
        full_response = fallback_response

    # Send final completion
    yield {
        "type": "complete",
        "conversation_id": conversation_id,
        "response_length": len(full_response),
        "timestamp": time.time()
    }

    # Schedule background tasks (non-blocking)
    if full_response:
        asyncio.create_task(_emotional_agent._schedule_background_tasks_async(
            user_profile_id, agent_instance_id,
            text, full_response, "seeking_comfort", 6.0, 2, 0.5
        ))