
# #  , first consume this endpoint it will handle the incoming call untill user intent is not getting detected_intent , if detected_intent is null then let incoming call talk to this use respososne to send to user , if intent is gettinf detected then only  
# # http://localhost:8000/initial/chat

# # response will be like this 

# # `` {
# #   "response": "That's fantastic to hear! Quitting smoking is a huge step, and I admire your willingness to take it on. It's definitely not easy, but it's so worth it for your health and well-being.\n\nWhat's making you want to quit right now? And how are you feeling about the whole process? Excited, nervous, maybe a bit of both?",
# #   "detected_intent": "accountability",
# #   "confidence": 0.95,
# #   "selected_agent": "accountability_buddy",
# #   "selected_agent_name": "Accountability Buddy",
# #   "should_route": true,
# #   "conversation_turn": 1,
# #   "needs_more_conversation": false
# # }  ``\
    
    
    
    
    
    
""" Twilio controller for handling call management and tracking - Cleaned Version """

from typing import Dict, Optional, Set, Deque, List, Any, AsyncGenerator
from datetime import datetime
import logging
import json
import base64
import asyncio
from collections import deque
import time
import uuid

from twilio.rest import Client
from twilio.base.exceptions import TwilioException
from twilio.twiml.voice_response import VoiceResponse, Connect
from fastapi import Request, WebSocket, WebSocketDisconnect, Response, BackgroundTasks
import orjson
import logging
import uuid
import asyncio
import time
import base64
from contextlib import suppress
import threading
import httpx
from concurrent.futures import ThreadPoolExecutor

from ..config import settings
from ..schema import CallRecord, CallStatus
from ..services.userVerification import UserVerificationService

# Configure logging
logger = logging.getLogger(__name__)

# Voice Activity Detection thresholds
VAD_SILENCE_THRESHOLD = 80
VAD_SPEECH_THRESHOLD = 250
VAD_MIN_SPEECH_DURATION = 0.3
VAD_PAUSE_THRESHOLD = 1.2
VAD_END_UTTERANCE_THRESHOLD = 2.0


class EnhancedAudioBuffer:
    """Advanced audio buffer with continuous streaming and improved VAD"""

    def __init__(self):
        self.buffer = bytearray()
        self.chunks = deque()
        
        # Audio format constants
        self.sample_rate = 8000
        self.bytes_per_second = self.sample_rate
        
        # Configurable buffer size (10 seconds max)
        self.max_duration = 10.0
        self.max_bytes = int(self.max_duration * self.bytes_per_second)
        
        # VAD state tracking
        self.last_activity_time = time.time()
        self.speech_ongoing = False
        self.speech_start_time = None
        self.silence_start_time = None
        self.vad_state = "SILENCE"
        
        # Speech segments for more accurate transcription
        self.current_segment = bytearray()
        self.completed_segments = []
        
        # Energy tracking for dynamic VAD
        self.energy_levels = deque(maxlen=20)
        self.background_noise_level = 50

    def add_chunk(self, chunk: bytes) -> dict:
        """Add audio chunk and return speech state information"""
        current_time = time.time()
        chunk_size = len(chunk)
        
        # Add to main buffer with truncation to max size
        self.buffer.extend(chunk)
        if len(self.buffer) > self.max_bytes:
            excess = len(self.buffer) - self.max_bytes
            self.buffer = self.buffer[excess:]
        
        # Store chunk with timestamp
        self.chunks.append((chunk, current_time))
        
        # Remove old chunks
        while self.chunks and current_time - self.chunks[0][1] > self.max_duration:
            self.chunks.popleft()
            
        # Add to current segment
        self.current_segment.extend(chunk)
        
        # Update energy tracking
        energy = chunk_size if chunk_size > 0 else 1
        self.energy_levels.append(energy)
        
        # Dynamically adjust noise level
        if len(self.energy_levels) >= 10:
            sorted_levels = sorted(self.energy_levels)
            lowest_values = sorted_levels[:3]
            if lowest_values:
                avg_low = sum(lowest_values) / len(lowest_values)
                self.background_noise_level = (0.95 * self.background_noise_level + 0.05 * avg_low)
        
        # Determine VAD thresholds based on background noise
        silence_threshold = max(VAD_SILENCE_THRESHOLD, self.background_noise_level * 1.5)
        speech_threshold = max(VAD_SPEECH_THRESHOLD, self.background_noise_level * 3)
        
        # Voice Activity Detection state machine
        is_silent = chunk_size < silence_threshold
        is_speech = chunk_size > speech_threshold
        
        result = {
            "state": self.vad_state,
            "segment_ready": False,
            "should_process": False,
            "is_final": False
        }
        
        # VAD state transitions
        if self.vad_state == "SILENCE":
            if is_speech:
                self.vad_state = "POTENTIAL_SPEECH"
                self.speech_start_time = current_time
            
        elif self.vad_state == "POTENTIAL_SPEECH":
            if is_speech:
                if current_time - self.speech_start_time > VAD_MIN_SPEECH_DURATION:
                    self.vad_state = "SPEECH"
                    self.speech_ongoing = True
                    self.last_activity_time = current_time
                    logger.debug("VAD: Speech detected")
            elif is_silent:
                self.vad_state = "SILENCE"
                
        elif self.vad_state == "SPEECH":
            if is_speech:
                self.last_activity_time = current_time
            elif is_silent:
                self.vad_state = "POTENTIAL_SILENCE"
                self.silence_start_time = current_time
                
        elif self.vad_state == "POTENTIAL_SILENCE":
            silence_duration = current_time - self.silence_start_time
            
            if is_speech:
                self.vad_state = "SPEECH"
                self.last_activity_time = current_time
            elif silence_duration > VAD_END_UTTERANCE_THRESHOLD:
                self.vad_state = "SILENCE"
                self.speech_ongoing = False
                
                if len(self.current_segment) > 0:
                    self.completed_segments.append(bytes(self.current_segment))
                    self.current_segment = bytearray()
                    result["segment_ready"] = True
                    result["is_final"] = True
                    result["should_process"] = True
                    
            elif silence_duration > VAD_PAUSE_THRESHOLD:
                if len(self.current_segment) > self.bytes_per_second:
                    self.completed_segments.append(bytes(self.current_segment))
                    self.current_segment = bytearray()
                    result["segment_ready"] = True
                    result["should_process"] = True
        
        result["state"] = self.vad_state
        return result

    def get_audio_data(self, segment_index: int = -1) -> bytes:
        """Get audio data from completed segments or current buffer"""
        if segment_index is None:
            return bytes(self.buffer)
        
        if self.completed_segments:
            if segment_index == -1:
                return self.completed_segments[-1]
            elif 0 <= segment_index < len(self.completed_segments):
                return self.completed_segments[segment_index]
                
        return b''
        
    def get_all_segments(self) -> bytes:
        """Get all completed segments concatenated"""
        if not self.completed_segments:
            return b''
        return b''.join(self.completed_segments)
    
    def clear_segments(self):
        """Clear completed segments"""
        self.completed_segments = []
        
    def clear(self):
        """Clear all audio data"""
        self.buffer = bytearray()
        self.chunks.clear()
        self.current_segment = bytearray()
        self.completed_segments = []
        self.vad_state = "SILENCE"
        self.speech_ongoing = False


