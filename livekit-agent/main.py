"""
Noyco Voice Agent - Production Version
Based on LiveKit Agents v1.2+ API
Properly handles user speech by overriding on_user_turn_completed
Uses WebSocket for real-time communication with backend
"""
import asyncio
import logging
import json
import aiohttp
import websockets

from livekit import agents, rtc
from livekit.agents import (
    Agent,
    AgentSession,
    JobContext,
    WorkerOptions,
    cli,
    llm as llm_module,
    StopResponse,
    utils,
)
from livekit.plugins import deepgram, elevenlabs, silero

from config import get_settings

# Load settings
settings = get_settings()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class NoycoAssistant(Agent):
    """
    Noyco Voice Assistant that intercepts user messages
    and routes them to Noyco backend via WebSocket
    """
    
    def __init__(self, session_data: dict, backend_url: str, ws_url: str):
        self.session_data = session_data
        self.backend_url = backend_url
        self.ws_url = ws_url
        self.websocket = None
        self.ws_connected = False
        self.ws_lock = asyncio.Lock()
        self.audio_source = None  # For typing sound playback
        
        # Get ElevenLabs API key from settings
        elevenlabs_key = settings.ELEVENLABS_API_KEY
        
        # Initialize the base Agent
        super().__init__(
            instructions="You are Noyco, a helpful and empathetic AI voice assistant.",
            stt=deepgram.STT(
                model=settings.STT_MODEL,
                language=settings.STT_LANGUAGE,
                interim_results=settings.STT_INTERIM_RESULTS,
                smart_format=settings.STT_SMART_FORMAT,          # Better punctuation and formatting
                punctuate=settings.STT_PUNCTUATE,                # Add punctuation
            ),
            llm=elevenlabs.TTS(api_key=elevenlabs_key),
            tts=elevenlabs.TTS(api_key=elevenlabs_key),
        )
        
        logger.info(f"✅ NoycoAssistant initialized for session: {session_data.get('session_id')}")
    
    async def connect_websocket(self):
        """Establish WebSocket connection to backend"""
        async with self.ws_lock:
            if self.ws_connected and self.websocket:
                return True
            
            try:
                session_id = self.session_data.get("session_id")
                if not session_id:
                    logger.warning("No session_id available for WebSocket connection")
                    return False
                
                ws_endpoint = f"{self.ws_url}/api/v1/voice/ws/voice-session/{session_id}"
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
                        logger.info(f"✅ WebSocket connected for session: {session_id}")
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
    
    async def _send_typing_indicator(self):
        """Send typing indicator to indicate processing (visual feedback if supported)"""
        try:
            # Send typing indicator through the session if available
            # This can be picked up by the frontend to show a "thinking" animation
            if hasattr(self.session, 'emit_metadata'):
                await self.session.emit_metadata({"typing": True})
            
            # Keep indicator active while processing
            await asyncio.sleep(0.1)  # Small delay to ensure it's sent
                    
        except Exception as e:
            logger.debug(f"Typing indicator error (non-critical): {e}")
    
    async def on_user_turn_completed(
        self, 
        turn_ctx: llm_module.ChatContext, 
        new_message: llm_module.ChatMessage
    ) -> None:
        """
        Called when the user finishes speaking.
        This is where we intercept user input and send it to our backend.
        """
        # Extract user's text
        user_text = new_message.text_content
        
        if not user_text or not user_text.strip():
            logger.warning("Empty user message received")
            raise StopResponse()  # Don't generate a response
        
        logger.info(f"🗣️ User said: '{user_text}'")
        logger.info("⏳ Processing response...")
        
        try:
            # Start typing indicator in background
            typing_task = asyncio.create_task(self._send_typing_indicator())
            
            try:
                # Get response from Noyco backend
                response_text = await self._get_backend_response(user_text)
            finally:
                # Stop typing indicator
                typing_task.cancel()
                try:
                    await typing_task
                except asyncio.CancelledError:
                    pass
                
                # Send typing stopped indicator
                try:
                    if hasattr(self.session, 'emit_metadata'):
                        await self.session.emit_metadata({"typing": False})
                except:
                    pass
            
            if response_text and response_text.strip():
                logger.info(f"⬅️ Backend response: {response_text[:100]}...")
                # Use session.say() to speak the response
                self.session.say(response_text)
            else:
                logger.warning("Empty response from backend")
                self.session.say("I'm processing that. Could you tell me more?")
        
        except Exception as e:
            logger.error(f"Error getting backend response: {e}", exc_info=True)
            self.session.say("I'm having trouble right now. Could you try again?")
        
        # Stop the default LLM response since we handled it
        raise StopResponse()
    
    async def _get_backend_response(self, user_text: str) -> str:
        """Get response from Noyco backend via WebSocket (with HTTP fallback)"""
        
        # Try WebSocket first
        if self.ws_connected and self.websocket:
            try:
                logger.info(f"➡️ Sending via WebSocket: '{user_text[:100]}...'")
                
                # Send message via WebSocket
                await self.websocket.send(json.dumps({
                    "type": "user_message",
                    "text": user_text
                }))
                
                # Wait for response with timeout
                response = await asyncio.wait_for(
                    self.websocket.recv(), 
                    timeout=settings.BACKEND_RESPONSE_TIMEOUT
                )
                data = json.loads(response)
                
                if data.get("type") == "assistant_response":
                    assistant_response = data.get("text", "")
                    if assistant_response and assistant_response.strip():
                        logger.info(f"⬅️ WebSocket response: {assistant_response[:100]}...")
                        return assistant_response
                    else:
                        logger.warning("WebSocket returned empty response")
                elif data.get("type") == "error":
                    error_msg = data.get("message", "Unknown error")
                    logger.error(f"WebSocket error: {error_msg}")
                    # Fall through to HTTP
                else:
                    logger.warning(f"Unexpected WebSocket message type: {data.get('type')}")
                    # Fall through to HTTP
                    
            except asyncio.TimeoutError:
                logger.warning("WebSocket response timeout, falling back to HTTP")
                self.ws_connected = False
            except websockets.exceptions.ConnectionClosed:
                logger.warning("WebSocket connection closed, falling back to HTTP")
                self.ws_connected = False
                self.websocket = None
            except Exception as e:
                logger.error(f"WebSocket error: {e}, falling back to HTTP")
                self.ws_connected = False
        
        # HTTP fallback (or primary if WebSocket not connected)
        try:
            payload = {
                "session_id": self.session_data.get("session_id"),
                "text": user_text,
                "conversation_id": self.session_data.get("conversation_id"),
                "individual_id": self.session_data.get("individual_id"),
                "user_profile_id": self.session_data.get("user_profile_id"),
            }
            
            logger.info(f"➡️ Sending via HTTP: '{user_text[:100]}...'")
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.backend_url}/api/v1/voice/voice-message",
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=settings.HTTP_REQUEST_TIMEOUT)
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        
                        if result.get("status") == "success":
                            assistant_response = result.get("assistant_response", "")
                            
                            if assistant_response and assistant_response.strip():
                                logger.info(f"⬅️ HTTP response: {assistant_response[:100]}...")
                                return assistant_response
                            else:
                                logger.warning("Backend returned empty response")
                                return "I'm processing that. Could you tell me more?"
                        else:
                            error_msg = result.get("error", "Unknown error")
                            logger.error(f"Backend error: {error_msg}")
                            return "I encountered an issue. Could you repeat that?"
                    else:
                        error_text = await response.text()
                        logger.error(f"Backend HTTP error: {response.status} - {error_text}")
                        return "I'm having trouble right now. Could you try again?"
                                
        except asyncio.TimeoutError:
            logger.error("Backend request timed out")
            return "I need a moment. Could you say that again?"
        except Exception as e:
            logger.error(f"Error getting backend response: {e}", exc_info=True)
            return "I ran into an issue. Let's try again."


