
from typing import Dict
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    """Global application and external service settings"""

    # Server settings
    PORT: int = 8000
    DEBUG: bool = False

    # Twilio settings - All from environment
    TWILIO_ACCOUNT_SID: str
    TWILIO_AUTH_TOKEN: str
    TWILIO_PHONE_NUMBER: str
    TWILIO_BASE_WEBHOOK_URL: str
    HOST_URL:str
    
    # Service URLs
    ORCHESTRATOR_URL: str
    
    # Google Cloud settings
    GOOGLE_CREDENTIALS_PATH: str
    GOOGLE_PROJECT_ID: str

    # Gemini settings
    GEMINI_API_KEY:              str    = "AIzaSyCklVFWThy-L9Ad4TqQdYNefGF4f206THM"
    GEMINI_MODEL:                str    = "gemini-1.5-flash"

    # WebSocket settings
    # WebSocket settings
    WS_TIMEOUT: int = 300

    # Audio settings
    AUDIO_SAMPLE_RATE: int = 8000
    AUDIO_CHANNELS: int = 1
    AUDIO_ENCODING: str = "mulaw"

    # Tell Pydantic v2 how to load and validate
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8-sig",
        case_sensitive=True,
        extra="ignore"
    )

    def get_twilio_webhook_urls(self, user_profile_id: str) -> Dict[str, str]:
        """Generate dynamic Twilio webhook URLs for a given user profile ID"""
        return {
            "voice_webhook":  f"{self.TWILIO_BASE_WEBHOOK_URL}/phone/voice",
            "forward_webhook":f"{self.TWILIO_BASE_WEBHOOK_URL}/phone/forward-webhook?user_profile_id={user_profile_id}",
            "status_webhook": f"{self.TWILIO_BASE_WEBHOOK_URL}/phone/forward-status?user_profile_id={user_profile_id}",
        }

# Singleton instance to use across app
settings = Settings()

