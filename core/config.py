"""
Core Service Configuration
Handles configuration for the consolidated core service
"""

import os
from typing import Optional


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