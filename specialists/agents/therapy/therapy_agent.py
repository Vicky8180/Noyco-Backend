"""
Therapy (Mental Health) Check-In Agent for Mental Health Support
Main agent implementation for mood tracking, relaxation tools, and weekly trend reporting
"""

import logging
import uuid
import asyncio
from typing import Dict, List, Optional, Any
from datetime import datetime, date, time, timedelta
import re
import os
import json

# Import shared memory clients with correct path
from memory.mongo_client import MongoMemory
from memory.redis_client import RedisMemory

# Import local modules
from .schema import (
    TherapyRequest, TherapyResponse, ToolCall,
    MoodEntry, WeeklySummary, ProgressEntry, UserProfile,
    RiskLevel, CheckpointState, SourceType
)
from .response_generator import TherapyResponseGenerator
from .llm_service import TherapyLLMService

# Import common models
from common.models import AgentResult

logger = logging.getLogger(__name__)

class TherapyCheckInAgent:
    """
    Therapy Check-In Agent for Mental Health Support
    
    Features:
    - Mood tracking with 1-10 scale and descriptive feelings
    - Short relaxation tools (breathing exercises)
    - Weekly trend reporting and insights
    - Crisis language detection and escalation
    - Personalized empathetic responses
    """
    
    def __init__(self):
        # Use shared memory connections
        self.mongo_memory = MongoMemory()
        self.redis_memory = RedisMemory()
        
        # Local services
        self.response_generator = TherapyResponseGenerator()
        self.llm_service = TherapyLLMService()
        # Default template for new agent instance documents
        self._default_instance_template = {
            # Core identifiers
            "agent_instance_id": None,  # to be filled dynamically
            "user_profile_id": None,
            "individual_id": None,

            # Progress / goals / tracking – can be expanded later
            "progress": {
                "sessions_completed": 0,
                "last_session_date": None,
            },
            "goals": [],
            "tracking": {
                "mood_ratings": [],
                "streaks": 0,
            },
            "help_notes": [],

            # Existing richer arrays used by older schema – keep for compatibility
            "daily_check_ins": [],
            "progress_tracking": [],
            "mood_trends": [],

            # Check-in flow
            "last_checkpoint": CheckpointState.GREETING,

            # Metadata
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
        }
        
        self.initialized = False
        
    async def initialize(self):
        """Initialize all connections and services"""
        try:
            # Initialize shared memory connections
            await self.mongo_memory.initialize()
            await self.redis_memory.check_connection()
            
            # Initialize local services
            await self.llm_service.initialize()
            
            self.initialized = True
            logger.info("✅ Therapy Check-In Agent initialized successfully")
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize Therapy Agent: {e}")
            raise
            
    async def process_message(self, request: TherapyRequest) -> AgentResult:
        """Main entry point for processing user messages"""
        try:
            if not self.initialized:
                await self.initialize()
                
            logger.info(f"🧠 Processing therapy request from user {request.user_profile_id}")
            
            # Fetch existing agent instance from MongoDB
            agent_instance = await self._get_agent_instance(request.agent_instance_id)

            # If it doesn't exist yet, create a skeleton so future updates have full structure
            if agent_instance is None:
                agent_instance = await self._ensure_agent_instance(request)
            else:
                # Back-fill any missing default fields from legacy documents
                await self._patch_instance_defaults(agent_instance, request)
            
            # Get current checkpoint
            if agent_instance:
                current_checkpoint = request.checkpoint or agent_instance.get("last_checkpoint", CheckpointState.GREETING)
            else:
                current_checkpoint = request.checkpoint or CheckpointState.GREETING
            
            # Check for crisis language
            risk_level, risk_reason = await self.llm_service.analyze_risk_level(request.text)
            
            if risk_level >= RiskLevel.MODERATE:
                # Override checkpoint for crisis handling
                current_checkpoint = CheckpointState.CRISIS_ESCALATION
                logger.warning(f"⚠️ Crisis language detected (level {risk_level}): {risk_reason}")
            
            # Process based on checkpoint
            response_data = await self._process_checkpoint(
                request, current_checkpoint, agent_instance, risk_level
            )
            
            # Update agent instance with new checkpoint if it exists
            # Ensure agent instance document exists & checkpoint stored (upsert)
            new_checkpoint = response_data.get("checkpoint", current_checkpoint)
            await self._update_checkpoint(request.agent_instance_id, new_checkpoint)
            
            # Log the conversation message (always use resolved checkpoint)
            logged_checkpoint = response_data.get("checkpoint", current_checkpoint)
            try:
                await self._log_conversation(request, logged_checkpoint, risk_level)
            except Exception as log_err:
                logger.warning(f"Failed to log therapy message: {log_err}")
            
            # Create agent result
            result = AgentResult(
                agent_name="therapy_checkin",
                status="success",
                result_payload=response_data,
                message_to_user=response_data.get("reply", "I'm here to support you."),
                action_required=False
            )
            
            logger.info(f"✅ Successfully processed therapy request")
            return result
            
        except Exception as e:
            logger.error(f"❌ Error processing therapy message: {e}")
            
            # Return error result
            return AgentResult(
                agent_name="therapy_checkin",
                status="error",
                result_payload={"error": str(e)},
                message_to_user="I'm having trouble right now, but I'm here to support you. Please try again.",
                action_required=False
            )
            
    async def _process_checkpoint(
        self, request: TherapyRequest, checkpoint: str, 
        agent_instance: Dict[str, Any], risk_level: int
    ) -> Dict[str, Any]:
        """Process the request based on current checkpoint"""
        
        # Get user profile (for personalization)
        user_profile = await self._get_user_profile(request.user_profile_id)
        
        # Handle crisis escalation first (highest priority)
        if risk_level >= RiskLevel.HIGH or checkpoint == CheckpointState.CRISIS_ESCALATION:
            return await self._handle_crisis(request, user_profile, risk_level)
            
        # Process based on checkpoint
        if checkpoint == CheckpointState.GREETING:
            return await self._handle_greeting(request)
            
        elif checkpoint == CheckpointState.ASKED_MOOD_RATING:
            return await self._handle_mood_rating(request)
            
        elif checkpoint == CheckpointState.ASK_FEELINGS:
            return await self._handle_feelings(request)
            
        elif checkpoint == CheckpointState.OFFER_EXERCISE:
            return await self._handle_exercise_offer(request)
            
        elif checkpoint == CheckpointState.BREATHING_SESSION_RUNNING:
            return await self._handle_breathing_session(request)
            
        elif checkpoint == CheckpointState.LOGGING_ENTRY:
            return await self._handle_logging(request, agent_instance, risk_level)
            
        elif checkpoint == CheckpointState.CHECKIN_SUMMARY:
            return await self._handle_summary(request, agent_instance)
            
        elif checkpoint == CheckpointState.CLOSING:
            return await self._handle_closing(request)
            
        else:
            # Default to greeting
            return await self._handle_greeting(request)
            
    async def _handle_greeting(self, request: TherapyRequest) -> Dict[str, Any]:
        """Handle initial greeting"""
        greeting = self.response_generator.generate_greeting()
        
        return {
            "reply": greeting,
            "checkpoint": CheckpointState.ASKED_MOOD_RATING,
            "tool_call": None
        }
        
    async def _handle_mood_rating(self, request: TherapyRequest) -> Dict[str, Any]:
        """Handle mood rating request"""
        # Try to extract mood rating from text
        mood_rating = self._extract_mood_rating(request.text)
        
        if mood_rating is None:
            # No rating found, ask again
            prompt = self.response_generator.generate_mood_rating_prompt()
            return {
                "reply": prompt,
                "checkpoint": CheckpointState.ASKED_MOOD_RATING,
                "tool_call": None
            }
            
        # Rating found, move to feelings
        response = self.response_generator.generate_mood_response(mood_rating, [])
        feelings_prompt = self.response_generator.generate_feeling_prompt()
        
        return {
            "reply": f"{response} {feelings_prompt}",
            "checkpoint": CheckpointState.ASK_FEELINGS,
            "context": {"mood_rating": mood_rating},
            "tool_call": None
        }
        
    async def _handle_feelings(self, request: TherapyRequest) -> Dict[str, Any]:
        """Handle feelings response"""
        # Extract feelings from text
        feelings = await self.llm_service.extract_feelings(request.text)
        
        # Get mood rating from context
        mood_rating = request.context.get("mood_rating", 5)
        
        # Generate response based on mood and feelings
        response = self.response_generator.generate_mood_response(mood_rating, feelings)
        
        # Offer breathing exercise
        breathing_offer = self.response_generator.generate_breathing_offer()
        
        return {
            "reply": f"{response} {breathing_offer}",
            "checkpoint": CheckpointState.OFFER_EXERCISE,
            "context": {"mood_rating": mood_rating, "feelings": feelings},
            "tool_call": None
        }
        
    async def _handle_exercise_offer(self, request: TherapyRequest) -> Dict[str, Any]:
        """Handle breathing exercise offer response"""
        # Check if user wants to do the exercise with more comprehensive patterns
        user_text = request.text.lower()
        
        # Positive response patterns
        positive_patterns = [
            r"yes", r"yeah", r"sure", r"ok", r"okay", r"let's", r"lets", 
            r"i'?d like", r"sounds good", r"i'?ll try", r"go ahead", 
            r"that sounds", r"i want", r"please", r"good idea", r"alright"
        ]
        
        # Negative response patterns
        negative_patterns = [
            r"no", r"nope", r"not", r"don'?t", r"skip", r"pass", r"later",
            r"not now", r"not interested", r"not today", r"maybe later"
        ]
        
        # Check for positive response
        wants_exercise = False
        for pattern in positive_patterns:
            if re.search(pattern, user_text):
                logger.info(f"✅ User wants breathing exercise: matched '{pattern}'")
                wants_exercise = True
                break
                
        # Check for negative response (overrides positive)
        for pattern in negative_patterns:
            if re.search(pattern, user_text):
                logger.info(f"ℹ️ User declined breathing exercise: matched '{pattern}'")
                wants_exercise = False
                break
                
        # If no clear indication, check for general sentiment
        if not any(re.search(p, user_text) for p in positive_patterns + negative_patterns):
            # Default to positive if text is short and doesn't contain negative indicators
            wants_exercise = len(user_text.split()) <= 5 and not any(neg in user_text for neg in ["no", "not", "don't", "skip", "pass"])
            logger.info(f"ℹ️ No clear exercise preference, defaulting to: {wants_exercise}")
        
        if wants_exercise:
            # Start breathing session
            duration_sec = 120  # 2 minutes default
            
            try:
                # Start session in Redis
                session_id = await self._start_breathing_session(
                    request.user_profile_id, 
                    request.conversation_id, 
                    duration_sec
                )
                
                # Create tool call
                tool_call = ToolCall(
                    name="startBreathingSession",
                    input={"durationSec": duration_sec}
                )
                
                # Generate start instruction
                instruction = self.response_generator.generate_breathing_instruction("start")
                
                logger.info(f"✅ Started breathing session: {session_id}")
                
                return {
                    "reply": instruction,
                    "checkpoint": CheckpointState.BREATHING_SESSION_RUNNING,
                    "context": {
                        **(request.context or {}),
                        "breathing_session_id": session_id,
                        "breathing_duration_sec": duration_sec,
                        "breathing_start_time": datetime.utcnow().isoformat()
                    },
                    "tool_call": tool_call
                }
            except Exception as e:
                logger.error(f"❌ Error starting breathing session: {e}")
                # Fall back to logging if breathing session fails
                return await self._handle_logging(request, None, 0)
        else:
            # Skip exercise, go to logging
            logger.info("ℹ️ User declined breathing exercise, proceeding to logging")
            return await self._handle_logging(request, None, 0)
            
    async def _handle_breathing_session(self, request: TherapyRequest) -> Dict[str, Any]:
        """Handle ongoing breathing session"""
        # Check if session is complete
        session_id = request.context.get("breathing_session_id", "")
        duration_sec = request.context.get("breathing_duration_sec", 120)
        start_time = request.context.get("breathing_start_time", "")
        
        if not start_time:
            # Missing data, end session
            return await self._handle_logging(request, None, 0)
            
        # Calculate elapsed time
        try:
            start_datetime = datetime.fromisoformat(start_time)
            elapsed_sec = (datetime.utcnow() - start_datetime).total_seconds()
        except (ValueError, TypeError):
            elapsed_sec = duration_sec + 1  # Force completion
            
        if elapsed_sec >= duration_sec:
            # Session complete
            if session_id:
                await self._complete_breathing_session(session_id)
                
            # Generate completion message
            completion = self.response_generator.generate_breathing_instruction("complete")
            
            # Move to logging
            return {
                "reply": f"{completion} How do you feel now?",
                "checkpoint": CheckpointState.LOGGING_ENTRY,
                "context": request.context,
                "tool_call": None
            }
        else:
            # Session ongoing, provide next instruction
            stage = "continue"
            if elapsed_sec < 20:
                stage = "inhale"
            elif elapsed_sec < 40:
                stage = "exhale"
                
            instruction = self.response_generator.generate_breathing_instruction(stage)
            
            return {
                "reply": instruction,
                "checkpoint": CheckpointState.BREATHING_SESSION_RUNNING,
                "context": request.context,
                "tool_call": None
            }
            
    async def _handle_logging(self, request: TherapyRequest, agent_instance: Optional[Dict[str, Any]], risk_level: int) -> Dict[str, Any]:
        """Handle mood logging"""
        # Get data from context
        mood_rating = request.context.get("mood_rating", 5)
        feelings = request.context.get("feelings", [])
        
        # If feelings is empty, try to extract from current message
        if not feelings:
            feelings = await self.llm_service.extract_feelings(request.text)
            
        # Create mood entry
        mood_entry = {
            "user_profile_id": request.user_profile_id,
            "conversation_id": request.conversation_id,
            "timestampISO": datetime.utcnow().isoformat(),
            "moodScore": mood_rating,
            "feelings": feelings,
            "stress_score": None,  # Could be added later
            "voiceStress": None,   # Could be added later
            "notes": request.text if len(request.text) < 200 else request.text[:197] + "...",
            "source": SourceType.CHAT,
            "riskLevel": risk_level
        }
        
        # Save mood entry to MongoDB
        await self._append_mood_entry(request.agent_instance_id, mood_entry)
        
        # Update tracking arrays with mood data
        await self._update_mood_tracking(request.agent_instance_id, mood_rating, feelings)
        
        # Create tool call
        tool_call = ToolCall(
            name="logMood",
            input=mood_entry
        )
        
        # Generate closing message
        closing = self.response_generator.generate_closing_message()
        
        return {
            "reply": closing,
            "checkpoint": CheckpointState.CLOSING,
            "context": request.context,
            "tool_call": tool_call
        }
        
    async def _handle_summary(self, request: TherapyRequest, agent_instance: Dict[str, Any]) -> Dict[str, Any]:
        """Handle weekly summary request"""
        # Get mood history
        mood_entries = await self._get_mood_history(request.user_profile_id, 7)
        
        if not mood_entries:
            return {
                "reply": "I don't have enough mood data yet to generate a summary. Let's do a check-in first!",
                "checkpoint": CheckpointState.GREETING,
                "tool_call": None
            }
            
        # Generate insights using LLM
        insights = await self.llm_service.generate_weekly_insights(mood_entries)
        
        # Create weekly summary
        summary = {
            "avgMood": insights.get("avgMood", 5.0),
            "trend": insights.get("trend", "flat"),
            "avgStress": insights.get("avgStress"),
            "streakDays": agent_instance.get("streak_days", 0),
            "notes": insights.get("notes", []),
            "week_start": (datetime.utcnow() - timedelta(days=7)).isoformat(),
            "week_end": datetime.utcnow().isoformat(),
            "created_at": datetime.utcnow().isoformat()
        }
        
        # Save weekly summary to MongoDB
        await self._append_weekly_summary(request.agent_instance_id, summary)
        
        # Generate response
        response = self.response_generator.generate_weekly_summary_response(summary)
        
        return {
            "reply": response,
            "checkpoint": CheckpointState.CLOSING,
            "context": request.context,
            "tool_call": None
        }
        
    async def _handle_closing(self, request: TherapyRequest) -> Dict[str, Any]:
        """Handle closing/goodbye"""
        closing = self.response_generator.generate_closing_message()
        
        return {
            "reply": closing,
            "checkpoint": CheckpointState.GREETING,  # Reset for next session
            "tool_call": None
        }
        
    async def _handle_crisis(self, request: TherapyRequest, user_profile: Optional[Dict[str, Any]], risk_level: int) -> Dict[str, Any]:
        """Handle crisis escalation"""
        # Even in crisis, we should log mood data for tracking
        mood_rating = request.context.get("mood_rating", 1)  # Default to low mood in crisis
        feelings = request.context.get("feelings", [])
        
        # Extract feelings if not provided
        if not feelings:
            feelings = await self.llm_service.extract_feelings(request.text)
        
        # Create crisis mood entry
        crisis_mood_entry = {
            "user_profile_id": request.user_profile_id,
            "conversation_id": request.conversation_id,
            "timestampISO": datetime.utcnow().isoformat(),
            "moodScore": mood_rating,
            "feelings": feelings,
            "stress_score": None,
            "voiceStress": None,
            "notes": f"CRISIS: {request.text}" if len(request.text) < 190 else f"CRISIS: {request.text[:190]}...",
            "source": SourceType.CHAT,
            "riskLevel": risk_level,
            "crisis_intervention": True
        }
        
        # Save crisis mood entry
        await self._append_mood_entry(request.agent_instance_id, crisis_mood_entry)
        
        # Update tracking arrays with crisis data
        await self._update_crisis_tracking(request.agent_instance_id, mood_rating, feelings)
        
        # Get user's locale for appropriate crisis resources
        locale = "us"  # Default
        if user_profile and "locale" in user_profile:
            locale = user_profile["locale"]
            
        # Generate crisis message with resources
        crisis_message = self.response_generator.generate_crisis_message(locale)
        
        # Create tool call for crisis escalation
        tool_call = ToolCall(
            name="escalateCrisis",
            input={
                "user_profile_id": request.user_profile_id,
                "risk_level": risk_level,
                "message": request.text,
                "locale": locale,
                "timestamp": datetime.utcnow().isoformat(),
                "mood_entry": crisis_mood_entry
            }
        )
        
        return {
            "reply": crisis_message,
            "checkpoint": CheckpointState.CRISIS_ESCALATION,
            "context": request.context,
            "tool_call": tool_call
        }
    
    # MongoDB operations using shared MongoMemory
    async def _get_agent_instance(self, agent_instance_id: str) -> Optional[Dict[str, Any]]:
        """Get agent instance from MongoDB"""
        try:
            collection = self.mongo_memory.db["therapy_agent_instance"]
            instance = collection.find_one({"agent_instance_id": agent_instance_id})
            if instance:
                # Remove MongoDB _id field
                instance.pop("_id", None)
            return instance
        except Exception as e:
            logger.error(f"❌ Error getting agent instance: {e}")
            return None
    
    async def _update_checkpoint(self, agent_instance_id: str, checkpoint: str) -> bool:
        """Update the current checkpoint for a user"""
        try:
            collection = self.mongo_memory.db["therapy_agent_instance"]
            result = collection.update_one(
                {"agent_instance_id": agent_instance_id},
                {
                    "$set": {
                        "last_checkpoint": checkpoint,
                        "updated_at": datetime.utcnow().isoformat()
                    }
                },
                upsert=True
            )
            
            if result.modified_count > 0 or result.upserted_id:
                logger.info(f"✅ Updated checkpoint to {checkpoint} for user {agent_instance_id}")
                return True
                
        except Exception as e:
            logger.error(f"❌ Error updating checkpoint: {e}")
            
        return False
    
    async def _append_mood_entry(self, agent_instance_id: str, mood_entry: Dict[str, Any]) -> bool:
        """Append mood entry to agent instance"""
        try:
            collection = self.mongo_memory.db["therapy_agent_instance"]
            result = collection.update_one(
                {"agent_instance_id": agent_instance_id},
                {
                    "$push": {"daily_check_ins": mood_entry},
                    "$inc": {"total_check_ins": 1},
                    "$set": {
                        "last_check_in": datetime.utcnow().isoformat(),
                        "updated_at": datetime.utcnow().isoformat()
                    }
                },
                upsert=True
            )
            
            if result.modified_count > 0 or result.upserted_id:
                logger.info(f"✅ Added mood entry for user {agent_instance_id}")
                return True
                
        except Exception as e:
            logger.error(f"❌ Error appending mood entry: {e}")
            
        return False
    
    async def _append_weekly_summary(self, agent_instance_id: str, summary: Dict[str, Any]) -> bool:
        """Append weekly summary to agent instance"""
        try:
            collection = self.mongo_memory.db["therapy_agent_instance"]
            result = collection.update_one(
                {"agent_instance_id": agent_instance_id},
                {
                    "$push": {"mood_trends": summary},
                    "$set": {"updated_at": datetime.utcnow().isoformat()}
                },
                upsert=True
            )
            
            if result.modified_count > 0 or result.upserted_id:
                logger.info(f"✅ Added weekly summary for user {agent_instance_id}")
                return True
                
        except Exception as e:
            logger.error(f"❌ Error appending weekly summary: {e}")
            
        return False

    async def _ensure_agent_instance(self, request: TherapyRequest) -> Dict[str, Any]:
        """Create a skeleton therapy_agent_instance document if it doesn't exist."""
        doc = dict(self._default_instance_template)
        doc["agent_instance_id"] = request.agent_instance_id
        doc["user_profile_id"] = request.user_profile_id
        doc["individual_id"] = request.individual_id

        try:
            collection = self.mongo_memory.db["therapy_agent_instance"]
            collection.update_one(
                {"agent_instance_id": request.agent_instance_id},
                {"$setOnInsert": doc},
                upsert=True,
            )
            # Return the fully-initialized instance
            doc.pop("_id", None)
            return doc
        except Exception as e:
            logger.error(f"❌ Failed to create therapy_agent_instance: {e}")
            return doc

    async def _patch_instance_defaults(self, existing_doc: Dict[str, Any], request: TherapyRequest):
        """Update legacy documents with any fields missing from the default template."""
        try:
            missing = {}
            for key, value in self._default_instance_template.items():
                if key not in existing_doc:
                    # keep identifiers accurate
                    if key in ["agent_instance_id", "user_profile_id", "individual_id"]:
                        missing[key] = getattr(request, key, value)
                    else:
                        missing[key] = value

            if missing:
                collection = self.mongo_memory.db["therapy_agent_instance"]
                collection.update_one(
                    {"agent_instance_id": request.agent_instance_id},
                    {"$set": missing}
                )
        except Exception as e:
            logger.warning(f"Could not patch missing instance fields: {e}")
    
    async def _update_crisis_tracking(self, agent_instance_id: str, mood_rating: int, feelings: List[str]) -> bool:
        """Update tracking arrays with crisis-related data"""
        try:
            collection = self.mongo_memory.db["therapy_agent_instance"]
            updates = {
                "$push": {
                    "tracking.mood_ratings": mood_rating,
                    "progress_tracking": {
                        "type": "crisis_intervention",
                        "timestamp": datetime.utcnow().isoformat(),
                        "mood_rating": mood_rating,
                        "feelings": feelings,
                        "intervention_provided": True
                    }
                },
                "$inc": {"progress.sessions_completed": 1},
                "$set": {
                    "progress.last_session_date": datetime.utcnow().isoformat(),
                    "updated_at": datetime.utcnow().isoformat()
                }
            }
            
            result = collection.update_one(
                {"agent_instance_id": agent_instance_id},
                updates,
                upsert=True
            )
            
            if result.modified_count > 0 or result.upserted_id:
                logger.info(f"✅ Updated crisis tracking for {agent_instance_id}")
                return True
                
        except Exception as e:
            logger.error(f"❌ Error updating crisis tracking: {e}")
            
        return False
    
    async def _update_mood_tracking(self, agent_instance_id: str, mood_rating: int, feelings: List[str]) -> bool:
        """Update tracking arrays with mood data for regular check-ins"""
        try:
            collection = self.mongo_memory.db["therapy_agent_instance"]
            
            tracking_entry = {
                "type": "mood_checkin",
                "timestamp": datetime.utcnow().isoformat(),
                "mood_rating": mood_rating,
                "feelings": feelings,
                "crisis_intervention": False
            }
            
            updates = {
                "$push": {
                    "tracking.mood_ratings": mood_rating,
                    "progress_tracking": tracking_entry
                },
                "$inc": {"progress.sessions_completed": 1},
                "$set": {
                    "progress.last_session_date": datetime.utcnow().isoformat(),
                    "updated_at": datetime.utcnow().isoformat()
                }
            }
            
            result = collection.update_one(
                {"agent_instance_id": agent_instance_id},
                updates,
                upsert=True
            )
            
            if result.modified_count > 0 or result.upserted_id:
                logger.info(f"✅ Updated mood tracking for {agent_instance_id}")
                return True
                
        except Exception as e:
            logger.error(f"❌ Error updating mood tracking: {e}")
            
        return False
    
    async def _get_mood_history(self, user_profile_id: str, days: int = 7) -> List[Dict[str, Any]]:
        """Get recent mood entries for a user"""
        try:
            collection = self.mongo_memory.db["therapy_agent_instance"]
            instance = collection.find_one({"user_profile_id": user_profile_id})
            
            if not instance or 'daily_check_ins' not in instance:
                return []
                
            # Filter entries by date
            cutoff_date = (datetime.utcnow() - timedelta(days=days)).isoformat()
            
            mood_entries = [
                entry for entry in instance['daily_check_ins']
                if entry.get('timestampISO', '') >= cutoff_date
            ]
            
            return mood_entries
            
        except Exception as e:
            logger.error(f"❌ Error getting mood history: {e}")
            return []
            
    # Redis operations using shared RedisMemory
    async def _start_breathing_session(self, user_profile_id: str, conversation_id: str, duration_sec: int) -> str:
        """Start a breathing session in Redis"""
        try:
            session_id = f"breathing:{user_profile_id}:{conversation_id}:{uuid.uuid4()}"
            session_data = {
                "user_profile_id": user_profile_id,
                "conversation_id": conversation_id,
                "duration_sec": duration_sec,
                "start_time": datetime.utcnow().isoformat(),
                "status": "active"
            }
            
            # Store session in Redis with TTL
            await self.redis_memory.redis.set(
                session_id, 
                json.dumps(session_data), 
                ex=duration_sec + 60  # Add 1 minute buffer
            )
            
            logger.info(f"✅ Started breathing session {session_id}")
            return session_id
            
        except Exception as e:
            logger.error(f"❌ Error starting breathing session: {e}")
            return str(uuid.uuid4())  # Fallback ID
    
    async def _complete_breathing_session(self, session_id: str) -> bool:
        """Complete a breathing session in Redis"""
        try:
            # Get session data
            session_data = await self.redis_memory.redis.get(session_id)
            if not session_data:
                return False
                
            # Update session status
            session_dict = json.loads(session_data)
            session_dict["status"] = "completed"
            session_dict["end_time"] = datetime.utcnow().isoformat()
            
            # Store updated session with shorter TTL
            await self.redis_memory.redis.set(
                session_id, 
                json.dumps(session_dict), 
                ex=300  # 5 minute TTL after completion
            )
            
            logger.info(f"✅ Completed breathing session {session_id}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error completing breathing session: {e}")
            return False
            
    async def _get_user_profile(self, user_profile_id: str) -> Optional[Dict[str, Any]]:
        """Get user profile from shared memory"""
        try:
            # Try to get from Redis first
            profile_key = f"user_profile:{user_profile_id}"
            profile_data = await self.redis_memory.redis.get(profile_key)
            
            if profile_data:
                return json.loads(profile_data)
                
            # Fallback to MongoDB
            collection = self.mongo_memory.db["user_profiles"]
            profile = collection.find_one({"user_id": user_profile_id})
            
            if profile:
                # Remove MongoDB _id field
                profile.pop("_id", None)
                
                # Cache in Redis
                await self.redis_memory.redis.set(
                    profile_key,
                    json.dumps(profile),
                    ex=3600  # 1 hour TTL
                )
                
                return profile
                
            return None
            
        except Exception as e:
            logger.error(f"❌ Error getting user profile: {e}")
            return None
            
    def _extract_mood_rating(self, text: str) -> Optional[int]:
        """Extract mood rating from user text"""
        # Try to find numeric ratings
        patterns = [
            r'(\d+)\s*\/\s*10',  # "7/10"
            r'(\d+)\s*out of\s*10',  # "7 out of 10"
            r'rate.*?(\d+)',  # "I rate it 7"
            r'feeling\s+(?:is\s+)?(?:about\s+)?(?:a\s+)?(\d+)',  # "feeling is about a 7"
            r'(?:i\'m|im|i am)\s+(?:feeling\s+)?(?:a\s+)?(\d+)',  # "I'm feeling a 7"
            r'(\d+)(?!\d)',  # Just a digit
        ]
        
        text_lower = text.lower()
        
        # First try to match patterns
        for pattern in patterns:
            match = re.search(pattern, text_lower)
            if match:
                try:
                    rating = int(match.group(1))
                    if 1 <= rating <= 10:
                        logger.info(f"✅ Extracted mood rating: {rating} using pattern: {pattern}")
                        return rating
                    elif rating > 10:
                        logger.info(f"✅ Capping mood rating: {rating} -> 10")
                        return 10  # Cap at 10
                except (ValueError, IndexError):
                    continue
        
        # Look for word-based ratings
        low_mood_words = ["terrible", "awful", "horrible", "depressed", "miserable", "hopeless", "suicidal"]
        medium_low_words = ["bad", "down", "sad", "upset", "unhappy", "stressed", "worried", "anxious"]
        neutral_words = ["ok", "okay", "alright", "fine", "average", "neutral", "so-so"]
        medium_high_words = ["good", "well", "positive", "happy", "pleased", "content", "relaxed"]
        high_mood_words = ["great", "excellent", "amazing", "fantastic", "wonderful", "awesome", "excited"]
        
        # Check for word-based ratings
        for word in low_mood_words:
            if word in text_lower:
                logger.info(f"✅ Extracted mood rating: 2 from word: {word}")
                return 2
                
        for word in medium_low_words:
            if word in text_lower:
                logger.info(f"✅ Extracted mood rating: 4 from word: {word}")
                return 4
                
        for word in neutral_words:
            if word in text_lower:
                logger.info(f"✅ Extracted mood rating: 5 from word: {word}")
                return 5
                
        for word in medium_high_words:
            if word in text_lower:
                logger.info(f"✅ Extracted mood rating: 7 from word: {word}")
                return 7
                
        for word in high_mood_words:
            if word in text_lower:
                logger.info(f"✅ Extracted mood rating: 9 from word: {word}")
                return 9
        
        # Fallback: Check for any number between 1-10 in the text
        numbers = re.findall(r'\b([1-9]|10)\b', text)
        if numbers:
            try:
                rating = int(numbers[0])
                if 1 <= rating <= 10:
                    logger.info(f"✅ Extracted mood rating (fallback): {rating}")
                    return rating
            except (ValueError, IndexError):
                pass
                
        # No rating found
        logger.warning("⚠️ Could not extract mood rating from text")
        return None

    async def _log_conversation(self, request: "TherapyRequest", checkpoint: str, risk_level: int):
        """Insert a conversation message into the therapy_agent collection"""
        collection = self.mongo_memory.db["therapy_agent"]
        log_doc = {
            "user_profile_id": request.user_profile_id,
            "agent_instance_id": request.agent_instance_id,
            "conversation_id": request.conversation_id,
            "text": request.text,
            "checkpoint": checkpoint,
            "context": request.context or {},
            "riskLevel": risk_level,
            "timestampISO": datetime.utcnow().isoformat()
        }
        collection.insert_one(log_doc)


# Singleton cache for agent instance
_cached_agent: Optional[TherapyCheckInAgent] = None


async def process_message(
    text: str,
    conversation_id: str,
    user_profile_id: str,
    agent_instance_id: str,
    checkpoint: Optional[str] = None,
    context: Optional[Dict[str, Any]] = None,
    individual_id: Optional[str] = None,
) -> AgentResult:
    """Main entry point for the therapy check-in agent (FastAPI wrapper).

    The function keeps a **module-level cached agent** so that heavy
    initialisation (Mongo/Redis connections) only happens once
    per process instead of for every single HTTP request.
    """

    global _cached_agent

    if _cached_agent is None:
        _cached_agent = TherapyCheckInAgent()

    agent = _cached_agent

    # Initialise once
    if not agent.initialized:
        await agent.initialize()

    # Build request object
    request_obj = TherapyRequest(
        text=text,
        conversation_id=conversation_id,
        checkpoint=checkpoint,
        context=context or {},
        individual_id=individual_id,
        user_profile_id=user_profile_id,
        agent_instance_id=agent_instance_id,
    )

    try:
        return await agent.process_message(request_obj)
    except Exception as e:
        logger.error(f"❌ Therapy agent processing failed: {e}")
        raise
