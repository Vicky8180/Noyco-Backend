from pydantic_settings import BaseSettings
from typing import Optional

class OrchestratorSettings(BaseSettings):
    # Environment
    ENVIRONMENT: str = "development"
    
    # Core Service URLs
    MEMORY_URL: str = "http://localhost:8010"
    CHECKPOINT_URL: str = "http://localhost:8003"
    PRIMARY_SERVICE_URL: str = "http://localhost:8004/process"
    
    # Agent Service URLs
    CHECKLIST_SERVICE_URL: str = "http://localhost:8007/process"
    PRIVACY_SERVICE_URL: str = "http://localhost:8011/process"
    NUTRITION_SERVICE_URL: str = "http://localhost:8005/process"
    FOLLOWUP_SERVICE_URL: str = "http://localhost:8008/process"
    HISTORY_SERVICE_URL: str = "http://localhost:8009/process"
    HUMAN_INTERVENTION_SERVICE_URL: str = "http://localhost:8006/process"
    MEDICATION_SERVICE_URL: str = "http://localhost:8012/process"
    
    # Specialized Agent Services
    LONELINESS_SERVICE_URL: str = "http://localhost:8015/loneliness-companion/process"
    ACCOUNTABILITY_SERVICE_URL: str = "http://localhost:8015/accountability/process"
    THERAPY_SERVICE_URL: str = "http://localhost:8015/therapy/process"
    
    # Orchestrator Service Configuration
    ORCHESTRATOR_HOST: str = "0.0.0.0"
    ORCHESTRATOR_PORT: int = 8002
    ORCHESTRATOR_WORKERS: int = 1
    ORCHESTRATOR_CONCURRENCY_LIMIT: int = 100
    
    # HTTP Client Configuration
    HTTP_CONNECT_TIMEOUT: float = 5.0
    HTTP_READ_TIMEOUT: float = 30.0
    HTTP_WRITE_TIMEOUT: float = 15.0
    HTTP_POOL_TIMEOUT: float = 10.0
    MAX_KEEPALIVE_CONNECTIONS: int = 50
    MAX_CONNECTIONS: int = 200
    
    # Service Timeouts
    DEFAULT_SERVICE_TIMEOUT: float = 30.0
    CHECKPOINT_SERVICE_TIMEOUT: float = 5.0
    PRIMARY_SERVICE_TIMEOUT: float = 30.0
    HUMAN_INTERVENTION_TIMEOUT: float = 10.0
    CHECKLIST_TIMEOUT: float = 15.0
    MEDICATION_TIMEOUT: float = 45.0
    PRIVACY_TIMEOUT: float = 45.0
    
    # Cache Configuration
    REDIS_URL: str = "redis://localhost:6379"
    LOCAL_CACHE_SIZE: int = 1000
    CACHE_TTL: int = 3600
    CHECKPOINT_EVALUATION_CACHE_TTL: int = 60
    TASK_STATE_CACHE_TTL: int = 300
    
    # Agent Configuration
    MAX_SERVICE_RETRIES: int = 3
    
    # Logging
    LOG_LEVEL: str = "INFO"
    
    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "ignore"  # Ignore extra fields from .env file

def get_settings() -> OrchestratorSettings:
    return OrchestratorSettings()
