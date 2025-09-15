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
from common.models import Checkpoint
from .config import get_settings

# Load settings
settings = get_settings()

# Import agent processors
from .accountability.accountability_agent_v2 import AccountabilityAgentV2
# Use the minimal therapy agent that mirrors accountability behavior
from .therapy.minimal_agent import process_message as therapy_process
from .loneliness.loneliness_agent import process_message as loneliness_process

# Configure logging
logging.basicConfig(level=logging.INFO,
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
_logger = logging.getLogger(__name__)

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
    text: str = Field(..., description="User's message")
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

@app.get("/health")
async def health_check():
    """Health check endpoint for service monitoring"""
    return {"status": "ok", "service": "specialized_agents"}

@app.get("/accountability/health")
async def accountability_health_check():
    """Health check endpoint for accountability agent"""
    return {"status": "ok", "service": "accountability_agent", "agent": "accountability_buddy"}

@app.get("/therapy/health")
async def therapy_health_check():
    """Health check endpoint for therapy agent"""
    return {"status": "ok", "service": "therapy_agent", "agent": "therapy_checkin"}

@app.get("/loneliness/health")
async def loneliness_health_check():
    """Health check endpoint for loneliness agent"""
    return {"status": "ok", "service": "loneliness_agent", "agent": "loneliness"}

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
@app.post("/therapy/process")
async def process_therapy_message(request: TherapyAgentRequest):
    """Process therapy check-in agent requests"""
    try:
        start_time = time.time()
        
        result = await therapy_process(
            text=request.text,
            conversation_id=request.conversation_id,
            checkpoint=request.checkpoint,
            context=request.context,
            individual_id=request.individual_id,
            user_profile_id=request.user_profile_id,
            agent_instance_id=request.agent_instance_id
        )
        
        processing_time = time.time() - start_time
        
        return AgentResponse(
            response=result.get("response", "How are you feeling today?"),
            conversation_id=request.conversation_id,
            checkpoint_status=result.get("checkpoint_status", "completed"),
            requires_human=result.get("requires_human", False),
            processing_time=processing_time,
            agent_type="therapy_checkin",
            agent_specific_data=result.get("agent_specific_data", {})
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




# {
#   "user_query": "who is president of india and america",
#   "context": "",
#   "checkpoint": "",
#   "conversation_id": "test_conversation_123",
#   "user_profile_id": "user_profile_610f7db5658e",
#   "agent_instance_id": "loneliness_597",
#   "user_id": "individual_f068689a7d96"
# }
# STREAMING DISABLED - Commented out WebSocket endpoint
# @app.websocket("/loneliness/stream")
async def loneliness_websocket(websocket: WebSocket):
    """WebSocket endpoint for REAL streaming loneliness responses"""
    await websocket.accept()
    _logger.info("Loneliness WebSocket connection established")
    
    try:
        while True:
            # Receive request from client
            data = await websocket.receive_text()
            try:
                request_data = json.loads(data)
                _logger.info(f"Received WebSocket request: {request_data.get('conversation_id', '1000')}")
                
                # Validate request data
                request = LonelinessWebSocketRequest(**request_data)
                
                # Send start signal
                await websocket.send_json({
                    "type": "start",
                    "conversation_id": request.conversation_id,
                    "timestamp": time.time()
                })
                
                # REAL STREAMING: Use streaming client directly instead of regular agent
                from .loneliness.gemini_streaming import get_streaming_client
                from .loneliness.loneliness_agent import loneliness_agent
                
                # Initialize agent if needed
                if not loneliness_agent._initialized:
                    await loneliness_agent.initialize()
                
                # Get user data for prompt building
                try:
                    user_profile, agent_data = await loneliness_agent.get_cached_data(
                        request.user_profile_id, request.agent_instance_id
                    )
                    session_state = await loneliness_agent.get_session_state_fast(
                        request.conversation_id, request.user_profile_id
                    )
                except Exception as e:
                    _logger.warning(f"Data fetch error: {e}, using defaults")
                    # Use minimal defaults
                    user_profile = type('Profile', (), {'name': 'Friend', 'interests': []})()
                    agent_data = type('Agent', (), {'loneliness_goals': []})()
                    session_state = {'current_mood': 'neutral', 'conversation_turns': []}
                
                # Build prompt
                prompt = await loneliness_agent.build_gemini_prompt(
                    request.user_query, user_profile, agent_data, session_state
                )
                
                # REAL STREAMING: Stream directly from Gemini
                streaming_client = get_streaming_client()
                full_response = ""
                
                async for chunk in streaming_client.stream_generate_content(
                    prompt, max_tokens=200, temperature=0.7, chunk_size=2
                ):
                    # Forward chunks directly to WebSocket
                    chunk["conversation_id"] = request.conversation_id
                    await websocket.send_json(chunk)
                    
                    # Collect full response for background tasks
                    if chunk.get("type") == "content":
                        full_response += chunk.get("data", "")
                    elif chunk.get("type") == "done":
                        full_response = chunk.get("data", full_response)
                        break
                
                # Send final completion
                await websocket.send_json({
                    "type": "complete",
                    "conversation_id": request.conversation_id,
                    "response_length": len(full_response),
                    "timestamp": time.time()
                })
                
                # Schedule background tasks (non-blocking)
                if full_response:
                    asyncio.create_task(loneliness_agent._schedule_background_tasks_async(
                        request.user_profile_id, request.agent_instance_id,
                        request.user_query, full_response, "neutral", 5.0, 7.0, 0.5
                    ))
                
            except json.JSONDecodeError:
                await websocket.send_json({
                    "type": "error",
                    "data": "Invalid JSON format",
                    "timestamp": time.time()
                })
            except Exception as request_error:
                _logger.error(f"Error processing WebSocket request: {request_error}")
                await websocket.send_json({
                    "type": "error",
                    "data": f"Processing error: {str(request_error)}",
                    "timestamp": time.time()
                })
                
    except WebSocketDisconnect:
        _logger.info("Loneliness companion WebSocket connection closed")
    except Exception as e:
        _logger.error(f"WebSocket error: {e}")
        try:
            await websocket.send_json({
                "type": "error",
                "data": f"Connection error: {str(e)}",
                "timestamp": time.time()
            })
        except:
            pass  # Connection might be closed



@app.get("/loneliness/daily-call")
async def daily_loneliness_call():
    """Daily wellness call for loneliness agent"""
    return {"message": "Daily wellness check initiated", "status": "ok"}

@app.get("/agents")
async def get_available_agents():
    """Get list of available agents"""
    return {
        "agents": [
            {"name": "accountability_buddy", "endpoint": "/accountability/process"},
            {"name": "therapy_checkin", "endpoint": "/therapy/process"},
            {"name": "loneliness", "endpoint": "/loneliness/process"}
        ]
    }

@app.get("/accountability/info")
async def get_accountability_info():
    """Get information about accountability agent"""
    return {
        "name": "Accountability Buddy",
        "description": "Helps users stay accountable to their goals and commitments",
        "endpoint": "/accountability/process"
    }

@app.get("/therapy/info")
async def get_therapy_info():
    """Get information about therapy agent"""
    return {
        "name": "Therapy Check-in",
        "description": "Provides mental health check-ins and emotional support",
        "endpoint": "/therapy/process"
    }

@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": "Specialized Support Agents API",
        "version": "1.0.0",
        "available_agents": ["accountability_buddy", "therapy_checkin", "loneliness"]
    }

# Run the application
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8015)
