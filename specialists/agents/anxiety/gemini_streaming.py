"""Gemini streaming / async wrapper *local* to Anxiety agent.
This is essentially the same implementation used by the Therapy agent but
kept here so the Anxiety agent has *no dependency* on other packages.
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Any, AsyncGenerator, Dict

# Import config
try:
    from ..config import get_settings
    settings = get_settings()
except ImportError:
    # Fallback for when config is not available
    class FallbackSettings:
        GEMINI_API_KEY = None
        DEFAULT_MODEL_NAME = "gemini-1.5-flash"
        DEFAULT_MAX_TOKENS = 150
        DEFAULT_TEMPERATURE = 0.7
        DEFAULT_TOP_P = 0.8
        DEFAULT_TOP_K = 20
        STREAM_CHUNK_SIZE = 3
    settings = FallbackSettings()

logger = logging.getLogger(__name__)

try:
    import google.generativeai as genai
    GENAI_LIB = True
except ImportError:
    GENAI_LIB = False
    logger.warning("google-generativeai library not found – using fallback responses")


class AnxietyGeminiClient:
    """Very thin async wrapper for Google Gemini with anxiety-focused fallback responses."""

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
        """Non-streaming generation with enhanced error handling and retry logic."""
        if not self.model:
            return self._get_contextual_fallback(prompt)
        
        # Retry logic for API calls
        max_retries = 3
        base_timeout = 20.0
        
        for attempt in range(max_retries):
            try:
                timeout = base_timeout + (attempt * 10)  # Progressive timeout: 20s, 30s, 40s
                
                # Use ThreadPoolExecutor and asyncio.wait_for for timeout control
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(self.model.generate_content, prompt)
                    response = await asyncio.wait_for(
                        asyncio.wrap_future(future), 
                        timeout=timeout
                    )
                
                # Validate response
                if hasattr(response, 'text') and response.text and len(response.text.strip()) > 5:
                    logger.debug(f"Gemini API successful on attempt {attempt + 1}")
                    return response
                else:
                    logger.warning(f"Gemini API returned empty/invalid response on attempt {attempt + 1}")
                    
            except asyncio.TimeoutError:
                logger.warning(f"Gemini API timeout on attempt {attempt + 1} (timeout: {timeout}s)")
                if attempt == max_retries - 1:
                    return self._get_timeout_fallback(prompt)
                    
            except Exception as e:
                error_str = str(e).lower()
                logger.warning(f"Gemini API error on attempt {attempt + 1}: {type(e).__name__}: {e}")
                
                # Handle specific error types
                if "quota" in error_str or "rate limit" in error_str or "429" in error_str:
                    if attempt < max_retries - 1:
                        wait_time = (attempt + 1) * 2  # Progressive backoff: 2s, 4s, 6s
                        logger.info(f"Quota/rate limit hit, waiting {wait_time}s before retry...")
                        await asyncio.sleep(wait_time)
                        continue
                    else:
                        return self._get_quota_fallback(prompt)
                        
                elif "deadline exceeded" in error_str or "504" in error_str:
                    return self._get_timeout_fallback(prompt)
                    
                elif attempt == max_retries - 1:
                    return self._get_error_fallback(prompt, e)
        
        # Final fallback
        return self._get_contextual_fallback(prompt)
    
    def _get_contextual_fallback(self, prompt: str):
        """Get contextual fallback response based on prompt content"""
        fallback_responses = [
            "I understand you're feeling anxious right now. Take a deep breath with me. You're safe, and this feeling will pass.",
            "Anxiety can feel overwhelming, but remember - you've gotten through difficult moments before, and you can get through this one too.",
            "Let's focus on what you can control right now. Can you name 5 things you can see around you?",
            "Your anxiety is valid, and it's okay to feel this way. What's one small thing that usually helps you feel calmer?",
            "I'm here with you. Anxiety often tells us scary stories, but they're not always true. What's your body telling you right now?"
        ]
        
        # Anxiety-specific contextual selection based on prompt keywords
        prompt_lower = prompt.lower()
        if any(word in prompt_lower for word in ["panic", "panic attack", "can't breathe", "heart racing"]):
            fallback_text = "It sounds like you might be having a panic attack. Remember: you are safe. Try to breathe slowly - in for 4, hold for 4, out for 6. This will pass."
        elif any(word in prompt_lower for word in ["anxious", "worried", "nervous", "stress"]):
            fallback_text = "I can hear the anxiety in what you're sharing. That must feel really uncomfortable. Let's try some grounding - can you tell me 3 things you can see right now?"
        elif any(word in prompt_lower for word in ["overwhelmed", "too much", "can't handle"]):
            fallback_text = "Feeling overwhelmed is so hard. Let's break this down into smaller pieces. What's one tiny thing you could focus on right now?"
        elif any(word in prompt_lower for word in ["racing thoughts", "can't stop thinking", "mind won't stop"]):
            fallback_text = "Racing thoughts are exhausting. Your mind is trying to protect you, but it's working overtime. Let's try to slow things down together."
        elif any(word in prompt_lower for word in ["afraid", "scared", "fear"]):
            fallback_text = "Fear can make everything feel more intense. You're being so brave by reaching out. What would help you feel even a little bit safer right now?"
        else:
            import random
            fallback_text = random.choice(fallback_responses)
        
        class _Resp:
            def __init__(self, text):
                self.text = text
                
        logger.debug(f"Using anxiety-focused fallback response: {fallback_text[:50]}...")
        return _Resp(fallback_text)
    
    def _get_timeout_fallback(self, prompt: str):
        """Fallback for timeout errors"""
        fallback_text = "I'm experiencing some technical delays, but I'm still here with you. Take a moment to breathe deeply. How are you feeling right now?"
        
        class _Resp:
            def __init__(self, text):
                self.text = text
                
        return _Resp(fallback_text)
    
    def _get_quota_fallback(self, prompt: str):
        """Fallback for quota/rate limit errors"""
        fallback_text = "I'm experiencing high demand right now, but your wellbeing matters. Let's focus on your breathing for a moment. What's one thing that's helping you feel grounded?"
        
        class _Resp:
            def __init__(self, text):
                self.text = text
                
        return _Resp(fallback_text)
    
    def _get_error_fallback(self, prompt: str, error: Exception):
        """Fallback for general errors"""
        fallback_text = "I'm having some technical difficulties, but I want you to know that your feelings are valid and you're not alone. What's the most important thing you need right now?"
        
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
        """Enhanced streaming with robust error handling and fallback responses."""
        # Use config defaults if parameters not provided
        max_tokens = max_tokens or settings.DEFAULT_MAX_TOKENS
        temperature = temperature or settings.DEFAULT_TEMPERATURE
        chunk_size = chunk_size or settings.STREAM_CHUNK_SIZE
        
        if not self.model:
            # Anxiety-focused fallback streaming
            fallback = self._get_contextual_fallback(prompt).text
            words = fallback.split()
            for i in range(0, len(words), chunk_size):
                yield {"type": "content", "data": " ".join(words[i:i+chunk_size]) + (" " if i+chunk_size < len(words) else ""), "timestamp": time.time()}
            yield {"type": "done", "data": fallback, "timestamp": time.time()}
            return
        
        # Enhanced streaming with error handling
        try:
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(
                    lambda: self.model.generate_content(
                        prompt,
                        stream=True,
                        generation_config=genai.types.GenerationConfig(
                            max_output_tokens=max_tokens,
                            temperature=temperature,
                            top_p=settings.DEFAULT_TOP_P,
                            top_k=settings.DEFAULT_TOP_K,
                        ),
                    )
                )
                
                # Timeout for streaming initialization
                stream = await asyncio.wait_for(
                    asyncio.wrap_future(future), 
                    timeout=25.0
                )
            
            buffer = ""
            full = ""
            
            try:
                for chunk in stream:
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
                yield {"type": "done", "data": full.strip(), "timestamp": time.time()}
                
            except Exception as stream_error:
                logger.warning(f"Streaming chunk processing error: {stream_error}")
                # If we have partial content, yield it
                if full:
                    yield {"type": "content", "data": full, "timestamp": time.time()}
                    yield {"type": "done", "data": full.strip(), "timestamp": time.time()}
                else:
                    # Fall back to contextual response
                    await self._stream_fallback_response(prompt, chunk_size)
                    
        except asyncio.TimeoutError:
            logger.warning("Gemini streaming timeout, using fallback")
            async for chunk in self._stream_fallback_response(prompt, chunk_size):
                yield chunk
                
        except Exception as e:
            error_str = str(e).lower()
            logger.warning(f"Gemini streaming error: {type(e).__name__}: {e}")
            
            # Handle specific errors with appropriate fallbacks
            if "quota" in error_str or "rate limit" in error_str:
                fallback_text = "I'm experiencing high demand right now, but I'm here for you. Let's focus on what you need most right now."
            elif "deadline exceeded" in error_str or "504" in error_str:
                fallback_text = "There's a slight delay, but I'm still with you. Take a deep breath. What's the most important thing on your mind?"
            else:
                fallback_text = self._get_contextual_fallback(prompt).text
            
            # Stream the fallback response
            words = fallback_text.split()
            for i in range(0, len(words), chunk_size):
                yield {"type": "content", "data": " ".join(words[i:i+chunk_size]) + (" " if i+chunk_size < len(words) else ""), "timestamp": time.time()}
            yield {"type": "done", "data": fallback_text, "timestamp": time.time()}
    
    async def _stream_fallback_response(self, prompt: str, chunk_size: int = 3) -> AsyncGenerator[Dict[str, Any], None]:
        """Stream a contextual fallback response"""
        fallback_text = self._get_contextual_fallback(prompt).text
        words = fallback_text.split()
        
        for i in range(0, len(words), chunk_size):
            chunk_text = " ".join(words[i:i+chunk_size]) + (" " if i+chunk_size < len(words) else "")
            yield {"type": "content", "data": chunk_text, "timestamp": time.time()}
            
        yield {"type": "done", "data": fallback_text, "timestamp": time.time()}


# convenience ---------------------------------------------------------------

def get_streaming_client(model_name: str = None) -> AnxietyGeminiClient:
    return AnxietyGeminiClient(model_name=model_name)
