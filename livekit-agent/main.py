# """
# Noyco Voice Agent - Production Version
# Based on LiveKit Agents v1.2+ API
# Properly handles user speech by overriding on_user_turn_completed
# Uses WebSocket for real-time communication with backend
# """
# import asyncio
# import logging
# import json
# import aiohttp
# import websockets

# from livekit import agents, rtc
# from livekit.agents import (
#     Agent,
#     AgentSession,
#     JobContext,
#     WorkerOptions,
#     cli,
#     llm as llm_module,
#     StopResponse,
#     utils,
# )
# from livekit.plugins import deepgram, elevenlabs, silero, cartesia

# from config import get_settings

# # Load settings
# settings = get_settings()

# logging.basicConfig(level=logging.INFO)
# logger = logging.getLogger(__name__)


# class NoycoAssistant(Agent):
#     """
#     Noyco Voice Assistant that intercepts user messages
#     and routes them to Noyco backend via WebSocket
#     """
    
#     def __init__(self, session_data: dict, backend_url: str, ws_url: str):
#         self.session_data = session_data
#         self.backend_url = backend_url
#         self.ws_url = ws_url
#         self.websocket = None
#         self.ws_connected = False
#         self.ws_lock = asyncio.Lock()
#         self.audio_source = None  # For typing sound playback
#         self._room_instance = None  # Store room for data channel access
#         self._is_shutting_down = False  # Track shutdown state
        
#         # Get API keys from settings
#         elevenlabs_key = settings.ELEVENLABS_API_KEY
#         cartesia_key = settings.CARTESIA_API_KEY
        
#         # Store TTS fallback configuration
#         self.primary_tts = cartesia.TTS(api_key=cartesia_key) if cartesia_key else None
#         self.fallback_tts = elevenlabs.TTS(api_key=elevenlabs_key) if elevenlabs_key else None
#         self.use_fallback_tts = False
        
#         # Initialize the base Agent
#         super().__init__(
#             instructions="You are Noyco, a helpful and empathetic AI voice assistant.",
#             stt=deepgram.STT(
#                 model=settings.STT_MODEL,
#                 language=settings.STT_LANGUAGE,
#                 interim_results=settings.STT_INTERIM_RESULTS,
#                 smart_format=settings.STT_SMART_FORMAT,          # Better punctuation and formatting
#                 punctuate=settings.STT_PUNCTUATE,                # Add punctuation
#             ),
#             tts=self.primary_tts if self.primary_tts else self.fallback_tts,
#         )
        
#         logger.info(f"✅ NoycoAssistant initialized for session: {session_data.get('session_id')}")
    
#     async def connect_websocket(self):
#         """Establish WebSocket connection to backend"""
#         async with self.ws_lock:
#             if self.ws_connected and self.websocket:
#                 return True
            
#             try:
#                 session_id = self.session_data.get("session_id")
#                 if not session_id:
#                     logger.warning("No session_id available for WebSocket connection")
#                     return False
                
#                 ws_endpoint = f"{self.ws_url}/api/v1/voice/ws/voice-session/{session_id}"
#                 logger.info(f"🔌 Connecting to WebSocket: {ws_endpoint}")
                
#                 self.websocket = await asyncio.wait_for(
#                     websockets.connect(ws_endpoint),
#                     timeout=settings.WEBSOCKET_TIMEOUT
#                 )
                
#                 # Wait for connection confirmation
#                 try:
#                     response = await asyncio.wait_for(
#                         self.websocket.recv(), 
#                         timeout=settings.WEBSOCKET_TIMEOUT
#                     )
#                     data = json.loads(response)
#                     if data.get("type") == "connected":
#                         self.ws_connected = True
#                         logger.info(f"✅ WebSocket connected for session: {session_id}")
#                         return True
#                     else:
#                         logger.warning(f"Unexpected WebSocket response: {data}")
#                         return False
#                 except asyncio.TimeoutError:
#                     logger.warning("WebSocket connection confirmation timeout")
#                     return False
                    
#             except Exception as e:
#                 logger.error(f"WebSocket connection failed: {e}")
#                 self.websocket = None
#                 self.ws_connected = False
#                 return False
    
#     async def close_websocket(self):
#         """Close WebSocket connection"""
#         self._is_shutting_down = True
#         async with self.ws_lock:
#             if self.websocket:
#                 try:
#                     await self.websocket.close()
#                     logger.info("WebSocket closed")
#                 except Exception as e:
#                     logger.error(f"Error closing WebSocket: {e}")
#                 finally:
#                     self.websocket = None
#                     self.ws_connected = False
    
#     async def _send_message_to_frontend(self, text: str, sender: str):
#         """Send message to frontend via LiveKit data channel"""
#         try:
#             # Check if shutting down
#             if self._is_shutting_down:
#                 logger.debug("⚠️ Skipping message send - assistant is shutting down")
#                 return
            
#             # Check if we have access to the room
#             if not hasattr(self, '_room_instance') or self._room_instance is None:
#                 logger.warning(f"Cannot send message - room not available yet")
#                 return
            
#             message_data = {
#                 "type": "message",
#                 "sender": sender,
#                 "text": text,
#                 "timestamp": asyncio.get_event_loop().time()
#             }
            
#             # Send via data channel using room instance
#             data_packet = json.dumps(message_data).encode('utf-8')
#             await self._room_instance.local_participant.publish_data(
#                 data_packet,
#                 reliable=True
#             )
#             logger.info(f"✅ Message sent to frontend: {sender} - {text[:50]}...")
#         except Exception as e:
#             logger.error(f"❌ Error sending message to frontend: {e}", exc_info=True)
    
#     async def _speak_with_fallback(self, text: str):
#         """Speak text with TTS fallback mechanism"""
#         try:
#             # Try primary TTS (ElevenLabs)
#             if not self.use_fallback_tts and self.primary_tts:
#                 try:
#                     self.session.say(text)
#                     logger.info("✅ Speech generated with ElevenLabs")
#                 except Exception as primary_error:
#                     logger.warning(f"Primary TTS (ElevenLabs) failed: {primary_error}")
                    
