from pydantic_settings import BaseSettings
from typing import Optional

class OrchestratorSettings(BaseSettings):
    # Environment
    ENVIRONMENT: str = "development"
    
    # Core Service URLs
    MEMORY_URL: str 
    CHECKPOINT_URL: str 
    PRIMARY_SERVICE_URL: str 
    
    # Agent Service URLs
    CHECKLIST_SERVICE_URL: str 
    PRIVACY_SERVICE_URL: str 
    NUTRITION_SERVICE_URL: str 
    FOLLOWUP_SERVICE_URL: str 
    HISTORY_SERVICE_URL: str 
    HUMAN_INTERVENTION_SERVICE_URL: str 
    MEDICATION_SERVICE_URL: str 
    
    # Specialized Agent Services
    LONELINESS_SERVICE_URL: str 
    ACCOUNTABILITY_SERVICE_URL: str 
    THERAPY_SERVICE_URL: str 
    EMOTIONAL_SERVICE_URL: str 
    ANXIETY_SERVICE_URL: str 
    
    # Orchestrator Service Configuration
    ORCHESTRATOR_HOST: str = "0.0.0.0"
    ORCHESTRATOR_PORT: int = 8002
    ORCHESTRATOR_WORKERS: int = 1
    ORCHESTRATOR_CONCURRENCY_LIMIT: int = 100
    
    # HTTP Client Configuration
    HTTP_CONNECT_TIMEOUT: float 
    HTTP_READ_TIMEOUT: float 
    HTTP_WRITE_TIMEOUT: float 
    HTTP_POOL_TIMEOUT: float 
    MAX_KEEPALIVE_CONNECTIONS: int 
    MAX_CONNECTIONS: int 
    
    # Service Timeouts
    DEFAULT_SERVICE_TIMEOUT: float 
    CHECKPOINT_SERVICE_TIMEOUT: float 
    PRIMARY_SERVICE_TIMEOUT: float 
    HUMAN_INTERVENTION_TIMEOUT: float 
    CHECKLIST_TIMEOUT: float 
    MEDICATION_TIMEOUT: float 
    PRIVACY_TIMEOUT: float 
    
    # Cache Configuration
    REDIS_URL: str 
    LOCAL_CACHE_SIZE: int 
    CACHE_TTL: int 
    CHECKPOINT_EVALUATION_CACHE_TTL: int 
    TASK_STATE_CACHE_TTL: int 
    
    # Agent Configuration
    MAX_SERVICE_RETRIES: int
    
    # Logging
    LOG_LEVEL: str
    
    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "ignore"  # Ignore extra fields from .env file

def get_settings() -> OrchestratorSettings:
    return OrchestratorSettings()
