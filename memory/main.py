
# memory/main.py - Ultra Low Latency Optimized Version
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from contextlib import asynccontextmanager
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any, Literal
import logging
from datetime import datetime
import json
import asyncio
import time
from functools import wraps
from collections import defaultdict
import pickle
import hashlib
import weakref
from concurrent.futures import ThreadPoolExecutor

if __name__ == "__main__" and __package__ is None:
    import sys
    from os import path
    sys.path.append(path.dirname(path.dirname(path.abspath(__file__))))
    from memory.redis_client import RedisMemory
    # from memory.pinecone_client import PineconeMemory
    from memory.mongo_client import MongoMemory
    from memory.config import get_settings
else:
    from .redis_client import RedisMemory
    # from .pinecone_client import PineconeMemory
    from .mongo_client import MongoMemory
    from .config import get_settings

# Load settings
settings = get_settings()

# ============= PERFORMANCE OPTIMIZATIONS =============

# Thread pool for CPU-bound operations
executor = ThreadPoolExecutor(max_workers=4)

# In-memory caches with TTL
class TTLCache:
    def __init__(self, maxsize: int = 1000, ttl: int = 300):
        self.cache = {}
        self.timestamps = {}
        self.maxsize = maxsize
        self.ttl = ttl

    def get(self, key: str):
        if key in self.cache:
            if time.time() - self.timestamps[key] < self.ttl:
                return self.cache[key]
            else:
                del self.cache[key]
                del self.timestamps[key]
        return None

    def set(self, key: str, value: Any):
        if len(self.cache) >= self.maxsize:
            # Remove oldest entry
            oldest_key = min(self.timestamps, key=self.timestamps.get)
            del self.cache[oldest_key]
            del self.timestamps[oldest_key]

        self.cache[key] = value
        self.timestamps[key] = time.time()

# Multiple cache layers for different data types
conversation_cache = TTLCache(maxsize=2000, ttl=600)  # 10 minutes
agent_result_cache = TTLCache(maxsize=1000, ttl=300)  # 5 minutes
semantic_cache = TTLCache(maxsize=500, ttl=900)       # 15 minutes
patient_cache = TTLCache(maxsize=500, ttl=1800)      # 30 minutes

# Pre-compiled JSON encoders
def fast_json_encode(obj):
    """Ultra-fast JSON encoding with datetime support"""
    if isinstance(obj, datetime):
        return obj.isoformat()
    return obj

# Async cache decorator
def async_cache(cache_obj: TTLCache, key_func=None):
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Generate cache key
            if key_func:
                cache_key = key_func(*args, **kwargs)
            else:
                cache_key = f"{func.__name__}:{hash(str(args) + str(kwargs))}"

            # Try cache first
            cached_result = cache_obj.get(cache_key)
            if cached_result is not None:
                return cached_result

            # Execute function and cache result
            result = await func(*args, **kwargs)
            cache_obj.set(cache_key, result)
            return result
        return wrapper
    return decorator

# Batch operation queue
class BatchQueue:
    def __init__(self, batch_size: int = 10, flush_interval: float = 0.1):
        self.queue = defaultdict(list)
        self.batch_size = batch_size
        self.flush_interval = flush_interval
        self.last_flush = defaultdict(float)

    async def add(self, operation_type: str, data: Dict[str, Any]):
        self.queue[operation_type].append(data)
        current_time = time.time()

        # Flush if batch is full or time interval exceeded
        if (len(self.queue[operation_type]) >= self.batch_size or
            current_time - self.last_flush[operation_type] > self.flush_interval):
            await self.flush(operation_type)

    async def flush(self, operation_type: str):
        if not self.queue[operation_type]:
            return

        batch = self.queue[operation_type].copy()
        self.queue[operation_type].clear()
        self.last_flush[operation_type] = time.time()

        # Process batch in background
        asyncio.create_task(self.process_batch(operation_type, batch))

    async def process_batch(self, operation_type: str, batch: List[Dict[str, Any]]):
        # Implement batch processing logic here
        pass

batch_queue = BatchQueue()

