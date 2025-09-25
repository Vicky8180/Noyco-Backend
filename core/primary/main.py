import logging
from typing import Dict, List, Optional, Any
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
import uvicorn
import time

try:
    # Try relative imports first (when used as submodule)
    from .agent import process_message
    import_mode = "relative"
except ImportError:
    # Fallback to absolute imports (when run standalone)
    if __name__ == "__main__" and __package__ is None:
        import sys
        from os import path
        sys.path.append(path.dirname(path.dirname(path.abspath(__file__))))

        from agent import process_message
        import_mode = "standalone"
    else:
        from core.primary.agent import process_message
        import_mode = "module"

# Import common models - this is always at root level
from common.models import Checkpoint

# Configure logging
logging.basicConfig(level=logging.INFO,
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
_logger = logging.getLogger(__name__)

app = FastAPI(
    title="Primary Medical Agent",
    description="Optimized primary medical agent service with health monitoring"
)

# Add health endpoint for monitoring
@app.get("/health")
async def health_check():
    """Health check endpoint for service monitoring"""
    return {"status": "ok", "service": "primary"}

class PrimaryRequest(BaseModel):
    text: str
    conversation_id: str
    task_id: Optional[str] = None
    checkpoint: Optional[Checkpoint] = None
    context: Optional[List[Dict[str, str]]] = Field(default_factory=list)
    checkpoint_status: Optional[str] = "pending"
    sync_agent_results: Optional[List[dict]] = Field(default_factory=dict)
    async_agent_results: Optional[Dict[str, Any]] = Field(default_factory=dict)
    task_stack: Optional[List[Dict[str, Any]]] = Field(default_factory=list)

class PrimaryResponse(BaseModel):
    response: str
    conversation_id: str
    checkpoint_status: str  # pending, in_progress, complete
    requires_human: bool = False
    processing_time: float = 0.0
    collected_inputs: Optional[Dict[str, str]] = Field(default_factory=dict)
    action_required: bool = False
    
def is_last_checkpoint(task_stack: list, checkpoint: Optional[Checkpoint]) -> bool:
    """
    Determine if the given checkpoint is the last one in the active task's checklist.

    Args:
        task_stack (list): List of task dictionaries.
        checkpoint (Optional[Checkpoint]): The checkpoint object to check.

    Returns:
        bool: True if it is the last checkpoint in the checklist, False otherwise.
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
        if checkpoint_item.get("name", "").strip().lower() == normalized_input:
            return idx == len(checklist) - 1  # True if it's the last checkpoint

    return False  # If checkpoint not found
    

@app.post("/process", response_model=PrimaryResponse)
async def process_endpoint(request: PrimaryRequest):
    """Process a patient message and generate a response"""
    start_time = time.time()

    try:
        _logger.info(f"Processing message for conversation {request.conversation_id}")

  
        result = await process_message(
            text=request.text,
            conversation_id=request.conversation_id,
            task_id=request.task_id,
            checkpoint=request.checkpoint,
            context=request.context,
            checkpoint_status=request.checkpoint_status,
            sync_agent_results=request.sync_agent_results,
            async_agent_results=request.async_agent_results,
            task_stack=request.task_stack,
            is_last_checkpoint=is_last_checkpoint(request.task_stack, request.checkpoint.name if request.checkpoint else None)
        )


        # Calculate processing time
        processing_time = round((time.time() - start_time) * 1000, 2)  # ms

        # Log completion
        _logger.info(f"Processed message in {processing_time}ms")

        # Return the response
        return PrimaryResponse(
            response=result["response"],
            conversation_id=request.conversation_id,
            checkpoint_status=result.get("checkpoint_status", request.checkpoint_status),
            requires_human=result.get("requires_human", False),
            processing_time=processing_time,
            collected_inputs=result.get("collected_inputs", {}),
            action_required=result.get("action_required", False)
        )

    except Exception as e:
        _logger.exception("Error processing message")
        raise HTTPException(status_code=500, detail=f"Processing error: {str(e)}")

if __name__ == "__main__":
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8004,
        log_level="info"
    )
