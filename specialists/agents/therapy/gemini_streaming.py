"""Gemini streaming / async wrapper *local* to Therapy agent.
This is a trimmed-down copy of the Loneliness agent implementation so that the
Therapy agent is completely self-contained.
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Any, AsyncGenerator, Dict

logger = logging.getLogger(__name__)

try:
    import google.generativeai as genai
    GENAI_LIB = True
except ImportError:
    GENAI_LIB = False
    logger.warning("google-generativeai library not found – using fallback responses")


class TherapyGeminiClient:
    """Very thin async wrapper for Google Gemini with basic quota fallback."""

    def __init__(self, api_key: str | None = None, model_name: str = "gemini-1.5-flash"):
        # Only enable real client when we actually have an API key set.
        gemini_key="AIzaSyDtNnmtnh4UfEYOf5AcwN45o6xyL2cTWcU"
        env_key = (
            api_key
            or gemini_key
            or os.getenv("GOOGLE_API_KEY")
            or os.getenv("GEMINI_API_KEY")
            or os.getenv("GENAI_API_KEY")
        )
        self.api_key = env_key
        self.model_name = model_name
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
        """Non-streaming generation used for quick single responses."""
        if not self.model:
            reason = "No API key" if not self.api_key else "Library not available" if not GENAI_LIB else "Model initialization failed"
            logger.warning(f"Using fallback response - Reason: {reason}")
            
            # Contextual fallback based on prompt content
            fallback_responses = [
                "I hear you, and I want you to know that your feelings are valid. What's been on your mind lately?",
                "Thank you for sharing that with me. It sounds like you're going through something difficult. Can you tell me more?",
                "I'm here to support you. Sometimes it helps just to have someone listen. What would you like to talk about?",
                "That sounds challenging. You're not alone in feeling this way. What's been the hardest part for you?",
                "I appreciate you opening up. It takes courage to share how we're feeling. How can I best support you right now?"
            ]
            
            # Simple contextual selection based on prompt keywords
            prompt_lower = prompt.lower()
            if any(word in prompt_lower for word in ["anxious", "worried", "panic", "stress"]):
                fallback_text = "I can hear that you're feeling anxious. That must be really difficult. Remember that anxiety is temporary, even when it doesn't feel that way."
            elif any(word in prompt_lower for word in ["sad", "depressed", "down", "low"]):
                fallback_text = "I'm sorry you're feeling this way. It's okay to feel sad - these feelings are part of being human. You don't have to go through this alone."
            elif any(word in prompt_lower for word in ["angry", "frustrated", "mad"]):
                fallback_text = "It sounds like you're feeling really frustrated. Those feelings are completely understandable. What's been making you feel this way?"
            else:
                import random
                fallback_text = random.choice(fallback_responses)
            
            class _Resp:
                def __init__(self, text):
                    self.text = text
                    
            logger.debug(f"Using fallback response: {fallback_text[:50]}...")
            return _Resp(fallback_text)
            
        try:
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(None, lambda: self.model.generate_content(prompt))
            
            # Validate response
            if not hasattr(response, 'text') or not response.text:
                logger.warning("Gemini returned empty response, using fallback")
                raise ValueError("Empty response from Gemini")
                
            logger.debug(f"Gemini response received: {len(response.text)} characters")
            return response
            
        except Exception as e:
            logger.error(f"Gemini API call failed: {type(e).__name__}: {str(e)}")
            # Return fallback response instead of raising exception
            class _Resp:
                def __init__(self, text):
                    self.text = text
            return _Resp("I'm here to listen and support you. Can you tell me more about how you're feeling?")

    # ------------------------------------------------------------------
    async def stream_generate_content(
        self,
        prompt: str,
        max_tokens: int = 150,
        temperature: float = 0.7,
        chunk_size: int = 3,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Word-level streaming similar to Loneliness implementation."""
        if not self.model:
            reason = "No API key" if not self.api_key else "Library not available" if not GENAI_LIB else "Model initialization failed"
            logger.warning(f"Using fallback streaming response - Reason: {reason}")
            
            # simple fallback streaming
            fallback = "I'm here to listen and support you. How are you feeling today?"
            words = fallback.split()
            for i in range(0, len(words), chunk_size):
                yield {"type": "content", "data": " ".join(words[i:i+chunk_size]) + (" " if i+chunk_size < len(words) else ""), "timestamp": time.time()}
            yield {"type": "done", "data": fallback, "timestamp": time.time()}
            return
        # real call with error handling
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
                        top_p=0.8,
                        top_k=20,
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
                logger.debug(f"Streaming completed: {len(full)} characters, {chunk_count} chunks")
                yield {"type": "done", "data": full.strip(), "timestamp": time.time()}
            else:
                logger.warning("Gemini streaming returned empty content")
                fallback = "I'm here to support you. Can you tell me more about what's on your mind?"
                yield {"type": "done", "data": fallback, "timestamp": time.time()}
                
        except Exception as e:
            logger.error(f"Gemini streaming failed: {type(e).__name__}: {str(e)}")
            # Provide fallback streaming response
            fallback = "I'm experiencing some technical difficulties, but I'm still here to support you. How can I help?"
            words = fallback.split()
            for i in range(0, len(words), chunk_size):
                yield {"type": "content", "data": " ".join(words[i:i+chunk_size]) + (" " if i+chunk_size < len(words) else ""), "timestamp": time.time()}
            yield {"type": "done", "data": fallback, "timestamp": time.time()}


# convenience ---------------------------------------------------------------

def get_streaming_client(model_name: str = "gemini-1.5-flash") -> TherapyGeminiClient:
    return TherapyGeminiClient(model_name=model_name)