# Pre-initialize JSON dumps for common responses
COMMON_RESPONSES = {
    "success": json.dumps({"status": "success"}),
    "error_500": json.dumps({"status": "error", "detail": "Internal server error"}),
    "not_found": json.dumps({"status": "error", "detail": "Not found"})
}

# ============= OPTIMIZED MODELS =============

# Faster BaseModel with slots for memory efficiency
class OptimizedBaseModel(BaseModel):
    class Config:
        # Use enum values for better performance
        use_enum_values = True
        # Allow population by field name
        validate_by_name = True
        # Faster validation
        validate_assignment = False
        # Pre-compile regex patterns
        str_strip_whitespace = True
        # Use faster JSON encoder
        json_encoders = {datetime: fast_json_encode}

# Optimized enums
CheckpointType = Literal["Main", "SupportAgent", "Interrupt"]
CheckpointStatus = Literal["pending", "in_progress", "complete"]
AgentResponseStatus = Literal["success", "error", "partial"]

# Optimized models with Field validation
class Checkpoint(OptimizedBaseModel):
    name: str = Field(..., min_length=1, max_length=500)  # Increased max length to 500
    status: CheckpointStatus = "pending"
    expected_inputs: List[str] = Field(default_factory=list, max_items=50)
    collected_inputs: List[str] = Field(default_factory=list, max_items=50)

class Task(OptimizedBaseModel):
    task_id: str = Field(..., min_length=1, max_length=100)
    label: str = Field(..., min_length=1, max_length=500)
    source: CheckpointType
    checklist: List[Checkpoint] = Field(default_factory=list, max_items=100)
    current_checkpoint_index: int = Field(default=0, ge=0)
    is_active: bool = True
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

class AgentResult(OptimizedBaseModel):
    agent_name: str = Field(..., min_length=1, max_length=100)
    status: AgentResponseStatus
    result_payload: Dict[str, Any] = Field(default_factory=dict)
    message_to_user: Optional[str] = Field(None, max_length=2000)
    action_required: bool = False
    timestamp: datetime = Field(default_factory=datetime.now)
    consumed: bool = False

class ConversationState(OptimizedBaseModel):
    conversation_id: str = Field(..., min_length=1, max_length=100)
    
    # New identifier fields (replacing patient-specific ones)
    individual_id: Optional[str] = Field(None, min_length=1, max_length=100)
    user_profile_id: Optional[str] = Field(None, min_length=1, max_length=100)
    detected_agent: Optional[str] = Field(None, min_length=1, max_length=100)
    agent_instance_id: Optional[str] = Field(None, min_length=1, max_length=100)
    call_log_id: Optional[str] = Field(None, min_length=1, max_length=100)

    task_stack: List[Task] = Field(default_factory=list, max_items=50)
    context: List[Dict[str, str]] = Field(default_factory=list, max_items=200)
    complete_context: List[Dict[str, str]] = Field(default_factory=list, max_items=1000)
    temporary_context: List[Dict[str, str]] = Field(default_factory=list, max_items=100)
    checkpoint_progress: Dict[str, bool] = Field(default_factory=dict)
    type_of_checkpoints_active: str = "Main"
    async_agent_results: Dict[str, AgentResult] = Field(default_factory=dict)
    sync_agent_results: Dict[str, List[AgentResult]] = Field(default_factory=dict)
    is_verified: bool = False
    is_paused: bool = False
    pending_agent_invocation: Optional[str] = None
    resume_after_subtask: Optional[str] = None
    has_summary: bool = False
    summary: Optional[str] = Field(None, max_length=5000)
    key_points: List[str] = Field(default_factory=list, max_items=50)
    tags: List[str] = Field(default_factory=list, max_items=20)

class ConversationUpdate(OptimizedBaseModel):
    conversation_id: str = Field(..., min_length=1, max_length=100)
    context: List[Dict[str, str]] = Field(..., max_items=200)
    
    # New identifier fields (optional for backward compatibility)
    individual_id: Optional[str] = Field(None, min_length=1, max_length=100)
    user_profile_id: Optional[str] = Field(None, min_length=1, max_length=100)
    
    plan: str = Field(default="pro", pattern="^(lite|pro)$")

