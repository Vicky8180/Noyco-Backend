# File: checkpoint/main.py
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from datetime import datetime
import uvicorn
import logging

# Conditional imports to handle both standalone and package execution
try:
    # Try relative imports first (when used as submodule)
    from .generator import generate_checkpoints
    from .config import get_settings
    import_mode = "relative"
except ImportError:
    # Fallback to absolute imports (when run standalone)
    if __name__ == "__main__" and __package__ is None:
        import sys
        from os import path
        sys.path.append(path.dirname(path.dirname(path.abspath(__file__))))
        # Import from project root when running standalone
        from checkpoint.generator import generate_checkpoints
        from checkpoint.config import get_settings
        import_mode = "standalone"
    else:
        # Import with relative paths when running as part of the package
        from .generator import generate_checkpoints
        from .config import get_settings
        import_mode = "module"

# Import common models - this is always at root level
from common.models import Task, Checkpoint, CheckpointType

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize settings
settings = get_settings()

# Validate required environment variables on startup
def validate_environment():
    """Validate that all required environment variables are set"""
    if not settings.GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY environment variable is required but not set")
    

# Validate environment on startup
validate_environment()

app = FastAPI(
    title="Checkpoint Generator Service",
    version=settings.SERVICE_VERSION,
    description="Medical conversation checkpoint generation service"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure as needed
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class CheckpointRequest(BaseModel):
    text: str
    conversation_id: str
    task_type: CheckpointType = "Main"
    context: Optional[List[Dict[str, str]]] = None
    limit: Optional[int] = 2
    existing_task_id: Optional[str] = None
    detected_intent: Optional[str] = None  # Intent detected by the system
    agent_type: Optional[str] = None       # Type of agent assigned
    conversation_context: Optional[List[Dict[str, Any]]] = None  # Full conversation history

class CheckpointResponse(BaseModel):
    task: Task
    checkpoints: List[Checkpoint]
    timestamp: datetime = datetime.now()
    is_new_task: bool = True

@app.post("/generate", response_model=CheckpointResponse)
async def generate_endpoint(request: CheckpointRequest):
    """Generate medical conversation checkpoints based on query and context"""
    start_time = datetime.now()
    
    try:
        logger.info(f"Processing checkpoint request for conversation: {request.conversation_id}")
        logger.debug(f"Request text: {request.text[:100]}...")
        
        # Generate checkpoints using the context if provided
        checkpoints_data = await generate_checkpoints(
            request.text,
            request.task_type, 
            context=request.context, 
            limit=request.limit,
            detected_intent=request.detected_intent,
            agent_type=request.agent_type,
            conversation_context=request.conversation_context
        )

        # Create checkpoint objects
        checkpoint_objects = []
        for i, checkpoint_info in enumerate(checkpoints_data):
            checkpoint = Checkpoint(
                name=checkpoint_info.get("text"),
                status="pending",
                expected_inputs=checkpoint_info.get("expected_inputs", []),
                collected_inputs=[]
            )
            checkpoint_objects.append(checkpoint)

        # Create or update task object
        is_new_task = True
        if request.existing_task_id:
            task_id = request.existing_task_id
            label = f"Task updated with context at: {datetime.now().strftime('%H:%M:%S')}"
            is_new_task = False
        else:
            task_id = f"task_{request.conversation_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}"
            label = f"Task generated from: {request.text}"
        
        task = Task(
            task_id=task_id,
            label=label,
            source=request.task_type,
            checklist=checkpoint_objects,
            current_checkpoint_index=0,
            is_active=True
        )

        process_time = (datetime.now() - start_time).total_seconds()
        logger.info(f"Checkpoint generation completed in {process_time:.2f}s")

        return CheckpointResponse(
            task=task,
            checkpoints=checkpoint_objects,
            is_new_task=is_new_task
        )
    except Exception as e:
        process_time = (datetime.now() - start_time).total_seconds()
        logger.error(f"Checkpoint generation failed after {process_time:.2f}s: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Checkpoint generation error: {str(e)}")

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": settings.SERVICE_NAME,
        "version": settings.SERVICE_VERSION,
        "environment": settings.ENVIRONMENT,
        "timestamp": datetime.now()
    }

if __name__ == "__main__":
    uvicorn.run(
        app, 
        host="0.0.0.0", 
        port=settings.SERVICE_PORT,
        log_level="info" if settings.ENVIRONMENT == "development" else "warning"
    )



