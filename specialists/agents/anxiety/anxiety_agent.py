"""
Light-weight Anxiety Support Agent
==================================
This implementation mirrors the architecture of the Therapy companion,
while keeping the *behaviour* focused on anxiety management and coping strategies.

It avoids any imports from other agent packages – all helpers live in the
local directory (`data_manager`, `background_tasks`, `gemini_streaming`).
"""
from __future__ import annotations

"""
Light-weight Anxiety Support Agent
==================================
This implementation mirrors the architecture of the Therapy companion,
while keeping the *behaviour* focused on anxiety management and coping strategies.

It avoids any imports from other agent packages – all helpers live in the
local directory (`data_manager`, `background_tasks`, `gemini_streaming`).
"""

import asyncio
import logging
import time
from datetime import datetime
from typing import Any, AsyncGenerator, Dict, List, Optional

try:
    from .data_manager import AnxietyDataManager
    from .background_tasks import BackgroundTaskManager, AnxietyAnalyzer, ProgressTracker
    from .gemini_streaming import get_streaming_client
    from .schema import CheckpointState  # optional enum, we use its values as strings
except ImportError:
    # Fallback for direct execution
    from data_manager import AnxietyDataManager
    from background_tasks import BackgroundTaskManager, AnxietyAnalyzer, ProgressTracker
    from gemini_streaming import get_streaming_client
    from schema import CheckpointState

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
            'anxiety_agents': type('Collection', (), {'find_one': lambda x: None, 'update_one': lambda *args, **kwargs: None})()
        })()

logger = logging.getLogger(__name__)

# Initialize data manager with MongoDB/Redis clients
data_manager = AnxietyDataManager(RedisMemory(), MongoMemory())


class PanicDetector:
    """Heuristic, zero-cost detector for panic and high anxiety."""

    PANIC = {
        "panic attack", "can't breathe", "heart racing", "chest tight", "dying", 
        "losing control", "going crazy", "hyperventilating", "dizzy", "nauseous",
        "panic", "heart pounding", "sweating", "shaking"
    }
    HIGH_ANXIETY = {
        "panic", "severe anxiety", "overwhelming", "can't cope", "too much",
        "racing thoughts", "can't stop thinking", "restless", "on edge", "terrified"
    }

    @staticmethod
    def analyze(text: str) -> int:
        t = text.lower()
        if any(p in t for p in PanicDetector.PANIC):
            return 4  # Panic level
        if any(p in t for p in PanicDetector.HIGH_ANXIETY):
            return 3  # High anxiety
        return 0


