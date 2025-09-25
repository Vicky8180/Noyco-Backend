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
    secret_content = os.getenv("conversationalengine-secret")

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
        # env_file = ".env"
        case_sensitive = True
        extra = "allow"  # Allow extra fields from .env that this service doesn't use

def get_settings() -> AgentsSettings:
    return AgentsSettings()
