from pydantic_settings import BaseSettings
from typing import Optional

class CheckpointSettings(BaseSettings):
    # Environment
    ENVIRONMENT: str = "development"
    
    # API Keys - Required for checkpoint generation
    GEMINI_API_KEY: str
    
    # Service Configuration
    SERVICE_NAME: str = "checkpoint"
    SERVICE_VERSION: str = "1.0.0"
    SERVICE_PORT: int = 8003
    SERVICE_HOST: str = "0.0.0.0"
    
    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "ignore"  # Ignore extra fields from .env file

def get_settings() -> CheckpointSettings:
    return CheckpointSettings()