#                     # Switch to fallback if available
#                     if self.fallback_tts:
#                         logger.info("🔄 Switching to Cartesia TTS fallback...")
#                         self.use_fallback_tts = True
#                         # Update agent's TTS
#                         self.tts = self.fallback_tts
#                         # Try speaking with fallback
#                         try:
#                             self.session.say(text)
#                             logger.info("✅ Speech generated with Cartesia (fallback)")
#                         except Exception as fallback_error:
#                             logger.error(f"Fallback TTS (Cartesia) also failed: {fallback_error}")
#                             # Message already sent to frontend, so user can still read it
#                     else:
#                         logger.error("No fallback TTS available")
#             # Use fallback TTS if already switched
#             elif self.use_fallback_tts and self.fallback_tts:
#                 try:
#                     self.session.say(text)
#                     logger.info("✅ Speech generated with Cartesia (fallback)")
#                 except Exception as e:
#                     logger.error(f"Fallback TTS failed: {e}")
#             else:
#                 logger.error("No TTS available")
                
#         except Exception as e:
#             logger.error(f"Error in speak_with_fallback: {e}")
#             # Message still sent to frontend via data channel
    
#     async def _send_typing_indicator(self):
#         """Send typing indicator to indicate processing (visual feedback if supported)"""
#         try:
#             # Send typing indicator through the session if available
#             # This can be picked up by the frontend to show a "thinking" animation
#             if hasattr(self.session, 'emit_metadata'):
#                 await self.session.emit_metadata({"typing": True})
            
#             # Keep indicator active while processing
#             await asyncio.sleep(0.1)  # Small delay to ensure it's sent
                    
#         except Exception as e:
#             logger.debug(f"Typing indicator error (non-critical): {e}")
    
#     async def on_user_turn_completed(
#         self, 
#         turn_ctx: llm_module.ChatContext, 
#         new_message: llm_module.ChatMessage
#     ) -> None:
#         """
#         Called when the user finishes speaking.
#         This is where we intercept user input and send it to our backend.
#         """
#         # Check if shutting down
#         if self._is_shutting_down:
#             logger.info("⚠️ Ignoring user turn - assistant is shutting down")
#             raise StopResponse()
        
#         # Extract user's text
#         user_text = new_message.text_content
        
#         if not user_text or not user_text.strip():
#             logger.warning("Empty user message received")
#             raise StopResponse()  # Don't generate a response
        
#         logger.info(f"🗣️ User said: '{user_text}'")
#         logger.info("⏳ Processing response...")
        
#         # Send user's message to frontend
#         await self._send_message_to_frontend(user_text, "user")
        
#         response_text = None
        
#         try:
#             # Start typing indicator in background
#             typing_task = asyncio.create_task(self._send_typing_indicator())
            
#             try:
#                 # Get response from Noyco backend
#                 response_text = await self._get_backend_response(user_text)
#             finally:
#                 # Stop typing indicator
#                 typing_task.cancel()
#                 try:
#                     await typing_task
#                 except asyncio.CancelledError:
#                     pass
                
#                 # Send typing stopped indicator
#                 try:
#                     if hasattr(self.session, 'emit_metadata'):
#                         await self.session.emit_metadata({"typing": False})
#                 except:
#                     pass
            
#             if not response_text or not response_text.strip():
#                 logger.warning("Empty response from backend")
#                 response_text = "I'm processing that. Could you tell me more?"
        
#         except Exception as e:
#             logger.error(f"Error getting backend response: {e}", exc_info=True)
#             response_text = "I'm having trouble right now. Could you try again?"
        
#         # Always send the message via WebSocket/HTTP, even if TTS fails
#         if response_text and response_text.strip():
#             logger.info(f"⬅️ Backend response: {response_text[:100]}...")
            
#             # Send the text message to frontend via data channel
#             await self._send_message_to_frontend(response_text, "agent")
            
#             # Try to speak the response
#             await self._speak_with_fallback(response_text)
        
#         # Stop the default LLM response since we handled it
#         raise StopResponse()
    
#     async def _get_backend_response(self, user_text: str) -> str:
#         """Get response from Noyco backend via WebSocket (with HTTP fallback)"""
        
#         # Check if shutting down
#         if self._is_shutting_down:
#             logger.info("⚠️ Skipping backend request - assistant is shutting down")
#             return "I'm disconnecting now. Thank you for talking with me!"
        
#         # Try WebSocket first
#         if self.ws_connected and self.websocket:
#             try:
#                 logger.info(f"➡️ Sending via WebSocket: '{user_text[:100]}...'")
                
#                 # Send message via WebSocket
#                 await self.websocket.send(json.dumps({
#                     "type": "user_message",
#                     "text": user_text
#                 }))
                
#                 # Wait for response with timeout
#                 response = await asyncio.wait_for(
#                     self.websocket.recv(), 
#                     timeout=settings.BACKEND_RESPONSE_TIMEOUT
#                 )
#                 data = json.loads(response)
                
#                 if data.get("type") == "assistant_response":
#                     assistant_response = data.get("text", "")
#                     if assistant_response and assistant_response.strip():
#                         logger.info(f"⬅️ WebSocket response: {assistant_response[:100]}...")
#                         return assistant_response
#                     else:
#                         logger.warning("WebSocket returned empty response")
#                 elif data.get("type") == "error":
#                     error_msg = data.get("message", "Unknown error")
#                     logger.error(f"WebSocket error: {error_msg}")
#                     # Fall through to HTTP
#                 else:
#                     logger.warning(f"Unexpected WebSocket message type: {data.get('type')}")
#                     # Fall through to HTTP
                    
