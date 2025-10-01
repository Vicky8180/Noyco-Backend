"""
Professional Voice Assistant Pipeline
Updated to work with LiveKit AI Agent (main_prod.py)
"""

from fastapi import APIRouter, HTTPException, BackgroundTasks
from fastapi import WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from typing import Optional, Dict, Any
import asyncio
import logging
import json
import time
import aiohttp
from datetime import datetime, timedelta
from .config import get_livekit_settings
from livekit import api
from livekit.api import LiveKitAPI, CreateRoomRequest, UpdateRoomMetadataRequest
import os

logger = logging.getLogger(__name__)

# Get configuration from settings
settings = get_livekit_settings()

# Simple JWT token creation (replace with proper implementation)
def create_jwt_token(payload: Dict[str, Any]) -> str:
    """Create proper LiveKit JWT token"""
    try:
        # Get LiveKit credentials from environment
        livekit_api_key = os.getenv("LIVEKIT_API_KEY")
        livekit_api_secret = os.getenv("LIVEKIT_API_SECRET")
        
        if not livekit_api_key or not livekit_api_secret:
            raise ValueError("Missing LIVEKIT_API_KEY or LIVEKIT_API_SECRET")
        
        # Create access token
        token = api.AccessToken(livekit_api_key, livekit_api_secret)
        
        # Set token identity and metadata
        token.with_identity(payload.get("participant_name", "user"))
        token.with_name(payload.get("participant_name", "User"))
        token.with_metadata(json.dumps(payload))
        
        # Grant permissions
        token.with_grants(api.VideoGrants(
            room_join=True,
            room=payload.get("room_name", ""),
            can_publish=True,
            can_subscribe=True,
            can_publish_data=True
        ))
        
        return token.to_jwt()
        
    except Exception as e:
        logger.error(f"Error creating LiveKit token: {e}")
        raise

async def clear_intent_detection_state(user_profile_id: str, individual_id: str) -> bool:
    """
    Clear intent detection state from the initial call handler
    This ensures fresh intent detection when voice sessions are reset
    """
    try:
        from ..initial_call_handler.routes import clear_user_intent_state_internal
        
        cleared_any = False
        
        if user_profile_id:
            if clear_user_intent_state_internal(user_profile_id):
                logger.info(f"✅ Cleared intent state for user_profile_id {user_profile_id}")
                cleared_any = True
        
        if individual_id and individual_id != user_profile_id:
            if clear_user_intent_state_internal(individual_id):
                logger.info(f"✅ Cleared intent state for individual_id {individual_id}")
                cleared_any = True
        
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
        
        effective_user_id = user_id if user_id and user_id != "default_user" else f"user_{int(time.time())}"
        
        payload = {
            "message": message,
            "conversation_history": conversation_history,
            "user_id": effective_user_id
        }
        
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
        
        conversation_text = ""
        for exchange in conversation_context[-3:]:
            conversation_text += f"User: {exchange.get('user', '')}\nAssistant: {exchange.get('assistant', '')}\n"
        
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
            
        goal_data = await generate_goal_data(detected_intent, conversation_context)
        
        if not goal_data:
            logger.error(f"Failed to generate goal data for intent: {detected_intent}")
            return None
        
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
        user_messages = [exchange.get('user', '') for exchange in conversation_context if exchange.get('user')]
        conversation_text = " ".join(user_messages[-3:])
        
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
                "anxiety_level": 5,
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
    force_fresh_start: Optional[bool] = False
    session_reset_timestamp: Optional[int] = None

class VoiceMessageRequest(BaseModel):
    session_id: str
    text: str
    conversation_id: str
    individual_id: str
    user_profile_id: str
    audio_metadata: Optional[Dict[str, Any]] = None

# In-memory session storage
active_voice_sessions = {}

