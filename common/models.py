# File: common/models.py
from pydantic import BaseModel
from typing import List, Dict, Optional, Literal, Any
from datetime import datetime

# === ENUMS ===
CheckpointType = Literal["Main", "SupportAgent", "Interrupt"]
CheckpointStatus = Literal["pending", "in_progress", "complete"]
AgentResponseStatus = Literal["success", "error", "partial"]

# === CHECKPOINT ===
class Checkpoint(BaseModel):
    name: str
    status: CheckpointStatus = "pending"
    expected_inputs: List[str] = []             # What input we’re expecting (e.g., “dob”, “lab_name”)
    collected_inputs: List[str]=[]     # Collected key:value inputs so far


# === TASK ===
class Task(BaseModel):
    task_id: str                                 # Unique ID of this checklist or sub-checklist
    label: str                                   # Human-readable name
    source: CheckpointType                       # Main / SupportAgent / Interrupt
    checklist: List[Checkpoint] = []             # The checkpoints inside this task
    current_checkpoint_index: int = 0            # Which checkpoint we're on
    is_active: bool = True
    created_at: datetime = datetime.now()
    updated_at: datetime = datetime.now()

# === AGENT RESULT ===
class AgentResult(BaseModel):
    agent_name: str
    status: AgentResponseStatus
    result_payload: Dict[str, Any]               # Structured output
    message_to_user: Optional[str] = None
    action_required: Optional[bool] = False
    timestamp: datetime = datetime.now()
    consumed: bool = False                       # Will be set True once used by primary agent

# === CONVERSATION ===
class Conversation(BaseModel):
    conversation_id: str
    
    # New identifier fields (replacing patient-specific ones)
    individual_id: Optional[str] = None
    user_profile_id: Optional[str] = None
    detected_agent: Optional[str] = None
    agent_instance_id: Optional[str] = None

    task_stack: List[Task] = []                  # Main + sub-checklists
    context: List[Dict[str, str]] = []           # LLM window context
    complete_context: List[Dict[str, str]] = []  # Full conversation log
    temporary_context: List[Dict[str, str]] = [] # Data not yet tied to any checkpoint

    # Flattened view across stack (for quick access/debug)
    checkpoint_progress: Dict[str, bool] = {}    # e.g. {“cp1”: True, “cp2”: False}
    type_of_checkpoints_active: str= "Main"

    # Agent results
    async_agent_results: Dict[str, AgentResult] = {}  # For future/parallel agents (not needed now but reserved)
    sync_agent_results: Dict[str, List[AgentResult]] = {}   # Final outputs from agents

    # Verification and validation flags (generic, not patient-specific)
    is_verified: bool = False

    # State flags
    is_paused: bool = False
    pending_agent_invocation: Optional[str] = None
    resume_after_subtask: Optional[str] = None

    # Summarization
    has_summary: bool = False
    summary: Optional[str] = None
    key_points: List[str] = []
    tags: List[str] = []

    created_at: datetime = datetime.now()
    updated_at: datetime = datetime.now()


# Note: Patient models have been removed from common/models.py as part of 
# decoupling the engine from patient-specific dependencies.
# If patient data is needed, it should be handled through appropriate domain services.


class ConversationSummary(BaseModel):
    conversation_id: str
    
    # New identifier fields (optional for backward compatibility)
    individual_id: Optional[str] = None
    user_profile_id: Optional[str] = None
    
    summary: str
    tags: List[str] = []
    key_points: List[str] = []
    created_at: datetime = datetime.now()