#             except asyncio.TimeoutError:
#                 logger.warning("WebSocket response timeout, falling back to HTTP")
#                 self.ws_connected = False
#             except websockets.exceptions.ConnectionClosed:
#                 logger.warning("WebSocket connection closed, falling back to HTTP")
#                 self.ws_connected = False
#                 self.websocket = None
#             except Exception as e:
#                 logger.error(f"WebSocket error: {e}, falling back to HTTP")
#                 self.ws_connected = False
        
#         # HTTP fallback (or primary if WebSocket not connected)
#         try:
#             # Build payload, only including fields that have values
#             payload = {
#                 "session_id": self.session_data.get("session_id"),
#                 "text": user_text,
#             }
            
#             # Add optional fields only if they exist and are not None
#             if self.session_data.get("conversation_id"):
#                 payload["conversation_id"] = self.session_data.get("conversation_id")
#             if self.session_data.get("individual_id"):
#                 payload["individual_id"] = self.session_data.get("individual_id")
#             if self.session_data.get("user_profile_id"):
#                 payload["user_profile_id"] = self.session_data.get("user_profile_id")
            
#             logger.info(f"➡️ Sending via HTTP: '{user_text[:100]}...'")
            
#             async with aiohttp.ClientSession() as session:
#                 async with session.post(
#                     f"{self.backend_url}/api/v1/voice/voice-message",
#                     json=payload,
#                     timeout=aiohttp.ClientTimeout(total=settings.HTTP_REQUEST_TIMEOUT)
#                 ) as response:
#                     if response.status == 200:
#                         result = await response.json()
                        
#                         if result.get("status") == "success":
#                             assistant_response = result.get("assistant_response", "")
                            
#                             if assistant_response and assistant_response.strip():
#                                 logger.info(f"⬅️ HTTP response: {assistant_response[:100]}...")
#                                 return assistant_response
#                             else:
#                                 logger.warning("Backend returned empty response")
#                                 return "I'm processing that. Could you tell me more?"
#                         else:
#                             error_msg = result.get("error", "Unknown error")
#                             logger.error(f"Backend error: {error_msg}")
#                             return "I encountered an issue. Could you repeat that?"
#                     else:
#                         error_text = await response.text()
#                         logger.error(f"Backend HTTP error: {response.status} - {error_text}")
#                         return "I'm having trouble right now. Could you try again?"
                                
#         except asyncio.TimeoutError:
#             logger.error("Backend request timed out")
#             return "I need a moment. Could you say that again?"
#         except Exception as e:
#             logger.error(f"Error getting backend response: {e}", exc_info=True)
#             return "I ran into an issue. Let's try again."


# async def entrypoint(ctx: JobContext):
#     """Main entrypoint for Noyco LiveKit Agent"""
    
#     # Check API keys from settings
#     deepgram_key = settings.DEEPGRAM_API_KEY
#     elevenlabs_key = settings.ELEVENLABS_API_KEY
#     backend_url = settings.NOYCO_BACKEND_URL
#     ws_url = settings.NOYCO_WS_URL
    
#     if not all([deepgram_key, elevenlabs_key]):
#         raise ValueError("Missing required API keys for Deepgram or ElevenLabs")
    
#     # Connect to room
#     await ctx.connect()
#     logger.info(f"✅ Connected to room: {ctx.room.name}")
    
#     # Extract session data from room metadata
#     session_data = {}
#     if ctx.room.metadata:
#         try:
#             session_data = json.loads(ctx.room.metadata) if isinstance(ctx.room.metadata, str) else ctx.room.metadata
#             logger.info(f"✅ Loaded session data from room metadata")
#         except Exception as e:
#             logger.error(f"Failed to parse room metadata: {e}")
    
#     # Fallback: Try to fetch session data from backend if not in metadata
#     if not session_data or not session_data.get("session_id"):
#         logger.warning("⚠️ No valid session data in metadata, attempting to fetch from backend")
#         room_name = ctx.room.name
#         if room_name.startswith("voice_room_"):
#             extracted_session_id = room_name.replace("voice_room_", "")
#             try:
#                 async with aiohttp.ClientSession() as session:
#                     async with session.get(
#                         f"{backend_url}/api/v1/voice/voice-sessions/{extracted_session_id}",
#                         timeout=aiohttp.ClientTimeout(total=5)
#                     ) as response:
#                         if response.status == 200:
#                             result = await response.json()
#                             session_data = result.get("session_data", {})
#                             logger.info(f"✅ Retrieved session data from backend")
#                         else:
#                             logger.error(f"Failed to fetch session from backend: {response.status}")
#             except Exception as fetch_error:
#                 logger.error(f"Error fetching session data: {fetch_error}")
    
#     logger.info(f"📋 Final session data: {session_data}")
    
#     # Create the assistant
#     assistant = NoycoAssistant(session_data, backend_url, ws_url)
    
#     # Connect WebSocket before starting
#     await assistant.connect_websocket()
    
#     # Create AgentSession with VAD for turn detection
#     # Configure VAD with longer patience to allow natural pauses in speech
#     agent_session = AgentSession(
#         vad=silero.VAD.load(
#             min_speech_duration=settings.VAD_MIN_SPEECH_DURATION,
#             min_silence_duration=settings.VAD_MIN_SILENCE_DURATION,
#             prefix_padding_duration=settings.VAD_PADDING_DURATION,
#             activation_threshold=settings.VAD_ACTIVATION_THRESHOLD,
#         ),
#         turn_detection="vad",  # Use VAD for turn detection
#     )
    
#     logger.info("=== 🤖 NOYCO VOICE AGENT INITIALIZED ===")
#     logger.info(f"✅ STT: Deepgram Nova-2")
#     logger.info(f"✅ TTS: ElevenLabs")
#     logger.info(f"✅ VAD: Silero")
#     logger.info(f"✅ Backend: {backend_url}")
#     logger.info(f"✅ Session ID: {session_data.get('session_id', 'Unknown')}")
    
#     # Track if session is shutting down
#     is_shutting_down = False
#     shutdown_lock = asyncio.Lock()
    
#     try:
#         # Store room instance in assistant for message sending
#         assistant._room_instance = ctx.room
        