@router.post("/voice-sessions")
async def create_voice_session(request: VoiceSessionRequest):
    """
    Create a voice session with LiveKit AI Agent integration
    Returns connection details for LiveKit room
    """
    try:
        logger.info(f"=== Creating NEW VOICE SESSION ===")
        logger.info(f"Force fresh start: {request.force_fresh_start}")
        logger.info(f"Conversation ID: {request.conversation_id}")
        logger.info(f"User Profile ID: {request.user_profile_id}")
        
        import random
        session_id = f"voice_session_{int(time.time())}_{random.randint(1000, 9999)}_{request.participant_name}"
        room_name = f"voice_room_{session_id}"
        
        counter = 0
        base_session_id = session_id
        while session_id in active_voice_sessions and counter < 100:
            counter += 1
            session_id = f"{base_session_id}_{counter}"
        
        if session_id in active_voice_sessions:
            logger.error(f"Could not generate unique session ID after {counter} attempts")
            raise HTTPException(status_code=500, detail="Could not generate unique session ID")
        
        # Cleanup old sessions if force fresh start
        if request.force_fresh_start:
            logger.info("FORCE FRESH START requested - performing aggressive cleanup")
            
            sessions_to_remove = []
            for existing_session_id, existing_session_data in active_voice_sessions.items():
                if (existing_session_data.get("user_profile_id") == request.user_profile_id or
                    existing_session_data.get("individual_id") == request.individual_id or
                    existing_session_data.get("conversation_id") == request.conversation_id):
                    sessions_to_remove.append(existing_session_id)
            
            for old_session_id in sessions_to_remove:
                del active_voice_sessions[old_session_id]
                logger.info(f"Deleted old session: {old_session_id}")
                
            logger.info(f"Aggressive cleanup completed: removed {len(sessions_to_remove)} old sessions")
            
            intent_cleared = await clear_intent_detection_state(request.user_profile_id, request.individual_id)
            if intent_cleared:
                logger.info(f"✅ Intent detection state cleared for fresh start: {request.user_profile_id}")
        
        # Create metadata payload (this will be accessible to the agent)
        metadata_payload = {
            "session_id": session_id,
            "conversation_id": request.conversation_id,
            "individual_id": request.individual_id,
            "user_profile_id": request.user_profile_id,
            "participant_name": request.participant_name,
            "detected_agent": request.detected_agent,
            "agent_instance_id": request.agent_instance_id,
            "call_log_id": request.call_log_id,
            "session_type": "livekit_agent",
            "created_at": datetime.utcnow().isoformat(),
        }
        
        # Create token payload for authentication
        token_payload = {
            "participant_name": request.participant_name,
            "room_name": room_name,
            **metadata_payload  # Include all metadata in token too
        }
        
        # Create proper LiveKit token
        token = create_jwt_token(token_payload)
        
        # *** KEY FIX: Create/update room with metadata ***
        livekit_api_key = os.getenv("LIVEKIT_API_KEY")
        livekit_api_secret = os.getenv("LIVEKIT_API_SECRET")
        livekit_url = str(settings.LIVEKIT_URL)
        
        async with LiveKitAPI(livekit_url, livekit_api_key, livekit_api_secret) as livekit_client:
            try:
                await livekit_client.room.create_room(
                    CreateRoomRequest(
                        name=room_name, metadata=json.dumps(metadata_payload),
                        empty_timeout=300, max_participants=10
                    )
                )
                logger.info(f"✅ Room created with metadata: {room_name}")
            except Exception as room_error:
                logger.warning(f"Room creation failed: {room_error}, attempting to update metadata")
                try:
                    await livekit_client.room.update_room_metadata(
                        UpdateRoomMetadataRequest(room=room_name, metadata=json.dumps(metadata_payload))
                    )
                    logger.info(f"✅ Room metadata updated: {room_name}")
                except Exception as update_error:
                    logger.error(f"Failed to set room metadata: {update_error}")

        # Session data storage
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
            "url": str(settings.LIVEKIT_URL),
            "room_name": room_name,
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
                "intent_detected": False,
                "detected_intent": None,
                "intent_confidence": 0.0,
                "selected_agent": None,
                "context_history": [],
                "session_started_fresh": True,
                "force_fresh_start": request.force_fresh_start,
                "created_at": datetime.utcnow().isoformat()
            }
        }
        
        # Store session
        active_voice_sessions[session_id] = session_data
        
        logger.info(f"=== CREATED LIVEKIT AGENT SESSION: {session_id} ===")
        
        return {
            "status": "success",
            "session_id": session_id,
            "conversation_id": request.conversation_id,
            "individual_id": request.individual_id,
            "user_profile_id": request.user_profile_id,
            "participant_name": request.participant_name,
            "token": token,
            "url": str(settings.LIVEKIT_URL),
            "room_name": room_name,
            "voice_settings": session_data["voice_settings"],
            "force_fresh_start": request.force_fresh_start,
            "message": "LiveKit Agent session created"
        }
        
    except Exception as e:
        logger.error(f"Error creating voice session: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create voice session: {str(e)}")