# ----------------------------------------------------------------------------
class AnxietyCompanionAgent:
    """Production-ready anxiety support agent with fast start and streaming."""

    def __init__(self):
        self.redis_client = RedisMemory()
        self.mongo_client = MongoMemory()
        self.gemini_client = None
        
        # Initialize modular components
        self.data_manager = AnxietyDataManager(self.redis_client, self.mongo_client)
        self.background_tasks = BackgroundTaskManager(max_workers=8)
        self.anxiety_analyzer = AnxietyAnalyzer()
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
                self.gemini_client = get_streaming_client()
                logger.info("Streaming Gemini client initialized")
            except Exception as streaming_error:
                logger.error(f"Streaming Gemini client failed: {streaming_error}")
                self.gemini_client = None
            
            self._initialized = True
            logger.info("Anxiety companion agent initialized successfully")
            
        except asyncio.TimeoutError:
            logger.warning("Database initialization timeout - continuing with fallback mode")
            self._initialized = True
        except Exception as e:
            logger.error(f"Failed to initialize anxiety companion agent: {e}")
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
        agent_task = asyncio.create_task(self.data_manager.get_anxiety_agent_data(user_profile_id, agent_instance_id))
        
        try:
            # Use timeout to prevent hanging
            user_profile, agent_data = await asyncio.wait_for(
                asyncio.gather(profile_task, agent_task),
                timeout=6.0  # 6 second timeout
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
                'hobbies': [],
                'locale': 'us'
            })()
            
            fallback_agent = type('AnxietyAgent', (), {
                'anxiety_goals': []
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
                    "current_anxiety": "neutral",
                    "engagement_level": 5.0,
                    "last_activity": datetime.utcnow(),
                    "recent_triggers": []
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
                "current_anxiety": "neutral", 
                "engagement_level": 5.0,
                "last_activity": datetime.utcnow(),
                "recent_triggers": []
            }

    # ------------------------------------------------------------------
    async def build_prompt(
        self,
        user_query: str,
        user_profile: Dict[str, Any],
        session_state: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Build comprehensive, personalized prompt for anxiety support using user profile data"""
        context = context or {}
        anxiety_level = session_state.get("current_anxiety", "neutral")
        
        # Handle both dictionary and Pydantic object formats
        if hasattr(user_profile, 'model_dump'):
            profile_dict = user_profile.model_dump()
        elif isinstance(user_profile, dict):
            profile_dict = user_profile
        else:
            # Convert object to dict
            profile_dict = {
                'name': getattr(user_profile, 'name', 'Friend'),
                'age': getattr(user_profile, 'age', None),
                'gender': getattr(user_profile, 'gender', None),
                'interests': getattr(user_profile, 'interests', []),
                'hobbies': getattr(user_profile, 'hobbies', []),
                'personality_traits': getattr(user_profile, 'personality_traits', []),
                'loved_ones': getattr(user_profile, 'loved_ones', []),
                'past_stories': getattr(user_profile, 'past_stories', []),
                'preferences': getattr(user_profile, 'preferences', {}),
                'health_info': getattr(user_profile, 'health_info', {}),
                'emotional_baseline': getattr(user_profile, 'emotional_baseline', None),
                'locale': getattr(user_profile, 'locale', 'us')
            }

        # Extract key profile information
        name = profile_dict.get("name", "Friend")
        age = profile_dict.get("age")
        gender = profile_dict.get("gender")
        interests = profile_dict.get("interests", [])
        hobbies = profile_dict.get("hobbies", [])
        personality_traits = profile_dict.get("personality_traits", [])
        loved_ones = profile_dict.get("loved_ones", [])
        past_stories = profile_dict.get("past_stories", [])
        preferences = profile_dict.get("preferences", {})
        health_info = profile_dict.get("health_info", {})
        emotional_baseline = profile_dict.get("emotional_baseline")
        locale = profile_dict.get("locale", "us")

        # Build personalized context strings
        age_context = f", {age} years old" if age else ""
        gender_context = f" ({gender})" if gender else ""
        
        interests_str = ", ".join(interests[:3]) if interests else "general wellbeing"
        hobbies_str = ", ".join(hobbies[:3]) if hobbies else "various activities"
        traits_str = ", ".join(personality_traits[:3]) if personality_traits else "thoughtful, caring"
        
        # Extract anxiety-specific information
        anxiety_triggers = health_info.get("anxiety_triggers", [])
        coping_mechanisms = health_info.get("coping_mechanisms", [])
        panic_history = health_info.get("panic_history", False)
        previous_therapy = health_info.get("previous_therapy", False)
        
        trigger_context = f"Known triggers: {', '.join(anxiety_triggers[:3])}" if anxiety_triggers else "Triggers: still identifying"
        coping_context = f"Preferred coping: {', '.join(coping_mechanisms[:2])}" if coping_mechanisms else "Exploring coping strategies"
        
        # Communication preferences
        communication_style = preferences.get("communication_style", "gentle")
        comfort_techniques = preferences.get("comfort_techniques", ["breathing", "grounding"])
        
        # Recent conversation context
        recent = " | ".join(session_state.get("conversation_turns", [])[-4:])
        recent_triggers = session_state.get("recent_triggers", [])
        stress_level = session_state.get("stress_level", 0)
        
        # Context from current session
        conversation_history = context.get("conversation_history", [])
        user_intent = context.get("user_intent", "")
        emotional_triggers = context.get("emotional_triggers", [])
        previous_anxiety_state = context.get("previous_anxiety_state", "")
        conversation_summary = context.get("conversation_summary", "")
        comfort_level = context.get("comfort_level", "moderate")
        emotional_intensity = context.get("emotional_intensity", "moderate")
        
        # Get current checkpoint for context-aware responses
        checkpoint = session_state.get("current_checkpoint", "GREETING")
        
        # Build industry-standard anxiety support prompt
        prompt = f"""YYou are Calm, a supportive and insightful mental wellness companion. Your expertise is in helping people understand and navigate their anxiety. You are trained in evidence-based therapeutic modalities like CBT and mindfulness, but your primary goal is to create a safe, non-judgmental space for conversation. Your tone is warm, curious, and patient.

## CORE CONVERSATIONAL FRAMEWORK:
• **Connect First, Solve Later**: Your first priority is to understand the user's experience. Validate their feelings, and then get curious. Never offer a coping technique or exercise until you have asked at least one or two follow-up questions about the specific source of their anxiety.
• **Gentle Exploration**: Use open-ended, gentle questions to help the user explore their thoughts and feelings. Questions like "Tell me more about that," "What's the story that thought is telling you?" or "Where do you feel that in your body?" are powerful.
• **Embrace the "Why"**: When a user mentions a trigger (e.g., "a work email"), don't just accept it as a fact. Gently explore the emotions and beliefs attached to it. The goal is to uncover the underlying fear or worry.
• **Collaborative Approach**: Frame coping techniques as a collaborative experiment, not a prescription. Use phrases like, "Would you be open to trying something together?" or "I have an idea that might help with that feeling, but first..."
• **Pacing is Key**: A real conversation has a natural rhythm. Don't rush to fix things. Sometimes, the most helpful thing you can do is simply listen and ask a thoughtful question that helps the user see their situation more clearly.

## CLINICAL SPECIALIZATION:
**Primary Focus**: Anxiety disorders, panic disorder, generalized anxiety, social anxiety, specific phobias
**Therapeutic Modalities**: CBT, ACT, DBT, EMDR-informed approaches, somatic interventions
**Evidence-Based Techniques**: Cognitive restructuring, exposure therapy, mindfulness, grounding, progressive muscle relaxation
**Professional Training**: Licensed clinical psychologist with specialized anxiety disorder certification

## CORE THERAPEUTIC FRAMEWORK:
• **Anxiety-Informed Care**: Understanding anxiety as adaptive response that can become maladaptive
• **Neurobiological Awareness**: Recognize fight/flight/freeze responses and autonomic nervous system activation
• **Cognitive-Behavioral Integration**: Address thought-emotion-behavior cycles maintaining anxiety
• **Somatic Awareness**: Incorporate body-based interventions for anxiety regulation
• **Trauma-Sensitive Practice**: Assume potential trauma history; prioritize safety and stabilization
• **Strengths-Based Resilience**: Identify existing coping resources and adaptive responses
• **Cultural Responsiveness**: Adapt interventions to cultural context and individual presentation

## CLINICAL ASSESSMENT DATA:
**Client Identification**: {name}{age_context}{gender_context}
**Personality Resources**: {traits_str}
**Values & Interests**: {interests_str}
**Adaptive Activities**: {hobbies_str}
**Communication Preferences**: {communication_style} approach
**Anxiety Presentation**: {trigger_context}
**Existing Coping Skills**: {coping_context}
**Panic History**: {"Documented panic episodes" if panic_history else "No reported panic history"}
**Treatment History**: {"Previous therapeutic experience" if previous_therapy else "No prior therapy"}
**Baseline Functioning**: {emotional_baseline or "Assessment ongoing"}
**Current Anxiety Severity**: {anxiety_level}
**Stress Level**: {stress_level}/10 (moderate-high threshold ≥6)
**Session Comfort**: {comfort_level}
**Emotional Activation**: {emotional_intensity}

## SESSION DYNAMICS:
**Treatment Phase**: {checkpoint}
**Identified Triggers**: {', '.join(recent_triggers[:3]) if recent_triggers else "Assessment in progress"}
**Client Motivation**: {user_intent or "Seeking anxiety management support"}
**Anxiety Trajectory**: {previous_anxiety_state or "Baseline assessment"}
**Session History**: {recent if recent else "Initial clinical contact"}
**Clinical Context**: {conversation_summary if conversation_summary else "New therapeutic relationship"}

## THERAPEUTIC INTERVENTION PROTOCOL:
**1. Safety Assessment**: Evaluate for panic, dissociation, or crisis presentation
**2. Anxiety Psychoeducation**: Normalize anxiety as biological response; explain anxiety cycle
**3. Cognitive Assessment**: Identify catastrophic thinking, cognitive distortions, worry patterns
**4. Somatic Intervention**: Implement grounding techniques, breathing regulation, progressive relaxation
**5. Behavioral Activation**: Encourage approach behaviors vs. avoidance patterns
**6. Mindfulness Integration**: Present-moment awareness to interrupt rumination/anticipatory anxiety
**7. Coping Skills Training**: Teach specific, evidence-based anxiety management techniques
**8. Relapse Prevention**: Build sustainable anxiety management strategies

## CLINICAL RESPONSE GUIDELINES:
• **Immediate Stabilization**: For acute anxiety/panic - prioritize grounding and physiological regulation
• **Psychoeducational Approach**: Explain anxiety mechanisms to reduce fear of anxiety itself
• **Collaborative Empiricism**: Examine anxious thoughts together using Socratic questioning
• **Behavioral Experiments**: Suggest gentle exposure or behavioral tests when appropriate  
• **Mindfulness-Based Interventions**: Guide present-moment awareness practices
• **Strengths Amplification**: Highlight existing coping successes and resilience factors
• **Cultural Integration**: Reference their interests ({interests_str}) and cultural context
• **Age-Appropriate Communication**: {"Developmentally sensitive language for emerging adult" if age and age < 25 else "Mature, respectful clinical communication" if age and age > 50 else "Adult peer-level therapeutic engagement"}
• **Hope Instillation**: Maintain recovery-oriented, optimistic therapeutic stance
• **Professional Boundaries**: Maintain therapeutic frame while providing warmth and support

## CRISIS INTERVENTION RESOURCES:
**Emergency Services**: {"US: 988 Suicide & Crisis Lifeline, Crisis Text Line: HOME to 741741, Emergency: 911" if locale == "us" else "Local emergency services and crisis intervention resources"}
**Panic Protocol**: If severe panic - immediate grounding (5-4-3-2-1 technique), controlled breathing, safety reassurance

## CLIENT COMMUNICATION:
"{user_query}"

## CLINICAL DIRECTIVE:
Provide evidence-based, therapeutically sound anxiety intervention. Demonstrate clinical competence while maintaining therapeutic warmth. Integrate appropriate therapeutic techniques based on client presentation. Responses should be 60-150 words, professionally grounded, and immediately helpful for anxiety management. End with therapeutic questions that promote insight and skill development.

## YOUR DIRECTIVE:
Your primary goal is to make the user feel heard and understood. Engage with the *content* of their worries. Help them unpack the "tiny things" by asking gentle, insightful follow-up questions. Only after you have explored the user's specific trigger for a couple of turns should you collaboratively suggest a relevant coping technique. Your responses should be natural, empathetic, and aim to deepen the conversation.
"""
        
        return prompt

    # =========================
    # Checkpoint flow handlers
    # =========================
    async def _handle_greeting(self) -> Dict[str, Any]:
        reply = (
            "Hi, I'm Calm. I'm here to help you with anxiety. How are you feeling right now on a scale of 1-10, with 10 being very anxious?"
        )
        return {"reply": reply, "checkpoint": "ASKED_ANXIETY_RATING"}

    async def _extract_anxiety_rating(self, text: str) -> Optional[int]:
        import re
        m = re.search(r"\b([1-9]|10)\b", text)
        if m:
            val = int(m.group(1))
            return max(1, min(10, val))
        # heuristic words
        t = text.lower()
        if any(w in t for w in ["panic", "terrible", "awful", "can't cope", "overwhelming"]):
            return 9
        if any(w in t for w in ["very anxious", "stressed", "worried", "scared", "nervous"]):
            return 7
        if any(w in t for w in ["somewhat anxious", "uneasy", "concerned", "tense"]):
            return 5
        if any(w in t for w in ["okay", "fine", "calm", "relaxed", "good"]):
            return 3
        if any(w in t for w in ["great", "peaceful", "content", "wonderful"]):
            return 1
        return None

    async def _extract_triggers_from_text(self, text: str) -> List[str]:
        """Extract anxiety triggers from text."""
        return self.anxiety_analyzer.extract_triggers(text)
    
    def _extract_stress_indicators(self, user_query: str) -> List[str]:
        """Extract stress indicators from user query using keyword matching"""
        stress_indicators = []
        text = user_query.lower()
        
        # Physical stress indicators
        physical_stress = {
            'headache': ['headache', 'head hurts', 'head pain'],
            'muscle tension': ['tense', 'tight muscles', 'stiff', 'sore'],
            'fatigue': ['tired', 'exhausted', 'drained', 'worn out'],
            'sleep issues': ['can\'t sleep', 'insomnia', 'restless', 'no sleep'],
            'digestive': ['stomach', 'nausea', 'appetite', 'eating'],
            'heart racing': ['heart racing', 'palpitations', 'heart pounding']
        }
        
        # Emotional stress indicators  
        emotional_stress = {
            'overwhelmed': ['overwhelmed', 'too much', 'can\'t handle'],
            'irritable': ['angry', 'frustrated', 'annoyed', 'irritated'],
            'anxious': ['anxious', 'worried', 'nervous', 'scared'],
            'sad': ['sad', 'depressed', 'down', 'low'],
            'panic': ['panic', 'panic attack', 'losing control']
        }
        
        # Behavioral stress indicators
        behavioral_stress = {
            'avoidance': ['avoiding', 'don\'t want to', 'can\'t face'],
            'isolation': ['alone', 'isolated', 'withdrawn', 'hiding'],
            'concentration': ['can\'t focus', 'distracted', 'forgetful'],
            'substance use': ['drinking', 'smoking', 'medication']
        }
        
        all_indicators = {**physical_stress, **emotional_stress, **behavioral_stress}
        
        for indicator, keywords in all_indicators.items():
            if any(keyword in text for keyword in keywords):
                stress_indicators.append(indicator)
        
        return stress_indicators
    
    def _calculate_stress_level(self, user_query: str, stress_indicators: List[str]) -> int:
        """Calculate stress level from 1-10 based on query and indicators"""
        text = user_query.lower()
        base_stress = 3  # Default mild stress level
        
        # High-stress phrases get immediate high rating
        crisis_phrases = ['can\'t cope', 'breaking point', 'give up', 'end it all', 'can\'t go on']
        if any(phrase in text for phrase in crisis_phrases):
            return 10
            
        severe_phrases = ['panic attack', 'losing control', 'can\'t breathe', 'heart racing', 'going crazy']
        if any(phrase in text for phrase in severe_phrases):
            return 9
            
        high_phrases = ['overwhelming', 'too much', 'can\'t handle', 'breaking down', 'falling apart']
        if any(phrase in text for phrase in high_phrases):
            return 8
            
        moderate_phrases = ['stressed', 'anxious', 'worried', 'nervous', 'tense']
        if any(phrase in text for phrase in moderate_phrases):
            base_stress = 6
            
        # Adjust based on number of stress indicators
        indicator_bonus = min(len(stress_indicators), 4)  # Cap at 4 extra points
        
        # Check for intensity modifiers
        intensity_modifiers = {
            'very': 2, 'extremely': 3, 'really': 1, 'so': 1, 'totally': 2,
            'completely': 3, 'absolutely': 2, 'incredibly': 2
        }
        
        intensity_bonus = 0
        for modifier, bonus in intensity_modifiers.items():
            if modifier in text:
                intensity_bonus = max(intensity_bonus, bonus)
        
        final_stress = base_stress + indicator_bonus + intensity_bonus
        return min(max(final_stress, 1), 10)  # Ensure 1-10 range

    async def _handle_anxiety_rating(self, user_text: str) -> Dict[str, Any]:
        rating = await self._extract_anxiety_rating(user_text)
        if rating is None:
            return {
                "reply": "On a scale from 1 (very calm) to 10 (very anxious), where would you place yourself right now?",
                "checkpoint": "ASKED_ANXIETY_RATING",
                "context": {},
            }
        # acknowledge and ask triggers
        if rating >= 8:
            base = "That sounds really intense and overwhelming."
        elif rating >= 6:
            base = "That sounds quite challenging."
        elif rating >= 4:
            base = "I hear that you're feeling some anxiety."
        else:
            base = "I'm glad you're feeling relatively calm today."
        
        reply = base + " What's been triggering these feelings? What's on your mind?"
        return {
            "reply": reply,
            "checkpoint": "ASK_TRIGGERS",
            "context": {"anxiety_rating": rating},
        }

    async def _handle_triggers(self, user_text: str, ctx: Dict[str, Any]) -> Dict[str, Any]:
        triggers = await self._extract_triggers_from_text(user_text)
        rating = ctx.get("anxiety_rating", 5)
        
        if rating >= 7:
            reply = "I understand those triggers can be really intense. Would you like to try a quick grounding technique to help calm your nervous system?"
        else:
            reply = "Thank you for sharing that with me. Would you like to try a brief breathing exercise, or would you prefer a different coping technique?"
        
        return {
            "reply": reply,
            "checkpoint": "OFFER_COPING_TECHNIQUE",
            "context": {"anxiety_rating": rating, "triggers": triggers},
        }

    async def _handle_coping_offer(self, user_text: str, ctx: Dict[str, Any], user_profile_id: str, conversation_id: str) -> Dict[str, Any]:
        t = user_text.lower()
        wants = any(p in t for p in ["yes", "sure", "ok", "okay", "let's", "start", "please", "help"]) and not any(n in t for n in ["no", "not", "skip", "later"])
        
        if not wants:
            return await self._handle_logging(user_text, ctx)
        
        # Determine technique based on anxiety level
        rating = ctx.get("anxiety_rating", 5)
        if rating >= 8:
            technique = "box_breathing"
            instruction = (
                "Let's do box breathing together. Breathe in for 4 counts, hold for 4, out for 4, hold for 4. "
                "I'll guide you through this. Focus only on counting with me."
            )
            duration = 180  # 3 minutes for high anxiety
        elif rating >= 6:
            technique = "grounding_5_4_3_2_1"
            instruction = (
                "Let's try the 5-4-3-2-1 grounding technique. Name 5 things you can see, 4 you can touch, "
                "3 you can hear, 2 you can smell, and 1 you can taste. Take your time."
            )
            duration = 120
        else:
            technique = "deep_breathing"
            instruction = (
                "Let's do some calming breaths. Breathe in slowly through your nose for 4 counts, "
                "then out through your mouth for 6 counts. Let's do this together."
            )
            duration = 90
        
        # start session
        session_id = await self.data_manager.start_coping_session(user_profile_id, conversation_id, technique, duration)
        
        return {
            "reply": instruction,
            "checkpoint": "BREATHING_SESSION_RUNNING" if "breathing" in technique else "GROUNDING_EXERCISE",
            "context": {**ctx, "coping_session_id": session_id, "coping_technique": technique, "session_duration": duration, "session_start_time": datetime.utcnow().isoformat()},
        }

    async def _handle_coping_session(self, ctx: Dict[str, Any]) -> Dict[str, Any]:
        start = ctx.get("session_start_time")
        technique = ctx.get("coping_technique", "breathing")
        if not start:
            return {"reply": "How are you feeling now? Any shift in your anxiety level?", "checkpoint": "LOGGING_ENTRY", "context": ctx}
        
        # Complete the session
        sid = ctx.get("coping_session_id", "")
        if sid:
            await self.data_manager.complete_coping_session(sid)
        
        if "grounding" in technique:
            reply = "Nice work with the grounding technique. How do you feel now? Did that help you feel more present?"
        else:
            reply = "Great job with the breathing. How are you feeling now? Notice any changes in your body or mind?"
        
        return {"reply": reply, "checkpoint": "LOGGING_ENTRY", "context": ctx}

    async def _handle_logging(self, user_text: str, ctx: Dict[str, Any]) -> Dict[str, Any]:
        rating = int(ctx.get("anxiety_rating", 5))
        triggers = ctx.get("triggers", [])
        anxiety_level = self.anxiety_analyzer.quick_anxiety_analysis(user_text)
        
        await self.data_manager.add_anxiety_log(
            ctx.get("user_profile_id", ""), 
            ctx.get("agent_instance_id", ""), 
            rating, 
            anxiety_level,
            triggers, 
            user_text,
            ctx.get("stress_level", 0),
            ctx.get("panic_level", 0)
        )
        
        reply = "Thank you for sharing with me. Remember, you're doing great by reaching out. Would you like a brief summary of your anxiety patterns this week?"
        return {"reply": reply, "checkpoint": "ANXIETY_SUMMARY", "context": ctx}

    async def _handle_summary(self, user_profile_id: str, agent_instance_id: str, ctx: Dict[str, Any]) -> Dict[str, Any]:
        history = await self.data_manager.get_anxiety_history(user_profile_id, agent_instance_id, days=7)
        if not history:
            return {"reply": "I don't have enough data for a summary yet. Let's keep tracking your anxiety together.", "checkpoint": "CLOSING", "context": ctx}
        
        scores = [e.get("anxietyScore", 5) for e in history if isinstance(e, dict)]
        avg = round(sum(scores) / max(1, len(scores)), 1)
        
        # Get most common triggers
        all_triggers = []
        for entry in history:
            all_triggers.extend(entry.get("triggers", []))
        
        trigger_counts = {}
        for trigger in all_triggers:
            trigger_counts[trigger] = trigger_counts.get(trigger, 0) + 1
        
        common_triggers = sorted(trigger_counts.keys(), key=lambda x: trigger_counts[x], reverse=True)[:2]
        trigger_str = ", ".join(common_triggers) if common_triggers else "none identified"
        
        reply = f"This week your average anxiety was {avg}/10. Common triggers: {trigger_str}. You're building awareness - that's a huge step."
        return {"reply": reply, "checkpoint": "CLOSING", "context": ctx}

    async def _handle_panic(self, user_profile, user_query: str) -> Dict[str, Any]:
        """Panic/crisis path: immediate grounding and safety response."""
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
            help_line = "If you're in immediate danger, call 911. For crisis support, text HOME to 741741"
        else:
            help_line = "Please contact your local emergency services if you're in immediate danger"

        panic_prompt = (
            "You are Calm, a compassionate anxiety support companion. The user is having a panic attack or severe anxiety. "
            "Respond with: 1) immediate validation and reassurance, 2) simple grounding instruction they can do right now, "
            "3) remind them this will pass, 4) offer to stay with them through this. "
            "Keep it simple and calming. Avoid overwhelming them with too many instructions. "
            f"User name: {name}.\n\nUser message: \"{user_query}\"\n\n"
            "Write 40-90 words in a very calm, soothing tone."
        )

        reply: Optional[str] = None
        try:
            resp = await asyncio.wait_for(self.streaming_client.generate_content(panic_prompt), timeout=8.0)
            reply = (resp.text if hasattr(resp, 'text') else str(resp)).strip()
        except Exception:
            reply = None

        if not reply or len(reply) < 20:
            reply = (
                f"I'm right here with you, {name}. You're having a panic attack, but you are safe. "
                "This feeling will pass. Let's breathe together - in for 4, hold for 4, out for 6. "
                "Focus only on my voice and your breath. You're going to be okay."
            )

        return {"reply": reply, "checkpoint": "PANIC_ESCALATION"}

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

        # Extract stress indicators and calculate stress level
        stress_indicators = self._extract_stress_indicators(user_query)
        stress_level = self._calculate_stress_level(user_query, stress_indicators)
        
        # quick anxiety & metrics
        current_anxiety = self.anxiety_analyzer.quick_anxiety_analysis(user_query)
        session_state["current_anxiety"] = current_anxiety
        session_state["stress_indicators"] = stress_indicators
        session_state["stress_level"] = stress_level
        engagement = self.progress_tracker.calculate_engagement_score(user_query, "", 1)
        
        # Extract and store recent triggers
        triggers = self.anxiety_analyzer.extract_triggers(user_query)
        if triggers:
            session_state.setdefault("recent_triggers", []).extend(triggers)
            # Keep only recent unique triggers (last 5)
            session_state["recent_triggers"] = list(dict.fromkeys(session_state["recent_triggers"]))[-5:]
        
        # Enhanced context from session and user input
        enhanced_context = {
            **context,
            "conversation_history": session_state.get("conversation_turns", []),
            "user_intent": context.get("user_intent", "seeking_anxiety_support"),
            "emotional_triggers": triggers,
            "previous_anxiety_state": session_state.get("previous_anxiety", "unknown"),
            "conversation_summary": context.get("conversation_summary", ""),
            "comfort_level": context.get("comfort_level", "moderate"),
            "emotional_intensity": context.get("emotional_intensity", "moderate"),
            "stress_indicators": stress_indicators,
            "stress_level": stress_level
        }
        
        # Get current checkpoint for context
        if not checkpoint:
            checkpoint = await self.data_manager.get_checkpoint(user_profile_id, agent_instance_id)
        session_state["current_checkpoint"] = checkpoint

        # panic/high anxiety check
        panic_level = PanicDetector.analyze(user_query)
        if panic_level >= 4:
            result = await self._handle_panic(profile, user_query)
        else:
            # determine checkpoint
            if not checkpoint:
                checkpoint = await self.data_manager.get_checkpoint(user_profile_id, agent_instance_id)

            # route
            if checkpoint == "GREETING":
                result = await self._handle_greeting()
            elif checkpoint == "ASKED_ANXIETY_RATING":
                result = await self._handle_anxiety_rating(user_query)
            elif checkpoint == "ASK_TRIGGERS":
                result = await self._handle_triggers(user_query, context)
            elif checkpoint == "OFFER_COPING_TECHNIQUE":
                # enrich ctx with ids
                context.update({"user_profile_id": user_profile_id, "agent_instance_id": agent_instance_id})
                result = await self._handle_coping_offer(user_query, context, user_profile_id, conversation_id)
            elif checkpoint == "BREATHING_SESSION_RUNNING" or checkpoint == "GROUNDING_EXERCISE":
                result = await self._handle_coping_session(context)
            elif checkpoint == "LOGGING_ENTRY":
                result = await self._handle_logging(user_query, context)
            elif checkpoint == "ANXIETY_SUMMARY":
                result = await self._handle_summary(user_profile_id, agent_instance_id, context)
            elif checkpoint == "CLOSING":
                result = {"reply": "Thank you for sharing with me today. I'm here whenever you need support with anxiety.", "checkpoint": "GREETING", "context": context}
            else:
                result = await self._handle_greeting()

        # Always try to enhance with LLM for more natural responses (except in panic)
        if panic_level < 4:
            try:
                # Convert UserProfile object to dictionary for build_prompt
                profile_dict = profile.model_dump() if hasattr(profile, 'model_dump') else profile
                prompt = await self.build_prompt(user_query, profile_dict, session_state, enhanced_context)
                logger.debug(f"Built prompt for LLM: {prompt[:100]}...")
                
                resp = await asyncio.wait_for(self.streaming_client.generate_content(prompt), timeout=8.0)
                llm_reply = resp.text.strip() if hasattr(resp, 'text') else str(resp).strip()
                
                logger.debug(f"LLM response: {llm_reply[:100]}...")
                
                # For natural conversation flow: use LLM response as primary, fallback to structured
                if llm_reply and len(llm_reply) > 10:
                    # Use LLM response but maintain checkpoint flow
                    result["reply"] = llm_reply
                    logger.debug("Using LLM-generated response")
                else:
                    logger.debug("LLM response too short, using structured response")
                    
            except Exception as e:
                logger.warning(f"LLM generation failed: {e}, using structured response")

        # persist checkpoint
        await self.data_manager.update_checkpoint(user_profile_id, agent_instance_id, str(result.get("checkpoint", "GREETING")))

        # update state memory
        reply_text = result.get("reply", "I'm here to help you with your anxiety. Tell me more.")
        session_state.setdefault("conversation_turns", []).extend([f"User: {user_query}", f"Assistant: {reply_text}"])
        session_state["conversation_turns"] = session_state["conversation_turns"][-6:]
        self.data_manager.update_session_state(conversation_id, user_profile_id, session_state)

        # Schedule all background tasks as fire-and-forget (non-blocking)
        asyncio.create_task(self._schedule_background_tasks_async(
            user_profile_id, agent_instance_id, user_query, reply_text, 
            current_anxiety, engagement, panic_level, stress_level, time.time() - t0
        ))
        
        return {
            "response": reply_text,
            "processing_time": time.time() - t0,
            "conversation_id": conversation_id,
            "checkpoint_status": str(result.get("checkpoint", "")),
            "requires_human": panic_level >= 4,
            "agent_specific_data": {
                "current_anxiety": current_anxiety,
                "engagement": engagement,
                "panic_level": panic_level,
                "triggers": triggers,
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
        current_anxiety: str,
        engagement_score: float,
        panic_level: int,
        stress_level: int,
        processing_time: float
    ):
        """Async background tasks that don't block the main response"""
        try:
            # Derive ratings/triggers to avoid empty logs
            rating = await self._extract_anxiety_rating(user_query)
            if rating is None:
                rating = 5
            triggers = await self._extract_triggers_from_text(user_query)
            anxiety_score = self.progress_tracker.calculate_anxiety_score(current_anxiety)

            # All tasks run concurrently in background
            tasks = [
                self.data_manager.add_check_in(user_profile_id, agent_instance_id, user_query),
                self.data_manager.add_anxiety_log(user_profile_id, agent_instance_id, rating, current_anxiety, triggers, user_query, stress_level, panic_level),
                self.data_manager.update_progress(
                    user_profile_id, agent_instance_id, anxiety_score, engagement_score,
                    f"Conversation completed in {processing_time:.2f}s"
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
_anxiety_agent = AnxietyCompanionAgent()


async def process_message(
    user_query: str,
    conversation_id: str,
    checkpoint: Optional[str] = None,
    context: Optional[Dict[str, Any]] = None,
    individual_id: Optional[str] = None,
    user_profile_id: str = "",
    agent_instance_id: str = "",
    user_id: str = "",  # Keep for backward compatibility
):
    """
    Main entry point for anxiety companion agent processing
    Updated to match the main API signature with individual_id parameter
    """
    
    # Initialize agent if not already done
    if not _anxiety_agent._initialized:
        await _anxiety_agent.initialize()
    
    return await _anxiety_agent.process_message(
        user_query,
        conversation_id,
        user_profile_id,
        agent_instance_id,
        user_id,
        checkpoint,
        context,
    )


# Orchestrator-compat wrapper with therapy-style signature ---------------
async def process_message_compatible(
    user_query: str,
    context: str,
    checkpoint: str,
    conversation_id: str,
    user_profile_id: str,
    agent_instance_id: str,
    user_id: str,
) -> Dict[str, Any]:
    """Compatibility wrapper for orchestrator that uses therapy-style signature"""
    return await _anxiety_agent.process_message(
        user_query,
        conversation_id,
        user_profile_id,
        agent_instance_id,
        user_id,
        checkpoint,
        {},
    )


async def stream_anxiety_response(
    text: str,
    conversation_id: str,
    checkpoint: Optional[str] = None,
    context: Optional[Dict[str, Any]] = None,
    individual_id: Optional[str] = None,
    user_profile_id: str = "",
    agent_instance_id: str = "",
    user_id: str = "",
) -> AsyncGenerator[Dict[str, Any], None]:
    """Word-level streaming endpoint identical to therapy agent signature."""
    # send start
    yield {"type": "start", "conversation_id": conversation_id, "timestamp": time.time()}

    # Initialize agent if needed
    if not _anxiety_agent._initialized:
        await _anxiety_agent.initialize()

    # Get user data for prompt building
    try:
        user_profile, agent_data = await _anxiety_agent.get_cached_data(
            user_profile_id, agent_instance_id
        )
        session_state = await _anxiety_agent.get_session_state_fast(
            conversation_id, user_profile_id
        )
    except Exception as e:
        logger.warning(f"Data fetch error: {e}, using defaults")
        # Use minimal defaults
        user_profile = type('Profile', (), {'name': 'Friend', 'interests': [], 'locale': 'us'})()
        agent_data = type('Agent', (), {'anxiety_goals': []})()
        session_state = {'current_anxiety': 'neutral', 'conversation_turns': [], 'recent_triggers': []}

    # Build prompt
    # Convert UserProfile to dict if needed for build_prompt
    profile_dict = user_profile.model_dump() if hasattr(user_profile, 'model_dump') else user_profile
    prompt = await _anxiety_agent.build_prompt(text, profile_dict, session_state)

    # REAL STREAMING: Stream directly from Gemini
    streaming_client = _anxiety_agent.streaming_client
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
        asyncio.create_task(_anxiety_agent._schedule_background_tasks_async(
            user_profile_id, agent_instance_id,
            text, full_response, "neutral", 5.0, 0, 0, 0.5
        ))
