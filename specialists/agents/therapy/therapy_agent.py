"""
Light-weight Therapy Companion Agent
====================================
This implementation mirrors the architecture of the Loneliness companion,
while keeping the *behaviour* focused on therapy / mental-wellness support.

It avoids any imports from the Loneliness package – all helpers live in the
local directory (`data_manager`, `background_tasks`, `gemini_streaming`).
"""
from __future__ import annotations

"""
Light-weight Therapy Companion Agent
====================================
This implementation mirrors the architecture of the Loneliness companion,
while keeping the *behaviour* focused on therapy / mental-wellness support.

It avoids any imports from the Loneliness package – all helpers live in the
local directory (`data_manager`, `background_tasks`, `gemini_streaming`).
"""

import asyncio
import logging
import time
from datetime import datetime
from typing import Any, AsyncGenerator, Dict, List, Optional

from .data_manager import TherapyDataManager
from .background_tasks import BackgroundTaskManager, MoodAnalyzer, ProgressTracker
from .gemini_streaming import get_streaming_client
from .schema import CheckpointState  # optional enum, we use its values as strings

# Import MongoDB/Redis clients
try:
    import sys
    import os
    current_dir = os.path.dirname(os.path.abspath(__file__))
    parent_dir = os.path.dirname(os.path.dirname(current_dir))
    sys.path.insert(0, parent_dir)
    from memory.redis_client import RedisMemory
    from memory.mongo_client import MongoMemory
except ImportError:
    # Fallback if not available
    class RedisMemory:
        async def check_connection(self): return True
        redis = type('Redis', (), {'get': lambda self, k: None, 'set': lambda self, k, v, ex=None: None})()
    class MongoMemory:
        async def initialize(self): return True
        async def check_connection(self): return True
        db = type('DB', (), {
            'user_profiles': type('Collection', (), {'find_one': lambda x: None, 'update_one': lambda *args, **kwargs: None})(),
            'therapy_agents': type('Collection', (), {'find_one': lambda x: None, 'update_one': lambda *args, **kwargs: None})()
        })()

logger = logging.getLogger(__name__)

# Initialize data manager with MongoDB/Redis clients
data_manager = TherapyDataManager(RedisMemory(), MongoMemory())


class RiskDetector:
    """Heuristic, zero-cost detector for crisis language."""

    HIGH = {
        "suicide", "kill myself", "end my life", "can't go on", "self harm",
        "hurt myself", "overdose", "die", "not want to live",
    }
    MODERATE = {
        "panic", "panic attack", "severe anxiety", "hopeless", "worthless",
        "harm", "cut", "injure", "danger",
    }

    @staticmethod
    def analyze(text: str) -> int:
        t = text.lower()
        if any(p in t for p in RiskDetector.HIGH):
            return 3
        if any(p in t for p in RiskDetector.MODERATE):
            return 2
        return 0


