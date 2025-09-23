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
    GEMINI_API_KEY: Optional[str] = None
    GOOGLE_API_KEY: Optional[str] = None
    OPENAI_API_KEY: Optional[str] = None

    # Engine choices
    LLM_ENGINE: str = "gemini-2.0-flash"
    DEFAULT_MODEL_NAME: str = "gemini-2.0-flash"
    
    # Service Configuration
    SERVICE_NAME: str = "agents"
    SERVICE_VERSION: str = "1.0.0"
    AGENTS_SERVICE_PORT: int = 8015
    AGENTS_SERVICE_HOST: str = "0.0.0.0"
    
    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "allow"  # Allow extra fields from .env that this service doesn't use

def get_settings() -> AgentsSettings:
    return AgentsSettings()