#         # Start the session
#         await agent_session.start(room=ctx.room, agent=assistant)
        
#         logger.info("=== 🚀 SESSION STARTED ===")
        
#         # Send initial greeting
#         try:
#             greeting_response = await assistant._get_backend_response("__INITIAL_GREETING__")
#             agent_session.say(greeting_response)
#             logger.info("✅ Initial greeting sent")
#         except Exception as greeting_error:
#             logger.error(f"Error sending greeting: {greeting_error}")
#             agent_session.say("Hello! I'm Noyco, your voice assistant. How can I help you today?")
        
#         logger.info("🎯 Listening for user speech...")
        
#         # Wait for disconnection
#         disconnected_event = asyncio.Event()
        
#         @ctx.room.on("disconnected")
#         def on_disconnected():
#             logger.info("🚪 Room disconnected event received")
#             disconnected_event.set()
        
#         # Keep the session alive until disconnection
#         await disconnected_event.wait()
        
#         # Begin graceful shutdown
#         async with shutdown_lock:
#             if not is_shutting_down:
#                 is_shutting_down = True
#                 logger.info("🛑 Starting graceful shutdown...")
                
#                 # Give a moment for any in-flight operations to complete
#                 await asyncio.sleep(0.5)
                
#     except asyncio.CancelledError:
#         logger.info("⚠️ Entrypoint cancelled")
#         async with shutdown_lock:
#             is_shutting_down = True
#         raise
#     except Exception as e:
#         logger.error(f"❌ Session error: {e}", exc_info=True)
#     finally:
#         # Ensure cleanup happens only once
#         async with shutdown_lock:
#             if not is_shutting_down:
#                 is_shutting_down = True
            
#             logger.info("🧹 Starting cleanup...")
            
#             # Close WebSocket connection with timeout
#             try:
#                 await asyncio.wait_for(assistant.close_websocket(), timeout=2.0)
#             except asyncio.TimeoutError:
#                 logger.warning("WebSocket close timeout")
#             except Exception as cleanup_error:
#                 logger.error(f"Error during WebSocket cleanup: {cleanup_error}")
            
#             # Give a moment for any remaining tasks to finish
#             await asyncio.sleep(0.5)
            
#             logger.info("✅ Session cleanup completed")


# if __name__ == "__main__":
#     cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint))


"""
Multi-Tenant LiveKit Agent Service
Handles multiple concurrent user sessions in a single instance
"""
import asyncio
import logging
import json
import aiohttp
import websockets
from typing import Dict, Optional
from datetime import datetime

from livekit import agents, rtc
from livekit.agents import (
    Agent,
    AgentSession,
    JobContext,
    WorkerOptions,
    llm as llm_module,
    StopResponse,
)
from livekit.plugins import deepgram, elevenlabs, silero, cartesia, google
from config import get_settings

# Load settings
settings = get_settings()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class SessionManager:
    """
    Manages multiple concurrent agent sessions
    Thread-safe session lifecycle management
    """
    
    def __init__(self):
        self._sessions: Dict[str, Dict] = {}
        self._lock = asyncio.Lock()
        self._tasks: Dict[str, asyncio.Task] = {}
        
    async def add_session(self, session_id: str, session_data: Dict):
        """Add a new session"""
        async with self._lock:
            if session_id in self._sessions:
                logger.warning(f"Session {session_id} already exists, replacing...")
                await self.remove_session(session_id)
            
            self._sessions[session_id] = {
                "data": session_data,
                "created_at": datetime.utcnow(),
                "last_activity": datetime.utcnow(),
                "status": "active"
            }
            logger.info(f"✅ Session {session_id} added. Total sessions: {len(self._sessions)}")
    
    async def remove_session(self, session_id: str):
        """Remove a session"""
        async with self._lock:
            if session_id in self._sessions:
                # Cancel associated task if exists
                if session_id in self._tasks:
                    task = self._tasks[session_id]
                    if not task.done():
                        task.cancel()
                        try:
                            await task
                        except asyncio.CancelledError:
                            pass
                    del self._tasks[session_id]
                
                del self._sessions[session_id]
                logger.info(f"✅ Session {session_id} removed. Total sessions: {len(self._sessions)}")
    
    async def update_activity(self, session_id: str):
        """Update last activity timestamp"""
        async with self._lock:
            if session_id in self._sessions:
                self._sessions[session_id]["last_activity"] = datetime.utcnow()
    
    async def get_session(self, session_id: str) -> Optional[Dict]:
        """Get session data"""
        async with self._lock:
            return self._sessions.get(session_id)
    
    async def get_all_sessions(self) -> Dict[str, Dict]:
        """Get all sessions"""
        async with self._lock:
            return dict(self._sessions)
    
    def add_task(self, session_id: str, task: asyncio.Task):
        """Track a session task"""
        self._tasks[session_id] = task
    
    async def cleanup_stale_sessions(self, max_age_minutes: int = 30):
        """Remove sessions inactive for too long"""
        async with self._lock:
            now = datetime.utcnow()
            stale = []
            
            for session_id, session in self._sessions.items():
                age = (now - session["last_activity"]).total_seconds() / 60
                if age > max_age_minutes:
                    stale.append(session_id)
            
            for session_id in stale:
                logger.info(f"🧹 Cleaning up stale session: {session_id}")
                await self.remove_session(session_id)


# Global session manager
session_manager = SessionManager()


