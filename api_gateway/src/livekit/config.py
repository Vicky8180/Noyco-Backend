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
    DEFAULT_CONVERSATION_ID: str = "livekit_conversation"
    DEFAULT_PLAN: str = "lite"
    DEFAULT_INDIVIDUAL_ID: str = "individual_f068689a7d96"
    DEFAULT_USER_PROFILE_ID: str = "user_profile_610f7db5658e"
    DEFAULT_DETECTED_AGENT: str = "loneliness"
    DEFAULT_AGENT_INSTANCE_ID: str = "loneliness_658"
    DEFAULT_CALL_LOG_ID: str = "call_log_livekit"
    
    # TTS/STT Engine settings
    TTS_ENGINE: str = Field("deepgram")
    STT_ENGINE: str = Field("deepgram")
    LLM_ENGINE: str = Field("custom")

    # API keys for TTS/STT services
    DEEPGRAM_API_KEY: str = Field("3db5be5479faca82f4af64af88f9f05ef2a2d5c4")
    ELEVENLABS_API_KEY: str = Field("sk_494866b596424b0401e00b299e5c10a76d41d7abd6c681ed")
    GEMINI_API_KEY: str = Field("AIzaSyCOA-lmb8eSMvBn-SCZ7hE017WfKNKrGaw")

    # Audio settings
    SAMPLE_RATE: int = 16000
    CHUNK_SIZE: int = 4096
    AUDIO_FORMAT: str = "pcm"
    
    # Voice settings
    VOICE_ID: str = "alloy"  # Default voice for TTS
    
    # Timeout settings
    CONNECTION_TIMEOUT: int = 30
    RESPONSE_TIMEOUT: int = 10

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