class TaskStackUpdate(OptimizedBaseModel):
    conversation_id: str = Field(..., min_length=1, max_length=100)
    task_stack: List[Dict[str, Any]] = Field(..., max_items=50)

class VerificationRequest(OptimizedBaseModel):
    conversation_id: str = Field(..., min_length=1, max_length=100)
    is_verified: bool = False

# ============= LIFESPAN CONTEXT MANAGER =============

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    global redis_memory, pinecone_memory, mongo_memory
    
    logging.info("🚀 Starting Memory Service...")
    
    # Initialize critical services first with settings
    redis_memory = RedisMemory(redis_url=settings.REDIS_URL)
    mongo_memory = MongoMemory(uri=settings.MONGODB_URI, db_name=settings.DATABASE_NAME)

    # Initialize core services (Redis and MongoDB)
    startup_tasks = []
    
    # Redis initialization
    try:
        await redis_memory.check_connection()
        logging.info("✅ Redis connected successfully")
        health_checker.redis_healthy = True
    except Exception as e:
        logging.warning(f"⚠️ Redis connection failed: {e}")
        health_checker.redis_healthy = False

    # MongoDB initialization  
    try:
        await mongo_memory.check_connection()
        logging.info("✅ MongoDB connected successfully")
        health_checker.mongo_healthy = True
    except Exception as e:
        logging.warning(f"⚠️ MongoDB connection failed: {e}")
        health_checker.mongo_healthy = False

    # Initialize Pinecone in background (non-critical)
    asyncio.create_task(init_pinecone_background())
    
    logging.info("✅ Memory Service startup complete")
    
    yield
    
    # Shutdown
    logging.info("🛑 Shutting down Memory Service...")
    if redis_memory:
        await redis_memory.redis.aclose()
    if mongo_memory:
        mongo_memory.client.close()
    logging.info("✅ Memory Service shutdown complete")

async def init_pinecone_background():
    global pinecone_memory
    try:
        # pinecone_memory = PineconeMemory(
        #     api_key=settings.PINECONE_API_KEY,
        #     environment=settings.PINECONE_ENVIRONMENT
        # )
        await pinecone_memory.check_connection()
        health_checker.pinecone_healthy = True
        logging.info("✅ Pinecone initialized successfully")
    except Exception as e:
        logging.warning(f"⚠️ Pinecone initialization failed: {e}")
        health_checker.pinecone_healthy = False
        pinecone_memory = None

# ============= OPTIMIZED FASTAPI APP =============

logging.basicConfig(level=logging.INFO)  # Use INFO level to show connection status
app = FastAPI(
    title="Memory Service - Optimized",
    docs_url="/docs" if __name__ == "__main__" else None,  # Disable docs in production
    redoc_url=None,  # Disable redoc
    lifespan=lifespan  # Use modern lifespan instead of deprecated on_event
)

# Add performance middleware
app.add_middleware(GZipMiddleware, minimum_size=1000)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global connections
redis_memory: RedisMemory = None
pinecone_memory = None
mongo_memory: MongoMemory = None

# Connection pool and health check
class HealthChecker:
    def __init__(self):
        self.redis_healthy = False
        self.mongo_healthy = False
        self.pinecone_healthy = False
        self.last_check = 0
        self.check_interval = 30  # Check every 30 seconds

    async def check_health(self):
        current_time = time.time()
        if current_time - self.last_check < self.check_interval:
            return

        self.last_check = current_time

        # Check Redis with better error handling
        try:
            if redis_memory:
                result = await redis_memory.check_connection()
                self.redis_healthy = result if result is not None else self.redis_healthy
            else:
                self.redis_healthy = False
        except Exception as e:
            logging.debug(f"Redis health check failed: {e}")
            self.redis_healthy = False

        # Check MongoDB
        try:
            if mongo_memory:
                await mongo_memory.check_connection()
                self.mongo_healthy = True
            else:
                self.mongo_healthy = False
        except Exception as e:
            logging.debug(f"MongoDB health check failed: {e}")
            self.mongo_healthy = False

        # Check Pinecone
        try:
            if pinecone_memory:
                await pinecone_memory.check_connection()
                self.pinecone_healthy = True
            else:
                self.pinecone_healthy = False
        except Exception as e:
            logging.debug(f"Pinecone health check failed: {e}")
            self.pinecone_healthy = False