class NoycoAssistant(Agent):
    """
    Noyco Voice Assistant for multi-tenant deployment
    Each instance handles one user session
    """
    
    def __init__(self, session_data: dict, backend_url: str, ws_url: str):
        self.session_data = session_data
        self.session_id = session_data.get("session_id")
        self.backend_url = backend_url
        self.ws_url = ws_url
        self.websocket = None
        self.ws_connected = False
        self.ws_lock = asyncio.Lock()
        self._room_instance = None
        self._is_shutting_down = False
        self._all_services_failed = False  # Track if all services have failed
        
        # Get API keys from settings
        elevenlabs_key = settings.ELEVENLABS_API_KEY
        cartesia_key = settings.CARTESIA_API_KEY
        google_key = settings.GOOGLE_API_KEY
        google_creds = settings.GOOGLE_CREDENTIALS_PATH
        
        # STT Configuration with fallbacks
        # Priority: Deepgram (primary) -> Google (fallback)
        self.primary_stt = None
        self.fallback_stt = None
        self.current_stt_provider = "none"
        
        try:
            if settings.DEEPGRAM_API_KEY:
                self.primary_stt = deepgram.STT(
                    model=settings.STT_MODEL,
                    language=settings.STT_LANGUAGE,
                    interim_results=settings.STT_INTERIM_RESULTS,
                    smart_format=settings.STT_SMART_FORMAT,
                    punctuate=settings.STT_PUNCTUATE,
                )
                self.current_stt_provider = "Deepgram"
                logger.info("✅ Primary STT: Deepgram initialized")
        except Exception as e:
            logger.warning(f"Failed to initialize Deepgram STT: {e}")
        
        # Google STT as fallback
        try:
            if google_key or google_creds:
                self.fallback_stt = google.STT(
                    credentials_info=google_creds if google_creds else None,
                    language="en-US"
                )
                if not self.primary_stt:
                    self.current_stt_provider = "Google"
                logger.info("✅ Fallback STT: Google initialized")
        except Exception as e:
            logger.warning(f"Failed to initialize Google STT: {e}")
        
        # TTS Configuration with fallbacks
        # Priority: Cartesia (primary) -> ElevenLabs (secondary) -> Google (ultimate fallback)
        self.primary_tts = None
        self.secondary_tts = None
        self.fallback_tts = None
        self.current_tts_provider = "none"
        self.tts_fallback_level = 0  # 0=primary, 1=secondary, 2=ultimate fallback
        
        # Cartesia as primary (changed from ElevenLabs due to production timeout issues)
        try:
            if cartesia_key:
                self.primary_tts = cartesia.TTS(
                    api_key=cartesia_key,
                    model="sonic-english",  # Fast, low-latency model
                )
                self.current_tts_provider = "Cartesia"
                logger.info("✅ Primary TTS: Cartesia initialized")
        except Exception as e:
            logger.warning(f"Failed to initialize Cartesia TTS: {e}")
        
        # ElevenLabs as secondary fallback (demoted from primary due to timeout issues)
        try:
            if elevenlabs_key:
                self.secondary_tts = elevenlabs.TTS(
                    api_key=elevenlabs_key,
                    model_id="eleven_turbo_v2",  # Faster model to reduce timeouts
                )
                if not self.primary_tts:
                    self.current_tts_provider = "ElevenLabs"
                    self.tts_fallback_level = 1
                logger.info("✅ Secondary TTS: ElevenLabs initialized")
        except Exception as e:
            logger.warning(f"Failed to initialize ElevenLabs TTS: {e}")
        
        # Google TTS as ultimate fallback
        try:
            if google_key or google_creds:
                self.fallback_tts = google.TTS(
                    credentials_info=google_creds if google_creds else None,
                    language="en-US",
                    voice_name="en-US-Chirp-HD-F"
                )
                if not self.primary_tts and not self.secondary_tts:
                    self.current_tts_provider = "Google"
                    self.tts_fallback_level = 2
                logger.info("✅ Ultimate Fallback TTS: Google initialized")
        except Exception as e:
            logger.warning(f"Failed to initialize Google TTS: {e}")
        
        # Check if we have at least one working service
        if not (self.primary_stt or self.fallback_stt):
            logger.error("❌ No STT service available!")
            self._all_services_failed = True
        
        if not (self.primary_tts or self.secondary_tts or self.fallback_tts):
            logger.error("❌ No TTS service available!")
            self._all_services_failed = True
        
        # Choose initial STT and TTS
        active_stt = self.primary_stt if self.primary_stt else self.fallback_stt
        active_tts = self.primary_tts if self.primary_tts else (self.secondary_tts if self.secondary_tts else self.fallback_tts)
        
        # Initialize the base Agent
        super().__init__(
            instructions="You are Noyco, a helpful and empathetic AI voice assistant.",
            stt=active_stt,
            tts=active_tts,
        )
        
        logger.info(f"✅ NoycoAssistant initialized for session: {self.session_id}")
        logger.info(f"🎙️ Active STT: {self.current_stt_provider}")
        logger.info(f"🔊 Active TTS: {self.current_tts_provider}")
        
        if self._all_services_failed:
            logger.error("⚠️ CRITICAL: Voice services unavailable - text-only mode")
    
    async def connect_websocket(self):
        """Establish WebSocket connection to backend"""
        async with self.ws_lock:
            if self.ws_connected and self.websocket:
                return True
            
            try:
                if not self.session_id:
                    logger.warning("No session_id available for WebSocket connection")
                    return False
                
                ws_endpoint = f"{self.ws_url}/api/v1/voice/ws/voice-session/{self.session_id}"
                logger.info(f"🔌 Connecting to WebSocket: {ws_endpoint}")
                
                self.websocket = await asyncio.wait_for(
                    websockets.connect(ws_endpoint),
                    timeout=settings.WEBSOCKET_TIMEOUT
                )
                
                # Wait for connection confirmation
                try:
                    response = await asyncio.wait_for(
                        self.websocket.recv(), 
                        timeout=settings.WEBSOCKET_TIMEOUT
                    )
                    data = json.loads(response)
                    if data.get("type") == "connected":
                        self.ws_connected = True
                        logger.info(f"✅ WebSocket connected for session: {self.session_id}")
                        return True
                    else:
                        logger.warning(f"Unexpected WebSocket response: {data}")
                        return False
                except asyncio.TimeoutError:
                    logger.warning("WebSocket connection confirmation timeout")
                    return False
                    
            except Exception as e:
                logger.error(f"WebSocket connection failed: {e}")
                self.websocket = None
                self.ws_connected = False
                return False
    
    async def close_websocket(self):
        """Close WebSocket connection"""
        self._is_shutting_down = True
        async with self.ws_lock:
            if self.websocket:
                try:
                    await self.websocket.close()
                    logger.info("WebSocket closed")
                except Exception as e:
                    logger.error(f"Error closing WebSocket: {e}")
                finally:
                    self.websocket = None
                    self.ws_connected = False
    
    async def _send_message_to_frontend(self, text: str, sender: str):
        """Send message to frontend via LiveKit data channel"""
        try:
            if self._is_shutting_down:
                logger.debug("⚠️ Skipping message send - assistant is shutting down")
                return
            
            if not hasattr(self, '_room_instance') or self._room_instance is None:
                logger.warning(f"Cannot send message - room not available yet")
                return
            
            message_data = {
                "type": "message",
                "sender": sender,
                "text": text,
                "timestamp": asyncio.get_event_loop().time()
            }
            
            data_packet = json.dumps(message_data).encode('utf-8')
            await self._room_instance.local_participant.publish_data(
                data_packet,
                reliable=True
            )
            
            # Update session activity
            await session_manager.update_activity(self.session_id)
            
            logger.info(f"✅ [{self.session_id}] Message sent: {sender} - {text[:50]}...")
        except Exception as e:
            logger.error(f"❌ Error sending message to frontend: {e}", exc_info=True)
    
    async def _speak_with_fallback(self, text: str):
        """
        Speak text with comprehensive TTS fallback mechanism with runtime provider switching.
        This method tries each TTS provider in order, switching providers on failure.
        """
        
        # If all services failed, only send text message (already sent via data channel)
        if self._all_services_failed:
            logger.warning(f"⚠️ [{self.session_id}] All voice services unavailable - text-only mode")
            return
        
        # Build list of TTS providers to try in order
        tts_attempts = []
        
        if self.tts_fallback_level == 0:
            if self.primary_tts:
                tts_attempts.append(("Cartesia (primary)", self.primary_tts, 0))
            if self.secondary_tts:
                tts_attempts.append(("ElevenLabs (secondary)", self.secondary_tts, 1))
            if self.fallback_tts:
                tts_attempts.append(("Google (ultimate fallback)", self.fallback_tts, 2))
        elif self.tts_fallback_level == 1:
            if self.secondary_tts:
                tts_attempts.append(("ElevenLabs (secondary)", self.secondary_tts, 1))
            if self.fallback_tts:
                tts_attempts.append(("Google (ultimate fallback)", self.fallback_tts, 2))
        elif self.tts_fallback_level == 2:
            if self.fallback_tts:
                tts_attempts.append(("Google (ultimate fallback)", self.fallback_tts, 2))
        
        # Try each TTS provider in order with timeout protection
        last_error = None
        for provider_name, tts_instance, level in tts_attempts:
            try:
                logger.info(f"🎤 [{self.session_id}] Attempting TTS with {provider_name}")
                
                # Switch to this TTS provider
                self.tts = tts_instance
                self.tts_fallback_level = level
                
                # Attempt to speak with timeout protection
                # session.say() is non-blocking, so we need to wrap it carefully
                try:
                    self.session.say(text)
                    # Give it a moment to start processing
                    await asyncio.sleep(0.1)
                    logger.info(f"✅ [{self.session_id}] Speech queued with {provider_name}")
                    return
                except asyncio.TimeoutError:
                    raise Exception(f"Timeout waiting for {provider_name}")
                except Exception as say_error:
                    # If session.say() itself fails, try next provider
                    raise Exception(f"{provider_name} say() failed: {say_error}")
                
            except Exception as e:
                last_error = e
                logger.warning(f"⚠️ [{self.session_id}] {provider_name} TTS failed: {e}")
                
                # If this was the primary, mark it as failed and move to next
                if level == 0:
                    logger.info(f"🔄 [{self.session_id}] Switching from Cartesia to ElevenLabs fallback")
                elif level == 1:
                    logger.info(f"🔄 [{self.session_id}] Switching from ElevenLabs to Google fallback")
                
                # Continue to next provider
                continue
        
        # If we reach here, all TTS services have failed
        if not self._all_services_failed:
            self._all_services_failed = True
            logger.error(f"❌ [{self.session_id}] All TTS services failed (last error: {last_error})")
            logger.error(f"❌ [{self.session_id}] Switching to text-only mode")
            
            # Send explicit text-only message to user
            fallback_message = (
                "I apologize, but our voice services are currently experiencing issues. "
                "Our servers are overloaded at the moment. You can try our chat-based agent "
                "or please try again after some time. Thank you for your patience."
            )
            await self._send_message_to_frontend(fallback_message, "system")
    
    async def _send_typing_indicator(self):
        """Send typing indicator"""
        try:
            if hasattr(self.session, 'emit_metadata'):
                await self.session.emit_metadata({"typing": True})
            await asyncio.sleep(0.1)
        except Exception as e:
            logger.debug(f"Typing indicator error (non-critical): {e}")
    
    async def on_user_turn_completed(
        self, 
        turn_ctx: llm_module.ChatContext, 
        new_message: llm_module.ChatMessage
    ) -> None:
        """
        Called when the user finishes speaking.
        Intercepts user input and sends it to backend.
        """
        if self._is_shutting_down:
            logger.info(f"⚠️ [{self.session_id}] Ignoring user turn - assistant is shutting down")
            raise StopResponse()
        
        # Check if all services have failed
        if self._all_services_failed:
            logger.error(f"❌ [{self.session_id}] All voice services failed")
            fallback_message = (
                "I apologize, but our voice services are currently experiencing issues. "
                "Our servers are overloaded at the moment. You can try our chat-based agent "
                "or please try again after some time. Thank you for your patience."
            )
            await self._send_message_to_frontend(fallback_message, "agent")
            raise StopResponse()
        
        user_text = new_message.text_content
        
        if not user_text or not user_text.strip():
            logger.warning(f"[{self.session_id}] Empty user message received")
            raise StopResponse()
        
        logger.info(f"🗣️ [{self.session_id}] User said: '{user_text}'")
        
        # Update activity
        await session_manager.update_activity(self.session_id)
        
        # Send user's message to frontend
        await self._send_message_to_frontend(user_text, "user")
        
        response_text = None
        
        try:
            # Start typing indicator
            typing_task = asyncio.create_task(self._send_typing_indicator())
            
            try:
                response_text = await self._get_backend_response(user_text)
            finally:
                typing_task.cancel()
                try:
                    await typing_task
                except asyncio.CancelledError:
                    pass
                
                try:
                    if hasattr(self.session, 'emit_metadata'):
                        await self.session.emit_metadata({"typing": False})
                except:
                    pass
            
            if not response_text or not response_text.strip():
                logger.warning(f"[{self.session_id}] Empty response from backend")
                response_text = "I'm processing that. Could you tell me more?"
        
        except Exception as e:
            logger.error(f"[{self.session_id}] Error getting backend response: {e}", exc_info=True)
            response_text = "I'm having trouble right now. Could you try again?"
        
        if response_text and response_text.strip():
            logger.info(f"⬅️ [{self.session_id}] Backend response: {response_text[:100]}...")
            
            # Send to frontend
            await self._send_message_to_frontend(response_text, "agent")
            
            # Speak the response
            await self._speak_with_fallback(response_text)
        
        raise StopResponse()
    
    async def _get_backend_response(self, user_text: str) -> str:
        """Get response from Noyco backend via WebSocket (with HTTP fallback)"""
        
        if self._is_shutting_down:
            logger.info(f"⚠️ [{self.session_id}] Skipping backend request - shutting down")
            return "I'm disconnecting now. Thank you for talking with me!"
        
        # Try WebSocket first
        if self.ws_connected and self.websocket:
            try:
                logger.info(f"➡️ [{self.session_id}] Sending via WebSocket: '{user_text[:100]}...'")
                
                await self.websocket.send(json.dumps({
                    "type": "user_message",
                    "text": user_text
                }))
                
                response = await asyncio.wait_for(
                    self.websocket.recv(), 
                    timeout=settings.BACKEND_RESPONSE_TIMEOUT
                )
                data = json.loads(response)
                
                if data.get("type") == "assistant_response":
                    assistant_response = data.get("text", "")
                    if assistant_response and assistant_response.strip():
                        logger.info(f"⬅️ [{self.session_id}] WebSocket response: {assistant_response[:100]}...")
                        return assistant_response
                    else:
                        logger.warning(f"[{self.session_id}] WebSocket returned empty response")
                elif data.get("type") == "error":
                    error_msg = data.get("message", "Unknown error")
                    logger.error(f"[{self.session_id}] WebSocket error: {error_msg}")
                else:
                    logger.warning(f"[{self.session_id}] Unexpected WebSocket message: {data.get('type')}")
                    
            except asyncio.TimeoutError:
                logger.warning(f"[{self.session_id}] WebSocket timeout, falling back to HTTP")
                self.ws_connected = False
            except websockets.exceptions.ConnectionClosed:
                logger.warning(f"[{self.session_id}] WebSocket closed, falling back to HTTP")
                self.ws_connected = False
                self.websocket = None
            except Exception as e:
                logger.error(f"[{self.session_id}] WebSocket error: {e}, falling back to HTTP")
                self.ws_connected = False
        
        # HTTP fallback
        try:
            payload = {
                "session_id": self.session_id,
                "text": user_text,
            }
            
            if self.session_data.get("conversation_id"):
                payload["conversation_id"] = self.session_data.get("conversation_id")
            if self.session_data.get("individual_id"):
                payload["individual_id"] = self.session_data.get("individual_id")
            if self.session_data.get("user_profile_id"):
                payload["user_profile_id"] = self.session_data.get("user_profile_id")
            
            logger.info(f"➡️ [{self.session_id}] Sending via HTTP: '{user_text[:100]}...'")
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.backend_url}/api/v1/voice/voice-message",
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=settings.HTTP_REQUEST_TIMEOUT)
                ) as response:
                    if response.status == 200:
                        try:
                            result = await response.json()
                            
                            if result.get("status") == "success":
                                assistant_response = result.get("assistant_response", "")
                                
                                if assistant_response and assistant_response.strip():
                                    logger.info(f"⬅️ [{self.session_id}] HTTP response: {assistant_response[:100]}...")
                                    return assistant_response
                                else:
                                    logger.warning(f"[{self.session_id}] Backend returned empty response")
                                    return "I'm processing that. Could you tell me more?"
                            else:
                                error_msg = result.get("error", result.get("message", "Unknown error"))
                                logger.error(f"[{self.session_id}] Backend error: {error_msg}")
                                logger.debug(f"[{self.session_id}] Backend response: {result}")
                                return "I encountered an issue. Could you repeat that?"
                        except (KeyError, ValueError, TypeError) as parse_error:
                            logger.error(f"[{self.session_id}] Error parsing backend response: {parse_error}")
                            response_text = await response.text()
                            logger.debug(f"[{self.session_id}] Raw response: {response_text[:200]}")
                            return "I encountered an issue. Could you repeat that?"
                    else:
                        error_text = await response.text()
                        logger.error(f"[{self.session_id}] Backend HTTP error: {response.status} - {error_text[:200]}")
                        return "I'm having trouble right now. Could you try again?"
                                
        except asyncio.TimeoutError:
            logger.error(f"[{self.session_id}] Backend request timed out")
            return "I need a moment. Could you say that again?"
        except Exception as e:
            logger.error(f"[{self.session_id}] Error getting backend response: {e}", exc_info=True)
            return "I ran into an issue. Let's try again."