@router.post("/voice-message")
async def process_voice_message(request: VoiceMessageRequest):
    """
    Process voice message with intent detection and orchestration
    This endpoint is called by the LiveKit AI agent (main_prod.py)
    """
    try:
        logger.info(f"=== Processing voice message for session: {request.session_id} ===")
        logger.info(f"User said: {request.text}")
        
        # Special handling for initial greeting
        if request.text == "__INITIAL_GREETING__":
            logger.info("Generating initial greeting")
            return {
                "status": "success",
                "session_id": request.session_id,
                "assistant_response": "Hello! I'm Noyco, your voice assistant. How can I help you today?",
                "intent_status": "greeting"
            }
        
        # Get session data
        session_data = active_voice_sessions.get(request.session_id)
        
        if not session_data:
            logger.warning(f"Session not found: {request.session_id}, creating minimal session")
            # Create minimal session for standalone operation
            session_data = {
                "session_id": request.session_id,
                "conversation_id": request.conversation_id,
                "user_profile_id": request.user_profile_id,
                "individual_id": request.individual_id,
                "conversation_state": {
                    "turn_count": 0,
                    "intent_detected": False,
                    "context_history": [],
                    "detected_intent": None,
                    "selected_agent": None
                }
            }
            active_voice_sessions[request.session_id] = session_data
        
        # Update turn count
        session_data["conversation_state"]["turn_count"] += 1
        turn_count = session_data["conversation_state"]["turn_count"]
        
        logger.info(f"Turn count: {turn_count}")
        logger.info(f"Intent detected: {session_data['conversation_state']['intent_detected']}")
        
        # Check if intent is already detected
        if session_data["conversation_state"]["intent_detected"]:
            logger.info(f"Intent already detected: {session_data['conversation_state']['detected_intent']}")
            logger.info(f"Routing to orchestrator with agent: {session_data['conversation_state']['selected_agent']}")
            
            # Route to orchestrator
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
                "channel": "livekit_agent"
            }
            
            orchestrator_response = await send_to_orchestrator(orchestrator_payload)
            
            if orchestrator_response and "response" in orchestrator_response:
                assistant_response = orchestrator_response["response"]
            else:
                assistant_response = "I'm here to help. What would you like to talk about?"
            
            # Update context
            session_data["conversation_state"]["context_history"].append({
                "user": request.text,
                "assistant": assistant_response,
                "timestamp": datetime.utcnow().isoformat(),
                "turn": turn_count
            })
            
            # Keep only last 10 exchanges
            if len(session_data["conversation_state"]["context_history"]) > 10:
                session_data["conversation_state"]["context_history"] = session_data["conversation_state"]["context_history"][-10:]
            
            active_voice_sessions[request.session_id] = session_data
            
            return {
                "status": "success",
                "session_id": request.session_id,
                "assistant_response": assistant_response,
                "turn_count": turn_count,
                "intent_status": "routed",
                "detected_intent": session_data["conversation_state"]["detected_intent"]
            }
        
        else:
            # Intent not detected yet - send to intent detector
            logger.info(f"=== INTENT DETECTION for turn {turn_count} ===")
            
            # Build conversation history
            conversation_history = []
            
            if len(session_data["conversation_state"]["context_history"]) == 0:
                conversation_history.append({
                    "role": "system", 
                    "content": f"NEW_SESSION_START:{session_data['conversation_state']['created_at']}"
                })
            
            for exchange in session_data["conversation_state"]["context_history"]:
                conversation_history.append({"role": "user", "content": exchange["user"]})
                conversation_history.append({"role": "assistant", "content": exchange["assistant"]})
            
            logger.info(f"Sending to intent detector with {len(conversation_history)} context messages")
            
            # Send to intent detector
            intent_response = await send_to_intent_detector(
                request.text, 
                conversation_history, 
                request.user_profile_id
            )
            
            if intent_response:
                detected_intent = intent_response.get("detected_intent")
                should_route = intent_response.get("should_route", False)
                assistant_response = intent_response.get("response", "Tell me more about what's on your mind.")
                
                logger.info(f"Intent response - detected: {detected_intent}, should_route: {should_route}")
                
                # Check if we should route to specialist
                if detected_intent and detected_intent.lower() != "none" and should_route:
                    logger.info(f"✅ Intent detected: {detected_intent} with confidence {intent_response.get('confidence', 0.0)}")
                    
                    # Update session state
                    session_data["conversation_state"]["intent_detected"] = True
                    session_data["conversation_state"]["detected_intent"] = detected_intent
                    session_data["conversation_state"]["intent_confidence"] = intent_response.get("confidence", 0.0)
                    session_data["conversation_state"]["selected_agent"] = intent_response.get("selected_agent")
                    
                    # Create goal
                    created_goal_id = await create_goal_based_on_intent(
                        detected_intent, 
                        request.user_profile_id, 
                        session_data["conversation_state"]["context_history"]
                    )
                    
                    if created_goal_id:
                        session_data["goal_id"] = created_goal_id
                        session_data["agent_instance_id"] = created_goal_id
                        logger.info(f"Created goal {created_goal_id}")
                    
                    # Generate connecting message
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
                    assistant_response = f"I understand you need support with {detected_intent.replace('_', ' ')}. Let me connect you with our {specialist_name} who can help you better."
                
                # Update context
                session_data["conversation_state"]["context_history"].append({
                    "user": request.text,
                    "assistant": assistant_response,
                    "timestamp": datetime.utcnow().isoformat(),
                    "turn": turn_count
                })
                
                if len(session_data["conversation_state"]["context_history"]) > 10:
                    session_data["conversation_state"]["context_history"] = session_data["conversation_state"]["context_history"][-10:]
                
                active_voice_sessions[request.session_id] = session_data
                
                return {
                    "status": "success",
                    "session_id": request.session_id,
                    "assistant_response": assistant_response,
                    "turn_count": turn_count,
                    "intent_status": "detected" if should_route else "exploring",
                    "detected_intent": detected_intent,
                    "confidence": intent_response.get("confidence", 0.0),
                    "selected_agent": intent_response.get("selected_agent")
                }
            
            else:
                # Fallback response
                logger.warning("Intent detector unavailable, using fallback")
                assistant_response = "I'm here to listen. Could you tell me more about what brings you here today?"
                
                session_data["conversation_state"]["context_history"].append({
                    "user": request.text,
                    "assistant": assistant_response,
                    "timestamp": datetime.utcnow().isoformat(),
                    "turn": turn_count
                })
                
                active_voice_sessions[request.session_id] = session_data
                
                return {
                    "status": "success",
                    "session_id": request.session_id,
                    "assistant_response": assistant_response,
                    "turn_count": turn_count,
                    "intent_status": "fallback"
                }
            
    except Exception as e:
        logger.error(f"Error processing voice message: {e}", exc_info=True)
        return {
            "status": "error",
            "error": str(e),
            "assistant_response": "I'm having trouble processing that. Could you try again?"
        }