class SpeechRecognitionManager:
    """Manages continuous speech recognition with partial and final results"""
    
    def __init__(self):
        self.current_partial_text = ""
        self.accumulated_text = ""
        self.finalized_segments = []
        self.partial_segments = []
        self.segment_confidences = []
        self.stable_text_length = 0
        self.last_update_time = time.time()
        self.utterance_start_time = None
    
    async def process_audio_segment(self, audio_data: bytes, 
                                   stt_service, is_final: bool = False) -> dict:
        """Process audio segment and return transcription results"""
        result = {
            "text": "",
            "is_final": False,
            "confidence": 0.0,
            "stability": 0.0,
            "updated": False
        }
        
        if not audio_data or len(audio_data) < 100:
            return result
            
        try:
            transcript = await stt_service.transcribe_audio(audio_data, is_final=is_final)
            
            if not transcript or not transcript.text:
                return result
                
            text = transcript.text.strip()
            confidence = getattr(transcript, 'confidence', 0.8)
            
            if is_final:
                self._add_finalized_segment(text, confidence)
                result["is_final"] = True
                result["updated"] = True
            else:
                updated = self._update_partial_segment(text, confidence)
                result["updated"] = updated
                
            result["text"] = self.get_current_transcription()
            result["confidence"] = confidence
            result["stability"] = self._calculate_stability()
            
            return result
            
        except Exception as e:
            logger.error(f"Speech recognition error: {str(e)}")
            return result
    
    def _add_finalized_segment(self, text: str, confidence: float):
        """Add a finalized transcription segment"""
        if not text:
            return
            
        self.finalized_segments.append(text)
        self.segment_confidences.append(confidence)
        
        if not self.accumulated_text:
            self.accumulated_text = text
        else:
            self.accumulated_text = self._merge_text(self.accumulated_text, text)
            
        self.current_partial_text = ""
        self.partial_segments = []
        self.stable_text_length = len(self.accumulated_text)
        self.last_update_time = time.time()
    
    def _update_partial_segment(self, text: str, confidence: float) -> bool:
        """Update partial transcription segment, return True if updated"""
        if not text or text == self.current_partial_text:
            return False
            
        if self._is_better_partial(text, self.current_partial_text):
            self.current_partial_text = text
            self.partial_segments.append(text)
            self.last_update_time = time.time()
            
            if len(self.partial_segments) > 5:
                self.partial_segments = self.partial_segments[-5:]
                
            return True
            
        return False
    
    def _is_better_partial(self, new_text: str, current_text: str) -> bool:
        """Determine if new partial text is better than current"""
        if len(new_text) > len(current_text) * 1.2:
            return True
            
        if current_text and new_text and len(new_text) > 10:
            words_current = set(current_text.lower().split())
            words_new = set(new_text.lower().split())
            common_words = words_current.intersection(words_new)
            
            if len(common_words) >= len(words_current) * 0.7 and len(words_new) > len(words_current):
                return True
        
        return False
    
    def _calculate_stability(self) -> float:
        """Calculate stability of current transcription (0-1)"""
        if not self.partial_segments:
            return 1.0
            
        if len(self.partial_segments) >= 3:
            last_segments = self.partial_segments[-3:]
            if all(len(s) > 0 for s in last_segments):
                words_sets = [set(s.lower().split()) for s in last_segments]
                
                if len(words_sets) >= 2 and all(len(s) > 0 for s in words_sets):
                    similarities = []
                    for i in range(len(words_sets) - 1):
                        for j in range(i + 1, len(words_sets)):
                            intersection = len(words_sets[i].intersection(words_sets[j]))
                            union = len(words_sets[i].union(words_sets[j]))
                            if union > 0:
                                similarities.append(intersection / union)
                    
                    if similarities:
                        return sum(similarities) / len(similarities)
        
        time_since_update = time.time() - self.last_update_time
        return min(time_since_update / 2.0, 1.0)
    
    def _merge_text(self, base_text: str, new_text: str) -> str:
        """Intelligently merge base text with new text to avoid repetition"""
        if not base_text:
            return new_text
        if not new_text:
            return base_text
            
        base_words = base_text.split()
        new_words = new_text.split()
        
        for overlap_size in range(min(len(base_words), len(new_words), 5), 1, -1):
            if base_words[-overlap_size:] == new_words[:overlap_size]:
                return " ".join(base_words + new_words[overlap_size:])
        
        return f"{base_text} {new_text}"
    
    def get_current_transcription(self) -> str:
        """Get current transcription (accumulated + partial)"""
        if not self.accumulated_text and not self.current_partial_text:
            return ""
        if not self.current_partial_text:
            return self.accumulated_text
        if not self.accumulated_text:
            return self.current_partial_text
        return self._merge_text(self.accumulated_text, self.current_partial_text)
        
    def reset(self):
        """Reset transcription state"""
        self.current_partial_text = ""
        self.accumulated_text = ""
        self.finalized_segments = []
        self.partial_segments = []
        self.segment_confidences = []
        self.stable_text_length = 0
        self.last_update_time = time.time()
        self.utterance_start_time = None


