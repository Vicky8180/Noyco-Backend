"""
Core Service Configuration
Handles configuration for the consolidated core service
"""

import os
import logging
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

class CoreConfig:
    """Configuration for the core service"""
    
    def __init__(self):
        self.host = os.getenv('CORE_SERVICE_HOST', '0.0.0.0')
        self.port = int(os.getenv('CORE_SERVICE_PORT', '8002'))
        self.log_level = os.getenv('LOG_LEVEL', 'INFO')
        
        # Service-specific configurations
        self.orchestrator_enabled = os.getenv('ORCHESTRATOR_ENABLED', 'true').lower() == 'true'
        self.primary_enabled = os.getenv('PRIMARY_ENABLED', 'true').lower() == 'true'
        self.checkpoint_enabled = os.getenv('CHECKPOINT_ENABLED', 'true').lower() == 'true'
        self.checklist_enabled = os.getenv('CHECKLIST_ENABLED', 'true').lower() == 'true'


def get_core_config() -> CoreConfig:
    """Get core service configuration"""
    return CoreConfig()