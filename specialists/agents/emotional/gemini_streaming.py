"""Gemini streaming / async wrapper *local* to Emotional agent.
This is a trimmed-down copy of the Therapy agent implementation so that the
Emotional agent is completely self-contained.
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Any, AsyncGenerator, Dict

# Import config
try:
    from config import get_settings
    settings = get_settings()
except ImportError:
    from specialists.agents.config import get_settings
    settings = get_settings()
    # Fallback for when config is not available
    # class FallbackSettings:
    #     GEMINI_API_KEY = None
    #     DEFAULT_MODEL_NAME = "gemini-1.5-flash"
    #     DEFAULT_MAX_TOKENS = 150
    #     DEFAULT_TEMPERATURE = 0.7
    #     DEFAULT_TOP_P = 0.8
    #     DEFAULT_TOP_K = 20
    #     STREAM_CHUNK_SIZE = 3
    # settings = FallbackSettings()

logger = logging.getLogger(__name__)

try:
    import google.generativeai as genai
    GENAI_LIB = True
except ImportError:
    GENAI_LIB = False
    logger.warning("google-generativeai library not found – using fallback responses")


class EmotionalGeminiClient:
    """Very thin async wrapper for Google Gemini with basic quota fallback."""

    def __init__(self, api_key: str | None = None, model_name: str | None = None):
        # Use config values instead of hardcoded ones
        self.api_key = (
            api_key
            or settings.GEMINI_API_KEY
            or os.getenv("GOOGLE_API_KEY")
            or os.getenv("GEMINI_API_KEY")
            or os.getenv("GENAI_API_KEY")
        )
        self.model_name = model_name or settings.DEFAULT_MODEL_NAME
        self.model = None
        self._init_client()

    # ------------------------------------------------------------------
    def _init_client(self):
        if not GENAI_LIB:
            logger.warning("Google Generative AI library not available, using fallback responses")
            self.model = None
            return
        if not self.api_key:
            logger.warning("No Gemini API key found, using fallback responses")
            self.model = None
            return
        try:
            genai.configure(api_key=self.api_key)
            self.model = genai.GenerativeModel(self.model_name)
            logger.info(f"Gemini client initialized successfully with model {self.model_name}")
        except Exception as e:
            logger.error(f"Failed to init Gemini client: {e}")
            self.model = None

    # ------------------------------------------------------------------
    async def generate_content(self, prompt: str):
        """Non-streaming generation with enhanced error handling and emotional fallbacks"""
        if not self.model:
            reason = "No API key" if not self.api_key else "Library not available" if not GENAI_LIB else "Model initialization failed"
            logger.warning(f"Using emotional fallback response - Reason: {reason}")
            
            # Industry-standard therapeutic fallback responses based on prompt content
            fallback_responses = [
                "Thank you for reaching out and sharing with me. I can sense that you're going through something difficult right now, and I want you to know that your feelings are completely valid. I'm here to listen and support you through this.",
                "I'm honored that you're trusting me with what's on your heart. Whatever you're experiencing right now sounds really challenging, and it takes courage to reach out for support. You don't have to face this alone.",
                "I can hear that you're carrying something heavy right now, and I want you to know that what you're feeling makes complete sense. Your emotions matter, and you deserve support and understanding.",
                "Thank you for being brave enough to share with me. I can sense that you're going through a difficult time, and I want you to know that you're not alone in this. Your feelings are important and deserve to be heard.",
                "I'm here with you in this moment, and I can feel that you're struggling with something significant. Whatever you're experiencing is valid, and you deserve compassion and support as you navigate through this."
            ]
            
            # Contextual therapeutic responses based on emotional indicators in prompt
            prompt_lower = prompt.lower()
            if any(word in prompt_lower for word in ["anxious", "worried", "panic", "stress", "overwhelmed"]):
                fallback_text = "I can hear the anxiety and worry in what you're sharing, and I want you to acknowledge how overwhelming these feelings can be. What you're experiencing is a very human response to stress, and it makes complete sense that you'd feel this way. You're safe here with me, and we can take this one moment at a time."
            elif any(word in prompt_lower for word in ["sad", "depressed", "down", "low", "empty", "hopeless"]):
                fallback_text = "Thank you for sharing these difficult feelings with me. I can hear the sadness and pain in your words, and I want you to know that these emotions are completely valid and important. Sadness shows how deeply you feel and care. You don't have to carry this weight alone."
            elif any(word in prompt_lower for word in ["angry", "frustrated", "mad", "furious"]):
                fallback_text = "I can sense the frustration and anger you're experiencing, and I want you to know that these feelings are completely understandable and valid. Anger often tells us that something important to us has been affected. What you're feeling makes sense, and it's okay to have these emotions."
            elif any(word in prompt_lower for word in ["lonely", "alone", "isolated", "abandoned"]):
                fallback_text = "Loneliness can feel so isolating and painful, and I want you to know that what you're experiencing is deeply understood. Even in feeling alone, you're not truly alone right now - I'm here with you, and your presence in this world matters. Your feelings of loneliness are valid and deserve attention."
            elif any(word in prompt_lower for word in ["scared", "afraid", "terrified", "fear"]):
                fallback_text = "I can hear the fear in what you're sharing, and I want you to know that being scared is a completely normal human response. Fear shows that you're facing something that feels significant or threatening. You're braver than you know for reaching out, and I'm here to support you through this."
            elif any(word in prompt_lower for word in ["hurt", "pain", "broken", "devastated"]):
                fallback_text = "I can feel the deep emotional pain you're experiencing, and I want you to know that your hurt is real, valid, and deserves attention. Emotional pain can be just as intense as physical pain, and you don't have to minimize or push through it alone. I'm here to sit with you in this difficult moment."
            else:
                import random
                fallback_text = random.choice(fallback_responses)
            
            class _Resp:
                def __init__(self, text):
                    self.text = text
                    
            logger.debug(f"Using emotional fallback response: {fallback_text[:50]}...")
            return _Resp(fallback_text)
            
        try:
            # Use asyncio timeout to prevent 504 errors and avoid run_in_executor for better async handling
            import concurrent.futures
            
            # Create a dedicated thread pool executor for Gemini calls to prevent blocking
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                # Use asyncio.wait_for to ensure proper timeout handling
                future = executor.submit(self.model.generate_content, prompt)
                response = await asyncio.wait_for(
                    asyncio.wrap_future(future), 
                    timeout=25.0  # Generous timeout to prevent 504 errors
                )
            
            # Validate response
            if not hasattr(response, 'text') or not response.text:
                logger.warning("Emotional Gemini returned empty response, using fallback")
                raise ValueError("Empty response from Gemini")
                
            logger.debug(f"Emotional Gemini response received: {len(response.text)} characters")
            return response
            
        except asyncio.TimeoutError:
            logger.warning("Emotional Gemini generate_content timed out (25s) - preventing 504 error")
            # Return fallback immediately to prevent 504 errors
            class _Resp:
                def __init__(self, text):
                    self.text = text
            return _Resp("I understand you're reaching out for emotional support. While I'm experiencing some technical delays, I want you to know that your feelings are valid and important. I'm here to listen and support you through whatever you're experiencing.")
            
        except Exception as e:
            error_msg = f"{type(e).__name__}: {str(e)}"
            logger.error(f"Emotional Gemini API call failed: {error_msg}")
            
            # Check for specific error types that might cause 504s
            if "504" in error_msg or "deadline" in error_msg.lower() or "timeout" in error_msg.lower():
                logger.error("Detected potential 504 error condition in Gemini API")
                fallback_text = "I'm experiencing some connectivity challenges right now, but I want you to know that I'm here for you. Your emotional wellbeing matters to me. Can you share what's on your mind, and I'll do my best to support you?"
            elif "quota" in error_msg.lower() or "429" in error_msg:
                logger.warning("Quota exceeded - using emotional support fallback")
                fallback_text = "I'm currently at capacity, but your emotional needs are important to me. I want you to know that whatever you're feeling right now is valid. You're not alone, and it's okay to reach out for support."
            else:
                # General emotional support fallback
                fallback_text = "I'm here with you, holding space for whatever you're feeling. Your emotions are safe with me. Can you tell me what's in your heart right now?"
            
            class _Resp:
                def __init__(self, text):
                    self.text = text
            return _Resp(fallback_text)

    # ------------------------------------------------------------------
    async def stream_generate_content(
        self,
        prompt: str,
        max_tokens: int = None,
        temperature: float = None,
        chunk_size: int = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Enhanced emotional streaming with comprehensive error handling"""
        # Use config defaults if parameters not provided
        max_tokens = max_tokens or settings.DEFAULT_MAX_TOKENS
        temperature = temperature or settings.DEFAULT_TEMPERATURE
        chunk_size = chunk_size or settings.STREAM_CHUNK_SIZE
        
        if not self.model:
            reason = "No API key" if not self.api_key else "Library not available" if not GENAI_LIB else "Model initialization failed"
            logger.warning(f"Using emotional fallback streaming response - Reason: {reason}")
            
            # Emotionally supportive fallback streaming
            fallback = "I'm here to listen and support you through whatever you're feeling. You're not alone, and your emotions are valid. How can I help comfort you today?"
            words = fallback.split()
            for i in range(0, len(words), chunk_size):
                yield {"type": "content", "data": " ".join(words[i:i+chunk_size]) + (" " if i+chunk_size < len(words) else ""), "timestamp": time.time()}
            yield {"type": "done", "data": fallback, "timestamp": time.time()}
            return
        # real call with enhanced error handling for emotional support
        try:
            loop = asyncio.get_event_loop()
            stream = await loop.run_in_executor(
                None,
                lambda: self.model.generate_content(
                    prompt,
                    stream=True,
                    generation_config=genai.types.GenerationConfig(
                        max_output_tokens=max_tokens,
                        temperature=temperature,
                        top_p=settings.DEFAULT_TOP_P,
                        top_k=settings.DEFAULT_TOP_K,
                    ),
                ),
            )
            
            buffer = ""
            full = ""
            chunk_count = 0
            
            for chunk in stream:
                chunk_count += 1
                if hasattr(chunk, "text") and chunk.text:
                    buffer += chunk.text
                    full += chunk.text
                    words = buffer.split()
                    while len(words) >= chunk_size:
                        out = " ".join(words[:chunk_size]) + " "
                        buffer = " ".join(words[chunk_size:])
                        words = buffer.split()
                        yield {"type": "content", "data": out, "timestamp": time.time()}
                        
            if buffer.strip():
                yield {"type": "content", "data": buffer, "timestamp": time.time()}
                
            if full.strip():
                logger.debug(f"Emotional streaming completed: {len(full)} characters, {chunk_count} chunks")
                yield {"type": "done", "data": full.strip(), "timestamp": time.time()}
            else:
                logger.warning("Emotional Gemini streaming returned empty content")
                fallback = "I'm here with you, and I want you to know that your feelings are important. Can you tell me more about what's in your heart?"
                yield {"type": "done", "data": fallback, "timestamp": time.time()}
                
        except Exception as e:
            logger.error(f"Emotional Gemini streaming failed: {type(e).__name__}: {str(e)}")
            # Provide emotionally supportive fallback streaming response
            fallback = "I'm experiencing some technical difficulties, but my heart is still with you. I'm here to listen and support you through whatever you're feeling."
            words = fallback.split()
            for i in range(0, len(words), chunk_size):
                yield {"type": "content", "data": " ".join(words[i:i+chunk_size]) + (" " if i+chunk_size < len(words) else ""), "timestamp": time.time()}
            yield {"type": "done", "data": fallback, "timestamp": time.time()}


# convenience ---------------------------------------------------------------

def get_streaming_client(model_name: str = None) -> EmotionalGeminiClient:
    return EmotionalGeminiClient(model_name=model_name)