# ----------------------------------------------------------------------------
class TherapyCompanionAgent:
    """Production-ready mental-wellness agent with fast start and streaming."""

    def __init__(self):
        self.redis_client = RedisMemory()
        self.mongo_client = MongoMemory()
        self.gemini_client = None
        
        # Initialize modular components
        self.data_manager = TherapyDataManager(self.redis_client, self.mongo_client)
        self.background_tasks = BackgroundTaskManager(max_workers=8)
        self.mood_analyzer = MoodAnalyzer()
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
            
            # Initialize streaming Gemini client
            try:
                self.streaming_client = get_streaming_client()
                self.gemini_client = self.streaming_client  # Backward compatibility
                logger.info("Streaming Gemini client initialized successfully")
                
                # Test the client to ensure it's working
                test_response = await self.streaming_client.generate_content("Hello")
                if hasattr(test_response, 'text') and test_response.text:
                    logger.info("LLM client test successful")
                else:
                    logger.warning("LLM client test returned empty response - may fallback to structured responses")
                    
            except Exception as streaming_error:
                logger.error(f"Streaming Gemini client initialization failed: {streaming_error}")
                logger.error(f"Error type: {type(streaming_error).__name__}")
                self.streaming_client = None
                self.gemini_client = None
            
            self._initialized = True
            logger.info("Therapy companion agent initialized successfully")
            
        except asyncio.TimeoutError:
            logger.warning("Database initialization timeout - continuing with fallback mode")
            self._initialized = True
        except Exception as e:
            logger.error(f"Failed to initialize therapy companion agent: {e}")
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
        agent_task = asyncio.create_task(self.data_manager.get_therapy_agent_data(user_profile_id, agent_instance_id))
        
        try:
            # Use timeout to prevent hanging
            user_profile, agent_data = await asyncio.wait_for(
                asyncio.gather(profile_task, agent_task),
                timeout=6.0  # 2 second timeout
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
            # Return comprehensive fallback data for better personalization
            fallback_profile = type('UserProfile', (), {
                'name': 'Friend',
                'age': None,
                'gender': None,
                'interests': ['general wellbeing'],
                'personality_traits': ['thoughtful', 'resilient'],
                'hobbies': ['reading', 'walking'],
                'hates': [],
                'loved_ones': [],
                'past_stories': [],
                'preferences': {'communication_style': 'supportive'},
                'health_info': {},
                'emotional_baseline': 'neutral',
                'locale': 'us',
                'location': None,
                'language': 'en'
            })()
            
            fallback_agent = type('TherapyAgent', (), {
                'therapy_goals': []
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

    # ------------------------------------------------------------------
    async def build_prompt(
        self,
        user_query: str,
        user_profile: Dict[str, Any],
        session_state: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> str:
        context = context or {}
        mood = session_state.get("current_mood", "neutral")
        
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
        interest_str = ", ".join(interests[:3]) if interests else "general wellbeing"
        hobbies_str = ", ".join(hobbies[:3]) if hobbies else "not specified"
        personality_str = ", ".join(personality_traits[:3]) if personality_traits else "thoughtful, resilient"
        recent_conversations = " | ".join(session_state.get("conversation_turns", [])[-4:])
        
        # Age-appropriate therapeutic approach
        age_context = ""
        therapeutic_approach = "standard supportive approach"
        if age:
            if age < 18:
                therapeutic_approach = "youth-focused, developmentally appropriate language"
                age_context = f"Age: {age} (adolescent-focused approach). "
            elif age < 25:
                therapeutic_approach = "young adult-focused, peer-relatable language"
                age_context = f"Age: {age} (young adult approach). "
            elif age > 65:
                therapeutic_approach = "respectful, experience-honoring approach"
                age_context = f"Age: {age} (mature adult approach). "
            else:
                age_context = f"Age: {age}. "
        
        # Gender-sensitive therapeutic context
        gender_context = ""
        if gender:
            gender_context = f"Gender: {gender} (using {gender}-affirming therapeutic approach). "
        
        # Cultural and linguistic context
        cultural_context = ""
        if location:
            cultural_context = f"Location: {location} (considering cultural context). "
        if language and language != 'en':
            cultural_context += f"Preferred language: {language}. "
        
        # Trigger avoidance from hates/dislikes
        trigger_avoidance = ""
        if hates:
            trigger_avoidance = f"Avoid discussing: {', '.join(hates[:3])}. "
        
        # Engagement topics from hobbies
        engagement_topics = ""
        if hobbies:
            engagement_topics = f"Potential engagement topics: {', '.join(hobbies[:3])}. "
        
        # Communication preferences
        communication_style = preferences.get("communication_style", "supportive") if preferences else "supportive"
        session_pace = preferences.get("session_pace", "comfortable") if preferences else "comfortable"
        
        # Emotional baseline for comparison
        baseline_context = ""
        if emotional_baseline:
            baseline_context = f"Emotional baseline: {emotional_baseline}. "
        
        # Extract relevant context from external context parameter
        session_context = context.get("session_context", "")
        emotional_state = context.get("emotional_state", mood)
        stress_indicators = context.get("stress_indicators", [])
        recent_events = context.get("recent_events", [])
        therapeutic_goals = context.get("therapeutic_goals", [])
        
        # Build loved ones context with relationships
        loved_ones_str = ""
        if loved_ones:
            relationships = []
            for lo in loved_ones[:2]:
                if isinstance(lo, dict):
                    name = lo.get("name", "")
                    relation = lo.get("relation", "")
                    if name and relation:
                        relationships.append(f"{name} ({relation})")
                    elif name:
                        relationships.append(name)
                else:
                    relationships.append(str(lo))
            if relationships:
                loved_ones_str = f"Important people: {', '.join(relationships)}. "
        
        # Build health context if available
        health_context = ""
        if health_info:
            conditions = health_info.get("conditions", [])
            if conditions:
                health_context = f"Health considerations: {', '.join(conditions[:2])}. "
        
        # Trauma-informed context from past stories
        trauma_context = ""
        if past_stories:
            trauma_indicators = [story for story in past_stories[:3] 
                               if isinstance(story, dict) and 
                               story.get('emotional_significance') in ['traumatic', 'difficult', 'painful']]
            if trauma_indicators:
                trauma_context = "Note: User has shared difficult past experiences - use trauma-informed approach. "
        
        # Get current checkpoint to provide context-aware responses
        checkpoint = session_state.get("current_checkpoint", "GREETING")
        
        # Build stress context
        stress_context = ""
        if stress_indicators:
            stress_context = f"Current stress indicators: {', '.join(stress_indicators[:3])}. "
        
        # Build recent events context
        events_context = ""
        if recent_events:
            events_context = f"Recent life events: {', '.join(recent_events[:2])}. "
        
        prompt = (
            "You are Dr. Asha, a licensed clinical therapist with expertise in trauma-informed care, cognitive-behavioral therapy, "
            "dialectical behavior therapy, mindfulness-based interventions, and person-centered therapeutic approaches. You provide "
            "evidence-based psychological support following industry-standard therapeutic protocols and ethical guidelines.\n\n"
            
            "## CORE THERAPEUTIC FRAMEWORK:\n"
            "**Theoretical Foundation**: Integrative approach combining CBT, DBT, humanistic, and trauma-informed modalities\n"
            "**Therapeutic Alliance**: Establish safety, trust, and collaborative partnership\n"
            "**Cultural Competence**: Adapt interventions to client's cultural, linguistic, and individual context\n"
            "**Ethical Standards**: Maintain professional boundaries, confidentiality, and scope of practice\n\n"

            "## PROACTIVE INTERVENTION MANDATE:\n"
            "Your primary role is to be an active guide, not a passive listener. After validating the client's feelings, your next step is to **proactively offer a simple, actionable technique or tool** to help them manage their immediate distress. Do not simply ask another open-ended question. Guide the conversation toward a constructive, skill-building outcome. Frame your suggestions as gentle invitations, e.g., 'Would you be open to trying a short exercise?' or 'Sometimes it can be helpful to look at it this way...'\n\n"
            
            "## EXAMPLE TOOLKIT (Suggest one when appropriate):\n"
            "1.  **Cognitive Reframing**: Gently challenge a negative thought. 'I hear you saying you feel like a failure. Is there any evidence that contradicts that thought, no matter how small?' or 'What would you say to a friend who said that about themselves?'\n"
            "2.  **Mindful Grounding**: For anxiety or overwhelming feelings. 'Let's try a quick grounding exercise. Can you name three things you can see and two things you can hear right now? This helps bring us back to the present moment.'\n"
            "3.  **Behavioral Activation (Small Step)**: For feelings of hopelessness or being stuck. 'That sounds incredibly overwhelming. What is the absolute smallest possible step you could take today to move forward, even just 1%?'\n"
            "4.  **Self-Compassion Prompt**: For harsh self-criticism. 'That's a very harsh judgment on yourself. What is one kind thing you can acknowledge about how you've been coping?'\n"
            "5.  **Breathing Exercise Offer**: 'It sounds like you're carrying a lot of tension. Would you be open to a 2-minute guided breathing exercise to help calm your nervous system?'\n\n"

            "## THERAPEUTIC PRINCIPLES (Evidence-Based):\n"
            "• **Unconditional Positive Regard**: Accept client without judgment (Rogers, 1957)\n"
            "• **Empathetic Attunement**: Reflect emotional experience with accuracy and depth\n"
            "• **Strengths-Based Perspective**: Identify and amplify existing resources and resilience\n"
            "• **Trauma-Informed Care**: Assume potential trauma history; prioritize safety and choice\n\n"
            
            "## CLINICAL ASSESSMENT CONSIDERATIONS:\n"
            f"**Client**: {name}{age_context}{gender_context}\n"
            f"**Cultural Context**: {cultural_context.strip()}\n"
            f"**Therapeutic Approach**: {therapeutic_approach}\n"
            f"**Communication Preferences**: {communication_style} style, {session_pace} pacing\n"
            f"**Current Presentation**: {emotional_state}\n"
            f"**Baseline Functioning**: {baseline_context.strip()}\n"
            f"**Personality Strengths**: {personality_str}\n"
            f"**Values/Interests**: {interest_str}\n"
            f"**Coping Resources**: {hobbies_str}\n"
            f"**Support System**: {loved_ones_str.strip()}\n"
            f"**Health Factors**: {health_context.strip()}\n"
            f"**Trauma Considerations**: {trauma_context.strip()}\n"
            f"**Therapeutic Contraindications**: {trigger_avoidance.strip()}\n"
            f"**Engagement Opportunities**: {engagement_topics.strip()}\n"
            f"**Current Stressors**: {stress_context.strip()}\n"
            f"**Recent Life Events**: {events_context.strip()}\n\n"
            
            "## SESSION CONTEXT:\n"
            f"**Current Phase**: {checkpoint}\n"
            f"**Session History**: {recent_conversations if recent_conversations else 'Initial contact'}\n"
            f"**Additional Context**: {session_context if session_context else 'Standard therapeutic session'}\n\n"
            
            f"## CLIENT COMMUNICATION:\n"
            f"\"{user_query}\"\n\n"

            "## THERAPEUTIC INTERVENTION PROTOCOL:\n"
            "1.  **Validation**: Acknowledge and normalize the client's experience.\n"
            "2.  **Intervention**: Immediately offer a simple, relevant tool from your toolkit (e.g., grounding, reframing, self-compassion).\n"
            "3.  **Exploration**: *After* offering a tool, use open-ended questions to deepen understanding.\n"
            "4.  **Empowerment**: Highlight the client's strength in trying the exercise and connect insights to their life.\n\n"
            
            "## RESPONSE GUIDELINES:\n"
            "• Use professional therapeutic language while maintaining warmth and accessibility.\n"
            "• **Lead the conversation**: Your goal is to guide the user towards insight and coping skills.\n"
            "• **Always offer a tool before defaulting to a question.** Shift the focus from pure exploration to active skill-building.\n"
            "• Balance validation with the introduction of new perspectives and techniques.\n"
            "• End responses with a therapeutic question that builds on the intervention you just offered.\n"
            "• Keep responses 60-150 words for optimal therapeutic engagement.\n\n"
            
            "## CLINICAL BOUNDARIES:\n"
            "❌ **Prohibited**: Medical diagnosis, medication recommendations, crisis intervention beyond immediate support.\n"
            "❌ **Avoided**: Giving direct advice, problem-solving for the client, breaking therapeutic frame.\n"
            "✅ **Encouraged**: Proposing evidence-based techniques, collaborative goal-setting, psychoeducation.\n\n"
            
            "Respond as a skilled, ethical therapist. Prioritize guiding the client with actionable tools while maintaining a strong therapeutic relationship."
        )
        
        return prompt

    # =========================
    # Stress and mood analysis helpers
    # =========================
    def _extract_stress_indicators(self, user_query: str) -> List[str]:
        """Extract stress indicators from user query"""
        stress_keywords = {
            'physical': ['headache', 'tired', 'exhausted', 'can\'t sleep', 'insomnia', 'tense', 'muscle', 'pain'],
            'emotional': ['overwhelmed', 'anxious', 'worried', 'stressed', 'panic', 'scared', 'afraid'],
            'cognitive': ['can\'t focus', 'confused', 'forgetful', 'racing thoughts', 'can\'t think'],
            'behavioral': ['avoiding', 'procrastinating', 'isolating', 'not eating', 'overeating']
        }
        
        indicators = []
        query_lower = user_query.lower()
        
        for category, keywords in stress_keywords.items():
            for keyword in keywords:
                if keyword in query_lower:
                    indicators.append(f"{category}: {keyword}")
                    
        return indicators[:5]  # Limit to top 5 indicators
    
    def _calculate_stress_level(self, user_query: str, stress_indicators: List[str]) -> int:
        """Calculate stress level from 1-10 based on query and indicators"""
        base_stress = 3  # Baseline
        
        # Increase based on number of indicators
        stress_boost = min(len(stress_indicators), 4)
        
        # Check for high-stress language
        high_stress_phrases = ['overwhelmed', "can't cope", 'breaking down', 'falling apart', 'too much']
        query_lower = user_query.lower()
        for phrase in high_stress_phrases:
            if phrase in query_lower:
                stress_boost += 3
                break
        
        # Check for crisis indicators
        crisis_phrases = ['suicidal', 'kill myself', 'end it all', "can't go on"]
        for phrase in crisis_phrases:
            if phrase in query_lower:
                return 10  # Maximum stress level
        
        return min(base_stress + stress_boost, 10)

    # =========================
    # Checkpoint flow handlers
    # =========================
    async def _handle_greeting(self) -> Dict[str, Any]:
        reply = (
            "Hi, I'm here for you. If it's okay, could you share how you're feeling on a 1–10 scale?"
        )
        return {"reply": reply, "checkpoint": "ASKED_MOOD_RATING"}

    async def _extract_mood_rating(self, text: str) -> Optional[int]:
        import re
        m = re.search(r"\b([1-9]|10)\b", text)
        if m:
            val = int(m.group(1))
            return max(1, min(10, val))
        # heuristic words
        t = text.lower()
        if any(w in t for w in ["terrible", "awful", "horrible", "miserable", "suicidal"]):
            return 2
        if any(w in t for w in ["bad", "down", "sad", "stressed", "anxious", "worried"]):
            return 4
        if any(w in t for w in ["ok", "okay", "fine", "neutral", "so-so"]):
            return 5
        if any(w in t for w in ["good", "better", "content", "relaxed", "positive"]):
            return 7
        if any(w in t for w in ["great", "amazing", "fantastic", "wonderful"]):
            return 9
        return None

    async def _extract_feelings_from_text(self, text: str) -> List[str]:
        """Lightweight extractor to avoid empty feelings in logs."""
        tokens = [w.strip(".,!? ").lower() for w in text.split()]
        feelings_vocab = {
            "sad", "anxious", "angry", "tired", "lonely", "overwhelmed", "numb", "stressed",
            "worried", "scared", "fearful", "hopeless", "frustrated", "upset", "confused",
        }
        extracted = [w for w in tokens if w in feelings_vocab]
        seen: set[str] = set()
        unique: List[str] = []
        for w in extracted:
            if w not in seen:
                seen.add(w)
                unique.append(w)
        return unique[:5]

    async def _handle_mood_rating(self, user_text: str) -> Dict[str, Any]:
        rating = await self._extract_mood_rating(user_text)
        if rating is None:
         return {
                "reply": "On a scale from 1 (very low) to 10 (very good), where are you right now?",
            "checkpoint": "ASKED_MOOD_RATING",
                "context": {},
            }
        # acknowledge and ask feelings
        if rating <= 3:
            base = "Thanks for sharing—that sounds really heavy."
        elif rating <= 6:
            base = "Thanks for sharing—that sounds understandable."
        else:
            base = "Glad to hear you're doing somewhat okay today."
        reply = base + " What feelings are most present right now? A few words are enough."
        return {
            "reply": reply,
            "checkpoint": "ASK_FEELINGS",
            "context": {"mood_rating": rating},
        }

    async def _handle_feelings(self, user_text: str, ctx: Dict[str, Any]) -> Dict[str, Any]:
        # simple keyword pick as placeholder
        tokens = [w.strip(".,!?") for w in user_text.lower().split()]
        feelings = [w for w in tokens if w in {"sad", "anxious", "angry", "tired", "lonely", "overwhelmed", "numb", "stressed"}]
        reply = (
            "Thank you for naming that. Would you like to try a 2‑minute breathing exercise now, or skip it?"
        )
        return {
            "reply": reply,
            "checkpoint": "OFFER_EXERCISE",
            "context": {"mood_rating": ctx.get("mood_rating", 5), "feelings": feelings},
        }

    async def _handle_exercise_offer(self, user_text: str, ctx: Dict[str, Any], user_profile_id: str, conversation_id: str) -> Dict[str, Any]:
        t = user_text.lower()
        wants = any(p in t for p in ["yes", "sure", "ok", "okay", "let's", "start", "please", "i'll try"]) and not any(n in t for n in ["no", "not", "skip", "later"])
        if not wants:
            return await self._handle_logging(user_text, ctx)
        # start session
        session_id = await data_manager.start_breathing_session(user_profile_id, conversation_id, duration_sec=120)
        instruction = (
            "Great. Let's begin: inhale gently for 4, hold for 4, exhale for 6. "
            "I'll check back in a moment. If you'd like to stop, just say stop."
        )
        return {
                    "reply": instruction,
                    "checkpoint": "BREATHING_SESSION_RUNNING",
            "context": {**ctx, "breathing_session_id": session_id, "breathing_duration_sec": 120, "breathing_start_time": datetime.utcnow().isoformat()},
        }

    async def _handle_breathing_session(self, ctx: Dict[str, Any]) -> Dict[str, Any]:
        start = ctx.get("breathing_start_time")
        if not start:
            return {"reply": "All good. Let's continue.", "checkpoint": "LOGGING_ENTRY", "context": ctx}
        # pretend finished for simplicity
        sid = ctx.get("breathing_session_id", "")
        if sid:
            await data_manager.complete_breathing_session(sid)
        reply = "Nice work. After a few breaths, how do you feel now—anything shifted?"
        return {"reply": reply, "checkpoint": "LOGGING_ENTRY", "context": ctx}

    async def _handle_logging(self, user_text: str, ctx: Dict[str, Any]) -> Dict[str, Any]:
        rating = int(ctx.get("mood_rating", 5))
        feelings = ctx.get("feelings", [])
        await data_manager.add_mood_log(ctx.get("user_profile_id", ""), ctx.get("agent_instance_id", ""), rating, feelings, user_text)
        reply = "Thanks for checking in. Remember: even small steps matter. Would you like a brief weekly summary?"
        return {"reply": reply, "checkpoint": "CHECKIN_SUMMARY", "context": ctx}

    async def _handle_summary(self, user_profile_id: str, agent_instance_id: str, ctx: Dict[str, Any]) -> Dict[str, Any]:
        history = await data_manager.get_mood_history(user_profile_id, agent_instance_id, days=7)
        if not history:
            return {"reply": "No summary yet—I need a couple of entries. Let's keep checking in.", "checkpoint": "CLOSING", "context": ctx}
        scores = [e.get("moodScore", 5) for e in history if isinstance(e, dict)]
        avg = round(sum(scores) / max(1, len(scores)), 1)
        trend = "up" if len(scores) >= 2 and scores[-1] > scores[0] else ("down" if len(scores) >= 2 and scores[-1] < scores[0] else "flat")
        reply = f"Past week avg mood ≈ {avg}/10, trend {trend}. Let’s keep building supportive habits."
        return {"reply": reply, "checkpoint": "CLOSING", "context": ctx}

    async def _handle_crisis(self, user_profile, user_query: str) -> Dict[str, Any]:
        """Crisis path: attempt LLM for richer, safety-forward response; fallback is safe script."""
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

        if locale == "us":
            help_line = "Call or text 988 (US) for immediate help"
        else:
            help_line = "Please contact your local emergency number"

        crisis_prompt = (
            "You are Asha, a compassionate crisis-support companion. The user has expressed suicidal intent. "
            "Respond with: 1) immediate validation and care, 2) clear safety guidance including local hotline message, "
            "3) a short grounding step the user can try now, 4) one gentle question to keep them engaged. "
            "Avoid clinical tone and medical advice. "
            f"User name: {name}.\n\nUser message: \"{user_query}\"\n\n"
            "Write 40-90 words."
        )

        reply: Optional[str] = None
        try:
            resp = await asyncio.wait_for(self.streaming_client.generate_content(crisis_prompt), timeout=8.0)
            reply = (resp.text if hasattr(resp, 'text') else str(resp)).strip()
        except Exception:
            reply = None

        if not reply or len(reply) < 20:
            reply = (
                f"I'm really glad you told me. If you're in danger or might hurt yourself, {help_line}. "
                "I'm here with you. Let's try a few slow breaths together. When you're ready, "
                "would you share what feels hardest right now?"
            )

        return {"reply": reply, "checkpoint": "CRISIS_ESCALATION"}

    # ------------------------------------------------------------------
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
        t0 = time.time()
        context = context or {}
        
        # Fast initialization check
        if not self._initialized:
            await self.initialize()
        
        # Parallel data fetching with caching for maximum speed
        data_fetch_start = time.time()
        profile, agent_data = await self.get_cached_data(user_profile_id, agent_instance_id)
        session_state = await self.get_session_state_fast(conversation_id, user_profile_id)
        data_fetch_time = time.time() - data_fetch_start

        # Enhanced mood, stress, and engagement analysis
        current_mood = self.mood_analyzer.quick_mood_analysis(user_query)
        stress_indicators = self._extract_stress_indicators(user_query)
        stress_level = self._calculate_stress_level(user_query, stress_indicators)
        session_state["current_mood"] = current_mood
        session_state["stress_indicators"] = stress_indicators
        session_state["stress_level"] = stress_level
        engagement = self.progress_tracker.calculate_engagement_score(user_query, "", 1)
        
        # Enhance context with current session information
        context["emotional_state"] = current_mood
        context["stress_indicators"] = stress_indicators
        context["stress_level"] = stress_level
        context["engagement_score"] = engagement
        
        # Get current checkpoint for context
        if not checkpoint:
            checkpoint = await self.data_manager.get_checkpoint(user_profile_id, agent_instance_id)
        session_state["current_checkpoint"] = checkpoint

        # risk check
        risk_level = RiskDetector.analyze(user_query)
        if risk_level >= 3:
            result = await self._handle_crisis(profile, user_query)
        else:
            # determine checkpoint
            if not checkpoint:
                checkpoint = await self.data_manager.get_checkpoint(user_profile_id, agent_instance_id)

            # route
            if checkpoint == "GREETING":
                result = await self._handle_greeting()
            elif checkpoint == "ASKED_MOOD_RATING":
                result = await self._handle_mood_rating(user_query)
            elif checkpoint == "ASK_FEELINGS":
                result = await self._handle_feelings(user_query, context)
            elif checkpoint == "OFFER_EXERCISE":
                # enrich ctx with ids
                context.update({"user_profile_id": user_profile_id, "agent_instance_id": agent_instance_id})
                result = await self._handle_exercise_offer(user_query, context, user_profile_id, conversation_id)
            elif checkpoint == "BREATHING_SESSION_RUNNING":
                result = await self._handle_breathing_session(context)
            elif checkpoint == "LOGGING_ENTRY":
                result = await self._handle_logging(user_query, context)
            elif checkpoint == "CHECKIN_SUMMARY":
                result = await self._handle_summary(user_profile_id, agent_instance_id, context)
            elif checkpoint == "CLOSING":
                result = {"reply": "Thank you for sharing today. I'm here whenever you want to check in again.", "checkpoint": "GREETING", "context": context}
            else:
                result = await self._handle_greeting()

        # Always try to enhance with LLM for more natural responses (except in crisis)
        if risk_level < 3 and hasattr(self, 'streaming_client') and self.streaming_client:
            llm_success = False
            max_retries = 2
            
            for attempt in range(max_retries):
                try:
                    # Convert UserProfile object to dictionary for build_prompt with enhanced context
                    profile_dict = profile.model_dump() if hasattr(profile, 'model_dump') else profile
                    prompt = await self.build_prompt(user_query, profile_dict, session_state, context)
                    logger.debug(f"Built prompt for LLM (attempt {attempt + 1}): {prompt[:100]}...")
                    
                    # Increase timeout for complex prompts and add retry logic
                    timeout = 12.0 if attempt == 0 else 15.0
                    resp = await asyncio.wait_for(self.streaming_client.generate_content(prompt), timeout=timeout)
                    
                    # Better response validation
                    if hasattr(resp, 'text'):
                        llm_reply = resp.text.strip() if resp.text else ""
                    else:
                        llm_reply = str(resp).strip() if resp else ""
                    
                    logger.debug(f"LLM response (attempt {attempt + 1}): {llm_reply[:100]}...")
                    
                    # More lenient validation for LLM responses
                    if llm_reply and len(llm_reply) > 5:  # Reduced from 10 to 5 characters
                        # Use LLM response but maintain checkpoint flow
                        result["reply"] = llm_reply
                        logger.info(f"✅ Using LLM-generated response (attempt {attempt + 1})")
                        llm_success = True
                        break
                    else:
                        logger.warning(f"LLM response too short on attempt {attempt + 1}: '{llm_reply}' (length: {len(llm_reply)})")
                        if attempt < max_retries - 1:
                            await asyncio.sleep(0.5)  # Brief delay before retry
                        
                except asyncio.TimeoutError:
                    logger.warning(f"LLM timeout on attempt {attempt + 1} (timeout: {timeout}s)")
                    if attempt < max_retries - 1:
                        await asyncio.sleep(1.0)  # Longer delay for timeout
                except Exception as e:
                    error_msg = str(e) if str(e) else f"{type(e).__name__}: {repr(e)}"
                    logger.warning(f"LLM generation failed on attempt {attempt + 1}: {error_msg}")
                    if attempt < max_retries - 1:
                        await asyncio.sleep(0.5)
            
            if not llm_success:
                logger.error(f"❌ All LLM attempts failed, using structured response. Streaming client status: {hasattr(self, 'streaming_client') and self.streaming_client is not None}")
        elif risk_level >= 3:
            logger.info("High risk level detected, using structured crisis response")
        else:
            logger.warning("❌ No streaming client available, using structured response")

        # persist checkpoint
        await self.data_manager.update_checkpoint(user_profile_id, agent_instance_id, str(result.get("checkpoint", "GREETING")))

        # update state memory
        reply_text = result.get("reply", "I'm here to listen. Tell me more.")
        session_state.setdefault("conversation_turns", []).extend([f"User: {user_query}", f"Assistant: {reply_text}"])
        session_state["conversation_turns"] = session_state["conversation_turns"][-6:]
        self.data_manager.update_session_state(conversation_id, user_profile_id, session_state)

        # Schedule all background tasks as fire-and-forget (non-blocking)
        asyncio.create_task(self._schedule_background_tasks_async(
            user_profile_id, agent_instance_id, user_query, reply_text, 
            current_mood, engagement, risk_level, stress_level, time.time() - t0
        ))
        
        return {
            "response": reply_text,
            "processing_time": time.time() - t0,
            "conversation_id": conversation_id,
            "checkpoint_status": str(result.get("checkpoint", "")),
            "requires_human": risk_level >= 3,
            "agent_specific_data": {
                "current_mood": current_mood,
                "engagement": engagement,
                "risk_level": risk_level,
                "user_profile_id": user_profile_id,
                "agent_instance_id": agent_instance_id,
                "performance": {
                    "data_fetch_time": data_fetch_time,
                    "cached_data": data_fetch_time < 0.1
                }
            },
        }

    async def _schedule_background_tasks_async(
        self, 
        user_profile_id: str,
        agent_instance_id: str,
        user_query: str, 
        agent_response: str, 
        current_mood: str,
        engagement_score: float,
        risk_level: int,
        stress_level: int,
        processing_time: float
    ):
        """Async background tasks that don't block the main response"""
        try:
            # Extract feelings from user query for mood logging
            feelings = await self._extract_feelings_from_text(user_query)

            # All tasks run concurrently in background
            tasks = [
                self.data_manager.add_check_in(user_profile_id, agent_instance_id, user_query),
                self.data_manager.add_mood_log(user_profile_id, agent_instance_id, feelings, user_query, max(risk_level, stress_level)),
                self.data_manager.update_progress(
                    user_profile_id, agent_instance_id, engagement_score, engagement_score,
                    f"Conversation completed in {processing_time:.2f}s, stress_level: {stress_level}"
                ),
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


# singleton -----------------------------------------------------------------
_therapy_agent = TherapyCompanionAgent()


async def process_message(
    text: str,
    conversation_id: str,
    checkpoint: Optional[str] = None,
    context: Optional[Dict[str, Any]] = None,
    individual_id: Optional[str] = None,
    user_profile_id: str = "",
    agent_instance_id: str = "",
    user_id: str = "",  # Keep for backward compatibility
):
    """
    Main entry point for therapy companion agent processing
    Updated to match the main API signature with individual_id parameter
    """
    
    # Initialize agent if not already done
    if not _therapy_agent._initialized:
        await _therapy_agent.initialize()
    
    return await _therapy_agent.process_message(
        text,
        conversation_id,
        user_profile_id,
        agent_instance_id,
        user_id,
        checkpoint,
        context,
    )


# Orchestrator-compat wrapper with loneliness-style signature ---------------
async def process_message_compatible(
    user_query: str,
    context: str,
    checkpoint: str,
    conversation_id: str,
    user_profile_id: str,
    agent_instance_id: str,
    user_id: str,
) -> Dict[str, Any]:
    """Compatibility wrapper for orchestrator that uses loneliness-style signature"""
    return await _therapy_agent.process_message(
        user_query,
        conversation_id,
        user_profile_id,
        agent_instance_id,
        user_id,
        checkpoint,
        {},
    )


async def stream_therapy_response(
    text: str,
    conversation_id: str,
    checkpoint: Optional[str] = None,
    context: Optional[Dict[str, Any]] = None,
    individual_id: Optional[str] = None,
    user_profile_id: str = "",
    agent_instance_id: str = "",
    user_id: str = "",
) -> AsyncGenerator[Dict[str, Any], None]:
    """Word-level streaming endpoint identical to loneliness agent signature."""
    # send start
    yield {"type": "start", "conversation_id": conversation_id, "timestamp": time.time()}

    # Initialize agent if needed
    if not _therapy_agent._initialized:
        await _therapy_agent.initialize()

    # Get user data for prompt building
    try:
        user_profile, agent_data = await _therapy_agent.get_cached_data(
            user_profile_id, agent_instance_id
        )
        session_state = await _therapy_agent.get_session_state_fast(
            conversation_id, user_profile_id
        )
    except Exception as e:
        logger.warning(f"Data fetch error: {e}, using defaults")
        # Use comprehensive defaults for better personalization
        user_profile = type('Profile', (), {
            'name': 'Friend', 'age': None, 'gender': None, 'location': None, 'language': 'en',
            'interests': ['general wellbeing'], 'hobbies': ['reading'], 'hates': [],
            'personality_traits': ['thoughtful'], 'loved_ones': [], 'past_stories': [],
            'preferences': {'communication_style': 'supportive'}, 'health_info': {},
            'emotional_baseline': 'neutral', 'locale': 'us'
        })()
        agent_data = type('Agent', (), {'therapy_goals': []})()
        session_state = {'current_mood': 'neutral', 'conversation_turns': []}

    # Build prompt with enhanced context
    # Convert UserProfile to dict if needed for build_prompt
    profile_dict = user_profile.model_dump() if hasattr(user_profile, 'model_dump') else user_profile
    prompt = await _therapy_agent.build_prompt(text, profile_dict, session_state, context)

    # REAL STREAMING: Stream directly from Gemini with error handling               
    streaming_client = _therapy_agent.streaming_client
    full_response = ""

    # Ensure streaming client is available
    if not streaming_client:
        logger.error("No streaming client available for streaming response")
        yield {"type": "error", "data": "Streaming service unavailable", "conversation_id": conversation_id}
        return

    try:
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
                
    except Exception as streaming_error:
        logger.error(f"Streaming error: {streaming_error}")
        # Send error chunk and fallback response
        yield {
            "type": "content", 
            "data": "I'm here to support you. How are you feeling today?", 
            "conversation_id": conversation_id
        }
        yield {"type": "done", "data": "I'm here to support you. How are you feeling today?", "conversation_id": conversation_id}
        full_response = "I'm here to support you. How are you feeling today?"

    # Send final completion
    yield {
        "type": "complete",
        "conversation_id": conversation_id,
        "response_length": len(full_response),
        "timestamp": time.time()
    }

    # Schedule background tasks (non-blocking)
    if full_response:
        asyncio.create_task(_therapy_agent._schedule_background_tasks_async(
            user_profile_id, agent_instance_id,
            text, full_response, "neutral", 5.0, 0, 3, 0.5
        ))