class IncomingController:
    """Controller for managing Twilio voice calls with ultra-low latency streaming"""

    def __init__(self):
        """Initialize Twilio client with optimized settings"""
        self.client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
        self.call_records: Dict[str, CallRecord] = {}
        self.active_calls: Dict[str, Dict] = {}
        self.call_context: Dict[str, Dict] = {}

        # Ultra-low latency settings
        self.min_audio_chunk_size = 160
        self.processing_timeout = 2.5
        self.max_concurrent_processing = 4

        # Thread pool for CPU-intensive operations
        self.thread_pool = ThreadPoolExecutor(max_workers=4)

        # Processing state tracking
        self.processing_tasks: Dict[str, Set[asyncio.Task]] = {}
        self.call_locks: Dict[str, asyncio.Lock] = {}
        
        # Initialize user verification service
        self.user_verification_service = UserVerificationService()

    async def handle_voice_call(self, request: Request) -> Response:
        """Handle incoming and outgoing voice calls using Twilio TwiML"""
        try:
            # Extract query parameters
            query = dict(request.query_params)
            user_profile_id = query.get("user_profile_id")
            created_by = query.get("created_by")
            agent_instance_id = query.get("agent_instance_id")
            conversation_id = query.get("conversation_id")
        
            # Parse Twilio webhook data
            form_data = await request.form()
            call_data = dict(form_data)
            call_sid = call_data.get('CallSid', '')
            from_number = call_data.get("From", "")
            call_direction = call_data.get("Direction", "").lower()
        
            if not call_sid:
                raise ValueError("Missing CallSid in webhook data")
        
            is_outbound = call_direction == "outbound-api"
            logger.info(f"Processing {call_direction} call {call_sid} for user_profile: {user_profile_id}")
        
            # Create call record in background
            background_tasks = BackgroundTasks()
            background_tasks.add_task(self.create_call_record, call_data)

            # Initialize call context
            self._initialize_call_context(call_sid, user_profile_id, created_by, agent_instance_id, conversation_id)

            response = VoiceResponse()
        
            if is_outbound:
                await self._handle_outbound_call(response, call_sid, user_profile_id, 
                                               created_by, agent_instance_id, conversation_id)
            else:
                verification_result = await self._handle_incoming_call(response, call_sid, from_number)
                if not verification_result:
                    return Response(
                        content=str(response), 
                        media_type='application/xml',
                        background=background_tasks
                    )
        
            # Add speech gathering for continued conversation
            self._add_speech_gather(response, call_sid, user_profile_id, created_by, 
                                   agent_instance_id, conversation_id)
        
            # Fallback message if no response
            response.say(
                "I didn't hear anything. Please call back if you need assistance.",
                voice="Polly.Joanna-Neural",
                language="en-US"
            )
            response.hangup()

            return Response(
                content=str(response), 
                media_type='application/xml',
                background=background_tasks
            )

        except Exception as e:
            logger.error(f"Error handling voice call: {str(e)}")
            response = VoiceResponse()
            response.say("Sorry, we're experiencing technical difficulties. Please try again later.")
            response.hangup()
            return Response(content=str(response), media_type='application/xml')

    def _initialize_call_context(self, call_sid: str, user_profile_id: str, 
                                created_by: str, agent_instance_id: str, conversation_id: str):
        """Initialize call context and active call data"""
        self.active_calls[call_sid] = {
            "call_sid": call_sid,
            "last_activity": time.time(),
            "conversation_context": [],
            "user_profile_id": user_profile_id,
            "created_by": created_by,
            "agent_instance_id": agent_instance_id,
            "conversation_id": conversation_id,
            "intent_detected": False,
            "detected_intent": None,
            "using_orchestrator": False
        }

    async def _handle_outbound_call(self, response: VoiceResponse, call_sid: str, 
                                   user_profile_id: str, created_by: str, 
                                   agent_instance_id: str, conversation_id: str):
        """Handle outbound call with personalized greeting"""
        try:
            # Generate personalized greeting
            dummy_query = "Start the conversation by greeting patient and cover the checkpoints."
            personalized_greeting = await self._generate_chatbot_response(
                dummy_query, user_profile_id, created_by, agent_instance_id, 
                conversation_id, call_sid, is_incoming_call=False
            )
        
            response.say(
                personalized_greeting,
                voice="Polly.Joanna-Neural",
                language="en-US"
            )
        
            # Update conversation context
            self.active_calls[call_sid]["conversation_context"].append({
                "assistant": personalized_greeting,
                "timestamp": time.time()
            })
        
            logger.info(f"Outbound call {call_sid} started with personalized greeting")
        
        except Exception as e:
            logger.error(f"Error generating personalized greeting: {str(e)}")
            # Fallback greeting
            fallback_message = "Hello! This is your AI assistant calling you."
            response.say(
                fallback_message,
                voice="Polly.Joanna-Neural",
                language="en-US"
            )
        
            self.active_calls[call_sid]["conversation_context"].append({
                "assistant": fallback_message,
                "timestamp": time.time()
            })

    async def _handle_incoming_call(self, response: VoiceResponse, call_sid: str, from_number: str) -> bool:
        """Handle incoming call with user verification. Returns True if call should continue."""
        logger.info(f"Incoming call from: {from_number}")
    
        # Verify user
        verification_result = await self.user_verification_service.verify_user_by_phone(from_number)
    
        if not verification_result["verified"]:
            logger.info(f"User verification failed for {from_number}: {verification_result['message']}")
        
            # Determine appropriate message
            if verification_result["user_exists"]:
                message = self.user_verification_service.get_premium_plan_message()
            else:
                message = self.user_verification_service.get_user_not_found_message()
        
            response.say(message, voice="Polly.Joanna-Neural", language="en-US")
            response.hangup()
        
            # Update context and return False to terminate call
            self.active_calls[call_sid]["conversation_context"].append({
                "assistant": message,
                "timestamp": time.time(),
                "verification_failed": True
            })
        
            return False
    
        # User verified - proceed with greeting
        logger.info(f"User verified: {from_number}")
    
        # Store verified user profile
        self.active_calls[call_sid]["verified_user_profile"] = verification_result["user_profile"]
    
        greeting = "Hello! I'm your AI assistant. How can I help you today?"
        response.say(greeting, voice="Polly.Joanna-Neural", language="en-US")
    
        self.active_calls[call_sid]["conversation_context"].append({
            "assistant": greeting,
            "timestamp": time.time(),
            "user_verified": True
        })
    
        return True

    def _add_speech_gather(self, response: VoiceResponse, call_sid: str, 
                          user_profile_id: str, created_by: str, 
                          agent_instance_id: str, conversation_id: str):
        """Add speech gathering capability to TwiML response"""
        gather = response.gather(
            input="speech",
            action=f"{settings.TWILIO_BASE_WEBHOOK_URL}/phone/gather-response?call_sid={call_sid}&user_profile_id={user_profile_id}&created_by={created_by}&agent_instance_id={agent_instance_id}&conversation_id={conversation_id}",
            method="POST",
            timeout=5,
            speechTimeout="auto",
            language="en-US",
            enhanced=True,
            speechModel="phone_call"
        )

    async def handle_gather_response(self, request: Request) -> Response:
        """Handle user speech input from Twilio's <Gather> verb"""
        try:
            # Get call_sid from query params
            call_sid = request.query_params.get("call_sid")
            
            # Get form data
            form_data = await request.form()
            call_data = dict(form_data)
            
            # If call_sid not in query params, try to get it from form data
            if not call_sid:
                call_sid = call_data.get("CallSid")
            
            # Get or retrieve context parameters
            call_context = self._get_call_context(call_sid, request.query_params)
            user_profile_id = call_context["user_profile_id"]
            created_by = call_context["created_by"]
            agent_instance_id = call_context["agent_instance_id"]
            conversation_id = call_context["conversation_id"]
            
            # Check if this is an orchestrator mode redirect (after "please wait" message)
            orchestrator_mode = request.query_params.get("orchestrator_mode")
            if orchestrator_mode == "true":
                logger.info(f"Processing orchestrator mode request for call {call_sid}")
                return await self._handle_orchestrator_mode_response(
                    call_sid, user_profile_id, created_by, agent_instance_id, conversation_id
                )
    
            speech_result = call_data.get("SpeechResult")
            logger.info(f"Received speech input for call {call_sid}: '{speech_result}'")
            
            response = VoiceResponse()
            
            # Handle empty or very short input
            if not speech_result or len(speech_result.strip()) < 3:
                response.say(
                    "I didn't catch that clearly. Could you please repeat?",
                    voice="Polly.Joanna-Neural",
                    language="en-US"
                )
                self._add_speech_gather(response, call_sid, user_profile_id, created_by, 
                                       agent_instance_id, conversation_id)
                return Response(content=str(response), media_type='application/xml')
            
            # Update conversation context with user input
            self._update_conversation_context(call_sid, speech_result, "user")
            
            # Generate response using the two-stage approach for incoming calls
            try:
                chatbot_response = await self._generate_chatbot_response(
                    speech_result, user_profile_id, created_by, agent_instance_id, 
                    conversation_id, call_sid, is_incoming_call=True
                )
                
                # Check if this is a "please wait" message (indicating pending orchestrator request)
                call_data = self.active_calls.get(call_sid)
                if (call_data and call_data.get("pending_orchestrator_request") and 
                    chatbot_response.startswith("Please wait")):
                    
                    logger.info(f"Playing 'please wait' message and preparing orchestrator redirect for call {call_sid}")
                    
                    # Play the "please wait" message
                    response.say(
                        chatbot_response,
                        voice="Polly.Joanna-Neural",
                        language="en-US"
                    )
                    
                    # Add a small pause to let the message finish
                    response.pause(length=1)
                    
                    # Redirect to the SAME endpoint but with orchestrator_mode=true
                    redirect_url = f"{settings.TWILIO_BASE_WEBHOOK_URL}/phone/gather-response?call_sid={call_sid}&user_profile_id={user_profile_id}&created_by={created_by}&agent_instance_id={agent_instance_id}&conversation_id={conversation_id}&orchestrator_mode=true"
                    response.redirect(redirect_url, method="POST")
                    
                    return Response(content=str(response), media_type='application/xml')
                
                # Normal response flow
                # Update conversation context with assistant response
                self._update_conversation_context(call_sid, chatbot_response, "assistant")
       
                # Generate TwiML response
                response.say(
                    chatbot_response,
                    voice="Polly.Joanna-Neural",
                    language="en-US"
                )
                
                # Set up another gather for continued conversation
                self._add_speech_gather(response, call_sid, user_profile_id, created_by, 
                                       agent_instance_id, conversation_id)
                
                # Add fallback in case user doesn't respond
                response.say(
                    "I didn't hear anything. Goodbye!",
                    voice="Polly.Joanna-Neural",
                    language="en-US"
                )
                response.hangup()
                
            except Exception as e:
                logger.error(f"Error generating chatbot response: {str(e)}")
                response.say(
                    "I'm sorry, but I'm having trouble processing your request right now. Please try again later.",
                    voice="Polly.Joanna-Neural",
                    language="en-US"
                )
                response.hangup()
                
            return Response(content=str(response), media_type='application/xml')
                
        except Exception as e:
            logger.error(f"Error handling gather response: {str(e)}")
            response = VoiceResponse()
            response.say(
                "I apologize, but I encountered a technical issue. Please try calling again.",
                voice="Polly.Joanna-Neural",
                language="en-US"
            )
            response.hangup()
            return Response(content=str(response), media_type='application/xml')

    def _get_call_context(self, call_sid: str, query_params):
        """Get or retrieve call context parameters"""
        if call_sid in self.call_context:
            return self.call_context[call_sid]
        
        # Get from query params and store
        context = {
            "user_profile_id": query_params.get("user_profile_id"),
            "created_by": query_params.get("created_by"),
            "agent_instance_id": query_params.get("agent_instance_id"),
            "conversation_id": query_params.get("conversation_id")
        }
        
        if call_sid:
            self.call_context[call_sid] = context
        
        return context

    async def _handle_orchestrator_mode_response(self, call_sid: str, user_profile_id: str,
                                                created_by: str, agent_instance_id: str, 
                                                conversation_id: str) -> Response:
        """Handle orchestrator response after 'please wait' message"""
        try:
            logger.info(f"Handling orchestrator mode response for call {call_sid}")
            
            # Get the pending orchestrator request from call data
            call_data = self.active_calls.get(call_sid)
            if not call_data or not call_data.get("pending_orchestrator_request"):
                logger.error(f"No pending orchestrator request found for call {call_sid}")
                response = VoiceResponse()
                response.say(
                    "I'm sorry, there was an error processing your request. Please try again.",
                    voice="Polly.Joanna-Neural",
                    language="en-US"
                )
                response.hangup()
                return Response(content=str(response), media_type='application/xml')
            
            # Get the pending request and execute orchestrator
            pending_request = call_data.pop("pending_orchestrator_request")
            
            orchestrator_response = await self._use_orchestrator_endpoint(
                pending_request["speech_input"],
                pending_request["user_profile_id"],
                pending_request["created_by"],
                pending_request["agent_instance_id"],
                pending_request["conversation_id"],
                pending_request["detected_intent"]
            )
            
            # Update conversation context
            self._update_conversation_context(call_sid, orchestrator_response, "assistant")
            
            # Create TwiML response
            response = VoiceResponse()
            response.say(
                orchestrator_response,
                voice="Polly.Joanna-Neural",
                language="en-US"
            )
            
            # Set up another gather for continued conversation
            self._add_speech_gather(response, call_sid, user_profile_id, created_by, 
                                   agent_instance_id, conversation_id)
            
            # Add fallback in case user doesn't respond
            response.say(
                "I didn't hear anything. Goodbye!",
                voice="Polly.Joanna-Neural",
                language="en-US"
            )
            response.hangup()
            
            return Response(content=str(response), media_type='application/xml')
            
        except Exception as e:
            logger.error(f"Error in orchestrator mode response handler: {str(e)}")
            response = VoiceResponse()
            response.say(
                "I'm sorry, but I'm having trouble processing your request right now. Please try again later.",
                voice="Polly.Joanna-Neural",
                language="en-US"
            )
            response.hangup()
            return Response(content=str(response), media_type='application/xml')

    def _update_conversation_context(self, call_sid: str, content: str, role: str):
        """Update conversation context for a call"""
        if call_sid not in self.active_calls:
            self.active_calls[call_sid] = {
                "call_sid": call_sid,
                "last_activity": time.time(),
                "conversation_context": []
            }
        
        if "conversation_context" not in self.active_calls[call_sid]:
            self.active_calls[call_sid]["conversation_context"] = []
        
        self.active_calls[call_sid]["conversation_context"].append({
            role: content,
            "timestamp": time.time()
        })

    async def _generate_chatbot_response(self, speech_input: str, user_profile_id: str,
                                        created_by: str, agent_instance_id: str, 
                                        conversation_id: str, call_sid: str = None,
                                        is_incoming_call: bool = True) -> str:
        """Generate chatbot response with two-stage approach for incoming calls"""
        try:
            user_profile_id = user_profile_id or f"user-profile-{uuid.uuid4()}"
            conversation_id = conversation_id or f"conversation_{uuid.uuid4()}"
            
            # Get call data for state tracking
            call_data = self.active_calls.get(call_sid) if call_sid else None
            
            # Two-stage approach ONLY for incoming calls
            if is_incoming_call:
                # Check if there's a pending orchestrator request (after "please wait" message)
                if call_data and call_data.get("pending_orchestrator_request"):
                    logger.info(f"Executing pending orchestrator request for call {call_sid}")
                    pending_request = call_data.pop("pending_orchestrator_request")
                    
                    return await self._use_orchestrator_endpoint(
                        pending_request["speech_input"],
                        pending_request["user_profile_id"],
                        pending_request["created_by"],
                        pending_request["agent_instance_id"],
                        pending_request["conversation_id"],
                        pending_request["detected_intent"]
                    )
                
                # Check if we've already detected intent and should use orchestrator
                if call_data and call_data.get("using_orchestrator", False):
                    logger.info(f"Already using orchestrator mode for call {call_sid}")
                    detected_intent = call_data.get("detected_intent", "loneliness")
                    return await self._use_orchestrator_endpoint(
                        speech_input, user_profile_id, created_by,
                        agent_instance_id, conversation_id, detected_intent
                    )
                
                # Stage 1: Try initial/chat endpoint first
                return await self._handle_initial_chat_stage(
                    speech_input, user_profile_id, created_by, agent_instance_id, 
                    conversation_id, call_sid
                )
            
            else:
                # For OUTGOING calls - directly use orchestrator endpoint
                logger.info(f"Outgoing call {call_sid} - using orchestrator directly")
                return await self._use_orchestrator_endpoint(
                    speech_input, user_profile_id, created_by, 
                    agent_instance_id, conversation_id, "loneliness"
                )
                
        except Exception as e:
            logger.error(f"Error in chatbot response generation: {str(e)}")
            return "I apologize, but I'm experiencing some technical difficulties. Please try again."

    async def _handle_initial_chat_stage(self, speech_input: str, user_profile_id: str,
                                        created_by: str, agent_instance_id: str,
                                        conversation_id: str, call_sid: str) -> str:
        """Handle the initial chat stage for incoming calls"""
        from ..config import Settings
        settings = Settings()
        initial_chat_url = f"{settings.HOST_URL}/initial/chat"
        
        # Prepare payload for initial chat endpoint
        initial_payload = {
            "text": speech_input,
            "user_profile_id": user_profile_id,
            "conversation_id": conversation_id,
            "message": speech_input,
            "conversation_history": [],
            "created_by": created_by,
            "agent_instance_id": agent_instance_id
        }
        
        logger.info(f"Using initial/chat endpoint for call {call_sid}")
       

        try:
            timeout = httpx.Timeout(5.0, connect=0.5, read=2.5)
            async with httpx.AsyncClient(
                timeout=timeout,
                limits=httpx.Limits(max_keepalive_connections=50, max_connections=200),
                http2=True
            ) as client:
                logger.info(f"Sending request to {initial_chat_url}")
                initial_response = await client.post(initial_chat_url, json=initial_payload)
                initial_response.raise_for_status()
                
                initial_result = initial_response.json()
                logger.info(f"Initial chat response: {initial_result}")
                
                # Get response and intent detection
                response_text = initial_result.get("response", "")
                detected_intent = initial_result.get("detected_intent")
                should_route = initial_result.get("should_route", False)
                
                # Check if intent was detected
                if detected_intent and detected_intent.strip() and should_route:
                    logger.info(f"Intent detected: '{detected_intent}', switching to orchestrator")
                    
                    # Update call state to track orchestrator usage and store pending request
                    if call_sid and call_sid in self.active_calls:
                        call_data = self.active_calls[call_sid]
                        call_data["intent_detected"] = True
                        call_data["detected_intent"] = detected_intent
                        call_data["using_orchestrator"] = True
                        call_data["pending_orchestrator_request"] = {
                            "speech_input": speech_input,
                            "user_profile_id": user_profile_id,
                            "created_by": created_by,
                            "agent_instance_id": agent_instance_id,
                            "conversation_id": conversation_id,
                            "detected_intent": detected_intent
                        }
                    
                    # Return ONLY the waiting message to play immediately
                    return "Please wait while I connect you to the right specialist."
                
                else:
                    # No intent detected - continue with initial/chat response
                    logger.info(f"No intent detected, continuing with initial/chat response")
                    return response_text if response_text else "I'm here to help. Could you tell me more about what you need?"
                    
        except (httpx.ConnectError, httpx.HTTPStatusError, httpx.TimeoutException, asyncio.TimeoutError) as e:
            logger.error(f"Error with initial chat endpoint: {str(e)}")
            # Fallback to orchestrator
            return await self._use_orchestrator_endpoint(
                speech_input, user_profile_id, created_by, 
                agent_instance_id, conversation_id, "loneliness"
            )
        except Exception as e:
            logger.error(f"Unexpected error in initial chat: {str(e)}")
            return await self._use_orchestrator_endpoint(
                speech_input, user_profile_id, created_by, 
                agent_instance_id, conversation_id, "loneliness"
            )

    async def _use_orchestrator_endpoint(self, speech_input: str, user_profile_id: str,
                                        created_by: str, agent_instance_id: str,
                                        conversation_id: str, detected_agent: str = "loneliness") -> str:
        """Use orchestrator endpoint for communication after intent detection"""
        try:
            # Check if orchestrator URL is configured
            if not hasattr(settings, 'ORCHESTRATOR_URL') or not settings.ORCHESTRATOR_URL:
                logger.error("ORCHESTRATOR_URL not configured in settings")
                return "I'm sorry, the service is not properly configured. Please try again later."
            
            # Prepare payload for the orchestrate endpoint
            payload = {
                "text": speech_input,
                "user_profile_id": user_profile_id,
                "conversation_id": conversation_id,
                "plan": "lite",
                "services": ["privacy"],
                "individual_id": created_by,
                "agent_instance_id": agent_instance_id,
                "detected_agent": detected_agent,
                "call_log_id": f"call-log-{uuid.uuid4()}"
            }
           
            orchestrator_url = f"{settings.ORCHESTRATOR_URL}/orchestrate"
            logger.info(f"Using orchestrator endpoint: {orchestrator_url}")
        
            # Make request to the orchestrate endpoint
            timeout = httpx.Timeout(8.0, connect=0.5, read=7.0)
            async with httpx.AsyncClient(
                timeout=timeout,
                limits=httpx.Limits(max_keepalive_connections=30, max_connections=100),
                http2=True
            ) as client:
                response = await client.post(orchestrator_url, json=payload)
                response.raise_for_status()
            
                result = response.json()
                if not isinstance(result, dict):
                    logger.error("Invalid response format from orchestrator")
                    return "I'm sorry, I received an invalid response. Please try again."
            
                chatbot_response = result.get("response", "")
                if not chatbot_response:
                    logger.error("Empty response from orchestrator endpoint")
                    return "I'm sorry, I didn't get a proper response. Please try again."
                
                logger.info(f"Received response from orchestrator: {chatbot_response[:100]}...")
                return chatbot_response
                    
        except httpx.ConnectError as e:
            logger.error(f"Connection error to orchestrator endpoint: {str(e)}")
            return "I'm sorry, I'm having trouble connecting to the service. Please try again in a moment."
            
        except httpx.TimeoutException as e:
            logger.error(f"Timeout error to orchestrator endpoint: {str(e)}")
            return "I'm sorry, the request is taking too long. Please try again."
            
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error from orchestrator endpoint: {e.response.status_code}")
            if e.response.status_code == 422:
                return "I'm missing some information needed to process your request. Please ensure your account is properly set up."
            return "My service is currently experiencing issues. Please try again later."
            
        except Exception as e:
            logger.error(f"Error in orchestrator endpoint: {str(e)}")
            return "I apologize, I encountered an unexpected error. Please try again."

    # WebSocket handling methods (simplified)
    async def handle_media_stream(self, websocket: WebSocket, call_sid: str,
                                stt_service, tts_service, chatbot_service):
        """Handle media stream WebSocket with ultra-low latency processing"""
        await websocket.accept()
        logger.info(f"WebSocket connected for streaming: {call_sid}")

        self.processing_tasks[call_sid] = set()
        self.call_locks[call_sid] = asyncio.Lock()

        try:
            # Initialize call data with enhanced audio buffer
            self.active_calls[call_sid] = {
                "websocket": websocket,
                "stream_sid": None,
                "audio_buffer": EnhancedAudioBuffer(),
                "speech_recognition": SpeechRecognitionManager(),
                "is_processing": False,
                "last_activity": time.time(),
                "conversation_context": [],
                "user_speaking": False,
                "assistant_speaking": False,
                "interrupt_detected": False
            }

            # Send immediate greeting
            greeting_task = asyncio.create_task(
                self._send_immediate_greeting(call_sid, websocket, tts_service)
            )

            # Main message processing loop
            await self._process_websocket_messages(
                websocket, call_sid, stt_service, tts_service, chatbot_service
            )

        except WebSocketDisconnect:
            logger.info(f"WebSocket disconnected: {call_sid}")
        except Exception as e:
            logger.error(f"WebSocket error for {call_sid}: {str(e)}")
        finally:
            await self._cleanup_call(call_sid)

    async def _process_websocket_messages(self, websocket: WebSocket, call_sid: str,
                                        stt_service, tts_service, chatbot_service):
        """Process WebSocket messages with continuous streaming"""
        call_data = self.active_calls.get(call_sid)
        if not call_data:
            return

        while True:
            try:
                message = await asyncio.wait_for(websocket.receive_text(), timeout=5.0)
                call_data["last_activity"] = time.time()

                data = orjson.loads(message)
                event = data.get('event')

                if event == 'connected':
                    logger.debug(f"Stream connected: {call_sid}")

                elif event == 'start':
                    stream_sid = data.get('start', {}).get('streamSid')
                    call_data["stream_sid"] = stream_sid
                    logger.info(f"Stream started: {call_sid}, StreamSID: {stream_sid}")

                elif event == 'media':
                    await self._process_media_chunk(
                        call_sid, data, stt_service, tts_service, chatbot_service
                    )

                elif event == 'stop':
                    logger.info(f"Stream stopped: {call_sid}")
                    break

            except asyncio.TimeoutError:
                if time.time() - call_data["last_activity"] > 60:
                    logger.info(f"Call {call_sid} inactive, closing")
                    break
                with suppress(Exception):
                    await websocket.ping()

            except Exception as e:
                logger.error(f"Message processing error: {str(e)}")
                break

    async def _process_media_chunk(self, call_sid: str, data: dict,
                                 stt_service, tts_service, chatbot_service):
        """Process individual media chunks with continuous streaming"""
        call_data = self.active_calls.get(call_sid)
        if not call_data:
            return

        payload = data.get('media', {}).get('payload', '')
        if not payload:
            return

        try:
            audio_chunk = base64.b64decode(payload)
            if len(audio_chunk) < 10:
                return

            # Add to buffer and get VAD state
            audio_buffer = call_data["audio_buffer"]
            vad_result = audio_buffer.add_chunk(audio_chunk)
            
            # Update user speaking state
            call_data["user_speaking"] = vad_result["state"] in ["SPEECH", "POTENTIAL_SPEECH"]
            
            # Check for interrupt
            if call_data["user_speaking"] and call_data.get("assistant_speaking", False):
                call_data["interrupt_detected"] = True
                logger.info(f"Interrupt detected in call {call_sid}")
            
            # Process VAD results
            if vad_result["should_process"]:
                segment_audio = audio_buffer.get_audio_data(-1)
                if segment_audio and len(segment_audio) >= self.min_audio_chunk_size:
                    asyncio.create_task(
                        self._process_speech_segment(
                            call_sid, segment_audio, vad_result["is_final"],
                            stt_service, tts_service, chatbot_service
                        )
                    )

        except Exception as e:
            logger.error(f"Media chunk processing error: {str(e)}")

    async def _process_speech_segment(self, call_sid: str, audio_data: bytes, is_final: bool,
                                    stt_service, tts_service, chatbot_service):
        """Process speech segment with continuous streaming"""
        call_data = self.active_calls.get(call_sid)
        if not call_data or not audio_data:
            return
            
        async with self.call_locks[call_sid]:
            try:
                call_data["is_processing"] = True
                
                # Process with speech recognition manager
                speech_recognition = call_data["speech_recognition"]
                transcription_result = await speech_recognition.process_audio_segment(
                    audio_data, stt_service, is_final=is_final
                )
                
                if not transcription_result["updated"]:
                    return
                    
                transcription_text = transcription_result["text"]
                if not transcription_text:
                    return
                
                logger.info(f"Transcription for call {call_sid}: '{transcription_text[:50]}'")
                    
                call_data["full_transcription"] = transcription_text
                call_data["last_transcription_time"] = time.time()
                
                stability = transcription_result["stability"]
                
                if is_final or (stability > 0.7 and len(transcription_text) > 15):
                    await self._generate_streaming_response(
                        call_sid, transcription_text, chatbot_service, tts_service
                    )
                    
            except Exception as e:
                logger.error(f"Speech segment processing error for call {call_sid}: {str(e)}")
            finally:
                call_data["is_processing"] = False

    async def _generate_streaming_response(self, call_sid: str, text: str,
                                         chatbot_service, tts_service):
        """Generate and stream response"""
        call_data = self.active_calls.get(call_sid)
        if not call_data:
            return
            
        try:
            websocket = call_data["websocket"]
            stream_sid = call_data["stream_sid"]
            
            if not websocket or not stream_sid:
                return
            
            call_data["assistant_speaking"] = True
            
            # Update conversation context
            call_data["conversation_context"].append({
                "user": text, 
                "timestamp": time.time()
            })
            
            # Generate response (simplified)
            response = await self._generate_simple_response(text)
            
            # Generate and send audio
            await self._generate_and_send_audio(
                response, tts_service, websocket, stream_sid
            )
            
            # Update conversation context
            call_data["conversation_context"].append({
                "assistant": response,
                "timestamp": time.time()
            })
            
            call_data["assistant_speaking"] = False
            
        except Exception as e:
            logger.error(f"Streaming response error: {str(e)}")
            call_data["assistant_speaking"] = False

    async def _generate_simple_response(self, text: str) -> str:
        """Generate a simple response (fallback for WebSocket)"""
        return f"I heard you say: {text}. How can I help you with that?"

    async def _generate_and_send_audio(self, text: str, tts_service, 
                                     websocket: WebSocket, stream_sid: str):
        """Generate and send audio with minimal latency"""
        if not text or not websocket or not stream_sid:
            return
            
        try:
            audio_data = await tts_service.text_to_speech(text)
            if audio_data:
                await self._send_audio_to_twilio(websocket, audio_data, stream_sid)
        except Exception as e:
            logger.error(f"Audio generation/send error: {str(e)}")

    async def _send_immediate_greeting(self, call_sid: str, websocket: WebSocket, tts_service):
        """Send immediate greeting to reduce perceived latency"""
        try:
            await asyncio.sleep(0.3)
            
            call_data = self.active_calls.get(call_sid)
            if not call_data:
                return
                
            # Wait for stream_sid
            max_retries = 10
            retries = 0
            
            while not call_data.get("stream_sid") and retries < max_retries:
                await asyncio.sleep(0.5)
                retries += 1
                call_data = self.active_calls.get(call_sid)
                if not call_data:
                    return
            
            if not call_data.get("stream_sid"):
                return

            call_data["assistant_speaking"] = True

            greeting = "Hello! I'm your AI assistant. How can I help you today?"
            audio_data = await tts_service.text_to_speech(greeting)
            
            if audio_data and call_sid in self.active_calls:
                await self._send_audio_to_twilio(
                    websocket, audio_data, call_data["stream_sid"]
                )
                
                call_data["conversation_context"].append({
                    "assistant": greeting,
                    "timestamp": time.time()
                })

        except Exception as e:
            logger.error(f"Error sending greeting for call {call_sid}: {str(e)}")
        finally:
            if call_data:
                call_data["assistant_speaking"] = False

    async def _send_audio_to_twilio(self, websocket: WebSocket, audio_data: bytes, stream_sid: str):
        """Send audio data to Twilio with optimized encoding"""
        if not websocket or not audio_data or not stream_sid:
            return

        try:
            encoded_audio = base64.b64encode(audio_data).decode('utf-8')
            media_message = {
                "event": "media",
                "streamSid": stream_sid,
                "media": {"payload": encoded_audio}
            }
            await websocket.send_text(orjson.dumps(media_message).decode('utf-8'))
        except Exception as e:
            logger.error(f"Audio send error: {str(e)}")

    async def _cleanup_call(self, call_sid: str):
        """Cleanup call resources"""
        try:
            # Cancel all processing tasks
            if call_sid in self.processing_tasks:
                tasks = self.processing_tasks[call_sid]
                for task in tasks:
                    if not task.done():
                        task.cancel()
                del self.processing_tasks[call_sid]

            # Remove from active calls
            if call_sid in self.active_calls:
                del self.active_calls[call_sid]
                
            # Remove lock
            if call_sid in self.call_locks:
                del self.call_locks[call_sid]
                
            # Remove call context
            if call_sid in self.call_context:
                del self.call_context[call_sid]

            logger.info(f"Cleaned up resources for call: {call_sid}")

        except Exception as e:
            logger.error(f"Cleanup error: {str(e)}")

    # Call status and record management
    async def handle_call_status(self, request: Request):
        """Handle call status updates"""
        try:
            form_data = await request.form()
            call_data = dict(form_data)
            call_sid = call_data.get("CallSid")
            call_status = call_data.get("CallStatus")

            logger.info(f"Received call status update: {call_sid} -> {call_status}")

            # Import status update service
            from ...schedule.services.status_update_service import StatusUpdateService
            status_service = StatusUpdateService()

            result = await status_service.handle_call_status_update(call_data)
            asyncio.create_task(self.update_call_status(call_sid, call_status, call_data))
            
            return {"status": "success", "details": result}
            
        except Exception as e:
            logger.error(f"Call status error: {str(e)}")
            return {"status": "error", "message": str(e)}

    async def create_call_record(self, call_data: Dict) -> Optional[CallRecord]:
        """Create call record with optimized validation"""
        try:
            call_sid = call_data.get("CallSid")
            if not call_sid or call_sid in self.call_records:
                return self.call_records.get(call_sid)

            call_record = CallRecord(
                call_sid=call_sid,
                account_sid=call_data.get("AccountSid"),
                from_number=call_data.get("From"),
                to_number=call_data.get("To"),
                status=CallStatus(call_data.get("CallStatus", "initiated")),
                direction=call_data.get("Direction"),
                start_time=datetime.utcnow(),
                forwarded_from=call_data.get("ForwardedFrom"),
                caller_name=call_data.get("CallerName")
            )

            self.call_records[call_sid] = call_record
            return call_record
        except Exception as e:
            logger.error(f"Error creating call record: {str(e)}")
            return None

    async def update_call_status(self, call_sid: str, status: str, call_data: Dict) -> Optional[CallRecord]:
        """Update call status with optimized record handling"""
        if not call_sid or not status:
            return None

        try:
            call_record = self.call_records.get(call_sid)
            if not call_record and "AccountSid" in call_data:
                call_record = await self.create_call_record(call_data)
                if not call_record:
                    return None

            if call_record:
                call_record.status = CallStatus(status)

                if status in ["completed", "failed", "busy", "no-answer"]:
                    call_record.end_time = datetime.utcnow()
                    if call_record.start_time:
                        duration = (call_record.end_time - call_record.start_time).total_seconds()
                        call_record.duration = int(duration)
                    if "CallDuration" in call_data:
                        call_record.duration = int(call_data["CallDuration"])

            return call_record

        except Exception as e:
            logger.error(f"Error updating call status: {str(e)}")
            return None

    async def end_call(self, call_sid: str) -> bool:
        """End an active call"""
        if not call_sid:
            return False

        try:
            self.client.calls(call_sid).update(status="completed")
            return True
        except Exception:
            return False
    