@router.get("/voice-sessions/{session_id}")
async def get_voice_session(session_id: str):
    """Get voice session details"""
    try:
        session_data = active_voice_sessions.get(session_id)
        
        if not session_data:
            raise HTTPException(status_code=404, detail="Voice session not found")
        
        safe_session_data = {
            "session_id": session_data["session_id"],
            "conversation_id": session_data["conversation_id"],
            "status": session_data["status"],
            "created_at": session_data["created_at"],
            "conversation_state": session_data["conversation_state"]
        }
        
        return {
            "status": "success",
            "session_data": safe_session_data
        }
        
    except Exception as e:
        logger.error(f"Error getting voice session: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get session: {str(e)}")

@router.delete("/voice-sessions/{session_id}")
async def end_voice_session(session_id: str):
    """End voice session and cleanup"""
    try:
        session_data = active_voice_sessions.get(session_id)
        if session_data:
            user_profile_id = session_data.get("user_profile_id")
            individual_id = session_data.get("individual_id")
            
            session_data["status"] = "ended"
            session_data["ended_at"] = datetime.utcnow().isoformat()
            
            del active_voice_sessions[session_id]
            
            logger.info(f"Voice session deleted: {session_id}")
            
            if user_profile_id:
                intent_cleared = await clear_intent_detection_state(user_profile_id, individual_id)
                if intent_cleared:
                    logger.info(f"✅ Intent detection state cleared for user {user_profile_id}")
        
        return {
            "status": "success",
            "message": "Voice session ended",
            "session_id": session_id
        }
        
    except Exception as e:
        logger.error(f"Error ending voice session: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to end session: {str(e)}")

