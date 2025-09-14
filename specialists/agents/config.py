from pydantic_settings import BaseSettings
from typing import Optional

class AgentsSettings(BaseSettings):
    # Environment
    ENVIRONMENT: str = "development"
    
    # Database connections
    MONGODB_URI: str
    DATABASE_NAME: str = "conversionalEngine"
    REDIS_URL: str = "redis://localhost:6379"
    
    # API Keys
    GEMINI_API_KEY: str
    GOOGLE_API_KEY: Optional[str] = None
    OPENAI_API_KEY: Optional[str] = None
    
    # Google Cloud
    GOOGLE_APPLICATION_CREDENTIALS: Optional[str] = None
    GOOGLE_CLOUD_PROJECT: Optional[str] = None
    GOOGLE_CLOUD_LOCATION: str = "us-central1"
    GOOGLE_HEALTHCARE_DATASET: Optional[str] = None
    
    # Engine choices
    LLM_ENGINE: str = "gemini-2.0-flash"
    
    # Service Configuration
    SERVICE_NAME: str = "agents"
    SERVICE_VERSION: str = "1.0.0"
    AGENTS_SERVICE_PORT: int = 8015
    AGENTS_SERVICE_HOST: str = "0.0.0.0"
    
    # Service URLs (for cross-service communication)
    LONELINESS_SERVICE_URL: Optional[str] = "http://localhost:8015/loneliness/process"
    ACCOUNTABILITY_SERVICE_URL: Optional[str] = "http://localhost:8015/accountability/process"
    THERAPY_SERVICE_URL: Optional[str] = "http://localhost:8015/therapy/process"
    
    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "allow"  # Allow extra fields from .env that this service doesn't use

def get_settings() -> AgentsSettings:
    return AgentsSettings()
