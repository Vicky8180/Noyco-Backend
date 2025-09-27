from functools import lru_cache
# pydantic v2 moved BaseSettings to pydantic_settings
try:
    from pydantic_settings import BaseSettings, SettingsConfigDict  # type: ignore
except ImportError:  # Fallback for pydantic <2
    from pydantic import BaseSettings  # type: ignore
    SettingsConfigDict = None  # type: ignore

from pydantic import Field, AnyUrl

class LiveKitVoiceSettings(BaseSettings):
    # LiveKit settings - All from environment
    LIVEKIT_HOST: AnyUrl
    LIVEKIT_API_KEY: str
    LIVEKIT_API_SECRET: str
    LIVEKIT_TTL_MINUTES: int = 120

    # Custom orchestrator endpoint
    ORCHESTRATOR_ENDPOINT: str
    
    # Default session values for testing
    DEFAULT_CONVERSATION_ID: str 
    DEFAULT_PLAN: str 
    DEFAULT_INDIVIDUAL_ID: str 
    DEFAULT_USER_PROFILE_ID: str 
    DEFAULT_DETECTED_AGENT: str 
    DEFAULT_AGENT_INSTANCE_ID: str 
    DEFAULT_CALL_LOG_ID: str 
    
    # TTS/STT Engine settings
    TTS_ENGINE: str 
    STT_ENGINE: str 
    LLM_ENGINE: str 

    # API keys for TTS/STT services
    DEEPGRAM_API_KEY: str 
    ELEVENLABS_API_KEY: str 
    GEMINI_API_KEY: str

    # Audio settings
    SAMPLE_RATE: int = 16000
    CHUNK_SIZE: int = 4096
    AUDIO_FORMAT: str = "pcm"
    
    # Voice settings
    VOICE_ID: str = "alloy"  # Default voice for TTS
    
    # Timeout settings
    CONNECTION_TIMEOUT: int = 30
    RESPONSE_TIMEOUT: int = 10

    SERVICE_PORT: int = 8000

    # Use new model_config if available (pydantic v2)
    if SettingsConfigDict is not None:
        model_config = SettingsConfigDict(extra="allow", case_sensitive=False)
    else:
        class Config:
            extra = "allow"
            case_sensitive = False

@lru_cache()
def get_livekit_settings() -> LiveKitVoiceSettings:
    return LiveKitVoiceSettings()