health_checker = HealthChecker()

# ============= OPTIMIZED ENDPOINTS =============

# Ultra-fast state saving with caching
@app.post("/conversation/state")
async def save_conversation_state(state: Dict[str, Any]):
    try:
        # Validate required fields before creating model
        if "conversation_id" not in state:
            raise ValueError("Missing required field: conversation_id")
        if "conversation_id" not in state:
            raise ValueError("Missing required field: conversation_id")
            
        # Handle type conversion for specific fields to match model expectations
        # Convert task_stack if it exists
        if "task_stack" in state and isinstance(state["task_stack"], list):
            for task in state["task_stack"]:
                if "checklist" in task and isinstance(task["checklist"], list):
                    for checkpoint in task["checklist"]:
                        # Truncate checkpoint names that are too long
                        if "name" in checkpoint and isinstance(checkpoint["name"], str) and len(checkpoint["name"]) > 500:
                            checkpoint["name"] = checkpoint["name"][:497] + "..."
                            
                        # Ensure expected_inputs and collected_inputs are lists
                        if "expected_inputs" in checkpoint and not isinstance(checkpoint["expected_inputs"], list):
                            checkpoint["expected_inputs"] = list(checkpoint["expected_inputs"])
                        if "collected_inputs" in checkpoint and not isinstance(checkpoint["collected_inputs"], list):
                            checkpoint["collected_inputs"] = list(checkpoint["collected_inputs"])
        
        # Create model and validate
        try:
            # First attempt to create and validate the model
            try:
                conversation_state = ConversationState(**state)
                state_dict = conversation_state.dict()
            except Exception as validation_error:
                # Log the detailed error and problematic fields
                error_msg = str(validation_error)
                logging.error(f"Validation error: {error_msg}")
                
                # Find problematic fields and truncate/fix them
                if "string_too_long" in error_msg and "task_stack" in state:
                    field_path = error_msg.split("\n")[0]
                    if "task_stack" in field_path and "checklist" in field_path and "name" in field_path:
                        # Extract indices from error message (task_stack.X.checklist.Y.name)
                        parts = field_path.strip().split(".")
                        if len(parts) >= 5 and parts[0] == "task_stack" and parts[2] == "checklist" and parts[4] == "name":
                            try:
                                task_idx = int(parts[1])
                                checkpoint_idx = int(parts[3])
                                # Truncate the problematic name
                                if (task_idx < len(state["task_stack"]) and 
                                    "checklist" in state["task_stack"][task_idx] and 
                                    checkpoint_idx < len(state["task_stack"][task_idx]["checklist"])):
                                    name = state["task_stack"][task_idx]["checklist"][checkpoint_idx]["name"]
                                    state["task_stack"][task_idx]["checklist"][checkpoint_idx]["name"] = name[:197] + "..."
                                    logging.info(f"Truncated long checkpoint name at task_stack.{task_idx}.checklist.{checkpoint_idx}")
                            except (ValueError, IndexError) as e:
                                logging.error(f"Failed to parse indices from error message: {e}")
                
                # Try again with fixed data
                conversation_state = ConversationState(**state)
                state_dict = conversation_state.dict()
        except Exception as validation_error:
            logging.error(f"Validation error: {str(validation_error)}")
            # Include helpful diagnostic information in the error
            detail = {
                "error": str(validation_error),
                "suggestion": "Check field lengths and data types. Consider truncating long text fields."
            }
            raise HTTPException(status_code=422, detail=detail)
            
        cache_key = f"conv_state:{state['conversation_id']}"

        # Update cache immediately
        conversation_cache.set(cache_key, state_dict)

        # Parallel database operations
        tasks = [
            redis_memory.set_conversation_state(state["conversation_id"], state_dict),
            mongo_memory.save_conversation_state(state_dict)
        ]

        await asyncio.gather(*tasks, return_exceptions=True)
        return {"status": "success"}

    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        logging.exception(f"⨯ Error saving state: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error saving state: {str(e)}")

