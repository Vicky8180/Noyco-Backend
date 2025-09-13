
# orchestrator/state_manager.py

"""
Ultra-optimized state management for conversations.
Handles persistence and retrieval with Redis caching, local state, and intelligent API fallback.
"""

import logging
import asyncio
import json
import hashlib
from typing import Dict, List, Optional, Any, Literal, Union, Set
from collections import defaultdict, OrderedDict
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
import httpx
import redis.asyncio as redis
from contextlib import asynccontextmanager
from functools import wraps
import pickle
import threading
from concurrent.futures import ThreadPoolExecutor

from orchestrator.config import get_settings
from common.models import Conversation, AgentResult, Task, Checkpoint

_logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# Get settings
settings = get_settings()

# Enums from schema
CheckpointType = Literal["Main", "SupportAgent", "Interrupt"]
CheckpointStatus = Literal["pending", "in_progress", "complete"]
AgentResponseStatus = Literal["success", "error", "partial"]

# Cache configuration from settings
REDIS_URL = settings.REDIS_URL
CACHE_TTL = settings.CACHE_TTL
LOCAL_CACHE_SIZE = settings.LOCAL_CACHE_SIZE
BATCH_SIZE = 100

@dataclass
class CacheStats:
    """Cache performance statistics"""
    redis_hits: int = 0
    redis_misses: int = 0
    local_hits: int = 0
    local_misses: int = 0
    api_calls: int = 0
    cache_writes: int = 0

class LocalCache:
    """Thread-safe LRU local cache"""
    def __init__(self, max_size: int = LOCAL_CACHE_SIZE):
        self.cache = OrderedDict()
        self.max_size = max_size
        self.lock = threading.RLock()
        self.stats = CacheStats()

    def get(self, key: str) -> Optional[Any]:
        with self.lock:
            if key in self.cache:
                # Move to end (most recently used)
                value = self.cache.pop(key)
                self.cache[key] = value
                self.stats.local_hits += 1
                return value
            self.stats.local_misses += 1
            return None

    def set(self, key: str, value: Any) -> None:
        with self.lock:
            if key in self.cache:
                self.cache.pop(key)
            elif len(self.cache) >= self.max_size:
                # Remove least recently used
                self.cache.popitem(last=False)

            self.cache[key] = value

    def delete(self, key: str) -> bool:
        with self.lock:
            return self.cache.pop(key, None) is not None

    def clear(self) -> None:
        with self.lock:
            self.cache.clear()