@router.get("/voice-sessions")
async def list_active_voice_sessions():
    """List all active voice sessions"""
    try:
        active_sessions = []
        for session_id, session_data in active_voice_sessions.items():
            active_sessions.append({
                "session_id": session_id,
                "conversation_id": session_data["conversation_id"],
                "participant_name": session_data.get("participant_name", "Unknown"),
                "created_at": session_data["created_at"],
                "turn_count": session_data["conversation_state"]["turn_count"],
                "status": session_data["status"],
                "intent_detected": session_data["conversation_state"]["intent_detected"]
            })
        
        return {
            "status": "success",
            "active_sessions": active_sessions,
            "total_active": len(active_sessions)
        }
        
    except Exception as e:
        logger.error(f"Error listing voice sessions: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to list sessions: {str(e)}")
    

active_websockets: Dict[str, WebSocket] = {}


@router.websocket("/ws/voice-session/{session_id}")
async def voice_session_websocket(websocket: WebSocket, session_id: str):
    """
    WebSocket endpoint for real-time voice conversation
    """
    await websocket.accept()
    active_websockets[session_id] = websocket
    
    logger.info(f"WebSocket connected for session: {session_id}")
    
    try:
        # Get or create session data
        session_data = active_voice_sessions.get(session_id)
        if not session_data:
            await websocket.send_json({
                "type": "error",
                "message": "Session not found"
            })
            await websocket.close()
            return
        
        # Send connection confirmation
        await websocket.send_json({
            "type": "connected",
            "session_id": session_id,
            "message": "WebSocket connected successfully"
        })
        
        while True:
            # Receive message from client (main_prod.py)
            data = await websocket.receive_json()
            message_type = data.get("type")
            
            if message_type == "user_message":
                user_text = data.get("text", "")
                logger.info(f"Received via WebSocket: {user_text}")
                
                # Process the message
                response = await process_message_internal(
                    session_id=session_id,
                    text=user_text,
                    session_data=session_data
                )
                
                # Send response back
                await websocket.send_json({
                    "type": "assistant_response",
                    "text": response.get("assistant_response", ""),
                    "intent_status": response.get("intent_status"),
                    "detected_intent": response.get("detected_intent"),
                    "turn_count": response.get("turn_count")
                })
            
            elif message_type == "ping":
                await websocket.send_json({"type": "pong"})
            
            elif message_type == "disconnect":
                logger.info(f"Client requested disconnect for session: {session_id}")
                break
                
    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for session: {session_id}")
    except Exception as e:
        logger.error(f"WebSocket error for session {session_id}: {e}", exc_info=True)
    finally:
        if session_id in active_websockets:
            del active_websockets[session_id]
        logger.info(f"WebSocket cleanup completed for session: {session_id}")