async def entrypoint(ctx: JobContext):
    """Main entrypoint for Noyco LiveKit Agent"""
    
    # Check API keys from settings
    deepgram_key = settings.DEEPGRAM_API_KEY
    elevenlabs_key = settings.ELEVENLABS_API_KEY
    backend_url = settings.NOYCO_BACKEND_URL
    ws_url = settings.NOYCO_WS_URL
    
    if not all([deepgram_key, elevenlabs_key]):
        raise ValueError("Missing required API keys for Deepgram or ElevenLabs")
    
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
    
    # Fallback: Try to fetch session data from backend if not in metadata
    if not session_data or not session_data.get("session_id"):
        logger.warning("⚠️ No valid session data in metadata, attempting to fetch from backend")
        room_name = ctx.room.name
        if room_name.startswith("voice_room_"):
            extracted_session_id = room_name.replace("voice_room_", "")
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(
                        f"{backend_url}/api/v1/voice/voice-sessions/{extracted_session_id}",
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
    
    logger.info(f"📋 Final session data: {session_data}")
    
    # Create the assistant
    assistant = NoycoAssistant(session_data, backend_url, ws_url)
    
    # Connect WebSocket before starting
    await assistant.connect_websocket()
    
    # Create AgentSession with VAD for turn detection
    # Configure VAD with longer patience to allow natural pauses in speech
    session = AgentSession(
        vad=silero.VAD.load(
            min_speech_duration=settings.VAD_MIN_SPEECH_DURATION,
            min_silence_duration=settings.VAD_MIN_SILENCE_DURATION,
            padding_duration=settings.VAD_PADDING_DURATION,
            activation_threshold=settings.VAD_ACTIVATION_THRESHOLD,
        ),
        turn_detection="vad",  # Use VAD for turn detection
    )
    
    logger.info("=== 🤖 NOYCO VOICE AGENT INITIALIZED ===")
    logger.info(f"✅ STT: Deepgram Nova-2")
    logger.info(f"✅ TTS: ElevenLabs")
    logger.info(f"✅ VAD: Silero")
    logger.info(f"✅ Backend: {backend_url}")
    logger.info(f"✅ Session ID: {session_data.get('session_id', 'Unknown')}")
    
    try:
        # Start the session
        await session.start(room=ctx.room, agent=assistant)
        
        logger.info("=== 🚀 SESSION STARTED ===")
        
        # Send initial greeting
        try:
            greeting_response = await assistant._get_backend_response("__INITIAL_GREETING__")
            session.say(greeting_response)
            logger.info("✅ Initial greeting sent")
        except Exception as greeting_error:
            logger.error(f"Error sending greeting: {greeting_error}")
            session.say("Hello! I'm Noyco, your voice assistant. How can I help you today?")
        
        logger.info("🎯 Listening for user speech...")
        
        # Wait for disconnection
        disconnected_future = asyncio.Future()
        
        @ctx.room.on("disconnected")
        def on_disconnected():
            logger.info("🚪 Room disconnected")
            if not disconnected_future.done():
                disconnected_future.set_result(True)
        
        await disconnected_future
        
    except Exception as e:
        logger.error(f"Session error: {e}", exc_info=True)
    finally:
        # Close WebSocket connection
        await assistant.close_websocket()
        logger.info("🛑 Session ended")


if __name__ == "__main__":
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint))