class CacheManager:
    """Manages Redis and local caching with intelligent fallback"""

    def __init__(self):
        self.redis_client: Optional[redis.Redis] = None
        self.local_cache = LocalCache()
        self.stats = CacheStats()
        self.connection_pool = None
        self.redis_available = False
        self._lock = asyncio.Lock()

    async def initialize(self):
        """Initialize Redis connection with fallback"""
        try:
            self.connection_pool = redis.ConnectionPool.from_url(
                REDIS_URL,
                max_connections=20,
                retry_on_timeout=True,
                socket_connect_timeout=2,
                socket_timeout=2
            )
            self.redis_client = redis.Redis(connection_pool=self.connection_pool)

            # Test connection
            await self.redis_client.ping()
            self.redis_available = True
            _logger.debug("✅ Redis cache initialized successfully")

        except Exception as e:
            _logger.warning(f"⚠️ Redis unavailable, using local cache only: {e}")
            self.redis_available = False

    async def get(self, key: str) -> Optional[Any]:
        """Get from cache with multi-level fallback"""
        # Try local cache first (fastest)
        local_value = self.local_cache.get(key)
        if local_value is not None:
            return local_value

        # Try Redis if available
        if self.redis_available:
            try:
                redis_value = await self.redis_client.get(key)
                if redis_value:
                    self.stats.redis_hits += 1
                    # Deserialize and cache locally
                    value = pickle.loads(redis_value)
                    self.local_cache.set(key, value)
                    return value
                else:
                    self.stats.redis_misses += 1
            except Exception as e:
                _logger.warning(f"Redis get error for key {key}: {e}")
                self.redis_available = False

        return None

    async def set(self, key: str, value: Any, ttl: int = CACHE_TTL) -> None:
        """Set in cache with multi-level storage"""
        # Always cache locally
        self.local_cache.set(key, value)

        # Try Redis if available
        if self.redis_available:
            try:
                serialized = pickle.dumps(value)
                await self.redis_client.setex(key, ttl, serialized)
                self.stats.cache_writes += 1
            except Exception as e:
                _logger.warning(f"Redis set error for key {key}: {e}")
                self.redis_available = False

    async def delete(self, key: str) -> None:
        """Delete from all cache levels"""
        self.local_cache.delete(key)

        if self.redis_available:
            try:
                await self.redis_client.delete(key)
            except Exception as e:
                _logger.warning(f"Redis delete error for key {key}: {e}")

    async def batch_get(self, keys: List[str]) -> Dict[str, Any]:
        """Batch get operation for better performance"""
        results = {}
        missing_keys = []

        # Check local cache first
        for key in keys:
            local_value = self.local_cache.get(key)
            if local_value is not None:
                results[key] = local_value
            else:
                missing_keys.append(key)

        # Batch get from Redis for missing keys
        if missing_keys and self.redis_available:
            try:
                redis_values = await self.redis_client.mget(missing_keys)
                for key, redis_value in zip(missing_keys, redis_values):
                    if redis_value:
                        value = pickle.loads(redis_value)
                        results[key] = value
                        self.local_cache.set(key, value)
                        self.stats.redis_hits += 1
                    else:
                        self.stats.redis_misses += 1
            except Exception as e:
                _logger.warning(f"Redis batch get error: {e}")

        return results

    def get_stats(self) -> Dict[str, Any]:
        """Get cache performance statistics"""
        return {
            "redis_available": self.redis_available,
            "redis_hits": self.stats.redis_hits,
            "redis_misses": self.stats.redis_misses,
            "local_hits": self.stats.local_hits,
            "local_misses": self.stats.local_misses,
            "api_calls": self.stats.api_calls,
            "cache_writes": self.stats.cache_writes,
            "hit_rate": (self.stats.redis_hits + self.stats.local_hits) /
                       max(1, self.stats.redis_hits + self.stats.redis_misses +
                           self.stats.local_hits + self.stats.local_misses) * 100
        }

# Global cache manager instance
cache_manager = CacheManager()

def cache_key(prefix: str, *args) -> str:
    """Generate consistent cache keys"""
    key_parts = [str(arg) for arg in args if arg is not None]
    key_string = f"{prefix}:{':'.join(key_parts)}"
    return hashlib.md5(key_string.encode()).hexdigest()[:16]

def cached(ttl: int = CACHE_TTL, prefix: str = "default"):
    """Decorator for caching method results"""
    def decorator(func):
        @wraps(func)
        async def wrapper(self, *args, **kwargs):
            # Generate cache key
            key_args = [getattr(self, 'conversation_id', ''), str(args), str(sorted(kwargs.items()))]
            key = cache_key(f"{prefix}:{func.__name__}", *key_args)

            # Try cache first
            cached_result = await cache_manager.get(key)
            if cached_result is not None:
                return cached_result

            # Execute function and cache result
            result = await func(self, *args, **kwargs)
            if result is not None:
                await cache_manager.set(key, result, ttl)

            return result
        return wrapper
    return decorator

