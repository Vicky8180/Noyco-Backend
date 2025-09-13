

"""
Simplified Main entry point for the Conversation Orchestrator service.
This module sets up the FastAPI application and defines the main orchestration endpoint.
"""

import asyncio
import logging
import json
from typing import Dict, List, Optional, Any
from datetime import datetime
import httpx
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Response, BackgroundTasks, status, Depends, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from common.models import Task
from .auth.validateAPI import get_current_user, JWTClaims
import websockets
from urllib.parse import urlparse

# Import local modules - Only keeping what we need
from orchestrator.models import OrchestratorQuery, OrchestratorResponse
from orchestrator.timing import TimingMetrics
from orchestrator.config import get_settings
from orchestrator.services import (
    call_checklist_service,
    call_service, 
    http_client, 
    ensure_http_client
)
from orchestrator.utils import get_conversation_state
from orchestrator.state_manager import cache_manager
import orchestrator.services
import uvicorn

# Import direct streaming function for loneliness agent
from specialists.agents.loneliness.loneliness_agent import stream_loneliness_response

# Get settings
settings = get_settings()

# Configure logging
logging.basicConfig(level=getattr(logging, settings.LOG_LEVEL),
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
_logger = logging.getLogger(__name__)

# Configuration constants from settings
HTTP_TIMEOUT = httpx.Timeout(
    connect=settings.HTTP_CONNECT_TIMEOUT,
    read=settings.HTTP_READ_TIMEOUT,
    write=settings.HTTP_WRITE_TIMEOUT,
    pool=settings.HTTP_POOL_TIMEOUT
)
CHECKPOINT_TIMEOUT = httpx.Timeout(settings.CHECKPOINT_SERVICE_TIMEOUT)
PRIMARY_TIMEOUT = httpx.Timeout(settings.PRIMARY_SERVICE_TIMEOUT)


"""
Simplified Main entry point for the Conversation Orchestrator service.
This module sets up the FastAPI application and defines the main orchestration endpoint.
"""

import asyncio
import logging
import json
from typing import Dict, List, Optional, Any
from datetime import datetime
import httpx
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Response, BackgroundTasks, status, Depends, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from common.models import Task
from .auth.validateAPI import get_current_user, JWTClaims
import websockets
from urllib.parse import urlparse

# Import local modules - Only keeping what we need
from orchestrator.models import OrchestratorQuery, OrchestratorResponse
from orchestrator.timing import TimingMetrics
from orchestrator.services import (
    call_checklist_service,
    call_service, 
    http_client, 
    ensure_http_client
)
from orchestrator.utils import get_conversation_state
from orchestrator.state_manager import cache_manager

# Configure logging
logging.basicConfig(level=logging.INFO,
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
_logger = logging.getLogger(__name__)

# Configuration constants
HTTP_TIMEOUT = httpx.Timeout(10.0, connect=2.0, read=8.0)
CHECKPOINT_TIMEOUT = httpx.Timeout(5.0)
PRIMARY_TIMEOUT = httpx.Timeout(5.0)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager with optimized HTTP client setup."""
    global http_client
    
    # Initialize cache manager first
    await cache_manager.initialize()
    _logger.debug("Cache manager initialized")
    
    limits = httpx.Limits(
        max_keepalive_connections=settings.MAX_KEEPALIVE_CONNECTIONS,
        max_connections=settings.MAX_CONNECTIONS
    )
    http_client = httpx.AsyncClient(
        timeout=HTTP_TIMEOUT,
        limits=limits,
        http2=True
    )
    _logger.debug("HTTP client initialized with optimized settings")

    # Export the http_client to the services module
    orchestrator.services.http_client = http_client

    yield

    # Clean up resources
    await http_client.aclose()
    _logger.info("HTTP client closed")

app = FastAPI(title="Conversation Orchestrator", lifespan=lifespan)

@app.on_event("startup")
async def startup_event():
    """Additional startup event handler"""
    ensure_http_client()

class SimplifiedOrchestrator:
    """Simplified orchestration logic for direct conversation flow."""

    def __init__(self):
        self._cached_context = None
        self._context_cache_key = None

    async def get_cached_context(self, state, plan: str, text: str, force_refresh: bool = False) -> List[Dict]:
        """Get context with caching to avoid repeated expensive calls."""
        cache_key = f"{state.conversation_id}_{plan}_{hash(text)}"

        if not force_refresh and self._context_cache_key == cache_key and self._cached_context is not None:
            _logger.info("Using cached context")
            return self._cached_context

        context = await state.get_context(plan=plan, text=text)

        # Ensure context is always a list
        if context is not None and not isinstance(context, list):
            context = [context] if isinstance(context, dict) else []
        else:
            context = context or []

        # Cache the result
        self._cached_context = context
        self._context_cache_key = cache_key

        return context

    async def prepare_checkpoint_data(self, query: OrchestratorQuery, state, timing: TimingMetrics) -> tuple[Optional[str], bool, Optional[Dict]]:
        """Prepare checkpoint-related data efficiently."""
        timing.start("checkpoint_preparation")

        current_checkpoint = state.get_current_checkpoint()
        checkpoint_complete = False
        checklist_result = None

        # Get context early for use in multiple places
        context_task = asyncio.create_task(
            self.get_cached_context(state, query.plan, query.text)
        )

        # Get current task
        current_task = None
        if state.task_stack:
            for task in reversed(state.task_stack):
                if task.get('is_active', False):
                    current_task = task
                    break

        # We need to generate new checkpoints in these scenarios:
        # 1. New conversation (initial 2 checkpoints)
        # 2. Second-to-last checkpoint reached (background generation)
        
        # Calculate if we need to generate more checkpoints
        generate_more_checkpoints = False
        existing_task_id = None
        
        if current_task:
            # Check if we're on second-to-last checkpoint
            checklist = current_task.get('checklist', [])
            current_index = current_task.get('current_checkpoint_index', 0)
            if len(checklist) > 1 and current_index == len(checklist) - 2:
                _logger.info("Reached second-to-last checkpoint - generating more checkpoints")
                generate_more_checkpoints = True
                existing_task_id = current_task.get('task_id')
        
        # Handle new conversation checkpoint generation
        checkpoints_task = None
        if state.is_new_conversation():
            _logger.info("Starting new conversation - generating initial checkpoints")

            timing.start("checkpoint_generation")
            checkpoints_task = asyncio.create_task(
                call_service(
                    f"{settings.CHECKPOINT_URL}/generate",
                    {
                        "text": query.text,
                        "conversation_id": query.conversation_id,
                        "limit": 2  # Initial generation limited to 2 checkpoints
                    },
                    timing,
                    "checkpoint_generator",
                    timeout=CHECKPOINT_TIMEOUT
                )
            )
        # Generate more checkpoints in background if needed
        elif generate_more_checkpoints:
            # Get conversation context
            context = await context_task
            
            # Generate one new checkpoint in the background
            # Note: We'll handle this in the main orchestrate endpoint
            
            # Note: Don't need to wait for this task to complete

        # Handle checkpoint evaluation if current checkpoint exists
        checklist_task = None
        if current_checkpoint:
            timing.start("checkpoint_evaluation")
            context = await context_task
            checklist_task = asyncio.create_task(
                call_checklist_service(
                    query.conversation_id,
                    query.text,
                    current_checkpoint,
                    context,
                    True,  # evaluation_only
                    timing
                )
            )
        else:
            await context_task  # Ensure context task completes

        # Process checkpoint generation results
        if checkpoints_task:
            checkpoint_result = await checkpoints_task
            checkpoints = checkpoint_result.get("checkpoints", [])
            checkpoint_types = checkpoint_result.get("checkpoint_types", "Main")
            task = checkpoint_result.get("task", Task)

            if checkpoints and task:
                state.set_Tasks(checkpoints, task, checkpoint_types)
                current_checkpoint = state.get_current_checkpoint()
                _logger.info(f"Generated {len(checkpoints)} initial checkpoints")

            timing.end("checkpoint_generation")

        # Process checklist evaluation results
        if checklist_task:
            checklist_result = await checklist_task
            checkpoint_complete = checklist_result.get("checkpoint_complete", False)
            timing.end("checkpoint_evaluation")

            if checkpoint_complete:
                state.mark_checkpoint_complete(current_checkpoint, query.text)
                current_checkpoint = state.get_current_checkpoint()
                _logger.info(f"✓ Checkpoint marked complete, next: '{current_checkpoint}'")

        timing.end("checkpoint_preparation")
        return current_checkpoint, checkpoint_complete, checklist_result
        
    async def _generate_next_checkpoint(
        self, 
        conversation_id: str, 
        text: str, 
        context: List[Dict], 
        existing_task_id: str,
        state
    ):
        """Generate next checkpoint in the background."""
        _logger.info(f"Generating next checkpoint in the background for task {existing_task_id}")
        
        try:
            # Call checkpoint service to generate a single new checkpoint
            result = await call_service(
                f"{settings.CHECKPOINT_URL}/generate",
                {
                    "text": text,
                    "conversation_id": conversation_id,
                    "context": context,
                    "limit": 1,  # Just generate 1 additional checkpoint
                    "existing_task_id": existing_task_id
                },
                TimingMetrics(),
                "background_checkpoint_generator",
                timeout=CHECKPOINT_TIMEOUT
            )
            
            # Process the new checkpoint
            if result and not result.get("is_new_task", True):
                checkpoints = result.get("checkpoints", [])
                task = result.get("task")
                
                if checkpoints and task:
                    # Append the new checkpoint to the existing task
                    for task_item in state.task_stack:
                        if task_item.get('task_id') == existing_task_id:
                            # Get the existing checklist
                            checklist = task_item.get('checklist', [])
                            
                            # Append the new checkpoints
                            for checkpoint in checkpoints:
                                checklist.append({
                                    "id": checkpoint.get('name', f"cp_{len(checklist)}"),
                                    "name": checkpoint.get('name', f"cp_{len(checklist)}"),
                                    "label": f"Step {len(checklist) + 1}",
                                    "type": "Main",
                                    "status": "pending",
                                    "expected_inputs": checkpoint.get('expected_inputs', []),
                                    "collected_inputs": [],
                                    "start_time": None, "end_time": None
                                })
                            
                            task_item['checklist'] = checklist
                            _logger.info(f"Added {len(checkpoints)} new checkpoints to task {existing_task_id}")
                            
                            # Save the state
                            await state.save(force=True)
                            break
            
        except Exception as e:
            _logger.error(f"Error generating next checkpoint: {e}")

# Global orchestrator instance
_orchestrator = SimplifiedOrchestrator()

@app.post("/orchestrate", response_model=OrchestratorResponse)
async def orchestrate_endpoint(
    query: OrchestratorQuery,
    response: Response,
    background_tasks: BackgroundTasks,
    # user: JWTClaims = Depends(get_current_user)
):
    """
    Simplified main orchestration endpoint - direct conversation flow.
    """
    timing = TimingMetrics()
    timing.start("total_orchestration")

    try:
        _logger.info(f"⟳ Orchestration start for conversation {query.conversation_id}")

        # 1) Get conversation state
        timing.start("state_initialization")
        state = await get_conversation_state(query.conversation_id, query.individual_id)
        
        # Set the new identifier fields from the query
        state.individual_id = query.individual_id
        state.user_profile_id = query.user_profile_id
        state.detected_agent = query.detected_agent
        state.agent_instance_id = query.agent_instance_id
        state.call_log_id = query.call_log_id

        timing.end("state_initialization")

        # 2) Prepare checkpoint data efficiently (handles both new conversations and evaluations)
        current_checkpoint, checkpoint_complete, checklist_result = await _orchestrator.prepare_checkpoint_data(
            query, state, timing
        )
        
        # Handle dynamic checkpoint generation in the background if needed
        if state.task_stack:
            for task in reversed(state.task_stack):
                if task.get('is_active', False):
                    # Check if we're on second-to-last checkpoint
                    checklist = task.get('checklist', [])
                    current_index = task.get('current_checkpoint_index', 0)
                    if len(checklist) > 1 and current_index == len(checklist) - 2:
                        _logger.info("Adding background task to generate next checkpoint")
                        
                        # Get context for background generation
                        context = await _orchestrator.get_cached_context(state, query.plan, query.text)
                        
                        # Add the background task
                        background_tasks.add_task(
                            _orchestrator._generate_next_checkpoint,
                            query.conversation_id,
                            query.text,
                            context,
                            task.get('task_id'),
                            state
                        )
                    break

        # 3) Prepare data for primary service call
        timing.start("primary_service_preparation")
        
        # Get context with caching
        context = await _orchestrator.get_cached_context(state, query.plan, query.text)
        
        # Get any stored results from previous interactions
        # stored_async_results = state.get_async_agent_results()
        # if asyncio.iscoroutine(stored_async_results):
        #     stored_async_results = await stored_async_results
        
        # Get unconsumed sync results
        # unconsumed_sync_results = state.get_unconsumed_agent_results()
        # if asyncio.iscoroutine(unconsumed_sync_results):
        #     unconsumed_sync_results = await unconsumed_sync_results
        
        timing.end("primary_service_preparation")

        # 4) Call primary service directly
        timing.start("primary_service")

        # Check detected_agent and call appropriate service
        if query.detected_agent == "loneliness":
            # Call loneliness companion service
            loneliness_payload = {
                "user_query": query.text,
                "context": str(context),
                "checkpoint": str(current_checkpoint) if current_checkpoint else "",
                "conversation_id": query.conversation_id,
                "user_profile_id": query.user_profile_id,
                "agent_instance_id": query.agent_instance_id,
                "user_id": query.user_profile_id
            }

            primary_result = await call_service(
                settings.LONELINESS_SERVICE_URL,
                loneliness_payload,
                timing,
                "loneliness_companion",
                timeout=PRIMARY_TIMEOUT
            )
        elif query.detected_agent == "accountability":
            # Convert checkpoint object to string if it exists
            checkpoint_str = None
            if current_checkpoint:
                if isinstance(current_checkpoint, dict):
                    checkpoint_str = current_checkpoint.get('name') or current_checkpoint.get('id', '')
                else:
                    checkpoint_str = str(current_checkpoint)
            
            accountability_payload = {
                "text": query.text,
                "conversation_id": query.conversation_id,
                "checkpoint": checkpoint_str,
                "context": {'day':'monday'},
                "individual_id": query.individual_id,
                "user_profile_id": query.user_profile_id,
                "agent_instance_id": query.agent_instance_id
            }

            primary_result = await call_service(
                settings.ACCOUNTABILITY_SERVICE_URL,
                accountability_payload,
                timing,
                "accountability_companion",
                timeout=PRIMARY_TIMEOUT
            )
    
        else:
            # Prepare primary service payload with correct data types
            primary_payload = {
                "text": query.text,
                "conversation_id": query.conversation_id,
                "checkpoint": current_checkpoint,
                "context": context,
                "checkpoint_complete": bool(checkpoint_complete),
                "specialist_responses": {},      # Dict - empty since no agents
                "async_agent_results":  {},       # Dict - from previous interactions
                "sync_agent_results": [],        # List - empty since no agents (FIXED DATA TYPE)
                "task_stack": list(getattr(state, "task_stack", [])),
                "patient_verified": bool(getattr(state, "patient_verified", False)),
                "is_paused": bool(getattr(state, "is_paused", False)),
                
           
            }

            primary_result = await call_service(
                settings.PRIMARY_SERVICE_URL,
                primary_payload,
                timing,
                "primary",
                timeout=PRIMARY_TIMEOUT
            )
        
        timing.end("primary_service")

        # 5) Update state in background
        background_tasks.add_task(
            _handle_simple_background_operations,
            state, query, primary_result
        )

        # 6) Return response
        timing.end("total_orchestration")
        
        metrics = timing.get_metrics()
        total_time = metrics.get("total_orchestration", 0)
        response.headers["Server-Timing"] = f"total;dur={total_time}"

        _logger.info(f"Orchestration completed in {total_time:.2f}ms")

        return OrchestratorResponse(
            response=primary_result["response"],
            conversation_id=query.conversation_id,
            checkpoints=[],
            checkpoint_progress=getattr(state, "checkpoint_progress", {}),
            task_stack=getattr(state, "task_stack", []),
            has_summary=getattr(state, "has_summary", False),
            summary=getattr(state, "summary", None),
            key_points=getattr(state, "key_points", []),
            tags=getattr(state, "tags", []),
            requires_human=primary_result.get("requires_human", False),
            is_paused=getattr(state, "is_paused", False),
            patient_verified=getattr(state, "patient_verified", False),
            async_agent_results=getattr(state, "async_agent_results", {}),
            sync_agent_results=getattr(state, "sync_agent_results", {}),
            timing_metrics=metrics,
            is_enriched=False
        )

    except Exception as e:
        timing.end("total_orchestration")
        if not isinstance(e, HTTPException):
            _logger.exception("⨯ Orchestration error")
            raise HTTPException(status_code=500, detail=f"Orchestration service error: {str(e)}")
        raise

async def _handle_simple_background_operations(
    state,
    query: OrchestratorQuery,
    primary_result: Dict[str, Any]
):
    """Simplified background operations."""
    try:
        # Update context
        await state.update_context(query.text, primary_result["response"], query.plan)
        
        # Handle state updates from primary response
        if "updated_task_stack" in primary_result:
            state.task_stack = primary_result["updated_task_stack"]
        if "is_paused" in primary_result:
            state.is_paused = primary_result["is_paused"]
        if "patient_verified" in primary_result:
            state.patient_verified = primary_result["patient_verified"]
        if "pending_agent_invocation" in primary_result:
            state.pending_agent_invocation = primary_result["pending_agent_invocation"]
        if "resume_after_subtask" in primary_result:
            state.resume_after_subtask = primary_result["resume_after_subtask"]
        
        # Save state
        await state.save()
        
        _logger.info("Background operations completed successfully")
        
    except Exception as e:
        _logger.exception(f"Error in background operations: {e}")


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "service": "orchestrator", "version": "simplified"}

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app,
        host=settings.ORCHESTRATOR_HOST,
        port=settings.ORCHESTRATOR_PORT,
        log_level=settings.LOG_LEVEL.lower(),
        workers=settings.ORCHESTRATOR_WORKERS,
        limit_concurrency=settings.ORCHESTRATOR_CONCURRENCY_LIMIT,
        http="h11",
    )
