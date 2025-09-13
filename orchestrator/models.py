# # orchestrator/models.py

"""
Pydantic models for request and response objects used in the orchestrator service.
"""

from pydantic import BaseModel, Field
from typing import Dict, List, Optional, Literal, Any
from common.models import AgentResponseStatus, CheckpointType, CheckpointStatus, AgentResult

class OrchestratorQuery(BaseModel):
    """Model representing an incoming orchestrator query."""
    text: str
    conversation_id: str
    plan: str
    services: List[str]
    
    # New identifiers (replacing patient-specific ones)
    individual_id: str
    user_profile_id: str
    detected_agent: str
    agent_instance_id: str
    call_log_id: str

    # Optional legacy fields (for backward compatibility during transition)
    channel: Optional[str] = None  # Communication channel (e.g., phone, chat)
class OrchestratorResponse(BaseModel):
    """Model representing the response from the orchestrator."""
    response: str
    conversation_id: str

    # Updated to reflect new schema structure
    checkpoints: List[str]
    checkpoint_progress: Dict[str, bool]
    task_stack: List[Dict[str, Any]] = []  # Serialized task stack

    # Agent results
    sync_agent_results: Dict[str, List[AgentResult]] = {}  # Serialized agent results
    async_agent_results: Dict[str, Dict[str, Any]] = {}

    # State flags
    requires_human: bool
    is_paused: bool = False
    is_enriched: bool = False  # Flag to indicate if response was enriched by specialists

    # Metrics
    timing_metrics: Dict[str, float]
