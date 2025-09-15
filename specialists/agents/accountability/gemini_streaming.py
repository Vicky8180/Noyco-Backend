"""Gemini streaming / async wrapper local to Accountability agent.
Mirrors the therapy agent implementation for consistency.
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


class AccountabilityGeminiClient:
    """Thin async wrapper for Google Gemini with graceful fallback."""

    def __init__(self, api_key: str | None = None, model_name: str = "gemini-1.5-flash"):
        gemini_key="AIzaSyBzGxy5W1lnV6OFsbkyAMwkIRfLpJK5BWw"
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

    async def generate_content(self, prompt: str):
        if not self.model:
            fallback_text = (
                "I'm here to support your goals. What's one small step you can take today?"
            )
            class _Resp:
                def __init__(self, text):
                    self.text = text
            return _Resp(fallback_text)
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, lambda: self.model.generate_content(prompt))

    async def stream_generate_content(
        self,
        prompt: str,
        max_tokens: int = 150,
        temperature: float = 0.7,
        chunk_size: int = 3,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        if not self.model:
            fallback = "Let's make progress together—how did you do today?"
            words = fallback.split()
            for i in range(0, len(words), chunk_size):
                yield {"type": "content", "data": " ".join(words[i:i+chunk_size]) + (" " if i+chunk_size < len(words) else ""), "timestamp": time.time()}
            yield {"type": "done", "data": fallback, "timestamp": time.time()}
            return
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


def get_streaming_client(model_name: str = "gemini-1.5-flash") -> AccountabilityGeminiClient:
    return AccountabilityGeminiClient(model_name=model_name)