async def handle_session(ctx: JobContext):
    """
    Handle a single user session in multi-tenant mode
    This runs as an async task for each connected user
    """
    session_id = None
    
    try:
        # Connect to room
        await ctx.connect()
        logger.info(f"✅ Connected to room: {ctx.room.name}")
        
        # Extract session data from room metadata
        session_data = {}
        if ctx.room.metadata:
            try:
                session_data = json.loads(ctx.room.metadata) if isinstance(ctx.room.metadata, str) else ctx.room.metadata
                logger.info(f"✅ Loaded session data from room metadata")
            except Exception as e:
                logger.error(f"Failed to parse room metadata: {e}")
        
        # Fallback: Fetch from backend if not in metadata
        if not session_data or not session_data.get("session_id"):
            logger.warning("⚠️ No valid session data in metadata, attempting to fetch from backend")
            room_name = ctx.room.name
            if room_name.startswith("voice_room_"):
                extracted_session_id = room_name.replace("voice_room_", "")
                try:
                    async with aiohttp.ClientSession() as session:
                        async with session.get(
                            f"{settings.NOYCO_BACKEND_URL}/api/v1/voice/voice-sessions/{extracted_session_id}",
                            timeout=aiohttp.ClientTimeout(total=5)
                        ) as response:
                            if response.status == 200:
                                result = await response.json()
                                session_data = result.get("session_data", {})
                                logger.info(f"✅ Retrieved session data from backend")
                            else:
                                logger.error(f"Failed to fetch session from backend: {response.status}")
                except Exception as fetch_error:
                    logger.error(f"Error fetching session data: {fetch_error}")
        
        session_id = session_data.get("session_id")
        
        if not session_id:
            logger.error("❌ No session_id found, cannot proceed")
            return
        
        logger.info(f"📋 Session {session_id} starting...")
        
        # Register session with manager
        await session_manager.add_session(session_id, session_data)
        
        # Create the assistant
        assistant = NoycoAssistant(session_data, settings.NOYCO_BACKEND_URL, settings.NOYCO_WS_URL)
        
        # Connect WebSocket
        await assistant.connect_websocket()
        
        # Create AgentSession with VAD
        agent_session = AgentSession(
            vad=silero.VAD.load(
                min_speech_duration=settings.VAD_MIN_SPEECH_DURATION,
                min_silence_duration=settings.VAD_MIN_SILENCE_DURATION,
                prefix_padding_duration=settings.VAD_PADDING_DURATION,
                activation_threshold=settings.VAD_ACTIVATION_THRESHOLD,
            ),
            turn_detection="vad",
        )
        
        logger.info(f"=== 🤖 ASSISTANT READY FOR SESSION: {session_id} ===")
        
        # Store room instance
        assistant._room_instance = ctx.room
        
        # Start the session
        await agent_session.start(room=ctx.room, agent=assistant)
        
        logger.info(f"=== 🚀 SESSION {session_id} STARTED ===")
        
        # Send initial greeting
        try:
            greeting_response = await assistant._get_backend_response("__INITIAL_GREETING__")
            agent_session.say(greeting_response)
            logger.info(f"✅ [{session_id}] Initial greeting sent")
        except Exception as greeting_error:
            logger.error(f"[{session_id}] Error sending greeting: {greeting_error}")
            agent_session.say("Hello! I'm Noyco, your voice assistant. How can I help you today?")
        
        logger.info(f"🎯 [{session_id}] Listening for user speech...")
        
        # Wait for disconnection
        disconnected_event = asyncio.Event()
        
        @ctx.room.on("disconnected")
        def on_disconnected():
            logger.info(f"🚪 [{session_id}] Room disconnected")
            disconnected_event.set()
        
        # Keep session alive
        await disconnected_event.wait()
        
        logger.info(f"🛑 [{session_id}] Starting graceful shutdown...")
        
        # Give a moment for cleanup
        await asyncio.sleep(0.5)
        
    except asyncio.CancelledError:
        logger.info(f"⚠️ [{session_id}] Session cancelled")
        raise
    except Exception as e:
        logger.error(f"❌ [{session_id}] Session error: {e}", exc_info=True)
    finally:
        # Cleanup
        if session_id:
            logger.info(f"🧹 [{session_id}] Starting cleanup...")
            
            try:
                if 'assistant' in locals():
                    await asyncio.wait_for(assistant.close_websocket(), timeout=2.0)
            except asyncio.TimeoutError:
                logger.warning(f"[{session_id}] WebSocket close timeout")
            except Exception as cleanup_error:
                logger.error(f"[{session_id}] Error during cleanup: {cleanup_error}")
            
            # Remove from session manager
            await session_manager.remove_session(session_id)
            
            await asyncio.sleep(0.5)
            
            logger.info(f"✅ [{session_id}] Session cleanup completed")


