"""
Gemini Streaming Client for Loneliness Companion Agent
Handles streaming responses from Gemini API without importing gemini_client.
"""

import asyncio
import json
import logging
from typing import AsyncGenerator, Dict, Any, Optional
import time
import sys
import os

# Add parent directory for config access
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.insert(0, parent_dir)

from config import get_settings

logger = logging.getLogger(__name__)

# Check if google.generativeai is available
try:
    import google.generativeai as genai
    from google.generativeai.types import GenerateContentResponse
    GENAI_AVAILABLE = True
    logger.debug("Google GenerativeAI library available")
except ImportError as e:
    GENAI_AVAILABLE = False
    logger.warning(f"Google GenerativeAI not available: {e}")

class GeminiStreamingClient:
    """Optimized Gemini streaming client for ultra-low latency with quota management"""
    
    def __init__(self, api_key: str = None, model_name: str = None):
        settings = get_settings()
        self.api_key = api_key or settings.GEMINI_API_KEY
        self.model_name = model_name or settings.LLM_ENGINE
        self.model = None
        self.quota_exceeded = False
        self.last_quota_error = 0
        self.quota_retry_delay = 60  # 1 minute default retry delay
        self._initialize_client()
    
    def _initialize_client(self):
        """Initialize Gemini client with optimizations"""
        if not GENAI_AVAILABLE:
            logger.warning("Google GenerativeAI not available - using fallback mode")
            self.model = None
            return
            
        try:
            if not self.api_key:
                raise ValueError("Gemini API key not found")
            
            genai.configure(api_key=self.api_key)
            self.model = genai.GenerativeModel(self.model_name)
            logger.info(f"Gemini client initialized: {self.model_name}")
            
        except Exception as e:
            logger.error(f"Failed to initialize Gemini client: {e}")
            self.model = None
    
    
    def _check_quota_status(self) -> bool:
        """Check if we're in quota limit cooldown"""
        current_time = time.time()
        if self.quota_exceeded and (current_time - self.last_quota_error) < self.quota_retry_delay:
            return False
        elif self.quota_exceeded and (current_time - self.last_quota_error) >= self.quota_retry_delay:
            # Reset quota status after cooldown
            self.quota_exceeded = False
            logger.info("Quota cooldown period ended, retrying Gemini API")
        return True
    
    def _handle_quota_error(self, error_msg: str):
        """Handle quota exceeded errors"""
        self.quota_exceeded = True
        self.last_quota_error = time.time()
        # Extract retry delay from error if available
        if "retry_delay" in error_msg:
            try:
                # Parse retry delay from error (simplified)
                if "seconds: 30" in error_msg:
                    self.quota_retry_delay = 35  # Add 5 sec buffer
                elif "seconds: 60" in error_msg:
                    self.quota_retry_delay = 65
                else:
                    self.quota_retry_delay = 60  # Default 1 minute
            except:
                self.quota_retry_delay = 60
        logger.warning(f"Quota exceeded - will retry after {self.quota_retry_delay} seconds")

    async def stream_generate_content(
        self, 
        prompt: str, 
        max_tokens: int = 150,
        temperature: float = 0.7,
        chunk_size: int = 3
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Ultra-fast streaming content generation with quota management
        """
        # Check quota status first
        if not self._check_quota_status():
            logger.info("In quota cooldown - using fallback response")
            fallback_response = "I'm here to listen and support you. How are you feeling today?"
            async for chunk in self._stream_fallback_response(fallback_response, chunk_size):
                yield chunk
            return
        
        if not self.model or not GENAI_AVAILABLE:
            logger.info("Gemini not available - using fallback response")
            fallback_response = "I understand you want to talk. How are you feeling today? I'm here to listen."
            async for chunk in self._stream_fallback_response(fallback_response, chunk_size):
                yield chunk
            return
        
        try:
            # Optimized generation parameters for speed
            generation_config = genai.types.GenerationConfig(
                max_output_tokens=max_tokens,
                temperature=temperature,
                top_p=0.8,
                top_k=20
            )
            
            # Generate streaming response with timeout
            response_stream = await asyncio.wait_for(
                asyncio.get_event_loop().run_in_executor(
                    None, 
                    lambda: self.model.generate_content(
                        prompt, 
                        generation_config=generation_config,
                        stream=True
                    )
                ),
                timeout=5.0
            )
            
            full_response = ""
            buffer = ""
            
            # Process streaming chunks
            for chunk in response_stream:
                if hasattr(chunk, 'text') and chunk.text:
                    text_chunk = chunk.text
                    full_response += text_chunk
                    buffer += text_chunk
                    
                    # Split into word chunks for smooth streaming
                    words = buffer.split()
                    if len(words) >= chunk_size:
                        chunk_text = ' '.join(words[:chunk_size])
                        buffer = ' '.join(words[chunk_size:])
                        
                        yield {
                            "type": "content",
                            "data": chunk_text + " ",
                            "timestamp": time.time()
                        }
                        
                        await asyncio.sleep(0.05)  # Smooth streaming delay
            
            # Send remaining buffer
            if buffer.strip():
                yield {
                    "type": "content",
                    "data": buffer,
                    "timestamp": time.time()
                }
            
            # Send completion signal
            yield {
                "type": "done",
                "data": full_response.strip(),
                "timestamp": time.time()
            }
            
        except Exception as e:
            error_str = str(e)
            
            # Handle quota errors specifically
            if "429" in error_str or "quota" in error_str.lower():
                self._handle_quota_error(error_str)
                logger.warning("Quota exceeded - using fallback response")
                fallback_response = "I'm here to support you. Let's talk about how you're feeling."
            else:
                logger.error(f"Gemini streaming error: {e}")
                fallback_response = "I'm here to listen and support you. What's on your mind?"
            
            # Stream fallback response
            async for fallback_chunk in self._stream_fallback_response(fallback_response, chunk_size):
                yield fallback_chunk
    
    async def _stream_fallback_response(
        self, 
        response: str, 
        chunk_size: int = 3
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Stream a fallback response when Gemini is unavailable"""
        words = response.split()
        
        for i in range(0, len(words), chunk_size):
            chunk = ' '.join(words[i:i + chunk_size])
            yield {
                "type": "content",
                "data": chunk + (" " if i + chunk_size < len(words) else ""),
                "timestamp": time.time()
            }
            await asyncio.sleep(0.05)  # Smooth streaming delay
        
        yield {
            "type": "done",
            "data": response,
            "timestamp": time.time()
        }
    
    async def generate_content(self, prompt: str) -> object:
        """
        Generate content with backward compatibility for loneliness agent
        Returns a response object with .text attribute
        """
        # Check quota status first
        if not self._check_quota_status():
            logger.info("In quota cooldown - using fallback response")
            return type('Response', (), {
                'text': "I'm here to support you. How are you feeling today?"
            })()
        
        if not self.model or not GENAI_AVAILABLE:
            logger.info("Gemini not available - using fallback response")
            return type('Response', (), {
                'text': "I understand you want to talk. I'm here to listen and support you."
            })()
        
        try:
            response = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self.model.generate_content(
                    prompt,
                    generation_config=genai.types.GenerationConfig(
                        max_output_tokens=150,
                        temperature=0.7
                    )
                )
            )
            return type('Response', (), {'text': response.text.strip()})()
            
        except Exception as e:
            error_str = str(e)
            
            # Handle quota errors
            if "429" in error_str or "quota" in error_str.lower():
                self._handle_quota_error(error_str)
                logger.warning("Quota exceeded - using fallback response")
            else:
                logger.error(f"Generate content error: {e}")
            
            # Return fallback response object
            return type('Response', (), {
                'text': "I'm here to support you. How are you feeling today?"
            })()