# Optimized agent result handling
@app.post("/conversation/agent_result")
async def save_agent_result(conversation_id: str, result: AgentResult):
    try:
        # Cache the result
        cache_key = f"agent_result:{conversation_id}:{result.agent_name}"
        agent_result_cache.set(cache_key, result.dict())

        # Parallel operations
        tasks = [
            redis_memory.set_agent_result(
                conversation_id, result.agent_name, result.status,
                result.result_payload, result.message_to_user, result.action_required
            ),
            mongo_memory.save_agent_result(
                conversation_id, result.agent_name, result.result_payload
            )
        ]

        await asyncio.gather(*tasks, return_exceptions=True)
        return {"status": "success"}

    except Exception as e:
        logging.exception(f"⨯ Error saving agent result: {e}")
        raise HTTPException(status_code=500, detail=f"Error saving agent result: {str(e)}")

@app.post("/conversation/sync_agent_result")
async def sync_agent_result(conversation_id: str, result: AgentResult):
    try:
        # Cache the sync result
        cache_key = f"sync_agent_result:{conversation_id}:{result.agent_name}"
        agent_result_cache.set(cache_key, result.dict())

        # Parallel operations
        tasks = [
            redis_memory.set_sync_agent_result(
                conversation_id, result.agent_name, result.status,
                result.result_payload, result.message_to_user, result.action_required
            ),
            mongo_memory.save_sync_agent_result(
                conversation_id, result.agent_name, result.result_payload
            )
        ]

        await asyncio.gather(*tasks, return_exceptions=True)
        return {"status": "success"}

    except Exception as e:
        logging.exception(f"⨯ Error syncing agent result: {e}")
        raise HTTPException(status_code=500, detail=f"Error syncing agent result: {str(e)}")

# Cached patient verification
# @app.post("/conversation/update_patient_verification_status")
# async def update_patient_verification_status(state: PatientVerificationRequest):
#     try:
#         # Update cache
#         cache_key = f"conv_state:{state.conversation_id}"
#         cached_state = conversation_cache.get(cache_key)
#         if cached_state:
#             cached_state["patient_verified"] = False
#             conversation_cache.set(cache_key, cached_state)

#         # Parallel database operations
#         tasks = [
#             redis_memory.update_patient_verification_status(state.conversation_id, False),
#             mongo_memory.update_patient_verification_status(state.conversation_id, False)
#         ]

#         await asyncio.gather(*tasks, return_exceptions=True)
#         return {"status": "success", "message": "Patient verification status updated successfully"}

#     except Exception as e:
#         logging.exception(f"⨯ Error updating patient verification status: {str(e)}")
#         raise HTTPException(status_code=500, detail=f"Error updating patient verification status: {str(e)}")

# Ultra-fast conversation retrieval with multi-layer caching
@app.get("/conversation/{conversation_id}")
@async_cache(conversation_cache, lambda conversation_id: f"conv_state:{conversation_id}")
async def get_conversation(conversation_id: str):
    try:
        # Layer 1: Memory cache (fastest)
        cache_key = f"conv_state:{conversation_id}"
        cached_state = conversation_cache.get(cache_key)
        if cached_state:
            return cached_state

        # Layer 2: Redis (fast)
        state = await redis_memory.get_conversation_state(conversation_id)

        if not state:
            # Layer 3: MongoDB (slower, but comprehensive)
            state = await mongo_memory.find_one_and_update_conversation_state(conversation_id)

            if state:
                # Restore to faster caches
                conversation_cache.set(cache_key, state)
                asyncio.create_task(redis_memory.set_conversation_state(conversation_id, state))
            else:
                raise HTTPException(status_code=404, detail="Conversation not found")
        else:
            # Cache in memory for next time
            conversation_cache.set(cache_key, state)

        return state

    except HTTPException:
        raise
    except Exception as e:
        logging.exception(f"⨯ Error fetching conversation: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error fetching conversation: {str(e)}")

