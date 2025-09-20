#orchestrator/agents.py
"""
Agent configuration and detection functions.
This module handles the agent configuration and detection logic.
"""

import logging
from typing import List, Tuple, Dict, Any, Optional
from functools import lru_cache
# from orchestrator.timing import TimingMetrics

from common.models import AgentResult, AgentResponseStatus

_logger = logging.getLogger(__name__)

# Updated agent configuration with detailed type classification
AGENT_CONFIG = {
    "primary": {"port": 8004, "path": "/process", "type": "core", "dependencies": []},
    "checklist": {"port": 8007, "path": "/process", "type": "sync","dependencies": []},
    "privacy": {"port": 8011, "path": "/process", "type": "sync","dependencies": []},
    "nutrition": {"port": 8005, "path": "/process", "type": "sync", "dependencies": [ "privacy","followup"]},
    "followup": {"port": 8008, "path": "/process", "type": "sync","dependencies": []},
    "history": {"port": 8009, "path": "/process", "type": "async","dependencies": []},
    "human_intervention": {"port": 8006, "path": "/process", "type": "sync","dependencies": []},
    "medication": {"port": 8012, "path": "/process", "type": "sync","dependencies": []},

}

# Map from detector agent names to system agent names
AGENT_NAME_MAPPING = {
    "checklist": "checklist",
    "privacy": "privacy",
    "nutrition": "nutrition",
    "followup": "followup",
    "history": "history",
    "medication": "medication",
    "human_intervention": "human_intervention",

}

CHECKLISTS = {
    "followup": {
        "task_id": "followup",
        "label": "followup",
        "source": "SupportAgent",
        "checklist": [
            {
                "name": "Please confirm your full name.",
                "status": "pending",
                "expected_inputs": ["full_name"],
                "collected_inputs": []
            },
            {
                "name": "Please provide your date of birth.",
                "status": "pending",
                "expected_inputs": ["date_of_birth"],
                "collected_inputs": []
            },
            {
                "name": "Please share your contact number.",
                "status": "pending",
                "expected_inputs": ["phone_number"],
                "collected_inputs": []
            }
        ],
        "current_checkpoint_index": 0,
        "is_active": True
    },
    "privacy": {
        "task_id": "privacy",
        "label": "privacy",
        "source": "SupportAgent",
        "checklist": [
            {
                "name": "provide me your full name ",
                "status": "pending",
                "expected_inputs": ["name and surname"],
                "collected_inputs": []
            },
            {
                "name": "please let me know your date of birth",
                "status": "pending",
                "expected_inputs": ["date", "date of birth", "dob", "dd/mm/yyyy"],
                "collected_inputs": []
            },
            {
                "name": "please provide your contact number",
                "status": "pending",
                "expected_inputs": ["contact number", "phone number"],
                "collected_inputs": []
            }
        ],
        "current_checkpoint_index": 0,
        "is_active": True
    }
}


# Cache for specialist service configurations
@lru_cache(maxsize=128)
def get_specialist_config():
    """Cache the specialist configuration to avoid repeated dictionary lookups"""
    return AGENT_CONFIG

# Service URL cache
@lru_cache(maxsize=32)
def get_service_url(service_name: str) -> str:
    """Get cached service URL to avoid string operations during request handling"""
    from orchestrator.config import get_settings
    settings = get_settings()
    
    config = get_specialist_config()
    if service_name in config:
        return f"http://localhost:{config[service_name]['port']}{config[service_name]['path']}"
    return settings.PRIMARY_SERVICE_URL  # Default to primary from settings

def resolve_dependencies(agents: List[str]) -> List[str]:
    """
    Resolves dependencies for a list of agents and returns a list with dependencies
    at the front of the array.

    Args:
        agents: List of agent names

    Returns:
        List of agents with dependencies at the front
    """
    resolved = []
    visited = set()

    def resolve_agent_dependencies(agent):
        if agent in visited:
            return
        visited.add(agent)

        # Process dependencies first
        if agent in AGENT_CONFIG:
            for dependency in AGENT_CONFIG[agent]["dependencies"]:
                if dependency in AGENT_CONFIG:
                    resolve_agent_dependencies(dependency)

        # Add the agent if not already in the resolved list
        if agent not in resolved:
            resolved.append(agent)

    # Process each agent
    for agent in agents:
        resolve_agent_dependencies(agent)

    return resolved

def get_agent_checklists(agents: List[str]) -> Dict[str, Any]:
    """
    Get checklists for the given agents.

    Args:
        agents: List of agent names

    Returns:
        Dictionary mapping agent names to their checklists
    """
    agent_checklists = {}

    for agent in agents:
        if agent in CHECKLISTS:
            agent_checklists[agent] = CHECKLISTS[agent]

    return agent_checklists



def create_agent_result(
    agent_name: str,
    status: AgentResponseStatus,
    result_payload: Dict[str, Any],
    message_to_user: Optional[str] = None,
    action_required: bool = False
) -> AgentResult:
    """
    Create a standardized agent result object based on the new schema.

    Args:
        agent_name: Name of the agent
        status: Status of the agent response (success, error, partial)
        result_payload: Structured output from the agent
        message_to_user: Optional message to display to the user
        action_required: Whether action is required from the user

    Returns:
        An AgentResult object
    """
    return AgentResult(
        agent_name=agent_name,
        status=status,
        result_payload=result_payload,
        message_to_user=message_to_user,
        action_required=action_required,
        consumed=False
    )

def get_agent_type(agent_name: str) -> str:
    """
    Get the agent type (sync, async, core) for a given agent name.

    Args:
        agent_name: Name of the agent

    Returns:
        Agent type as a string
    """
    if agent_name in AGENT_CONFIG:
        return AGENT_CONFIG[agent_name]["type"]
    return "unknown"
