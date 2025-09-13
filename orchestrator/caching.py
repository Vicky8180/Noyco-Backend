# orchestrator/caching.py

"""
Caching utilities for the orchestrator service.
Provides caching mechanisms for service responses to reduce latency.
"""

import logging
import aiocache
from typing import Dict, Optional, Any
from orchestrator.config import get_settings

_logger = logging.getLogger(__name__)

# Get settings
settings = get_settings()

# Cache for recently completed checkpoint evaluations
checkpoint_cache = aiocache.Cache(
    cache_class=aiocache.SimpleMemoryCache,
    namespace="checkpoint_evaluations",
    ttl=settings.CHECKPOINT_EVALUATION_CACHE_TTL
)

# Additional cache for task state
task_cache = aiocache.Cache(
    cache_class=aiocache.SimpleMemoryCache,
    namespace="task_state",
    ttl=settings.TASK_STATE_CACHE_TTL
)

async def get_cached_checkpoint_evaluation(
    conversation_id: str,
    checkpoint: str,
    text_hash: int
) -> Optional[Dict[str, Any]]:
    """
    Get a cached checkpoint evaluation result.

    Args:
        conversation_id: The conversation ID
        checkpoint: The checkpoint being evaluated
        text_hash: A hash of the text content

    Returns:
        The cached result dict or None if not found
    """
    cache_key = f"{conversation_id}:{checkpoint}:{text_hash}"
    return await checkpoint_cache.get(cache_key)

async def cache_checkpoint_evaluation(
    conversation_id: str,
    checkpoint: str,
    text_hash: int,
    result: Dict[str, Any]
):
    """
    Cache a checkpoint evaluation result.

    Args:
        conversation_id: The conversation ID
        checkpoint: The checkpoint being evaluated
        text_hash: A hash of the text content
        result: The evaluation result to cache
    """
    cache_key = f"{conversation_id}:{checkpoint}:{text_hash}"
    await checkpoint_cache.set(cache_key, result)
    _logger.debug(f"Cached checkpoint evaluation: {checkpoint}")

async def get_cached_task_state(
    conversation_id: str,
    task_id: str
) -> Optional[Dict[str, Any]]:
    """
    Get a cached task state.

    Args:
        conversation_id: The conversation ID
        task_id: The task ID

    Returns:
        The cached task state or None if not found
    """
    cache_key = f"{conversation_id}:{task_id}"
    return await task_cache.get(cache_key)

async def cache_task_state(
    conversation_id: str,
    task_id: str,
    state: Dict[str, Any]
):
    """
    Cache a task state.

    Args:
        conversation_id: The conversation ID
        task_id: The task ID
        state: The task state to cache
    """
    cache_key = f"{conversation_id}:{task_id}"
    await task_cache.set(cache_key, state)
    _logger.debug(f"Cached task state for task: {task_id}")
