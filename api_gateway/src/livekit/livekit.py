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
from datetime import datetime
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

async def send_to_intent_detector(message: str, conversation_history: list) -> Optional[Dict[str, Any]]:
    """Send request to intent detection endpoint"""
    try:
        payload = {
            "message": message,
            "conversation_history": conversation_history
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post("http://localhost:8000/initial/chat", json=payload) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    logger.error(f"Intent detector error: {response.status}")
                    return None
    except Exception as e:
        logger.error(f"Failed to send to intent detector: {e}")
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
    """
    try:
        # Generate session ID
        session_id = f"voice_session_{int(time.time())}_{request.participant_name}"
        
        # Create JWT token for this session
        token_payload = {
            "session_id": session_id,
            "conversation_id": request.conversation_id,
            "individual_id": request.individual_id,
            "user_profile_id": request.user_profile_id,
            "participant_name": request.participant_name,
            "session_type": "professional_voice",
            "created_at": datetime.utcnow().isoformat()
        }
        
        token = create_jwt_token(token_payload)
        
        # LiveKit configuration for professional voice
        livekit_config = {
            "url": str(settings.LIVEKIT_HOST),
            "room_name": f"voice_room_{session_id}",
            "participant_name": request.participant_name
        }
        
        # Session data
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
                "context_history": [],
                "intent_detected": False,
                "detected_intent": None,
                "intent_confidence": 0.0,
                "selected_agent": None,
                "selected_agent_name": None,
                "should_route": False
            }
        }
        
        # Store session
        active_voice_sessions[session_id] = session_data
        
        logger.info(f"Created professional voice session: {session_id}")
        
        return {
            "status": "success",
            "session_id": session_id,
            "conversation_id": request.conversation_id,
            "token": token,
            "url": livekit_config["url"],
            "room_name": livekit_config["room_name"],
            "voice_settings": session_data["voice_settings"],
            "message": "Professional voice session created successfully"
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
        # Get session data
        session_data = active_voice_sessions.get(request.session_id)
        
        if not session_data:
            raise HTTPException(status_code=404, detail="Voice session not found")
        
        # Update conversation state
        session_data["conversation_state"]["turn_count"] += 1
        session_data["conversation_state"]["last_user_message"] = request.text
        
        # Check if intent is already detected for this session
        if session_data["conversation_state"]["intent_detected"]:
            logger.info(f"Intent already detected for session {request.session_id}, routing directly to orchestrator")
            
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
                "channel": "voice_assistant"
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
            logger.info(f"Intent not detected for session {request.session_id}, checking intent detection")
            
            # Build conversation history for intent detection
            conversation_history = []
            for exchange in session_data["conversation_state"]["context_history"]:
                conversation_history.append({"role": "user", "content": exchange["user"]})
                conversation_history.append({"role": "assistant", "content": exchange["assistant"]})
            
            # Send to intent detector
            intent_response = await send_to_intent_detector(request.text, conversation_history)
            
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
                    
                    # Now send to orchestrator with detected intent
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
                    
                    orchestrator_response = await send_to_orchestrator(orchestrator_payload)
                    
                    if orchestrator_response and "response" in orchestrator_response:
                        assistant_response = orchestrator_response["response"]
                    else:
                        assistant_response = intent_response.get("response", "I understand what you're looking for. Let me help you with that.")
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
            # Mark as ended
            session_data["status"] = "ended"
            session_data["ended_at"] = datetime.utcnow().isoformat()
            
            # Remove from active sessions
            del active_voice_sessions[session_id]
            
            logger.info(f"Voice session ended: {session_id}")
        
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
