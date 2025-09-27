"""
Professional Voice Assistant Pipeline
Advanced voice processing with VAD-like behavior for smooth conversations
"""

from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import Optional, Dict, Any
import asyncio
import logging
import json
import time
import aiohttp
from datetime import datetime, timedelta
from .config import get_livekit_settings

logger = logging.getLogger(__name__)

# Get configuration from settings
settings = get_livekit_settings()

# Simple JWT token creation (replace with proper implementation)
def create_jwt_token(payload: Dict[str, Any]) -> str:
    """Simple token creation - replace with proper JWT implementation"""
    import base64
    import json
    token_data = json.dumps(payload)
    return base64.b64encode(token_data.encode()).decode()

async def clear_intent_detection_state(user_profile_id: str, individual_id: str) -> bool:
    """
    Clear intent detection state from the initial call handler
    This ensures fresh intent detection when voice sessions are reset
    """
    try:
        # Import the direct internal cleanup function
        from ..initial_call_handler.routes import clear_user_intent_state_internal
        
        cleared_any = False
        
        # Clear using user_profile_id
        if user_profile_id:
            if clear_user_intent_state_internal(user_profile_id):
                logger.info(f"✅ Cleared intent state for user_profile_id {user_profile_id}")
                cleared_any = True
        
        # Also clear using individual_id if different
        if individual_id and individual_id != user_profile_id:
            if clear_user_intent_state_internal(individual_id):
                logger.info(f"✅ Cleared intent state for individual_id {individual_id}")
                cleared_any = True
        
        # Clear common fallback user IDs (this is now handled inside the internal function)
        return cleared_any
                    
    except Exception as e:
        logger.error(f"Error clearing intent detection state: {e}")
        return False