async def entrypoint(ctx: JobContext):
    """
    Multi-tenant entrypoint
    Spawns async task for each session
    """
    session_id = f"unknown_{ctx.room.name}"
    
    try:
        # Create a task for this session
        task = asyncio.create_task(handle_session(ctx))
        
        # Track the task
        session_manager.add_task(session_id, task)
        
        # Wait for the task to complete
        await task
        
    except asyncio.CancelledError:
        logger.info(f"⚠️ Entrypoint cancelled for {session_id}")
        raise
    except Exception as e:
        logger.error(f"❌ Entrypoint error for {session_id}: {e}", exc_info=True)


# Background task for cleanup
async def cleanup_worker():
    """Periodically cleanup stale sessions"""
    while True:
        try:
            await asyncio.sleep(300)  # Every 5 minutes
            logger.info("🧹 Running stale session cleanup...")
            await session_manager.cleanup_stale_sessions(max_age_minutes=30)
        except asyncio.CancelledError:
            logger.info("Cleanup worker cancelled")
            break
        except Exception as e:
            logger.error(f"Error in cleanup worker: {e}")


if __name__ == "__main__":
    from livekit.agents import cli
    
    # Start cleanup worker in background
    asyncio.create_task(cleanup_worker())
    
    # Run the agent
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint))