# Optimized semantic context with aggressive caching
@app.post("/get_semantic_context")
async def get_semantic_context(individual_id: str, query: str, limit: int = 50):
    try:
        # Input validation
        if not query or not query.strip() or len(query.strip()) < 3:
            return {"status": "error", "context": [], "error": "Query too short"}

        # Multi-level caching
        cache_key = f"semantic:{individual_id}:{hashlib.md5(query.encode()).hexdigest()}:{limit}"
        cached_result = semantic_cache.get(cache_key)
        if cached_result:
            return cached_result

        # Quick timeout for performance
        async def search_with_timeout():
            if not pinecone_memory or not pinecone_memory.initialized:
                return []

            try:
                return await pinecone_memory.search_with_context_awareness(
                    individual_id=individual_id, query=query,
                    current_conversation_id=individual_id, limit=min(limit, 50)
                )
            except:
                return await pinecone_memory.search_optimized(
                    individual_id=individual_id, query=query,
                    limit=min(limit, 50), filters={"type": "message"}
                )

        try:
            search_results = await asyncio.wait_for(search_with_timeout(), timeout=5.0)
        except:
            result = {"status": "success", "context": [], "total_results": 0}
            semantic_cache.set(cache_key, result)
            return result

        # Process results
        context = [
            {'role': result['role'], 'content': result['content']}
            for result in search_results
            if result.get('role') and result.get('content') and len(result['content'].strip()) > 10
        ][:limit]

        result = {
            "status": "success",
            "context": context,
            "total_results": len(context)
        }

        # Cache the result
        semantic_cache.set(cache_key, result)
        return result

    except Exception as e:
        logging.error(f"Semantic context API error: {str(e)}")
        return {"status": "error", "context": [], "error": "Search temporarily unavailable"}

# Optimized conversation update with batching
@app.post("/conversation/update")
async def update_conversation(update: ConversationUpdate, background_tasks: BackgroundTasks):
    try:
        # Update cache immediately
        cache_key = f"conv_state:{update.conversation_id}"
        cached_state = conversation_cache.get(cache_key)
        if cached_state:
            cached_state["context"] = update.context
            conversation_cache.set(cache_key, cached_state)

        # Parallel core operations
        tasks = [
            redis_memory.set_conversation_context(update.conversation_id, update.context),
            mongo_memory.update_conversation_context(update.conversation_id, update.context, update.individual_id)
        ]

        await asyncio.gather(*tasks, return_exceptions=True)

        # Background Pinecone operations for Pro users
        if update.plan == "pro" and pinecone_memory:
            recent_messages = update.context[-2:] if len(update.context) >= 2 else update.context
            for msg in recent_messages:
                if msg.get("role") and msg.get("content") and len(msg["content"].strip()) > 5:
                    background_tasks.add_task(safe_store_message, update.conversation_id, msg["role"], msg["content"])

        return {"status": "success"}

    except Exception as e:
        logging.exception(f"⨯ Error updating conversation: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error updating conversation: {str(e)}")

# Optimized background task
async def safe_store_message(conversation_id: str, role: str, content: str):
    try:
        if pinecone_memory and pinecone_memory.initialized:
            await asyncio.wait_for(
                pinecone_memory.store_message(conversation_id, role, content),
                timeout=10.0
            )
    except:
        pass  # Silent fail for non-critical background operation

# Batch semantic context (optimized)
@app.post("/get_semantic_context_batch")
async def get_semantic_context_batch(requests: List[Dict[str, Any]]):
    try:
        # Process requests in parallel with semaphore for controlled concurrency
        semaphore = asyncio.Semaphore(5)  # Limit concurrent requests

        async def process_request(req):
            async with semaphore:
                individual_id = req.get("individual_id")
                query = req.get("query")
                limit = req.get("limit", 50)

                if not individual_id or not query:
                    return {"status": "error", "context": [], "error": "Missing individual_id or query"}

                # Use the cached single request endpoint
                return await get_semantic_context(individual_id, query, limit)

        # Execute all requests concurrently
        results = await asyncio.gather(
            *[process_request(req) for req in requests],
            return_exceptions=True
        )

        # Handle exceptions
        processed_results = []
        for result in results:
            if isinstance(result, Exception):
                processed_results.append({"status": "error", "context": [], "error": str(result)})
            else:
                processed_results.append(result)

        return {
            "status": "success",
            "results": processed_results,
            "total_requests": len(requests)
        }

    except Exception as e:
        logging.error(f"Batch semantic context API error: {str(e)}")
        return {"status": "error", "results": [], "error": str(e)}

