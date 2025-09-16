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
    DEFAULT_MODEL_NAME: str = "gemini-2.0-flash"
    
    # LLM Configuration
    DEFAULT_MAX_TOKENS: int = 150
    DEFAULT_TEMPERATURE: float = 0.7
    DEFAULT_TOP_P: float = 0.8
    DEFAULT_TOP_K: int = 20
    STREAM_CHUNK_SIZE: int = 3
    
    # Service Configuration
    SERVICE_NAME: str = "agents"
    SERVICE_VERSION: str = "1.0.0"
    AGENTS_SERVICE_PORT: int = 8015
    AGENTS_SERVICE_HOST: str = "0.0.0.0"
    
    # Service URLs (for cross-service communication)
    LONELINESS_SERVICE_URL: Optional[str] = "http://localhost:8015/loneliness/process"
    ACCOUNTABILITY_SERVICE_URL: Optional[str] = "http://localhost:8015/accountability/process"
    THERAPY_SERVICE_URL: Optional[str] = "http://localhost:8015/therapy/process"
    EMOTIONAL_SERVICE_URL: Optional[str] = "http://localhost:8015/emotional/process"
    ANXIETY_SERVICE_URL: Optional[str] = "http://localhost:8015/anxiety/process"
    
    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "allow"  # Allow extra fields from .env that this service doesn't use

def get_settings() -> AgentsSettings:
    return AgentsSettings()
