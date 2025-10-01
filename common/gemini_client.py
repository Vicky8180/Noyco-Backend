

# common/gemini_client.py
import google.generativeai as genai
import asyncio
from typing import Any
import logging
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from common.config import get_settings

logger = logging.getLogger(__name__)

# Smaller thread pool for better resource management
_EXECUTOR = ThreadPoolExecutor(max_workers=3, thread_name_prefix="gemini")
_API_CONFIGURED = False

class AsyncGeminiClient:
    """Optimized asynchronous client for Google's Gemini API"""

    def __init__(self, api_key: str, model_name: str = "models/gemini-2.5-flash-lite"):
        if not api_key:
            raise ValueError("API key cannot be empty")

        global _API_CONFIGURED
        if not _API_CONFIGURED:
            genai.configure(api_key=api_key)
            _API_CONFIGURED = True

        # Configure model with optimized settings
        generation_config = genai.types.GenerationConfig(
            temperature=0.3,  # Lower temperature for more consistent responses
            top_p=0.8,
            top_k=20,
            max_output_tokens=1000,  # Limit output length
            stop_sequences=None,
        )

        self.model = genai.GenerativeModel(
            model_name=model_name,
            generation_config=generation_config
        )

    async def generate_content(self, prompt: str, **kwargs) -> Any:
        """
        Async wrapper with timeout and optimized settings
        """
        try:
            # Set reasonable timeout and run in thread pool
            loop = asyncio.get_running_loop()
            
            # Create a wrapper function that includes timeout
            def _generate_with_timeout():
                return self.model.generate_content(
                    prompt, 
                    safety_settings=[
                        {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
                        {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
                        {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
                        {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
                    ],
                    **kwargs
                )
            
            # Run with timeout
            response = await asyncio.wait_for(
                loop.run_in_executor(_EXECUTOR, _generate_with_timeout),
                timeout=8.0  # 8 second timeout
            )
            
            return response

        except asyncio.TimeoutError:
            logger.error("Gemini API call timed out")
            raise
        except Exception as e:
            logger.error(f"Error generating content: {str(e)}")
            raise

@lru_cache(maxsize=1)
def get_gemini_client(model_name: str = "models/gemini-2.5-flash-lite") -> AsyncGeminiClient:
    """Get cached Gemini client instance"""
    
    # Load from configuration using pydantic-settings
    try:
        settings = get_settings()
        api_key = settings.GEMINI_API_KEY
    except Exception as e:
        logger.error(f"Failed to load configuration: {str(e)}")
        raise ValueError(
            "Failed to load GEMINI_API_KEY from configuration. Please check your .env file."
        )

    if not api_key:
        raise ValueError(
            "GEMINI_API_KEY environment variable not set. Please export a valid key before starting services."
        )

    try:
        return AsyncGeminiClient(api_key, model_name)
    except Exception as e:
        logger.error(f"Failed to create Gemini client: {str(e)}")
        raise
