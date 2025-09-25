"""
Main FastAPI application for specialized emotional and social support agents
Including Accountability Buddy for Life Reboots and Therapy Check-In Agent
"""

import logging
from typing import Dict, List, Optional, Any
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
import uvicorn
import time
import json
import asyncio
from config import get_settings

# Import agent processors
if __name__ == "__main__" and __package__ is None:
    import sys
    from os import path
    sys.path.append(path.dirname(path.dirname(path.abspath(__file__))))

    from accountability.accountability_agent_v2 import AccountabilityAgentV2
    from emotional.emotional_companion_agent import process_message as emotional_process
    from anxiety.anxiety_agent import process_message as anxiety_process
    from therapy.therapy_agent import process_message as therapy_process
    from loneliness.loneliness_agent import process_message as loneliness_process
else:
    from .accountability.accountability_agent_v2 import AccountabilityAgentV2
    from .emotional.emotional_companion_agent import process_message as emotional_process
    from .anxiety.anxiety_agent import process_message as anxiety_process
    from .therapy.therapy_agent import process_message as therapy_process
    from .loneliness.loneliness_agent import process_message as loneliness_process

from common.models import Checkpoint
# Configure logging
logging.basicConfig(level=logging.INFO,
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
_logger = logging.getLogger(__name__)

# Load settings
settings = get_settings()

app = FastAPI(
    title="Specialized Support Agents",
    description="Accountability buddy, therapy check-in, emotional companion, loneliness support, mental health, and social anxiety preparation agents"
)

# === REQUEST/RESPONSE MODELS ===

class AgentRequest(BaseModel):
    text: str
    conversation_id: str
    user_id: Optional[str] = None
    task_id: Optional[str] = None
    checkpoint: Optional[Checkpoint] = None
    context: Optional[List[Dict[str, str]]] = Field(default_factory=list)
    checkpoint_status: Optional[str] = "pending"
    sync_agent_results: Optional[List[dict]] = Field(default_factory=list)
    async_agent_results: Optional[Dict[str, Any]] = Field(default_factory=dict)
    task_stack: Optional[List[Dict[str, Any]]] = Field(default_factory=list)

class AccountabilityAgentRequest(BaseModel):
    user_query: str = Field(..., description="User query or message")
    conversation_id: str = Field(..., description="Unique ID of the ongoing conversation")
    checkpoint: Optional[str] = Field(None, description="Current checkpoint/state in the conversation flow")
    context: str = Field(default="", description="Additional context as string")
    user_id: str = Field(..., description="User ID for backward compatibility")
    user_profile_id: str = Field(..., description="ID of the user's profile (used to fetch complete user context)")
    agent_instance_id: str = Field(..., description="ID of the agent instance collection (tracks goals, progress, and updates)")

class TherapyAgentRequest(BaseModel):
    user_query: str = Field(..., description="User's message")
    conversation_id: str = Field(..., description="Conversation identifier")
    checkpoint: Optional[str] = Field(None, description="Current checkpoint/state in the conversation flow")
    context: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Additional context")
    individual_id: Optional[str] = Field(None, description="Reference to the individual agent instance")
    user_profile_id: str = Field(..., description="ID of the user's profile")
    agent_instance_id: str = Field(..., description="ID of the agent instance collection (existing)")

class EmotionalAgentRequest(BaseModel):
    user_query: str = Field(..., description="User's message")
    conversation_id: str = Field(..., description="Conversation identifier")
    checkpoint: Optional[str] = Field(None, description="Current checkpoint/state in the conversation flow")
    context: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Additional context")
    individual_id: Optional[str] = Field(None, description="Reference to the individual agent instance")
    user_profile_id: str = Field(..., description="ID of the user's profile")
    agent_instance_id: str = Field(..., description="ID of the agent instance collection (existing)")

class AnxietyAgentRequest(BaseModel):
    user_query: str = Field(..., description="User's message")
    conversation_id: str = Field(..., description="Conversation identifier")
    checkpoint: Optional[str] = Field(None, description="Current checkpoint/state in the conversation flow")
    context: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Additional context")
    individual_id: Optional[str] = Field(None, description="Reference to the individual agent instance")
    user_profile_id: str = Field(..., description="ID of the user's profile")
    agent_instance_id: str = Field(..., description="ID of the agent instance collection (existing)")

class LonelinessCompanionRequest(BaseModel):
    user_query: str
    context: str
    checkpoint: str
    conversation_id: str
    user_profile_id: str  # Updated to use user_profile_id
    agent_instance_id: str  # Added agent_instance_id
    user_id: str  # Keep for backward compatibility

class LonelinessWebSocketRequest(BaseModel):
    user_query: str
    context: str = ""
    checkpoint: str = ""
    conversation_id: str
    user_profile_id: str
    agent_instance_id: str
    user_id: str = ""  # Keep for backward compatibility
    streaming_config: Optional[Dict[str, Any]] = Field(default_factory=dict)

class AgentResponse(BaseModel):
    response: str
    conversation_id: str
    checkpoint_status: str
    requires_human: bool = False
    processing_time: float = 0.0
    collected_inputs: Optional[Dict[str, str]] = Field(default_factory=dict)
    action_required: bool = False
    agent_type: str
    agent_specific_data: Optional[Dict[str, Any]] = Field(default_factory=dict)

# === UTILITY FUNCTIONS ===

def is_last_checkpoint(task_stack: list, checkpoint: Optional[Checkpoint]) -> bool:
    """
    Determine if the given checkpoint is the last one in the active task's checklist.
    """
    if not task_stack or checkpoint is None:
        return False

    # Find the active task
    active_task = next((task for task in task_stack if task.get("is_active")), None)
    if not active_task or "checklist" not in active_task:
        return False

    checklist = active_task["checklist"]

    # Extract the checkpoint name from the Checkpoint object
    checkpoint_name = getattr(checkpoint, "name", "")
    if not checkpoint_name:
        return False
        
    # Clean and match checkpoint name
    normalized_input = checkpoint_name.strip().lower()
    for idx, checkpoint_item in enumerate(checklist):
        if normalized_input in checkpoint_item.get("name", "").strip().lower():
            return idx == len(checklist) - 1

    return False  # If checkpoint not found

# === ENDPOINTS ===

@app.post("/accountability/process")
async def process_accountability_message(request: AccountabilityAgentRequest):
    """Process accountability buddy agent requests"""
    try:
        start_time = time.time()
        
        # Initialize accountability agent
        agent = AccountabilityAgentV2()
        await agent.initialize()
        
        # Convert string context to dict if needed
        context_dict = {}
        if request.context:
            try:
                # Try to parse as JSON if it's a JSON string
                import json
                context_dict = json.loads(request.context) if request.context.strip().startswith('{') else {"context": request.context}
            except:
                # If not JSON, treat as simple string context
                context_dict = {"context": request.context}
        
        result = await agent.process_message(
            text=request.user_query,  # Use user_query instead of text
            conversation_id=request.conversation_id,
            user_profile_id=request.user_profile_id,
            agent_instance_id=request.agent_instance_id,
            user_id=request.user_id,  # Use the provided user_id
            checkpoint=request.checkpoint,
            context=context_dict,  # Use converted context dict
            individual_id=None  # Set to None since it's not in the request
        )
        
        processing_time = time.time() - start_time
        
        # Debug logging
        _logger.info(f"Accountability agent result: {result}")
        _logger.info(f"Processing time: {processing_time:.2f}s")
        
        return AgentResponse(
            response=result.get("response", "I'm here to help you stay accountable!"),
            conversation_id=request.conversation_id,
            checkpoint_status=result.get("checkpoint_status", "completed"),
            requires_human=result.get("requires_human", False),
            processing_time=processing_time,
            agent_type="accountability_buddy",
            agent_specific_data=result.get("agent_specific_data", {})
        )
        
    except Exception as e:
        _logger.error(f"Error in accountability agent: {e}")
        raise HTTPException(status_code=500, detail=f"Accountability agent error: {str(e)}")
    
    
    
    



@app.post("/emotional/process")
async def process_emotional_message(request: EmotionalAgentRequest):
    """Process emotional companion agent requests"""
    try:
        start_time = time.time()
        
        result = await emotional_process(
            text=request.user_query,
            conversation_id=request.conversation_id,
            checkpoint=request.checkpoint,
            context=request.context,
            individual_id=request.individual_id,
            user_profile_id=request.user_profile_id,
            agent_instance_id=request.agent_instance_id,
            user_id=""
        )
        
        processing_time = time.time() - start_time
        
        # Debug logging
        _logger.info(f"Emotional agent result: {result}")
        _logger.info(f"Processing time: {processing_time:.2f}s")
        
        return AgentResponse(
            response=result.get("response", result.get("reply", "I'm here to listen and support you.")),
            conversation_id=request.conversation_id,
            checkpoint_status=result.get("checkpoint_status", result.get("checkpoint", "completed")),
            requires_human=result.get("requires_human", False),
            processing_time=processing_time,
            agent_type="emotional_companion",
            agent_specific_data=result.get("agent_specific_data", result.get("context", {}))
        )
        
    except Exception as e:
        _logger.error(f"Error in emotional agent: {e}")
        raise HTTPException(status_code=500, detail=f"Emotional agent error: {str(e)}")    
@app.post("/therapy/process")
async def process_therapy_message(request: TherapyAgentRequest):
    """Process therapy check-in agent requests"""
    try:
        start_time = time.time()
        
        result = await therapy_process(
            text=request.user_query,
            conversation_id=request.conversation_id,
            checkpoint=request.checkpoint,
            context=request.context,
            individual_id=request.individual_id,
            user_profile_id=request.user_profile_id,
            agent_instance_id=request.agent_instance_id,
            user_id=""  # Add user_id parameter
        )
        
        processing_time = time.time() - start_time
        
        # Debug logging
        _logger.info(f"Therapy agent result: {result}")
        _logger.info(f"Processing time: {processing_time:.2f}s")
        
        return AgentResponse(
            response=result.get("response", result.get("reply", "How are you feeling today?")),
            conversation_id=request.conversation_id,
            checkpoint_status=result.get("checkpoint_status", result.get("checkpoint", "completed")),
            requires_human=result.get("requires_human", False),
            processing_time=processing_time,
            agent_type="therapy_checkin",
            agent_specific_data=result.get("agent_specific_data", result.get("context", {}))
        )
        
    except Exception as e:
        _logger.error(f"Error in therapy agent: {e}")
        raise HTTPException(status_code=500, detail=f"Therapy agent error: {str(e)}")

@app.post("/loneliness/process", response_model=AgentResponse)
async def process_loneliness(request: LonelinessCompanionRequest):
    """Process loneliness agent requests"""
    try:
        start_time = time.time()
        
        result = await loneliness_process(
            user_query=request.user_query,
            context=request.context,
            checkpoint=request.checkpoint,
            conversation_id=request.conversation_id,
            user_profile_id=request.user_profile_id,
            agent_instance_id=request.agent_instance_id,
            user_id=request.user_id
        )
        
        processing_time = time.time() - start_time
        
        return AgentResponse(
            response=result.get("response", "I'm here to keep you company. How are you feeling?"),
            conversation_id=request.conversation_id,
            checkpoint_status=result.get("checkpoint_status", "completed"),
            requires_human=result.get("requires_human", False),
            processing_time=processing_time,
            agent_type="loneliness",
            agent_specific_data=result.get("agent_specific_data", {})
        )
        
    except Exception as e:
        _logger.error(f"Error in loneliness agent: {e}")
        raise HTTPException(status_code=500, detail=f"Loneliness agent error: {str(e)}")



@app.post("/anxiety/process")
async def process_anxiety_message(request: AnxietyAgentRequest):
    """Process anxiety support agent requests"""
    try:
        start_time = time.time()
        
        result = await anxiety_process(
            user_query=request.user_query,
            conversation_id=request.conversation_id,
            checkpoint=request.checkpoint,
            context=request.context,
            individual_id=request.individual_id,
            user_profile_id=request.user_profile_id,
            agent_instance_id=request.agent_instance_id,
            user_id=""
        )
        
        processing_time = time.time() - start_time
        
        # Debug logging
        _logger.info(f"Anxiety agent result: {result}")
        _logger.info(f"Processing time: {processing_time:.2f}s")
        
        return AgentResponse(
            response=result.get("response", result.get("reply", "I'm here to help you with your anxiety.")),
            conversation_id=request.conversation_id,
            checkpoint_status=result.get("checkpoint_status", result.get("checkpoint", "completed")),
            requires_human=result.get("requires_human", False),
            processing_time=processing_time,
            agent_type="anxiety_support",
            agent_specific_data=result.get("agent_specific_data", result.get("context", {}))
        )
        
    except Exception as e:
        _logger.error(f"Error in anxiety agent: {e}")
        raise HTTPException(status_code=500, detail=f"Anxiety agent error: {str(e)}")

# === HEALTH CHECKS ===

@app.get("/health")
async def health_check():
    """General health check for the specialized agents service"""
    return {"status": "healthy", "message": "Specialized agents service is running"}

@app.get("/therapy/health")
async def therapy_health_check():
    """Health check for the therapy agent"""
    # Basic check, can be expanded with dependency checks (e.g., model loading)
    return {"status": "healthy", "agent": "therapy_checkin"}

@app.get("/loneliness/health")
async def loneliness_health_check():
    """Health check for the loneliness agent"""
    return {"status": "healthy", "agent": "loneliness_companion"}

@app.get("/accountability/health")
async def accountability_health_check():
    """Health check for the accountability agent"""
    return {"status": "healthy", "agent": "accountability_buddy"}

# Therapy streaming endpoint removed as requested

# Emotional streaming endpoint removed as requested

# Anxiety streaming endpoint removed as requested

@app.get("/")
async def root():
    """Root endpoint"""
    return {"message": "Specialized Support Agents API", "status": "active"}

# Run the application
if __name__ == "__main__":
    uvicorn.run(app, host=settings.SERVICE_HOST, port=settings.SERVICE_PORT)