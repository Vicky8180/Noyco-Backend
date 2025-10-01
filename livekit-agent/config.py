"""
LiveKit Agent Configuration
Handles configuration for the LiveKit voice agent service
"""

import os
import logging
from pydantic_settings import BaseSettings
from typing import Optional
from dotenv import load_dotenv

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def _load_production_secrets():
    """
    Loads secrets from a single environment variable in production.
    If the variable is not found, it falls back to a local .env file.
    """
    # This is the environment variable you will set in Cloud Run
    # Its value will be the entire content of your production .env file
    secret_content = os.getenv("conversationalengine-secrets")

    if secret_content:
        logger.info("✅ Production secrets found. Loading from environment.")
        try:
            # Parse the multi-line secret string and set environment variables
            for line in secret_content.strip().split('\n'):
                if '=' in line and not line.strip().startswith('#'):
                    key, value = line.strip().split('=', 1)
                    os.environ[key] = value
            logger.info("✅ Environment variables set from production secrets.")
        except Exception as e:
            logger.error(f"❌ Failed to parse production secrets: {e}")
    else:
        logger.warning("⚠️ Production secrets not found. Falling back to local .env file.")
        load_dotenv()

# Run the loader function when this module is imported
_load_production_secrets()

class LiveKitAgentSettings(BaseSettings):
    # Environment
    ENVIRONMENT: str = "development"
    
    # LiveKit Configuration
    LIVEKIT_URL: str
    LIVEKIT_API_KEY: str
    LIVEKIT_API_SECRET: str
    
    # Speech-to-Text (Deepgram)
    DEEPGRAM_API_KEY: str
    
    # Text-to-Speech (ElevenLabs)
    ELEVENLABS_API_KEY: Optional[str] = None
    
    # Text-to-Speech Fallback (Cartesia)
    CARTESIA_API_KEY: Optional[str] = None
    
    # Google API (if needed for additional services)
    GOOGLE_API_KEY: Optional[str] = None
    
    # Noyco Backend Configuration
    NOYCO_BACKEND_URL: str = "http://localhost:8000"
    NOYCO_WS_URL: str = "ws://localhost:8000"
    
    # Service Configuration
    SERVICE_NAME: str = "livekit-agent"
    SERVICE_VERSION: str = "1.0.0"
    
    # VAD (Voice Activity Detection) Settings
    VAD_MIN_SPEECH_DURATION: float = 0.3  # Minimum speech duration in seconds
    VAD_MIN_SILENCE_DURATION: float = 0.8  # Minimum silence to end turn
    VAD_PADDING_DURATION: float = 0.3      # Padding around speech segments
    VAD_ACTIVATION_THRESHOLD: float = 0.5  # Sensitivity (0.0-1.0)
    
    # Deepgram STT Settings
    STT_MODEL: str = "nova-2"
    STT_LANGUAGE: str = "en-US"
    STT_INTERIM_RESULTS: bool = True
    STT_SMART_FORMAT: bool = True
    STT_PUNCTUATE: bool = True
    
    # Timeout Settings
    WEBSOCKET_TIMEOUT: float = 5.0
    HTTP_REQUEST_TIMEOUT: float = 30.0
    BACKEND_RESPONSE_TIMEOUT: float = 30.0
    
    class Config:
        case_sensitive = True
        extra = "ignore"  # Ignore extra environment variables

def get_settings() -> LiveKitAgentSettings:
    """Get LiveKit agent settings"""
    return LiveKitAgentSettings()
