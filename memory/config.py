from pydantic_settings import BaseSettings
from typing import Optional

class MemorySettings(BaseSettings):
    # Environment
    ENVIRONMENT: str = "development"
    
    # Database connections
    MONGODB_URI: str
    DATABASE_NAME: str = "conversionalEngine"
    REDIS_URL: str = "redis://localhost:6379"
    
    # API Keys
    PINECONE_API_KEY: Optional[str] = None
    PINECONE_ENVIRONMENT: str = "us-west1-gcp"
    
    # Service Configuration
    SERVICE_NAME: str = "memory"
    SERVICE_VERSION: str = "1.0.0"
    SERVICE_PORT: int = 8010
    
    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "ignore"  # Ignore extra environment variables

def get_settings() -> MemorySettings:
    return MemorySettings()