# Optimized task stack update
@app.post("/conversation/update_tasks_stack")
async def update_tasks_stack(update: TaskStackUpdate):
    try:
        conversation_id = update.conversation_id

        # Update cache first
        cache_key = f"conv_state:{conversation_id}"
        cached_state = conversation_cache.get(cache_key)

        if not cached_state:
            # Try Redis first, then MongoDB
            cached_state = await redis_memory.get_conversation_state(conversation_id)
            if not cached_state:
                cached_state = await mongo_memory.find_one_and_update_conversation_state(conversation_id)
                if not cached_state:
                    raise HTTPException(status_code=404, detail=f"Conversation {conversation_id} not found")

        # Update the state
        cached_state["task_stack"] = update.task_stack
        cached_state["updated_at"] = datetime.now().isoformat()

        # Update cache
        conversation_cache.set(cache_key, cached_state)

        # Parallel database operations
        tasks = [
            redis_memory.set_conversation_state(conversation_id, cached_state),
            mongo_memory.update_task_stack(conversation_id, update.task_stack)
        ]

        await asyncio.gather(*tasks, return_exceptions=True)
        return {"status": "success", "message": "Task stack updated successfully"}

    except HTTPException:
        raise
    except Exception as e:
        logging.exception(f"⨯ Error updating task stack: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error updating task stack: {str(e)}")

# Generic conversations endpoint (replacing patient-specific endpoint)
@app.get("/individual/{individual_id}/conversations")
@async_cache(conversation_cache, lambda individual_id: f"individual_convos:{individual_id}")
async def get_individual_conversations(individual_id: str):
    try:
        # For now, we'll return an empty list since we're decoupling from patient collections
        # This can be implemented later to query conversations by individual_id if needed
        return {"conversations": [], "message": "Individual conversations endpoint - implementation pending"}
    except Exception as e:
        logging.exception(f"⨯ Error fetching individual conversations: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error fetching individual conversations: {str(e)}")

# Health check endpoint
@app.get("/health")
async def health_check():
    await health_checker.check_health()
    return {
        "status": "healthy",
        "redis": health_checker.redis_healthy,
        "mongodb": health_checker.mongo_healthy,
        "pinecone": health_checker.pinecone_healthy,
        "cache_stats": {
            "conversation_cache": len(conversation_cache.cache),
            "agent_result_cache": len(agent_result_cache.cache),
            "semantic_cache": len(semantic_cache.cache),
            "patient_cache": len(patient_cache.cache)
        }
    }

# Cache management endpoints
@app.post("/admin/clear_cache")
async def clear_cache(cache_type: str = "all"):
    if cache_type == "all" or cache_type == "conversation":
        conversation_cache.cache.clear()
        conversation_cache.timestamps.clear()
    if cache_type == "all" or cache_type == "agent":
        agent_result_cache.cache.clear()
        agent_result_cache.timestamps.clear()
    if cache_type == "all" or cache_type == "semantic":
        semantic_cache.cache.clear()
        semantic_cache.timestamps.clear()
    if cache_type == "all" or cache_type == "patient":
        patient_cache.cache.clear()
        patient_cache.timestamps.clear()

    return {"status": "success", "message": f"Cache {cache_type} cleared"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8010,
        workers=1,  # Single worker for optimal caching
        loop="asyncio",  # Use standard asyncio instead of uvloop
        http="h11",  # Use standard h11 instead of httptools
        access_log=False,  # Disable access logging for performance
        log_level="warning"
    )
