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
from livekit.plugins import deepgram, silero, cartesia, google
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
        self.tts_error_count = 0  # Track TTS errors for monitoring
        self.stt_fallback_active = False  # True if fallback STT is being used
        self.tts_fallback_active = False  # True if fallback TTS is being used
        
        # Manual send mode feature
        self.auto_send_enabled = True  # True = auto-send (default), False = manual send
        self.transcript_buffer = []  # Buffer to accumulate transcripts in manual mode
        self.buffer_lock = asyncio.Lock()  # Lock for thread-safe buffer access
        
        # Track Google TTS instance creation for debugging
        self.google_tts_creation_count = 0
        
        # Get API keys from settings
        cartesia_key = settings.CARTESIA_API_KEY
        google_key = settings.GOOGLE_API_KEY
        google_creds = None
        
        # Load Google credentials from file if path is provided
        if settings.GOOGLE_CREDENTIALS_PATH:
            try:
                import json
                with open(settings.GOOGLE_CREDENTIALS_PATH, 'r') as f:
                    google_creds = json.load(f)
                logger.info("✅ Google credentials loaded from file")
            except Exception as e:
                logger.warning(f"Failed to load Google credentials from file: {e}")
                google_creds = None
        
        # STT Configuration with fallbacks
        # Priority: Deepgram (primary) -> Google (fallback)
        self.primary_stt = None
        self.fallback_stt = None
        self.current_stt_provider = "none"
        
        # Try to initialize Deepgram (primary)
        deepgram_available = False
        try:
            if settings.DEEPGRAM_API_KEY:
                self.primary_stt = deepgram.STT(
                    model=settings.STT_MODEL,
                    language=settings.STT_LANGUAGE,
                    interim_results=settings.STT_INTERIM_RESULTS,
                    smart_format=settings.STT_SMART_FORMAT,
                    punctuate=settings.STT_PUNCTUATE,
                )
                deepgram_available = True
                logger.info("✅ Primary STT: Deepgram initialized")
        except Exception as e:
            logger.warning(f"Failed to initialize Deepgram STT: {e}")
            self.primary_stt = None
        
        # Try to initialize Google STT as fallback
        google_stt_available = False
        try:
            if google_key or google_creds:
                self.fallback_stt = google.STT(
                    credentials_info=google_creds if google_creds else None,
                    language="en-US"
                )
                google_stt_available = True
                logger.info("✅ Fallback STT: Google initialized")
        except Exception as e:
            logger.warning(f"Failed to initialize Google STT: {e}")
            self.fallback_stt = None
        
        # Determine which STT to use based on availability
        if deepgram_available:
            self.current_stt_provider = "Deepgram"
            logger.info(f"🎙️ Using Deepgram as primary STT")
        elif google_stt_available:
            self.current_stt_provider = "Google"
            self.stt_fallback_active = True
            logger.warning(f"⚠️ Deepgram unavailable, using Google STT as primary")
        else:
            logger.error("❌ No STT service available!")
            self.current_stt_provider = "none"
        
        # TTS Configuration with fallbacks
        # Priority: Cartesia (primary) -> Google (fallback)
        self.primary_tts = None
        self.fallback_tts = None
        self.current_tts_provider = "none"
        self.tts_fallback_level = 0  # 0=primary, 1=fallback
        
        # Cartesia as primary
        try:
            if cartesia_key:
                self.primary_tts = cartesia.TTS(
                    api_key=cartesia_key,
                    model="sonic-english",
                )
                self.current_tts_provider = "Cartesia"
                logger.info("✅ Primary TTS: Cartesia initialized")
        except Exception as e:
            logger.warning(f"Failed to initialize Cartesia TTS: {e}")
        
        # Google TTS as fallback
        # Store credentials for creating fresh instances
        self.google_tts_credentials = google_creds
        self.google_tts_key = google_key
        
        try:
            if google_key or google_creds:
                self.fallback_tts = self._create_google_tts_instance()
                if not self.primary_tts:
                    self.current_tts_provider = "Google"
                    self.tts_fallback_level = 1
                logger.info("✅ Fallback TTS: Google initialized")
        except Exception as e:
            logger.warning(f"Failed to initialize Google TTS: {e}")
            self.fallback_tts = None
        
        # Check if we have at least one working service
        if not (self.primary_stt or self.fallback_stt):
            logger.error("❌ No STT service available!")
            self._all_services_failed = True
        
        if not (self.primary_tts or self.fallback_tts):
            logger.error("❌ No TTS service available!")
            self._all_services_failed = True
        
        # Choose initial STT and TTS based on availability
        # Use the active provider determined during initialization
        if self.stt_fallback_active:
            active_stt = self.fallback_stt
        else:
            active_stt = self.primary_stt if self.primary_stt else self.fallback_stt
            if not self.primary_stt and self.fallback_stt:
                self.stt_fallback_active = True
        
        # TTS selection
        active_tts = self.primary_tts if self.primary_tts else self.fallback_tts
        if not self.primary_tts and self.fallback_tts:
            self.tts_fallback_active = True

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
    
    def _create_google_tts_instance(self):
        """Create a fresh Google TTS instance to avoid decoder issues"""
        try:
            self.google_tts_creation_count += 1
            logger.info(f"🏗️ [{self.session_id}] Creating Google TTS instance #{self.google_tts_creation_count}")
            
            instance = google.TTS(
                credentials_info=self.google_tts_credentials if self.google_tts_credentials else None,
                language="en-US",
                voice_name="en-US-Chirp-HD-F",
                # Add sample rate specification for better compatibility
                sample_rate=24000,
            )
            
            logger.info(f"✅ [{self.session_id}] Google TTS instance created successfully (ID: {id(instance)})")
            return instance
        except Exception as e:
            logger.error(f"❌ Failed to create Google TTS instance: {e}", exc_info=True)
            return None
    
    def _refresh_google_tts(self):
        """Refresh the Google TTS instance to prevent decoder issues"""
        if self.google_tts_credentials or self.google_tts_key:
            try:
                logger.info(f"🔄 [{self.session_id}] Creating fresh Google TTS instance...")
                new_instance = self._create_google_tts_instance()
                if new_instance:
                    old_instance_id = id(self.fallback_tts) if self.fallback_tts else None
                    self.fallback_tts = new_instance
                    new_instance_id = id(self.fallback_tts)
                    
                    logger.info(f"✅ [{self.session_id}] Google TTS instance refreshed (old: {old_instance_id}, new: {new_instance_id})")
                    
                    # Update the session's internal TTS reference
                    if hasattr(self, 'session') and self.session:
                        try:
                            # Try to update the AgentSession's TTS instance
                            if hasattr(self.session, '_tts'):
                                self.session._tts = new_instance
                                logger.debug(f"[{self.session_id}] Updated session._tts reference")
                            # Also update the agent's TTS if accessible
                            if hasattr(self.session, '_agent') and hasattr(self.session._agent, '_tts'):
                                self.session._agent._tts = new_instance
                                logger.debug(f"[{self.session_id}] Updated session._agent._tts reference")
                        except Exception as update_error:
                            logger.warning(f"Could not update session TTS reference: {update_error}")
                    
                    return True
            except Exception as e:
                logger.error(f"❌ Failed to refresh Google TTS: {e}", exc_info=True)
        else:
            logger.warning(f"[{self.session_id}] Cannot refresh Google TTS - no credentials available")
        return False

    @property
    def stt(self):
        if self.stt_fallback_active:
            return self.fallback_stt
        return self.primary_stt

    @property
    def tts(self):
        if self.tts_fallback_active:
            return self.fallback_tts
        return self.primary_tts

    def _switch_tts_provider(self):
        """Switch to the next available TTS provider."""
        if not self.tts_fallback_active and self.fallback_tts:
            logger.warning(f"[{self.session_id}] Switching TTS provider from Primary to Fallback due to errors.")
            self.tts_fallback_active = True
            return True
        
        logger.error(f"[{self.session_id}] No more TTS providers to fall back to.")
        self._all_services_failed = True
        return False

    async def _handle_stt_failure(self):
        """Handle STT failure by switching to fallback."""
        if not self.stt_fallback_active and self.fallback_stt:
            logger.warning(f"[{self.session_id}] Primary STT failed. Switching to fallback STT for the session.")
            self.stt_fallback_active = True
            return True
        else:
            logger.error(f"[{self.session_id}] STT service failed, and no fallback is available.")
            self._all_services_failed = True
            return False
    
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
    
    async def _send_transcript_update(self, transcript: str):
        """Send accumulated transcript to frontend for display in manual mode"""
        try:
            if self._is_shutting_down or not self._room_instance:
                return
            
            update_data = {
                "type": "transcript_update",
                "text": transcript,
                "timestamp": asyncio.get_event_loop().time()
            }
            
            data_packet = json.dumps(update_data).encode('utf-8')
            await self._room_instance.local_participant.publish_data(
                data_packet,
                reliable=True
            )
            
            logger.debug(f"📝 [{self.session_id}] Transcript update sent: {transcript[:50]}...")
        except Exception as e:
            logger.error(f"❌ Error sending transcript update: {e}", exc_info=True)
    
    async def _process_manual_send(self):
        """Process the buffered transcript when manual send is triggered"""
        try:
            async with self.buffer_lock:
                if not self.transcript_buffer:
                    logger.warning(f"[{self.session_id}] Manual send triggered but buffer is empty")
                    return
                
                # Combine all buffered transcripts
                user_text = " ".join(self.transcript_buffer).strip()
                self.transcript_buffer.clear()
            
            if not user_text:
                logger.warning(f"[{self.session_id}] Manual send: empty transcript after joining")
                return
            
            logger.info(f"📤 [{self.session_id}] Processing manual send: '{user_text[:100]}...'")
            
            # Send user's message to frontend
            await self._send_message_to_frontend(user_text, "user")
            
            # Process the message (get response and speak)
            await self._process_user_message(user_text)
            
        except Exception as e:
            logger.error(f"❌ [{self.session_id}] Error processing manual send: {e}", exc_info=True)
    
    async def _process_user_message(self, user_text: str):
        """Common logic to process a user message and generate response"""
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
    
    async def _speak_with_fallback(self, text: str):
        """
        Speak text with TTS fallback. Tries all providers in order.
        If all fail, sends text-only message to user.
        """
        
        if self._all_services_failed:
            logger.warning(f"⚠️ [{self.session_id}] Text-only mode active")
            return
        
        # Build list of providers to try based on current state
        providers_to_try = []
        
        # If fallback is already active, only try fallback
        if self.tts_fallback_active:
            if self.fallback_tts:
                providers_to_try.append(("Google", self.fallback_tts, 1))
        else:
            # Try primary first, then fallback
            if self.primary_tts:
                providers_to_try.append(("Cartesia", self.primary_tts, 0))
            if self.fallback_tts:
                providers_to_try.append(("Google", self.fallback_tts, 1))
        
        # Try each provider
        for provider_name, tts_instance, level in providers_to_try:
            try:
                logger.info(f"🎤 [{self.session_id}] Trying {provider_name} TTS")
                
                # Refresh Google TTS instance before use to prevent decoder issues
                if provider_name == "Google":
                    if not self._refresh_google_tts():
                        logger.error(f"⚠️ [{self.session_id}] Failed to refresh Google TTS instance")
                        continue
                
                # Only do health check for Cartesia (primary) to avoid decoder issues with Google
                if provider_name == "Cartesia":
                    # Pre-validate: Try synthesizing a small test phrase to check if TTS is working
                    # This will catch API errors before we queue the actual message
                    try:
                        test_stream = tts_instance.synthesize("test")
                        # Try to get first chunk to verify connection works
                        await asyncio.wait_for(test_stream.__anext__(), timeout=5.0)
                        logger.debug(f"✅ [{self.session_id}] {provider_name} TTS health check passed")
                    except Exception as health_error:
                        logger.warning(f"⚠️ [{self.session_id}] {provider_name} health check failed: {health_error}")
                        self.tts_error_count += 1
                        # Switch to fallback if this is the primary and we haven't switched yet
                        if level == 0 and not self.tts_fallback_active:
                            self._switch_tts_provider()
                        raise health_error
                else:
                    # For Google TTS, skip health check
                    logger.debug(f"✅ [{self.session_id}] {provider_name} TTS - refreshed instance ready")
                
                # Update the fallback level to track which provider is being used
                self.tts_fallback_level = level
                
                # For Google TTS, use a more aggressive approach
                # Instead of relying on session.say(), manually synthesize
                if provider_name == "Google":
                    try:
                        logger.info(f"🎵 [{self.session_id}] Using manual synthesis for Google TTS to avoid caching")
                        
                        # Get the current TTS instance
                        tts_to_use = self.fallback_tts
                        
                        # Manually trigger synthesis and speech
                        # This bypasses any session-level caching
                        from livekit.agents import tts as tts_module
                        
                        # Create a synthesis stream
                        synthesis_handle = tts_to_use.synthesize(text)
                        
                        # Use the session's play_audio method if available
                        if hasattr(self.session, 'play_audio'):
                            await self.session.play_audio(synthesis_handle)
                            logger.info(f"✅ [{self.session_id}] Manual synthesis completed with {provider_name}")
                            return
                        else:
                            # Fallback: use session.say() but force TTS update first
                            logger.debug(f"[{self.session_id}] play_audio not available, using session.say() with forced update")
                            # Force update all possible references
                            if hasattr(self.session, '_tts'):
                                self.session._tts = tts_to_use
                            if hasattr(self.session, '_agent') and hasattr(self.session._agent, '_tts'):
                                self.session._agent._tts = tts_to_use
                            
                            self.session.say(text)
                            logger.info(f"✅ [{self.session_id}] TTS queued with {provider_name} (fallback)")
                            return
                            
                    except Exception as manual_error:
                        logger.error(f"❌ [{self.session_id}] Manual synthesis failed: {manual_error}", exc_info=True)
                        # Continue to the normal flow as last resort
                        logger.info(f"[{self.session_id}] Trying standard session.say() as last resort")
                
                # For non-Google TTS or as fallback, use standard approach
                # Update the Agent's session TTS instance before using it
                if hasattr(self, 'session') and self.session:
                    # Try multiple ways to update the TTS reference
                    updated = False
                    
                    # Method 1: Update session's _tts
                    if hasattr(self.session, '_tts'):
                        if provider_name == "Google":
                            self.session._tts = self.fallback_tts
                        elif provider_name == "Cartesia":
                            self.session._tts = self.primary_tts
                        updated = True
                        logger.debug(f"[{self.session_id}] Updated session._tts")
                    
                    # Method 2: Update session's _agent._tts if exists
                    if hasattr(self.session, '_agent'):
                        if hasattr(self.session._agent, '_tts'):
                            if provider_name == "Google":
                                self.session._agent._tts = self.fallback_tts
                            elif provider_name == "Cartesia":
                                self.session._agent._tts = self.primary_tts
                            updated = True
                            logger.debug(f"[{self.session_id}] Updated session._agent._tts")
                    
                    if updated:
                        logger.debug(f"✅ [{self.session_id}] TTS reference updated successfully")
                
                # Queue the message using self.session.say()
                self.session.say(text)
                logger.info(f"✅ [{self.session_id}] TTS queued with {provider_name}")
                return  # Success, exit
                
            except Exception as e:
                logger.warning(f"⚠️ [{self.session_id}] {provider_name} TTS failed: {e}")
                # Continue to next provider
                continue
        
        # If we get here, all TTS providers failed
        self._all_services_failed = True
        logger.error(f"❌ [{self.session_id}] All TTS providers failed")
        
        # Send text-only fallback message
        fallback_message = (
            "I apologize, but our voice services are experiencing issues. "
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
        In manual mode, buffers the transcript instead of processing immediately.
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
        
        # Check if manual send mode is enabled
        if not self.auto_send_enabled:
            # Buffer the transcript instead of processing
            async with self.buffer_lock:
                self.transcript_buffer.append(user_text)
                logger.info(f"📝 [{self.session_id}] Buffered transcript (manual mode): '{user_text[:50]}...'")
            
            # Send the transcript to frontend for display
            await self._send_transcript_update(" ".join(self.transcript_buffer))
            
            # Don't process - wait for manual send
            raise StopResponse()
        
        # Auto-send mode: process immediately
        await self._send_message_to_frontend(user_text, "user")
        await self._process_user_message(user_text)
        
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

        @agent_session.on("error")
        def on_agent_error(error_event):
            """Listen for background errors from the agent session."""
            # Extract error details from the event object
            error_type = getattr(error_event, 'type', 'unknown')
            error = getattr(error_event, 'error', error_event)
            
            logger.error(f"💥 [{session_id}] Asynchronous Agent Error Detected - Type: {error_type}, Error: {error}")

            # Check if the error is specifically from the TTS system
            if error_type == "tts" or "tts" in str(error_type).lower() or "tts_error" in str(error):
                # Switch immediately on first error to avoid retries with failed provider
                if not assistant.tts_fallback_active:
                    switched = assistant._switch_tts_provider()
                    if switched:
                        logger.info(f"🔄 [{session_id}] TTS provider switched to fallback immediately.")
                    else:
                        # If switching fails, send a text message to the user
                        async def send_fallback_message():
                            fallback_message = (
                                "I apologize, but our voice services are experiencing issues. "
                                "Please try again shortly."
                            )
                            await assistant._send_message_to_frontend(fallback_message, "system")
                        
                        asyncio.create_task(send_fallback_message())
            
            elif error_type == "stt" or "stt" in str(error_type).lower() or "stt_error" in str(error):
                if not assistant.stt_fallback_active:
                    logger.error(f"💥 [{session_id}] Asynchronous STT Error Detected: {error}")
                    asyncio.create_task(assistant._handle_stt_failure())

        
        # Store room instance
        assistant._room_instance = ctx.room
        
        # Track TTS failures for automatic fallback
        tts_failure_count = 0
        
        # Set up error handlers
        @agent_session.on("agent_speech_interrupted")
        def on_speech_interrupted():
            logger.warning(f"[{session_id}] Agent speech interrupted")
        
        @agent_session.on("agent_speech_committed")  
        def on_speech_committed():
            logger.debug(f"[{session_id}] Agent speech committed")
        
        # Monitor for TTS errors in the background
        # async def monitor_tts_errors():
        #     nonlocal tts_failure_count
        #     while True:
        #         try:
        #             await asyncio.sleep(5)  # Check every 5 seconds
        #             # If we've had multiple failures, try switching
        #             if tts_failure_count > 2 and assistant.tts_fallback_level == 0:
        #                 logger.warning(f"[{session_id}] Multiple TTS failures detected, switching to fallback")
        #                 assistant._switch_tts_provider()
        #                 tts_failure_count = 0
        #         except asyncio.CancelledError:
        #             break
        #         except Exception as e:
        #             logger.error(f"Error in TTS monitor: {e}")
        
        # # Start TTS error monitor
        # monitor_task = asyncio.create_task(monitor_tts_errors())
            
        await agent_session.start(room=ctx.room, agent=assistant)

        # Start the session
        await agent_session.start(room=ctx.room, agent=assistant)
        
        logger.info(f"=== 🚀 SESSION {session_id} STARTED ===")
        
        # Send initial greeting
        try:
            greeting_response = await assistant._get_backend_response("__INITIAL_GREETING__")
            await assistant._speak_with_fallback(greeting_response)
            logger.info(f"✅ [{session_id}] Initial greeting sent")
        except Exception as greeting_error:
            logger.error(f"[{session_id}] Error sending greeting: {greeting_error}")
            await assistant._speak_with_fallback("Hello! I'm Noyco, your voice assistant. How can I help you today?")
        
        logger.info(f"🎯 [{session_id}] Listening for user speech...")
        
        # Set up data channel listener for control messages
        @ctx.room.on("data_received")
        def on_data_received(data: rtc.DataPacket):
            """Handle data channel messages from frontend"""
            try:
                payload = data.data.decode('utf-8')
                message = json.loads(payload)
                message_type = message.get('type')
                
                logger.info(f"📨 [{session_id}] Received data: {message_type}")
                
                if message_type == 'toggle_auto_send':
                    # Toggle auto-send mode
                    new_state = message.get('enabled', True)
                    assistant.auto_send_enabled = new_state
                    logger.info(f"🔄 [{session_id}] Auto-send mode: {new_state}")
                    
                    # Clear buffer if switching to auto mode
                    if new_state:
                        asyncio.create_task(_clear_buffer())
                
                elif message_type == 'manual_send':
                    # Process buffered transcript
                    logger.info(f"📤 [{session_id}] Manual send triggered")
                    asyncio.create_task(assistant._process_manual_send())
                
                elif message_type == 'user_message':
                    # Direct message from frontend (alternative path)
                    text = message.get('text', '').strip()
                    if text:
                        logger.info(f"💬 [{session_id}] Direct message from frontend: '{text[:50]}...'")
                        asyncio.create_task(_handle_direct_message(text))
                
            except json.JSONDecodeError:
                logger.warning(f"[{session_id}] Invalid JSON in data packet")
            except Exception as e:
                logger.error(f"[{session_id}] Error processing data: {e}", exc_info=True)
        
        async def _clear_buffer():
            """Clear the transcript buffer"""
            async with assistant.buffer_lock:
                assistant.transcript_buffer.clear()
                logger.info(f"🗑️ [{session_id}] Transcript buffer cleared")
        
        async def _handle_direct_message(text: str):
            """Handle direct message from frontend"""
            try:
                await assistant._send_message_to_frontend(text, "user")
                await assistant._process_user_message(text)
            except Exception as e:
                logger.error(f"[{session_id}] Error handling direct message: {e}", exc_info=True)
        
        # Wait for disconnection
        disconnected_event = asyncio.Event()
        
        @ctx.room.on("disconnected")
        def on_disconnected():
            logger.info(f"🚪 [{session_id}] Room disconnected")
            disconnected_event.set()
        
        # Keep session alive
        await disconnected_event.wait()
        
        logger.info(f"🛑 [{session_id}] Starting graceful shutdown...")
        
        # Note: monitor_task was removed - TTS refresh happens per-request instead
        
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