async def process_message_internal(session_id: str, text: str, session_data: dict) -> dict:
    """
    Internal message processing logic (extracted from /voice-message endpoint)
    """
    try:
        # Special handling for initial greeting
        if text == "__INITIAL_GREETING__":
            return {
                "status": "success",
                "assistant_response": "Hello! I'm Noyco, your voice assistant. How can I help you today?",
                "intent_status": "greeting"
            }
        
        # Update turn count
        session_data["conversation_state"]["turn_count"] += 1
        turn_count = session_data["conversation_state"]["turn_count"]
        
        # Check if intent is already detected
        if session_data["conversation_state"]["intent_detected"]:
            # Route to orchestrator
            orchestrator_payload = {
                "text": text,
                "conversation_id": session_data["conversation_id"],
                "plan": "lite",
                "services": [],
                "individual_id": session_data["individual_id"],
                "user_profile_id": session_data["user_profile_id"],
                "detected_agent": session_data["conversation_state"]["selected_agent"],
                "agent_instance_id": session_data.get("agent_instance_id"),
                "call_log_id": session_data.get("call_log_id"),
                "channel": "livekit_agent"
            }
            
            orchestrator_response = await send_to_orchestrator(orchestrator_payload)
            
            assistant_response = orchestrator_response.get("response", "I'm here to help.") if orchestrator_response else "I'm here to help."
            
            # Update context
            session_data["conversation_state"]["context_history"].append({
                "user": text,
                "assistant": assistant_response,
                "timestamp": datetime.utcnow().isoformat(),
                "turn": turn_count
            })
            
            if len(session_data["conversation_state"]["context_history"]) > 10:
                session_data["conversation_state"]["context_history"] = session_data["conversation_state"]["context_history"][-10:]
            
            return {
                "status": "success",
                "assistant_response": assistant_response,
                "turn_count": turn_count,
                "intent_status": "routed",
                "detected_intent": session_data["conversation_state"]["detected_intent"]
            }
        
        else:
            # Intent detection flow (same as before)
            conversation_history = []
            
            if len(session_data["conversation_state"]["context_history"]) == 0:
                conversation_history.append({
                    "role": "system",
                    "content": f"NEW_SESSION_START:{session_data['conversation_state']['created_at']}"
                })
            
            for exchange in session_data["conversation_state"]["context_history"]:
                conversation_history.append({"role": "user", "content": exchange["user"]})
                conversation_history.append({"role": "assistant", "content": exchange["assistant"]})
            
            intent_response = await send_to_intent_detector(
                text,
                conversation_history,
                session_data["user_profile_id"]
            )
            
            if intent_response:
                detected_intent = intent_response.get("detected_intent")
                should_route = intent_response.get("should_route", False)
                assistant_response = intent_response.get("response", "Tell me more.")
                
                if detected_intent and detected_intent.lower() != "none" and should_route:
                    session_data["conversation_state"]["intent_detected"] = True
                    session_data["conversation_state"]["detected_intent"] = detected_intent
                    session_data["conversation_state"]["selected_agent"] = intent_response.get("selected_agent")
                    
                    # Create goal
                    created_goal_id = await create_goal_based_on_intent(
                        detected_intent,
                        session_data["user_profile_id"],
                        session_data["conversation_state"]["context_history"]
                    )
                    
                    if created_goal_id:
                        session_data["goal_id"] = created_goal_id
                        session_data["agent_instance_id"] = created_goal_id
                
                session_data["conversation_state"]["context_history"].append({
                    "user": text,
                    "assistant": assistant_response,
                    "timestamp": datetime.utcnow().isoformat(),
                    "turn": turn_count
                })
                
                return {
                    "status": "success",
                    "assistant_response": assistant_response,
                    "turn_count": turn_count,
                    "intent_status": "detected" if should_route else "exploring",
                    "detected_intent": detected_intent
                }
            else:
                return {
                    "status": "success",
                    "assistant_response": "I'm here to listen. Tell me more.",
                    "turn_count": turn_count,
                    "intent_status": "fallback"
                }
                
    except Exception as e:
        logger.error(f"Error in process_message_internal: {e}", exc_info=True)
        return {
            "status": "error",
            "assistant_response": "I'm having trouble processing that."
        }