async def send_to_orchestrator(payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Send request to orchestrator"""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(settings.ORCHESTRATOR_ENDPOINT, json=payload) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    logger.error(f"Orchestrator error: {response.status}")
                    return None
    except Exception as e:
        logger.error(f"Failed to send to orchestrator: {e}")
        return None

async def send_to_intent_detector(message: str, conversation_history: list, user_id: str = None) -> Optional[Dict[str, Any]]:
    """Send request to intent detection endpoint with proper user identification"""
    try:
        logger.info(f"🔍 DEBUG: send_to_intent_detector received user_id = {user_id}")
        
        # Ensure we have a valid user_id - use the original or a timestamped fallback
        effective_user_id = user_id if user_id and user_id != "default_user" else f"user_{int(time.time())}"
        
        payload = {
            "message": message,
            "conversation_history": conversation_history,
            "user_id": effective_user_id  # Use the effective user ID
        }
        
        logger.info(f"🔍 DEBUG: payload user_id = {payload['user_id']}")
        logger.info(f"Sending to intent detector with user_id: {payload['user_id']}")
        logger.info(f"Sending to intent detector with {len(conversation_history)} context messages")
        
        async with aiohttp.ClientSession() as session:
            async with session.post(f"http://localhost:{settings.SERVICE_PORT}/initial/chat", json=payload) as response:
                if response.status == 200:
                    result = await response.json()
                    logger.info(f"Intent detector response: {result}")
                    return result
                else:
                    logger.error(f"Intent detector error: {response.status}")
                    return None
    except Exception as e:
        logger.error(f"Failed to send to intent detector: {e}")
        return None

async def create_goal_based_on_intent(detected_intent: str, user_profile_id: str, conversation_context: list) -> Optional[str]:
    """Create a goal based on detected intent and conversation context"""
    try:
        logger.info(f"🎯 Creating goal for intent: {detected_intent}")
        logger.info(f"🔍 DEBUG: Goal creation user_profile_id = {user_profile_id}")
        
        # Extract meaningful context from conversation
        conversation_text = ""
        for exchange in conversation_context[-3:]:  # Last 3 exchanges for context
            conversation_text += f"User: {exchange.get('user', '')}\nAssistant: {exchange.get('assistant', '')}\n"
        
        # Map detected intent to goal creation
        intent_to_endpoint = {
            "loneliness": "loneliness",
            "emotional_support": "emotional", 
            "emotional_companion": "emotional",
            "accountability": "accountability",
            "social_anxiety": "anxiety",
            "anxiety": "anxiety", 
            "therapy": "therapy",
            "therapy_checkin": "therapy"
        }
        
        endpoint_type = intent_to_endpoint.get(detected_intent.lower())
        if not endpoint_type:
            logger.warning(f"No goal endpoint mapping found for intent: {detected_intent}")
            return None
            
        # Generate goal data based on intent and conversation context
        goal_data = await generate_goal_data(detected_intent, conversation_context)
        
        if not goal_data:
            logger.error(f"Failed to generate goal data for intent: {detected_intent}")
            return None
        
        # Create goal via API
        async with aiohttp.ClientSession() as session:
            url = f"http://localhost:{settings.SERVICE_PORT}/user-profile/goals/{endpoint_type}/{user_profile_id}"
            
            async with session.put(url, json=goal_data) as response:
                if response.status in [200, 201]:
                    result = await response.json()
                    goal_id = result.get("goal_id") or result.get("id")
                    logger.info(f"Successfully created {detected_intent} goal: {goal_id}")
                    return goal_id
                else:
                    error_text = await response.text()
                    logger.error(f"Failed to create goal. Status: {response.status}, Error: {error_text}")
                    return None
                    
    except Exception as e:
        logger.error(f"Error creating goal for intent {detected_intent}: {e}")
        return None

async def generate_goal_data(detected_intent: str, conversation_context: list) -> Optional[Dict[str, Any]]:
    """Generate appropriate goal data based on intent and conversation context"""
    try:
        # Extract key themes and concerns from conversation
        user_messages = [exchange.get('user', '') for exchange in conversation_context if exchange.get('user')]
        conversation_text = " ".join(user_messages[-3:])  # Last 3 user messages
        
        current_time = datetime.utcnow()
        
        if detected_intent.lower() in ["loneliness", "loneliness_support"]:
            return {
                "title": "Overcoming Loneliness Together",
                "description": f"A personalized goal to address feelings of loneliness based on our conversation. Key areas identified: {conversation_text[:200]}...",
                "due_date": (current_time + timedelta(days=30)).isoformat(),
                "status": "active"
            }
            
        elif detected_intent.lower() in ["emotional_support", "emotional_companion"]:
            return {
                "title": "Emotional Wellness Journey", 
                "description": f"Supporting your emotional well-being through regular check-ins and coping strategies. Focus areas: {conversation_text[:200]}...",
                "due_date": (current_time + timedelta(days=21)).isoformat(),
                "status": "active",
                "memory_stack": [conversation_text[:500]] if conversation_text else [],
                "comfort_tips": ["Take deep breaths when feeling overwhelmed", "Practice daily gratitude", "Reach out when you need support"]
            }
            
        elif detected_intent.lower() in ["accountability", "accountability_buddy"]:
            return {
                "title": "Personal Accountability Goals",
                "description": f"Staying accountable to your commitments and goals. Areas discussed: {conversation_text[:200]}...",
                "due_date": (current_time + timedelta(days=14)).isoformat(), 
                "status": "active"
            }
            
        elif detected_intent.lower() in ["social_anxiety", "anxiety"]:
            return {
                "title": "Managing Social Anxiety",
                "description": f"Building confidence in social situations. Concerns identified: {conversation_text[:200]}...",
                "due_date": (current_time + timedelta(days=28)).isoformat(),
                "status": "active",
                "anxiety_level": 5,  # Default medium anxiety level
                "nervous_thoughts": [],
                "physical_symptoms": []
            }
            
        elif detected_intent.lower() in ["therapy", "therapy_checkin"]:
            return {
                "title": "Therapy Support Goals",
                "description": f"Complementing your therapy journey with regular check-ins. Discussion points: {conversation_text[:200]}...",
                "due_date": (current_time + timedelta(days=35)).isoformat(),
                "status": "active"
            }
        
        else:
            # Default goal structure
            return {
                "title": f"Personal Growth - {detected_intent.title()}",
                "description": f"A personalized goal based on our conversation about {detected_intent}. Context: {conversation_text[:200]}...",
                "due_date": (current_time + timedelta(days=21)).isoformat(),
                "status": "active"
            }
            
    except Exception as e:
        logger.error(f"Error generating goal data: {e}")
        return None

router = APIRouter()

class VoiceSessionRequest(BaseModel):
    conversation_id: str
    individual_id: str
    user_profile_id: str
    detected_agent: str
    agent_instance_id: str
    call_log_id: str
    participant_name: str
    voice_settings: Optional[Dict[str, Any]] = None
    force_fresh_start: Optional[bool] = False  # Flag to force complete fresh start
    session_reset_timestamp: Optional[int] = None  # Timestamp for session reset tracking

class VoiceMessageRequest(BaseModel):
    session_id: str
    text: str
    conversation_id: str
    individual_id: str
    user_profile_id: str
    audio_metadata: Optional[Dict[str, Any]] = None

class VoiceInterruptionRequest(BaseModel):
    session_id: str
    reason: str = "user_interruption"

# In-memory session storage (use Redis in production)
active_voice_sessions = {}

@router.post("/voice-sessions")
async def create_voice_session(request: VoiceSessionRequest):
    """
    Create a professional voice session with enhanced capabilities
    Ensures completely fresh context for intent detection
    """
    try:
        logger.info(f"=== Creating NEW VOICE SESSION ===")
        logger.info(f"Force fresh start: {request.force_fresh_start}")
        logger.info(f"Conversation ID: {request.conversation_id}")
        logger.info(f"User Profile ID: {request.user_profile_id}")
        logger.info(f"Individual ID: {request.individual_id}")
        logger.info(f"Session reset timestamp: {request.session_reset_timestamp}")
        
        # Generate unique session ID with extra randomness to prevent collisions
        import random
        session_id = f"voice_session_{int(time.time())}_{random.randint(1000, 9999)}_{request.participant_name}"
        
        # Ensure session ID is truly unique
        counter = 0
        base_session_id = session_id
        while session_id in active_voice_sessions and counter < 100:
            counter += 1
            session_id = f"{base_session_id}_{counter}"
        
        if session_id in active_voice_sessions:
            logger.error(f"Could not generate unique session ID after {counter} attempts")
            raise HTTPException(status_code=500, detail="Could not generate unique session ID")
        
        # ENHANCED: More aggressive cleanup if force_fresh_start is True
        if request.force_fresh_start:
            logger.info("FORCE FRESH START requested - performing aggressive cleanup")
            
            # Remove ALL sessions for this user/profile combination
            sessions_to_remove = []
            for existing_session_id, existing_session_data in active_voice_sessions.items():
                if (existing_session_data.get("user_profile_id") == request.user_profile_id or
                    existing_session_data.get("individual_id") == request.individual_id or
                    existing_session_data.get("conversation_id") == request.conversation_id):
                    sessions_to_remove.append(existing_session_id)
                    logger.info(f"Aggressive cleanup: removing session {existing_session_id}")
            
            for old_session_id in sessions_to_remove:
                del active_voice_sessions[old_session_id]
                logger.info(f"Deleted old session: {old_session_id}")
                
            logger.info(f"Aggressive cleanup completed: removed {len(sessions_to_remove)} old sessions")
            
            # CRITICAL: Clear intent detection state for fresh start
            logger.info(f"Force fresh start: clearing intent detection state for user {request.user_profile_id}")
            intent_cleared = await clear_intent_detection_state(request.user_profile_id, request.individual_id)
            if intent_cleared:
                logger.info(f"✅ Intent detection state cleared for fresh start: {request.user_profile_id}")
            else:
                logger.warning(f"⚠️ Failed to clear intent detection state for fresh start: {request.user_profile_id}")
        
        else:
            # Standard cleanup: Remove any old sessions with same conversation_id
            sessions_to_remove = []
            for existing_session_id, existing_session_data in active_voice_sessions.items():
                if existing_session_data.get("conversation_id") == request.conversation_id:
                    sessions_to_remove.append(existing_session_id)
                    logger.warning(f"Standard cleanup: removing session with same conversation_id: {existing_session_id}")
            
            for old_session_id in sessions_to_remove:
                del active_voice_sessions[old_session_id]
            
            logger.info(f"Standard cleanup: removed {len(sessions_to_remove)} old sessions")
        
        # Create JWT token for this session
        token_payload = {
            "session_id": session_id,
            "conversation_id": request.conversation_id,
            "individual_id": request.individual_id,
            "user_profile_id": request.user_profile_id,
            "participant_name": request.participant_name,
            "session_type": "professional_voice",
            "created_at": datetime.utcnow().isoformat(),
            "force_fresh_start": request.force_fresh_start,
            "session_reset_timestamp": request.session_reset_timestamp
        }
        
        token = create_jwt_token(token_payload)
        
        # LiveKit configuration for professional voice
        livekit_config = {
            "url": str(settings.LIVEKIT_HOST),
            "room_name": f"voice_room_{session_id}",
            "participant_name": request.participant_name
        }
        
        # Session data with COMPLETELY FRESH state
        session_data = {
            "session_id": session_id,
            "conversation_id": request.conversation_id,
            "individual_id": request.individual_id,
            "user_profile_id": request.user_profile_id,
            "detected_agent": request.detected_agent,
            "agent_instance_id": request.agent_instance_id,
            "call_log_id": request.call_log_id,
            "participant_name": request.participant_name,
            "token": token,
            "url": livekit_config["url"],
            "room_name": livekit_config["room_name"],
            "created_at": datetime.utcnow().isoformat(),
            "status": "active",
            "force_fresh_start": request.force_fresh_start,
            "session_reset_timestamp": request.session_reset_timestamp,
            "voice_settings": request.voice_settings or {
                "vad_enabled": True,
                "echo_cancellation": True,
                "noise_suppression": True,
                "auto_gain_control": True,
                "sample_rate": 16000,
                "interruption_enabled": True
            },
            "conversation_state": {
                "turn_count": 0,
                "last_user_message": None,
                "last_assistant_response": None,
                "context_history": [],  # Explicitly empty for fresh start
                "intent_detected": False,  # COMPLETELY FRESH intent detection
                "detected_intent": None,
                "intent_confidence": 0.0,
                "selected_agent": None,
                "selected_agent_name": None,
                "should_route": False,
                "session_started_fresh": True,  # Flag to indicate fresh start
                "force_fresh_start": request.force_fresh_start,  # Track if this was forced fresh
                "session_creation_timestamp": datetime.utcnow().isoformat(),
                "created_at": datetime.utcnow().isoformat()
            }
        }
        
        # Store session
        active_voice_sessions[session_id] = session_data
        
        logger.info(f"=== CREATED COMPLETELY FRESH VOICE SESSION: {session_id} ===")
        logger.info(f"Force fresh start applied: {request.force_fresh_start}")
        logger.info(f"Intent detection state: COMPLETELY RESET")
        
        return {
            "status": "success",
            "session_id": session_id,
            "conversation_id": request.conversation_id,
            "individual_id": request.individual_id,
            "user_profile_id": request.user_profile_id,
            "participant_name": request.participant_name,
            "token": token,
            "url": livekit_config["url"],
            "room_name": livekit_config["room_name"],
            "voice_settings": session_data["voice_settings"],
            "force_fresh_start": request.force_fresh_start,
            "message": "Professional voice session created with FRESH intent detection"
        }
        
    except Exception as e:
        logger.error(f"Error creating voice session: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create voice session: {str(e)}")

@router.post("/voice-message")
async def process_voice_message(request: VoiceMessageRequest):
    """
    Process voice message with intelligent intent detection pipeline
    Enhanced with context management and conversation flow
    """
    try:
        logger.info(f"=== Processing voice message for session: {request.session_id} ===")
        logger.info(f"🔍 DEBUG: Received user_profile_id = {request.user_profile_id}")
        logger.info(f"🔍 DEBUG: Received individual_id = {request.individual_id}")
        logger.info(f"🔍 DEBUG: Received conversation_id = {request.conversation_id}")
        
        # Get session data
        session_data = active_voice_sessions.get(request.session_id)
        
        if not session_data:
            logger.error(f"Voice session not found: {request.session_id}")
            logger.info(f"Available sessions: {list(active_voice_sessions.keys())}")
            raise HTTPException(status_code=404, detail="Voice session not found")
        
        logger.info(f"Session found. Intent detected: {session_data['conversation_state']['intent_detected']}")
        logger.info(f"Session created fresh: {session_data['conversation_state'].get('session_started_fresh', 'unknown')}")
        logger.info(f"Force fresh start: {session_data['conversation_state'].get('force_fresh_start', False)}")
        logger.info(f"Session creation timestamp: {session_data.get('created_at', 'unknown')}")
        logger.info(f"Context history length: {len(session_data['conversation_state']['context_history'])}")
        
        # Update conversation state
        session_data["conversation_state"]["turn_count"] += 1
        session_data["conversation_state"]["last_user_message"] = request.text
        
        # Check if intent is already detected for this session
        if session_data["conversation_state"]["intent_detected"]:
            logger.info(f"Intent already detected for session {request.session_id}: {session_data['conversation_state']['detected_intent']}")
            logger.info(f"Selected agent: {session_data['conversation_state']['selected_agent']}")
            logger.info(f"Routing directly to orchestrator")
            
            # Intent already detected, send directly to orchestrator
            orchestrator_payload = {
                "text": request.text,
                "conversation_id": request.conversation_id,
                "plan": "lite",
                "services": [],
                "individual_id": request.individual_id,
                "user_profile_id": request.user_profile_id,
                "detected_agent": session_data["conversation_state"]["selected_agent"] or session_data.get("detected_agent", "loneliness"),
                "agent_instance_id": session_data.get("agent_instance_id", "loneliness_658"),
                "call_log_id": session_data.get("call_log_id", f"voice_call_{request.session_id}"),
                "channel": "livekit"
            }
            
            orchestrator_response = await send_to_orchestrator(orchestrator_payload)
            
            if orchestrator_response and "response" in orchestrator_response:
                assistant_response = orchestrator_response["response"]
                
                # Update conversation state
                session_data["conversation_state"]["last_assistant_response"] = assistant_response
                session_data["conversation_state"]["context_history"].append({
                    "user": request.text,
                    "assistant": assistant_response,
                    "timestamp": datetime.utcnow().isoformat(),
                    "turn": session_data["conversation_state"]["turn_count"]
                })
                
                # Keep only last 10 exchanges for context
                if len(session_data["conversation_state"]["context_history"]) > 10:
                    session_data["conversation_state"]["context_history"] = session_data["conversation_state"]["context_history"][-10:]
                
                active_voice_sessions[request.session_id] = session_data
                
                return {
                    "status": "success",
                    "session_id": request.session_id,
                    "user_message": request.text,
                    "assistant_response": assistant_response,
                    "turn_count": session_data["conversation_state"]["turn_count"],
                    "processing_time": orchestrator_response.get("processing_time", 0),
                    "intent_status": "previously_detected",
                    "detected_intent": session_data["conversation_state"]["detected_intent"],
                    "selected_agent": session_data["conversation_state"]["selected_agent"],
                    "metadata": {
                        "conversation_id": request.conversation_id,
                        "session_type": "professional_voice",
                        "voice_optimized": True
                    }
                }
            else:
                logger.error(f"Invalid orchestrator response for session {request.session_id}")
                return {
                    "status": "error",
                    "error": "Invalid response from orchestrator",
                    "session_id": request.session_id
                }
        
        else:
            # Intent not detected yet, send to intent detection first
            logger.info(f"=== FRESH INTENT DETECTION for session {request.session_id} ===")
            logger.info(f"This is a {'FORCE FRESH' if session_data['conversation_state'].get('force_fresh_start', False) else 'STANDARD FRESH'} session")
            logger.info(f"Current context_history length: {len(session_data['conversation_state']['context_history'])}")
            logger.info(f"User message for intent detection: {request.text}")
            
            # Build conversation history for intent detection
            conversation_history = []
            
            # Add session context marker for fresh sessions to help intent detector reset
            if len(session_data["conversation_state"]["context_history"]) == 0:
                conversation_history.append({
                    "role": "system", 
                    "content": f"NEW_SESSION_START:{session_data['conversation_state']['created_at']}"
                })
            
            for exchange in session_data["conversation_state"]["context_history"]:
                conversation_history.append({"role": "user", "content": exchange["user"]})
                conversation_history.append({"role": "assistant", "content": exchange["assistant"]})
            
            logger.info(f"Sending to intent detector with {len(conversation_history)} context messages")
            
            # Add debugging for user ID
            logger.info(f"🔍 DEBUG: request.user_profile_id = {request.user_profile_id}")
            logger.info(f"🔍 DEBUG: About to send user_id = {request.user_profile_id}")
            
            # Send to intent detector with proper user identification
            intent_response = await send_to_intent_detector(
                request.text, 
                conversation_history, 
                request.user_profile_id  # Pass the actual user profile ID
            )
            
            if intent_response:
                # Check if intent was detected
                detected_intent = intent_response.get("detected_intent")
                should_route = intent_response.get("should_route", False)
                
                if detected_intent and detected_intent.lower() != "none" and should_route:
                    # Intent detected! Update session data
                    session_data["conversation_state"]["intent_detected"] = True
                    session_data["conversation_state"]["detected_intent"] = detected_intent
                    session_data["conversation_state"]["intent_confidence"] = intent_response.get("confidence", 0.0)
                    session_data["conversation_state"]["selected_agent"] = intent_response.get("selected_agent")
                    session_data["conversation_state"]["selected_agent_name"] = intent_response.get("selected_agent_name")
                    session_data["conversation_state"]["should_route"] = should_route
                    
                    logger.info(f"Intent detected for session {request.session_id}: {detected_intent} with confidence {intent_response.get('confidence', 0.0)}")
                    
                    # Create goal based on detected intent and conversation context
                    created_goal_id = await create_goal_based_on_intent(
                        detected_intent, 
                        request.user_profile_id, 
                        session_data["conversation_state"]["context_history"]
                    )
                    
                    # Update session with goal information
                    if created_goal_id:
                        session_data["goal_id"] = created_goal_id
                        session_data["agent_instance_id"] = created_goal_id  # Use goal_id as instance_id
                        logger.info(f"Created goal {created_goal_id} for session {request.session_id}")
                    else:
                        # Fallback to default instance_id if goal creation fails
                        logger.warning(f"Failed to create goal for session {request.session_id}, using default instance_id")
                        session_data["agent_instance_id"] = f"{detected_intent.lower()}_{int(time.time())}"
                    
                    # Now send to orchestrator with detected intent and dynamic instance_id
                    orchestrator_payload = {
                        "text": request.text,
                        "conversation_id": request.conversation_id,
                        "plan": "lite",
                        "services": [],
                        "individual_id": request.individual_id,
                        "user_profile_id": request.user_profile_id,
                        "detected_agent": intent_response.get("selected_agent", "loneliness"),
                        "agent_instance_id": session_data.get("agent_instance_id", "loneliness_658"),
                        "call_log_id": session_data.get("call_log_id", f"voice_call_{request.session_id}"),
                        "channel": "voice_assistant"
                    }
                    
                    # Generate connecting message based on detected agent
                    agent_name_map = {
                        "loneliness": "loneliness support specialist",
                        "emotional_companion": "emotional wellness specialist", 
                        "accountability": "accountability specialist",
                        "social_anxiety": "social confidence specialist",
                        "anxiety": "anxiety support specialist", 
                        "therapy": "therapy support specialist"
                    }
                    
                    selected_agent = intent_response.get("selected_agent", "loneliness")
                    specialist_name = agent_name_map.get(selected_agent.lower(), "specialist")
                    connecting_message = f"Please wait, we are connecting you with our {specialist_name}."
                    
                    # First, return the connecting message immediately
                    session_data["conversation_state"]["last_assistant_response"] = connecting_message
                    session_data["conversation_state"]["context_history"].append({
                        "user": request.text,
                        "assistant": connecting_message,
                        "timestamp": datetime.utcnow().isoformat(),
                        "turn": session_data["conversation_state"]["turn_count"],
                        "type": "connecting_message"
                    })
                    
                    active_voice_sessions[request.session_id] = session_data
                    
                    # Return the connecting message immediately, then orchestrator will handle the actual response
                    return {
                        "status": "success",
                        "session_id": request.session_id,
                        "user_message": request.text,
                        "assistant_response": connecting_message,
                        "turn_count": session_data["conversation_state"]["turn_count"],
                        "intent_status": "detected_connecting",
                        "detected_intent": detected_intent,
                        "confidence": intent_response.get("confidence", 0.0),
                        "selected_agent": intent_response.get("selected_agent"),
                        "selected_agent_name": intent_response.get("selected_agent_name"),
                        "should_route": should_route,
                        "is_connecting": True,
                        "orchestrator_payload": orchestrator_payload,  # Include payload for frontend to make follow-up call
                        "metadata": {
                            "conversation_id": request.conversation_id,
                            "session_type": "professional_voice",
                            "voice_optimized": True,
                            "intent_detection_used": True,
                            "specialist_type": specialist_name
                        }
                    }
                else:
                    # Intent not detected yet, use response from intent detector
                    assistant_response = intent_response.get("response", "I'm here to listen and understand how I can best help you. Could you tell me more?")
                    logger.info(f"Intent not yet detected for session {request.session_id}, continuing conversation")
                
                # Update conversation state
                session_data["conversation_state"]["last_assistant_response"] = assistant_response
                session_data["conversation_state"]["context_history"].append({
                    "user": request.text,
                    "assistant": assistant_response,
                    "timestamp": datetime.utcnow().isoformat(),
                    "turn": session_data["conversation_state"]["turn_count"]
                })
                
                # Keep only last 10 exchanges for context
                if len(session_data["conversation_state"]["context_history"]) > 10:
                    session_data["conversation_state"]["context_history"] = session_data["conversation_state"]["context_history"][-10:]
                
                active_voice_sessions[request.session_id] = session_data
                
                return {
                    "status": "success",
                    "session_id": request.session_id,
                    "user_message": request.text,
                    "assistant_response": assistant_response,
                    "turn_count": session_data["conversation_state"]["turn_count"],
                    "intent_status": "detected" if (detected_intent and detected_intent.lower() != "none" and should_route) else "not_detected",
                    "detected_intent": detected_intent,
                    "confidence": intent_response.get("confidence", 0.0),
                    "selected_agent": intent_response.get("selected_agent"),
                    "selected_agent_name": intent_response.get("selected_agent_name"),
                    "should_route": should_route,
                    "conversation_turn": intent_response.get("conversation_turn", session_data["conversation_state"]["turn_count"]),
                    "needs_more_conversation": intent_response.get("needs_more_conversation", True),
                    "metadata": {
                        "conversation_id": request.conversation_id,
                        "session_type": "professional_voice",
                        "voice_optimized": True,
                        "intent_detection_used": True
                    }
                }
            else:
                # Fallback if intent detector is unavailable
                logger.warning(f"Intent detector unavailable for session {request.session_id}, using fallback response")
                
                assistant_response = "I'm here to help you. Could you tell me more about what's on your mind?"
                
                # Update conversation state
                session_data["conversation_state"]["last_assistant_response"] = assistant_response
                session_data["conversation_state"]["context_history"].append({
                    "user": request.text,
                    "assistant": assistant_response,
                    "timestamp": datetime.utcnow().isoformat(),
                    "turn": session_data["conversation_state"]["turn_count"]
                })
                
                active_voice_sessions[request.session_id] = session_data
                
                return {
                    "status": "success",
                    "session_id": request.session_id,
                    "user_message": request.text,
                    "assistant_response": assistant_response,
                    "turn_count": session_data["conversation_state"]["turn_count"],
                    "intent_status": "detector_unavailable",
                    "metadata": {
                        "conversation_id": request.conversation_id,
                        "session_type": "professional_voice",
                        "voice_optimized": True,
                        "fallback_used": True
                    }
                }
            
    except Exception as e:
        logger.error(f"Error processing voice message: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to process voice message: {str(e)}")

@router.post("/voice-message-continue")
async def continue_voice_message(request: VoiceMessageRequest):
    """
    Continue processing voice message after connecting message
    This endpoint is called by frontend after the connecting message is played
    """
    try:
        # Get session data
        session_data = active_voice_sessions.get(request.session_id)
        
        if not session_data:
            raise HTTPException(status_code=404, detail="Voice session not found")
        
        # Build orchestrator payload from session data
        orchestrator_payload = {
            "text": request.text,
            "conversation_id": request.conversation_id,
            "plan": "lite",
            "services": [],
            "individual_id": request.individual_id,
            "user_profile_id": request.user_profile_id,
            "detected_agent": session_data["conversation_state"]["selected_agent"],
            "agent_instance_id": session_data.get("agent_instance_id", "loneliness_658"),
            "call_log_id": session_data.get("call_log_id", f"voice_call_{request.session_id}"),
            "channel": "voice_assistant"
        }
        
        # Send to orchestrator
        orchestrator_response = await send_to_orchestrator(orchestrator_payload)
        
        if orchestrator_response and "response" in orchestrator_response:
            assistant_response = orchestrator_response["response"]
        else:
            assistant_response = "I'm here to help you. How can I support you today?"
        
        # Update conversation state with actual orchestrator response
        session_data["conversation_state"]["turn_count"] += 1
        session_data["conversation_state"]["last_assistant_response"] = assistant_response
        session_data["conversation_state"]["context_history"].append({
            "user": request.text,
            "assistant": assistant_response,
            "timestamp": datetime.utcnow().isoformat(),
            "turn": session_data["conversation_state"]["turn_count"],
            "type": "orchestrator_response"
        })
        
        # Keep only last 10 exchanges for context
        if len(session_data["conversation_state"]["context_history"]) > 10:
            session_data["conversation_state"]["context_history"] = session_data["conversation_state"]["context_history"][-10:]
        
        active_voice_sessions[request.session_id] = session_data
        
        return {
            "status": "success",
            "session_id": request.session_id,
            "user_message": request.text,
            "assistant_response": assistant_response,
            "turn_count": session_data["conversation_state"]["turn_count"],
            "intent_status": "connected",
            "detected_intent": session_data["conversation_state"]["detected_intent"],
            "selected_agent": session_data["conversation_state"]["selected_agent"],
            "processing_time": orchestrator_response.get("processing_time", 0),
            "metadata": {
                "conversation_id": request.conversation_id,
                "session_type": "professional_voice",
                "voice_optimized": True,
                "orchestrator_used": True
            }
        }
        
    except Exception as e:
        logger.error(f"Error continuing voice message: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to continue voice message: {str(e)}")

@router.post("/voice-interrupt")
async def handle_voice_interruption(request: VoiceInterruptionRequest):
    """
    Handle voice interruption events (when user interrupts assistant)
    """
    try:
        session_data = active_voice_sessions.get(request.session_id)
        if not session_data:
            raise HTTPException(status_code=404, detail="Voice session not found")
        
        # Log interruption
        logger.info(f"Voice interruption in session {request.session_id}: {request.reason}")
        
        # Update session state
        if "interruptions" not in session_data:
            session_data["interruptions"] = []
        
        session_data["interruptions"].append({
            "timestamp": datetime.utcnow().isoformat(),
            "reason": request.reason,
            "turn_count": session_data["conversation_state"]["turn_count"]
        })
        
        active_voice_sessions[request.session_id] = session_data
        
        return {
            "status": "success",
            "message": "Interruption handled",
            "session_id": request.session_id
        }
        
    except Exception as e:
        logger.error(f"Error handling voice interruption: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to handle interruption: {str(e)}")

@router.get("/voice-sessions/{session_id}")
async def get_voice_session(session_id: str):
    """
    Get voice session details and status
    """
    try:
        session_data = active_voice_sessions.get(session_id)
        
        if not session_data:
            raise HTTPException(status_code=404, detail="Voice session not found")
        
        # Remove sensitive data
        safe_session_data = {
            "session_id": session_data["session_id"],
            "conversation_id": session_data["conversation_id"],
            "status": session_data["status"],
            "created_at": session_data["created_at"],
            "voice_settings": session_data["voice_settings"],
            "conversation_state": session_data["conversation_state"],
            "participant_name": session_data["participant_name"],
            "intent_info": {
                "intent_detected": session_data["conversation_state"]["intent_detected"],
                "detected_intent": session_data["conversation_state"]["detected_intent"],
                "intent_confidence": session_data["conversation_state"]["intent_confidence"],
                "selected_agent": session_data["conversation_state"]["selected_agent"],
                "selected_agent_name": session_data["conversation_state"]["selected_agent_name"],
                "should_route": session_data["conversation_state"]["should_route"]
            }
        }
        
        return {
            "status": "success",
            "session_data": safe_session_data
        }
        
    except Exception as e:
        logger.error(f"Error getting voice session: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get session: {str(e)}")

@router.post("/voice-sessions/{session_id}/reset-intent")
async def reset_session_intent(session_id: str):
    """
    Reset intent detection for a session (useful for testing)
    """
    try:
        session_data = active_voice_sessions.get(session_id)
        if not session_data:
            raise HTTPException(status_code=404, detail="Voice session not found")
        
        # Reset intent detection state
        session_data["conversation_state"]["intent_detected"] = False
        session_data["conversation_state"]["detected_intent"] = None
        session_data["conversation_state"]["intent_confidence"] = 0.0
        session_data["conversation_state"]["selected_agent"] = None
        session_data["conversation_state"]["selected_agent_name"] = None
        session_data["conversation_state"]["should_route"] = False
        
        active_voice_sessions[session_id] = session_data
        
        logger.info(f"Intent detection reset for session: {session_id}")
        
        return {
            "status": "success",
            "message": "Intent detection reset successfully",
            "session_id": session_id
        }
        
    except Exception as e:
        logger.error(f"Error resetting intent for session: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to reset intent: {str(e)}")

@router.delete("/voice-sessions/{session_id}")
async def end_voice_session(session_id: str):
    """
    End a voice session and cleanup resources
    """
    try:
        session_data = active_voice_sessions.get(session_id)
        if session_data:
            # Extract user information for intent cleanup
            user_profile_id = session_data.get("user_profile_id")
            individual_id = session_data.get("individual_id")
            
            # Mark as ended
            session_data["status"] = "ended"
            session_data["ended_at"] = datetime.utcnow().isoformat()
            
            # Remove from active sessions
            del active_voice_sessions[session_id]
            
            logger.info(f"Voice session deleted: {session_id}")
            
            # CRITICAL: Clear intent detection state to ensure fresh detection
            if user_profile_id:
                logger.info(f"Clearing intent detection state for user {user_profile_id}")
                intent_cleared = await clear_intent_detection_state(user_profile_id, individual_id)
                if intent_cleared:
                    logger.info(f"✅ Intent detection state cleared successfully for user {user_profile_id}")
                else:
                    logger.warning(f"⚠️ Failed to clear intent detection state for user {user_profile_id}")
        else:
            logger.warning(f"Session {session_id} not found for deletion")
        
        return {
            "status": "success",
            "message": "Voice session ended and intent detection state cleared",
            "session_id": session_id
        }
        
    except Exception as e:
        logger.error(f"Error ending voice session: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to end session: {str(e)}")

@router.get("/voice-sessions")
async def list_active_voice_sessions():
    """
    List all active voice sessions
    """
    try:
        active_sessions = []
        for session_id, session_data in active_voice_sessions.items():
            active_sessions.append({
                "session_id": session_id,
                "conversation_id": session_data["conversation_id"],
                "participant_name": session_data["participant_name"],
                "created_at": session_data["created_at"],
                "turn_count": session_data["conversation_state"]["turn_count"],
                "status": session_data["status"],
                "intent_detected": session_data["conversation_state"]["intent_detected"],
                "detected_intent": session_data["conversation_state"]["detected_intent"],
                "selected_agent": session_data["conversation_state"]["selected_agent"]
            })
        
        return {
            "status": "success",
            "active_sessions": active_sessions,
            "total_active": len(active_sessions)
        }
        
    except Exception as e:
        logger.error(f"Error listing voice sessions: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to list sessions: {str(e)}")