class StreamingResponseManager:
    """Manages streaming responses with proper error handling and fallbacks"""
    
    def __init__(self, gemini_client: GeminiStreamingClient):
        self.gemini_client = gemini_client
        self.active_streams = {}
    
    async def create_streaming_response(
        self,
        prompt: str,
        conversation_id: str,
        metadata: Dict[str, Any] = None
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Create a streaming response with optimized performance
        """
        stream_id = f"stream_{conversation_id}_{int(time.time())}"
        self.active_streams[stream_id] = True
        
        try:
            # Send initial metadata
            yield {
                "type": "start",
                "stream_id": stream_id,
                "conversation_id": conversation_id,
                "timestamp": time.time()
            }
            
            # Stream content from Gemini
            async for chunk in self.gemini_client.stream_generate_content(
                prompt, chunk_size=3, max_tokens=200
            ):
                if not self.active_streams.get(stream_id, False):
                    break  # Stream was cancelled
                
                # Add metadata to chunk
                chunk.update({
                    "stream_id": stream_id,
                    "conversation_id": conversation_id
                })
                
                yield chunk
                
                # Early exit on completion
                if chunk.get("type") == "done":
                    break
                
        except Exception as e:
            logger.error(f"Streaming response error: {e}")
            yield {
                "type": "error",
                "stream_id": stream_id,
                "conversation_id": conversation_id,
                "data": f"Streaming error: {str(e)}",
                "timestamp": time.time()
            }
        
        finally:
            # Cleanup
            self.active_streams.pop(stream_id, None)
            yield {
                "type": "end",
                "stream_id": stream_id,
                "conversation_id": conversation_id,
                "timestamp": time.time()
            }
    
    def cancel_stream(self, stream_id: str):
        """Cancel an active stream"""
        if stream_id in self.active_streams:
            self.active_streams[stream_id] = False
            logger.info(f"Stream {stream_id} cancelled")
    
    def get_active_stream_count(self) -> int:
        """Get number of active streams"""
        return sum(1 for active in self.active_streams.values() if active)


# Global instances - SINGLE INSTANCE ONLY
_gemini_streaming_client = None
_streaming_response_manager = None

def get_streaming_client() -> GeminiStreamingClient:
    """Get global streaming client instance - SINGLETON"""
    global _gemini_streaming_client
    if _gemini_streaming_client is None:
        _gemini_streaming_client = GeminiStreamingClient()
        logger.info("Created single global Gemini streaming client instance")
    return _gemini_streaming_client

def get_streaming_manager() -> StreamingResponseManager:
    """Get global streaming response manager - SINGLETON"""
    global _streaming_response_manager
    if _streaming_response_manager is None:
        _streaming_response_manager = StreamingResponseManager(get_streaming_client())
        logger.info("Created single global streaming response manager")
    return _streaming_response_manager
