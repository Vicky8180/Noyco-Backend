# File: core/checklist/main.py

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
from typing import Dict, List, Optional, Any, Union, Literal
import logging
import json
from datetime import datetime

try:
    # Try relative imports first (when used as submodule)
    from .agent import track_checkpoint_progress
    import_mode = "relative"
except ImportError:
    try:
        # Fallback to absolute imports 
        from core.checklist.agent import track_checkpoint_progress
        import_mode = "absolute"
    except ImportError:
        # Last resort for standalone execution
        import sys
        from os import path
        sys.path.append(path.dirname(path.dirname(path.abspath(__file__))))
        from core.checklist.agent import track_checkpoint_progress
        import_mode = "standalone"

# Import common models - this is always at root level
from common.models import CheckpointType, CheckpointStatus, AgentResponseStatus, Checkpoint

logging.basicConfig(level=logging.INFO)
_logger = logging.getLogger(__name__)

app = FastAPI(title="Checklist Specialist Agent")

class ChecklistRequest(BaseModel):
    text: str
    conversation_id: str
    checkpoint: Optional[Checkpoint] = None
    context: Optional[Union[List[Dict[str, str]], Dict[str, Any]]] = []

class ChecklistResponse(BaseModel):
    checkpoint_complete: bool
    progress_percentage: float
    next_question: Optional[str] = None
    confidence: Optional[float] = None

@app.get("/health")
async def health_check():
    """Health check endpoint for checklist agent"""
    return {"status": "ok", "service": "checklist_agent"}

@app.post("/process", response_model=ChecklistResponse)
async def process_endpoint(request: ChecklistRequest):
    """Track checkpoint progress in the conversation"""
    try:
        # Process context
        context_list = []
        if isinstance(request.context, list):
            context_list = request.context
        elif isinstance(request.context, dict):
            # Convert dictionary to list if needed
            context_list = [request.context]
        else:
            context_list = []

        # Track checkpoint progress
        result = await track_checkpoint_progress(
            request.text,
            request.checkpoint,
            context_list
        )


        return ChecklistResponse(**result)
    except Exception as e:
        _logger.exception("Checklist agent error")
        raise HTTPException(status_code=500, detail=f"Checklist agent error: {str(e)}")

@app.post("/debug")
async def debug_endpoint(request: Request):
    """Debug endpoint to inspect incoming request bodies"""
    body = await request.body()
    try:
        data = json.loads(body)
        _logger.info(f"Debug - Request body: {data}")
        _logger.info(f"Debug - Context type: {type(data.get('context'))}")
        return {"status": "debug complete", "body": data}
    except Exception as e:
        _logger.exception("Debug error")
        return {"status": "error", "message": str(e), "raw_body": body.decode('utf-8', errors='replace')}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8007)