class ConversationState:
    """
    Ultra-optimized conversation state manager with multi-level caching
    """

    def __init__(self, conversation_id: str, individual_id: Optional[str] = None):
        self.conversation_id = conversation_id
        self.individual_id = individual_id
        self.user_profile_id: Optional[str] = None
        self.detected_agent: Optional[str] = None
        self.agent_instance_id: Optional[str] = None
        self.call_log_id: Optional[str] = None

        # Pre-allocate data structures for better memory efficiency
        self.task_stack: List[Task] = []
        self.checkpoint_progress: Dict[str, bool] = {}
        self.type_of_checkpoints_active: str = "Main"

        # Context management with memory optimization
        self.context: List[Dict[str, str]] = []
        self.complete_context: List[Dict[str, str]] = []
        self.temporary_context: List[Dict[str, str]] = []

        # Agent results with optimized storage
        self.async_agent_results: Dict[str, AgentResult] = {}
        self.sync_agent_results: Dict[str, List[AgentResult]] = defaultdict(list)

        # State flags
        self.is_paused: bool = False
        self.pending_agent_invocation: Optional[str] = None
        self.resume_after_subtask: Optional[str] = None
        self.patient_verified: bool = False

        # Summary fields
        self.has_summary: bool = False
        self.summary: Optional[str] = None
        self.key_points: List[str] = []
        self.tags: List[str] = []

        self.is_new = True
        self.current_task: Optional[Dict[str, Any]] = None

        # Performance optimizations
        self._dirty_fields: Set[str] = set()
        self._last_save_time: Optional[datetime] = None
        self._http_client: Optional[httpx.AsyncClient] = None

    async def __aenter__(self):
        """Async context manager entry"""
        await self._ensure_http_client()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        if self._http_client:
            await self._http_client.aclose()

    async def _ensure_http_client(self):
        """Ensure HTTP client is available"""
        if not self._http_client:
            self._http_client = httpx.AsyncClient(
                timeout=httpx.Timeout(15.0, connect=5.0, read=15.0),
                limits=httpx.Limits(max_connections=10, max_keepalive_connections=5)
            )

    def _mark_dirty(self, field: str):
        """Mark field as dirty for incremental saves"""
        self._dirty_fields.add(field)

    @classmethod
    async def get_or_create(cls, conversation_id: str, individual_id: Optional[str] = None) -> 'ConversationState':
        """
        Get existing conversation state or create new with optimized caching
        """
        instance = cls(conversation_id, individual_id)

        # Try cache first
        cache_key_str = cache_key("conversation", conversation_id)
        cached_data = await cache_manager.get(cache_key_str)

        if cached_data:
            instance._load_from_dict(cached_data)
            instance.is_new = False
            _logger.info(f"✅ Loaded conversation {conversation_id} from cache")
            return instance

        # Fallback to API
        try:
            await instance._ensure_http_client()
            resp = await instance._http_client.get(
                f"{settings.MEMORY_URL}/conversation/{conversation_id}"
            )

            if resp.status_code == 200:
                data = resp.json()
                instance._load_from_dict(data)
                instance.is_new = False

                # Cache for future use
                await cache_manager.set(cache_key_str, data)
                cache_manager.stats.api_calls += 1

                _logger.info(f"✅ Loaded conversation {conversation_id} from API")

        except Exception as e:
            _logger.warning(f"Could not fetch conversation (will start new): {type(e).__name__}: {str(e)}")

        return instance

    def _load_from_dict(self, data: Dict[str, Any]):
        """Load state from dictionary data"""
        self.task_stack = data.get("task_stack", [])
        self.checkpoint_progress = data.get("checkpoint_progress", {})
        self.type_of_checkpoints_active = data.get("type_of_checkpoints_active", "Main")

        self.context = data.get("context", [])
        self.complete_context = data.get("complete_context", [])
        self.temporary_context = data.get("temporary_context", [])

        self.async_agent_results = data.get("async_agent_results", {})
        self.sync_agent_results = defaultdict(list, data.get("sync_agent_results", {}))

        self.is_paused = data.get("is_paused", False)
        self.pending_agent_invocation = data.get("pending_agent_invocation")
        self.resume_after_subtask = data.get("resume_after_subtask")
        self.patient_verified = data.get("patient_verified", False)

        self.has_summary = data.get("has_summary", False)
        self.summary = data.get("summary")
        self.key_points = data.get("key_points", [])
        self.tags = data.get("tags", [])

        self.individual_id = data.get("individual_id", self.individual_id)
        self.user_profile_id = data.get("user_profile_id", self.user_profile_id)
        self.detected_agent = data.get("detected_agent", self.detected_agent)
        self.agent_instance_id = data.get("agent_instance_id", self.agent_instance_id)
        self.call_log_id = data.get("call_log_id", self.call_log_id)
        self._update_current_task()

    def is_new_conversation(self) -> bool:
        """Check if this is a new conversation"""
        return self.is_new or len(self.task_stack) == 0

    def set_Tasks(self, checkpoints: List[Union[str, dict, Checkpoint]], task: Union[Task, dict],
                  checkpoint_types: Optional[List[CheckpointType]] = None) -> None:
        """Optimized task setting with minimal allocations"""
        # Prepare main task
        if not isinstance(task, dict):
            main_task = {
                "task_id": task.task_id,
                "label": task.label,
                "source": task.source,
                "checklist": [],
                "current_checkpoint_index": task.current_checkpoint_index,
                "is_active": task.is_active,
                "created_at": task.created_at.isoformat(),
                "updated_at": task.updated_at.isoformat()
            }
        else:
            main_task = task.copy()
            main_task["checklist"] = []

        # Process checkpoints efficiently
        now = datetime.now().isoformat()
        checklist = []

        for i, cp in enumerate(checkpoints):
            cp_type = checkpoint_types[i] if checkpoint_types and i < len(checkpoint_types) else "Main"

            if isinstance(cp, str):
                checkpoint = {
                    "id": cp, "name": cp, "label": f"Step {i+1}",
                    "type": cp_type, "status": "pending",
                    "expected_inputs": [], "collected_inputs": [],
                    "start_time": None, "end_time": None
                }
            elif isinstance(cp, dict):
                checkpoint = {
                    "id": cp.get('id', f"cp_{i}"),
                    "name": cp.get('name', cp.get('id', f"cp_{i}")),
                    "label": cp.get('label', f"Step {i+1}"),
                    "type": cp.get('type', cp_type),
                    "status": "pending",
                    "expected_inputs": cp.get('expected_inputs', []),
                    "collected_inputs": cp.get('collected_inputs', []),
                    "start_time": None, "end_time": None
                }
            else:
                continue

            checklist.append(checkpoint)

        # Set first checkpoint as in progress
        if checklist:
            checklist[0]["status"] = "in_progress"
            checklist[0]["start_time"] = now

        main_task["checklist"] = checklist
        self.task_stack = [main_task]

        # Update backward compatibility fields
        self.checkpoints = [cp["id"] for cp in checklist]
        self.checkpoint_progress = {cp["id"]: False for cp in checklist}
        self.type_of_checkpoints_active = "Main"

        self._update_current_task()
        self._mark_dirty("task_stack")

        _logger.info(f"Set tasks - current_task: {self.current_task.get('task_id') if self.current_task else 'None'}")

    def get_current_checkpoint(self) -> Optional[Dict[str, Any]]:
        """Optimized current checkpoint retrieval"""
        if not self.task_stack:
            return self._legacy_checkpoint_fallback()

        # Check active tasks from end to beginning
        for task in reversed(self.task_stack):
            if not task.get('is_active', False):
                continue

            checklist = task.get('checklist', [])
            current_index = task.get('current_checkpoint_index', 0)

            if checklist and current_index < len(checklist):
                checkpoint = checklist[current_index]
                if checkpoint.get("status") != "complete":
                    return checkpoint

        return self._legacy_checkpoint_fallback()

    def _legacy_checkpoint_fallback(self) -> Optional[str]:
        """Fallback to legacy checkpoint system"""
        if hasattr(self, 'checkpoints') and self.checkpoints:
            for cp in self.checkpoints:
                if not self.checkpoint_progress.get(cp, False):
                    return cp
        return None

    def _update_current_task(self) -> None:
        """Ultra-fast current task update"""
        old_id = self.current_task.get('task_id') if self.current_task else None

        for task in reversed(self.task_stack):
            if not task.get("is_active", False):
                continue

            checklist = task.get("checklist", [])
            current_index = task.get("current_checkpoint_index", 0)

            if (checklist and current_index < len(checklist) and
                checklist[current_index].get("status") != "complete"):

                self.current_task = task
                self.type_of_checkpoints_active = task.get("label", "Main")

                new_id = task.get('task_id')
                if old_id != new_id:
                    _logger.info(f"current_task updated: {old_id} → {new_id}")
                return

        if self.current_task:
            _logger.info(f"current_task cleared (was {old_id})")
        self.current_task = None

    def mark_checkpoint_complete(self, checkpoint: Optional[Dict[str, Any]], text: str) -> None:
        """Ultra-optimized checkpoint completion"""
        if not self.task_stack or not checkpoint:
            self._update_current_task()
            return

        checkpoint_name = checkpoint.get("name")
        if not checkpoint_name:
            self._update_current_task()
            return

        current_time = datetime.now().isoformat()

        # Single pass optimization
        for task in self.task_stack:
            checklist = task.get("checklist")
            if not checklist:
                continue

            for i, cp in enumerate(checklist):
                if cp["name"] != checkpoint_name:
                    continue

                # Update checkpoint
                cp.update({
                    "status": "complete",
                    "end_time": current_time
                })
                cp.setdefault("collected_inputs", []).append(text)

                task["is_active"] = True

                # Advance to next checkpoint
                checklist_len = len(checklist)
                if i == checklist_len - 1:
                    task["is_active"] = False
                    task["current_checkpoint_index"] = checklist_len
                else:
                    # Find next incomplete checkpoint
                    for j in range(i + 1, checklist_len):
                        if checklist[j]["status"] != "complete":
                            task["current_checkpoint_index"] = j
                            checklist[j].update({
                                "status": "in_progress",
                                "start_time": current_time
                            })
                            break
                    else:
                        task["current_checkpoint_index"] = checklist_len
                        task["is_active"] = False

                self._update_current_task()
                self._mark_dirty("task_stack")

                _logger.info(f"Checkpoint '{checkpoint_name}' completed")
                return

        _logger.warning(f"Checkpoint '{checkpoint_name}' not found")
        self._update_current_task()

    @cached(ttl=300, prefix="context")
    async def get_context(self, plan: Optional[str] = "lite", text: Optional[str] = None) -> List[Dict[str, str]]:
        """Cached context retrieval with semantic search"""
        if plan == "lite":
            return self.context[-16:] if len(self.context) > 16 else self.context

        if plan == "pro" and text:
            try:
                await self._ensure_http_client()
                response = await self._http_client.post(
                    f"{settings.MEMORY_URL}/get_semantic_context",
                    params={
                        "individual_id": self.individual_id or self.conversation_id,
                        "query": text,
                        "limit": 50
                    },
                    timeout=5.0
                )

                if response.status_code == 200:
                    api_response = response.json()
                    if api_response.get("status") == "success":
                        cache_manager.stats.api_calls += 1
                        return api_response.get("context", [])

            except Exception as e:
                _logger.error(f"Semantic context API error: {e}")

        return self.context[-16:] if len(self.context) > 16 else self.context

    async def update_context(self, query: str, response: str, plan: str) -> None:
        """Optimized context update with batch processing"""
        new_messages = [
            {"role": "user", "content": query},
            {"role": "assistant", "content": response}
        ]

        self.context.extend(new_messages)
        self.complete_context.extend(new_messages)
        self._mark_dirty("context")

        # Async save without blocking
        asyncio.create_task(self._save_context_async(plan))

    async def _save_context_async(self, plan: str):
        """Async context saving"""
        try:
            await self._ensure_http_client()
            await self._http_client.post(
                f"{settings.MEMORY_URL}/conversation/update",
                json={
                    "conversation_id": self.conversation_id,
                    "context": self.context,
                    "complete_context": self.complete_context,
                    "individual_id": self.individual_id,
                    "user_profile_id": self.user_profile_id,
                    "call_log_id": self.call_log_id,
                    "plan": plan
                },
                timeout=15.0  # Increased timeout for context updates
            )

            # Update cache
            cache_key_str = cache_key("conversation", self.conversation_id)
            await cache_manager.set(cache_key_str, self._to_dict())

        except Exception as e:
            _logger.error(f"Failed to save context: {type(e).__name__}: {str(e)}")
            if hasattr(e, 'response') and hasattr(e.response, 'text'):
                _logger.error(f"Response content: {e.response.text[:500]}")

    async def set_async_agent_result(self, agent_name: str, result: AgentResult) -> None:
        """Optimized async agent result storage"""
        agent_result = {
            "agent_name": agent_name,
            "status": result.get("status", "success"),
            "result_payload": result,
            "message_to_user": result.get("message_to_user"),
            "action_required": result.get("action_required", False),
            "timestamp": datetime.now().isoformat(),
            "consumed": False
        }

        self.async_agent_results[agent_name] = agent_result
        self._mark_dirty("async_agent_results")

        # Async save
        asyncio.create_task(self._save_agent_result_async(agent_result))

    async def set_sync_agent_result(self, agent_name: str, result: AgentResult) -> None:
        """Optimized sync agent result storage"""
        agent_result = {
            "agent_name": agent_name,
            "status": result.get("status", "success"),
            "result_payload": result.get("result_payload", {}),
            "message_to_user": result.get("message_to_user"),
            "action_required": result.get("action_required", False),
            "timestamp": datetime.now().isoformat(),
            "consumed": False
        }

        self.sync_agent_results[agent_name].append(agent_result)
        self._mark_dirty("sync_agent_results")

        # Async save
        asyncio.create_task(self._save_sync_agent_result_async(agent_name, result))

    async def _save_agent_result_async(self, agent_result: Dict[str, Any]):
        """Async agent result saving"""
        try:
            await self._ensure_http_client()
            await self._http_client.post(
                f"{settings.MEMORY_URL}/conversation/agent_result",
                params={"conversation_id": self.conversation_id},
                json=agent_result,
                timeout=10.0  # Added timeout for agent results
            )
        except Exception as e:
            _logger.error(f"Failed to save async agent result: {type(e).__name__}: {str(e)}")
            if hasattr(e, 'response') and hasattr(e.response, 'text'):
                _logger.error(f"Response content: {e.response.text[:500]}")

    async def _save_sync_agent_result_async(self, agent_name: str, result: AgentResult):
        """Async sync agent result saving"""
        try:
            await self._ensure_http_client()
            await self._http_client.post(
                f"{settings.MEMORY_URL}/conversation/sync_agent_result",
                params={"conversation_id": self.conversation_id},
                json={
                    "agent_name": agent_name,
                    "status": result.get("status", "success"),
                    "result_payload": result,
                    "message_to_user": result.get("message_to_user"),
                    "action_required": result.get("action_required", False),
                    "timestamp": datetime.now().isoformat()
                },
                timeout=10.0  # Added timeout for sync agent results
            )
        except Exception as e:
            _logger.error(f"Failed to save sync agent result: {type(e).__name__}: {str(e)}")
            if hasattr(e, 'response') and hasattr(e.response, 'text'):
                _logger.error(f"Response content: {e.response.text[:500]}")

    def get_async_agent_results(self) -> Dict[str, AgentResult]:
        """Get async agent results"""
        return self.async_agent_results

    def get_sync_agent_results(self) -> Dict[str, List[AgentResult]]:
        """Get sync agent results"""
        return dict(self.sync_agent_results)

    def _to_dict(self) -> Dict[str, Any]:
        """Convert state to dictionary for caching"""
        return {
            "conversation_id": self.conversation_id,
            "individual_id": self.individual_id,
            "user_profile_id": self.user_profile_id,
            "call_log_id": self.call_log_id,
            "detected_agent": self.detected_agent,
            "agent_instance_id": self.agent_instance_id,
            "task_stack": self.task_stack,
            "checkpoint_progress": self.checkpoint_progress,
            "type_of_checkpoints_active": self.type_of_checkpoints_active,
            "context": self.context,
            "complete_context": self.complete_context,
            "temporary_context": self.temporary_context,
            "async_agent_results": self.async_agent_results,
            "sync_agent_results": dict(self.sync_agent_results),
            "is_paused": self.is_paused,
            "pending_agent_invocation": self.pending_agent_invocation,
            "resume_after_subtask": self.resume_after_subtask,
            "patient_verified": self.patient_verified,
            "has_summary": self.has_summary,
            "summary": self.summary,
            "key_points": self.key_points,
            "tags": self.tags
        }

    async def save(self, force: bool = False) -> None:
        """Optimized save with incremental updates and caching"""
        if not force and not self._dirty_fields:
            return  # Nothing to save

        # Rate limiting
        now = datetime.now()
        if (not force and self._last_save_time and
            (now - self._last_save_time).seconds < 5):
            return

        try:
            state_dict = self._to_dict()

            # Update cache immediately
            cache_key_str = cache_key("conversation", self.conversation_id)
            await cache_manager.set(cache_key_str, state_dict)

            # Ensure state_dict matches memory service ConversationState schema
            # Convert task_stack, sync_agent_results, and async_agent_results to match expected schema
            for i, task in enumerate(state_dict.get("task_stack", [])):
                if "checklist" in task and isinstance(task["checklist"], list):
                    for j, checkpoint in enumerate(task["checklist"]):
                        # Truncate checkpoint names that are too long (max 200 chars)
                        if "name" in checkpoint and isinstance(checkpoint["name"], str) and len(checkpoint["name"]) > 200:
                            state_dict["task_stack"][i]["checklist"][j]["name"] = checkpoint["name"][:197] + "..."
                            
                        # Convert collected_inputs from dict to list as expected by memory service
                        if "collected_inputs" in checkpoint and isinstance(checkpoint["collected_inputs"], dict):
                            state_dict["task_stack"][i]["checklist"][j]["collected_inputs"] = list(checkpoint["collected_inputs"].keys())

            # Async API save with longer timeout
            await self._ensure_http_client()
            
            response = await self._http_client.post(
                f"{settings.MEMORY_URL}/conversation/state",
                json=state_dict,
                timeout=20.0  # Increased timeout for state saves
            )
            
            # Check for error responses
            if response.status_code >= 400:
                error_detail = "Unknown error"
                try:
                    error_detail = response.json()
                except:
                    if response.text:
                        error_detail = response.text[:500]  # Limit text size
                        
                _logger.error(f"HTTP error saving conversation state ({response.status_code}): {error_detail}")
                
                # If it's a validation error, try to fix common issues and retry
                if response.status_code == 422 and "string_too_long" in str(error_detail):
                    _logger.info("Attempting to fix string length issues and retry...")
                    # Further truncate all checkpoint names as a last resort
                    for i, task in enumerate(state_dict.get("task_stack", [])):
                        if "checklist" in task and isinstance(task["checklist"], list):
                            for j, checkpoint in enumerate(task["checklist"]):
                                if "name" in checkpoint and isinstance(checkpoint["name"], str) and len(checkpoint["name"]) > 100:
                                    state_dict["task_stack"][i]["checklist"][j]["name"] = checkpoint["name"][:97] + "..."
                    
                    # Try one more time with aggressively truncated strings
                    retry_response = await self._http_client.post(
                        f"{settings.MEMORY_URL}/conversation/state",
                        json=state_dict,
                        timeout=20.0  # Increased timeout for retries
                    )
                    if 200 <= retry_response.status_code < 300:
                        _logger.info(f"✅ Saved conversation state after retry: {retry_response.status_code}")
                        self._dirty_fields.clear()
                        self._last_save_time = now
                        return
                    
                response.raise_for_status()  # Will raise an exception with the status code
            else:
                self._dirty_fields.clear()
                self._last_save_time = now
                cache_manager.stats.api_calls += 1
                
                _logger.info(f"✅ Saved conversation state: {response.status_code}")
                
        except Exception as e:
            _logger.error(f"Failed to save conversation state: {type(e).__name__}: {str(e)}")
            if hasattr(e, 'response') and hasattr(e.response, 'text'):
                _logger.error(f"Response content: {e.response.text[:500]}")
            # Log the state dict size for debugging
            if 'state_dict' in locals():
                _logger.error(f"State dict size: {len(str(state_dict))} chars")

    async def set_sync_agent_checklists(self, sync_agent_checklists: Dict[str, Dict[str, Any]]) -> None:
        """
        FIXED: Update the task stack with synchronous agent checklists and save to all memory stores.
        Special handling for privacy checklists - they should always be at the end of the task stack.

        Args:
            sync_agent_checklists: Dictionary mapping agent names to their task definitions
                                   with checklists
        """
        # First, collect all privacy checklists from the existing task stack
        privacy_checklists = []
        non_privacy_tasks = []

        # Separate existing privacy checklists from other tasks
        for task in self.task_stack:
            if isinstance(task, dict) and task.get("label") == "privacy" and task.get("is_active") is True:
                privacy_checklists.append(task)
            else:
                non_privacy_tasks.append(task)

        # Set the task stack to non-privacy tasks for now
        self.task_stack = non_privacy_tasks

        # Process new tasks
        new_privacy_checklists = []

        for agent_name, task_def in sync_agent_checklists.items():
            # Check if this is a privacy checklist that should be handled specially

            is_privacy_checklist = task_def.get("label") == "privacy" and task_def.get("is_active") is True

            # Search for an existing task with the same ID
            existing_task_index = None
            for i, task in enumerate(self.task_stack):
                if isinstance(task, dict) and task.get("task_id") == task_def.get("task_id"):
                    existing_task_index = i
                    break

            # Handle based on whether it's privacy checklist or not
            if is_privacy_checklist:
                # Add to our collection of new privacy checklists
                new_privacy_checklists.append(task_def)
            else:
                # Regular task - update existing or append
                if existing_task_index is not None:
                    self.task_stack[existing_task_index] = task_def
                else:
                    self.task_stack.append(task_def)

        # Merge all privacy checklists (old and new) while removing duplicates
        all_privacy_checklists = []
        seen_task_ids = set()

        # Process existing privacy checklists first
        for checklist in privacy_checklists:
            task_id = checklist.get("task_id")
            if task_id not in seen_task_ids:
                all_privacy_checklists.append(checklist)
                seen_task_ids.add(task_id)

        # Then process new privacy checklists
        for checklist in new_privacy_checklists:
            task_id = checklist.get("task_id")
            if task_id not in seen_task_ids:
                all_privacy_checklists.append(checklist)
                seen_task_ids.add(task_id)

        # Append all unique privacy checklists at the end
        self.task_stack.extend(all_privacy_checklists)

        # FIXED: Always update current_task after modifying task stack

        self._update_current_task()

        _logger.info(f"Updated sync agent checklists - current_task: {self.current_task.get('task_id') if self.current_task else 'None'}")

        # Save updated state to memory service
        try:
            task_stack_serializable = [task.dict() if hasattr(task, 'dict') else task for task in self.task_stack]

            async with httpx.AsyncClient(timeout=httpx.Timeout(10.0, read=10.0)) as client:
                await client.post(
                    f"{settings.MEMORY_URL}/conversation/update_tasks_stack",
                    json={
                        "conversation_id": self.conversation_id,
                        "task_stack": task_stack_serializable
                    }
                )
                _logger.info(f"Successfully updated sync agent checklists in memory stores")
        except Exception as e:
            _logger.error(f"Failed to update sync agent checklists in memory stores: {e!r}")


    # async def update_patient_verification(self) -> Dict[str, Any]:
    #     """
    # Update the patient verification status and sync with databases.

    # Returns:
    #     Dictionary with status information
    # """
    #     try:
    #         self.patient_verified = False

    #     # Call API to update databases
    #         async with httpx.AsyncClient(timeout=httpx.Timeout(10.0, read=10.0)) as client:
    #             await client.post(
    #             f"{settings.MEMORY_URL}/conversation/update_patient_verification_status",
    #             json={
    #                 "conversation_id": self.conversation_id,
    #                 "patient_verified": False
    #             }
    #         )

    #         logging.info(f"✅ Successfully updated patient verification for conversation: {self.conversation_id}")
    #         return {
    #         "status": "success",
    #         "message": "Patient verification status updated successfully"
    #     }

    #     except Exception as e:
    #         logging.error(f"❌ Error updating patient verification: {str(e)}")
    #         return {
    #         "status": "error",
    #         "message": f"Error: {str(e)}"
    #     }


    async def get_unconsumed_agent_results(self) -> Dict[str, Any]:
        """
    Retrieve all unconsumed agent results from sync_agent_results.

    Returns:
        Dictionary with status and a list of unconsumed agent results.
    """
        try:
            unconsumed_results = []

            for agent_name, results in self.sync_agent_results.items():
                for result in results:
                    if not result.get("consumed", False):
                        unconsumed_results.append({
                            "agent_name": agent_name,
                          **result
                    })
                    # Mark as consumed after retrieving
                    result["consumed"] = True

            logging.info(f"🔍 Found {len(unconsumed_results)} unconsumed agent results.")

            return {
            "status": "success",
            "unconsumed_results": unconsumed_results
            }

        except Exception as e:
            logging.error(f"❌ Error fetching unconsumed agent results: {str(e)}")
            return {
            "status": "error",
            "message": f"Error: {str(e)}"
        }
    # Add these methods to your ConversationState class



    def get_completed_checklists(self) -> List[str]:
        """
    Get list of completed support agent checklists from the task stack.
    A task is considered completed if its is_active field is False.

    Returns:
        List[str]: List of task IDs or labels of completed support agent tasks
    """
        completed_checklists = []

    # Iterate through all tasks in the task stack
        for task in self.task_stack:
            if not isinstance(task, dict):
                continue

        # Check if the task is not active (meaning it's completed)
            is_active = task.get("is_active", False)

            if not is_active:
                task_identifier = task.get("task_id") or task.get("label")

                if task_identifier:
                    completed_checklists.append(task_identifier)
                    _logger.info(f"Found completed checklist: {task_identifier}")

        _logger.info(f"Total completed checklists found: {len(completed_checklists)}")
        return completed_checklists
