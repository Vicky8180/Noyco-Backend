import os
import logging
from pydantic_settings import BaseSettings
from typing import Optional
from dotenv import load_dotenv

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def _load_production_secrets():
    """
    Loads secrets from a single environment variable in production.
    If the variable is not found, it falls back to a local .env file.
    """
    # This is the environment variable you will set in Cloud Run
    # Its value will be the entire content of your production .env file
    secret_content = os.getenv("conversationalengine-secrets")

    if secret_content:
        logger.info("✅ Production secrets found. Loading from environment.")
        try:
            # Parse the multi-line secret string and set environment variables
            for line in secret_content.strip().split('\n'):
                if '=' in line and not line.strip().startswith('#'):
                    key, value = line.strip().split('=', 1)
                    os.environ[key] = value
            logger.info("✅ Environment variables set from production secrets.")
        except Exception as e:
            logger.error(f"❌ Failed to parse production secrets: {e}")
    else:
        logger.warning("⚠️ Production secrets not found. Falling back to local .env file.")
        load_dotenv()

# Run the loader function when this module is imported
_load_production_secrets()

class OrchestratorSettings(BaseSettings):
    # Environment
    ENVIRONMENT: str = "development"
    
    # Database Configuration (for integrated memory service)
    MONGODB_URI: str
    DATABASE_NAME: str = "conversionalEngine"
    REDIS_URL: str
    
    # Core Service URLs (MEMORY_URL kept for backward compatibility but not used)
    MEMORY_URL: str = "http://localhost:8003"  # Deprecated - using direct access now
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
        # env_file = ".env"
        case_sensitive = True
        extra = "ignore"  # Ignore extra fields from .env file

def get_settings() -> OrchestratorSettings:
    return OrchestratorSettings()
