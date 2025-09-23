


"""
Service call functions for interacting with agent services.
Manages calls to various specialized services and handles responses.
"""

import asyncio
import logging
from typing import List, Dict, Optional, Any, Callable
import httpx
from fastapi import HTTPException

if __name__ == "__main__" and __package__ is None:
    from orchestrator.timing import TimingMetrics
    from orchestrator.agents import get_service_url
    from orchestrator.caching import get_cached_checkpoint_evaluation, cache_checkpoint_evaluation
    from orchestrator.config import get_settings
    from common.models import AgentResult, AgentResponseStatus, CheckpointType, Checkpoint
else:
    from .timing import TimingMetrics
    from .agents import get_service_url
    from .caching import get_cached_checkpoint_evaluation, cache_checkpoint_evaluation
    from .config import get_settings
    from common.models import AgentResult, AgentResponseStatus, CheckpointType, Checkpoint

_logger = logging.getLogger(__name__)

# Get settings
settings = get_settings()

# Configuration constants from settings
CHECKPOINT_URL = f"{settings.CHECKPOINT_URL}/generate"
PRIMARY_URL = settings.PRIMARY_SERVICE_URL

# Service-specific timeout configurations
SERVICE_TIMEOUTS = {
    "default": httpx.Timeout(
        connect=settings.HTTP_CONNECT_TIMEOUT, 
        read=settings.HTTP_READ_TIMEOUT, 
        write=settings.HTTP_WRITE_TIMEOUT, 
        pool=settings.HTTP_POOL_TIMEOUT
    ),
    "human_intervention": httpx.Timeout(
        connect=3.0, 
        read=settings.HUMAN_INTERVENTION_TIMEOUT, 
        write=10.0, 
        pool=5.0
    ),
    "checklist": httpx.Timeout(
        connect=3.0, 
        read=settings.CHECKLIST_TIMEOUT, 
        write=10.0, 
        pool=5.0
    ),
    "primary_enriched": httpx.Timeout(
        connect=5.0, 
        read=60.0, 
        write=30.0, 
        pool=15.0
    ),
    "medication": httpx.Timeout(
        connect=5.0, 
        read=settings.MEDICATION_TIMEOUT, 
        write=20.0, 
        pool=10.0
    ),
    "privacy": httpx.Timeout(
        connect=5.0, 
        read=settings.PRIVACY_TIMEOUT, 
        write=20.0, 
        pool=10.0
    ),
}

# Global HTTP client to be initialized during application startup
http_client: Optional[httpx.AsyncClient] = None

def ensure_http_client():
    """Ensure that the HTTP client is initialized with optimized settings."""
    global http_client
    if http_client is None:
        _logger.warning("HTTP client was not initialized by lifespan. Creating new client.")

        # Optimized connection limits from settings
        limits = httpx.Limits(
            max_keepalive_connections=settings.MAX_KEEPALIVE_CONNECTIONS,
            max_connections=settings.MAX_CONNECTIONS,
            keepalive_expiry=30.0
        )

        # Default timeout from settings
        default_timeout = httpx.Timeout(
            connect=settings.HTTP_CONNECT_TIMEOUT,
            read=settings.HTTP_READ_TIMEOUT,
            write=settings.HTTP_WRITE_TIMEOUT,
            pool=10.0      # Time to get connection from pool
        )

        http_client = httpx.AsyncClient(
            timeout=default_timeout,
            limits=limits,
            http2=True,  # Enable HTTP/2 for connection multiplexing
            # Add retry configuration
            transport=httpx.AsyncHTTPTransport(
                http2=True,
                retries=2  # Retry failed requests
            )
        )
        _logger.debug("HTTP client initialized with optimized settings")

def get_service_timeout(service_name: str) -> httpx.Timeout:
    """Get appropriate timeout for a specific service."""
    return SERVICE_TIMEOUTS.get(service_name, SERVICE_TIMEOUTS["default"])

async def call_service(
    url: str,
    payload: dict,
    timing: TimingMetrics,
    service_name: str,
    timeout: Optional[httpx.Timeout] = None,
    max_retries: int = 3  # Increased default retries
) -> dict:
    """
    Enhanced function to call services with advanced error handling, dynamic timeouts, and
    intelligent retry logic.

    Args:
        url: The service URL
        payload: The request payload
        timing: The timing metrics tracker
        service_name: Name of the service for timing metrics
        timeout: Optional custom timeout
        max_retries: Maximum number of retries for failed requests

    Returns:
        Service response as dictionary

    Raises:
        HTTPException: If the service call fails after retries
    """
    global http_client

    # Ensure HTTP client is initialized
    ensure_http_client()

    # Use service-specific timeout if not provided
    if timeout is None:
        timeout = get_service_timeout(service_name)

    timing.start(f"service_call_{service_name}")
    _logger.info(f"Making request to {url} with payload keys: {list(payload.keys())}")

    last_exception = None

    for attempt in range(max_retries + 1):
        try:
            if attempt > 0:
                _logger.info(f"Retry attempt {attempt} for {service_name}")
                # Add exponential backoff
                await asyncio.sleep(0.5 * (2 ** (attempt - 1)))

            # Make the request with timeout
            resp = await http_client.post(url, json=payload, timeout=timeout)

            # Handle validation errors (422)
            if resp.status_code == 422:
                error_detail = "Unknown validation error"
                try:
                    error_data = resp.json()
                    if "detail" in error_data:
                        error_detail = str(error_data["detail"])
                except Exception:
                    pass

                _logger.error(f"Validation error in request to {url}: {error_detail}")
                _logger.debug(f"Request payload that caused 422: {payload}")
                raise HTTPException(
                    status_code=422,
                    detail=f"Invalid request to service: {error_detail}. Please check your input data."
                )

            # Raise for other HTTP errors
            resp.raise_for_status()

            # Parse JSON response
            result = resp.json()
            _logger.info(f"Successfully received response from {url}")

            if attempt > 0:
                _logger.info(f"Request succeeded on attempt {attempt + 1}")

            return result

        except httpx.HTTPStatusError as e:
            last_exception = e
            status_code = e.response.status_code

            # Don't retry certain status codes
            if status_code in [400, 401, 403, 404, 422]:
                break

            try:
                error_detail = e.response.json()
            except:
                error_detail = str(e)

            _logger.error(f"Service call failed (attempt {attempt + 1}): {url} - {status_code} - {error_detail}")

            if attempt == max_retries:
                break

        except httpx.TimeoutException as e:
            last_exception = e
            _logger.error(f"Timeout error (attempt {attempt + 1}): {url} - {str(e)}")
            _logger.error(f"Timeout settings: {timeout}")

            if attempt == max_retries:
                break

        except httpx.RequestError as e:
            last_exception = e
            error_type = type(e).__name__
            _logger.error(f"Request error (attempt {attempt + 1}): {url} - {error_type} - {str(e)}")

            # Don't retry connection errors beyond first attempt
            if attempt > 0:
                break

        except Exception as e:
            last_exception = e
            error_type = type(e).__name__
            _logger.error(f"Unexpected error (attempt {attempt + 1}): {url} - {error_type} - {str(e)}")
            break

    # Handle final failure after all retries
    if isinstance(last_exception, httpx.HTTPStatusError):
        status_code = last_exception.response.status_code
        try:
            error_detail = last_exception.response.json()
        except:
            error_detail = str(last_exception)

        raise HTTPException(
            status_code=502,
            detail=f"Service unavailable after {max_retries + 1} attempts: {status_code} {last_exception.response.reason_phrase}"
        )
    elif isinstance(last_exception, httpx.TimeoutException):
        _logger.error(f"Final timeout - Request payload size: {len(str(payload))} characters")
        raise HTTPException(
            status_code=504,
            detail=f"Service timeout after {max_retries + 1} attempts. Service took longer than {timeout.read}s to respond."
        )
    elif isinstance(last_exception, httpx.RequestError):
        error_type = type(last_exception).__name__
        raise HTTPException(
            status_code=503,
            detail=f"Service connection failed ({error_type}): {str(last_exception)}"
        )
    else:
        error_type = type(last_exception).__name__ if last_exception else "Unknown"
        raise HTTPException(
            status_code=500,
            detail=f"Internal service error ({error_type}): {str(last_exception)}"
        )

    timing.end(f"service_call_{service_name}")

async def call_checklist_service(
    conversation_id: str,
    text: str,
    checkpoint: Optional[Checkpoint],
    context: dict,
    evaluation_only: bool,
    timing: TimingMetrics
) -> dict:
    """
    Dedicated function for checklist calls with caching for evaluation calls.
    """
    # Try to get from cache first for evaluation calls
    if evaluation_only:
        cached_result = await get_cached_checkpoint_evaluation(
            conversation_id,
            checkpoint,
            hash(text)
        )
        if cached_result:
            _logger.info(f"Cache hit for checkpoint evaluation: {checkpoint}")
            return cached_result

    # Call the service if not in cache
    checklist_url = get_service_url("checklist")

    result = await call_service(
        checklist_url,
        {
            "text": text,
            "conversation_id": conversation_id,
            "checkpoint": checkpoint,
            "context": context,
            "evaluation_only": evaluation_only,
        },
        timing,
        "checklist"
    )

    # Cache evaluation results
    if evaluation_only:
        await cache_checkpoint_evaluation(
            conversation_id,
            checkpoint,
            hash(text),
            result
        )

    return result

async def call_specialists(
    specialists: List[str],
    text: str,
    conversation_id: str,
    checkpoint: Optional[Checkpoint],
    context: dict,
    timing: TimingMetrics,
    checklist_result: dict = None,
    early_response_callback=None
) -> Dict[str, dict]:
    """
    Optimized parallel specialist calls with priority handling and early response support.
    """
    if not specialists:
        return {}

    timing.start("specialists_calls")
    _logger.info(f"Calling specialists: {specialists}")

    specialist_responses = {}

    # Initialize with checklist result if already available
    if checklist_result and "checklist" in specialists:
        specialist_responses["checklist"] = checklist_result
        specialists = [s for s in specialists if s != "checklist"]

    # Early callback if we have results
    if early_response_callback and specialist_responses:
        try:
            await early_response_callback(specialist_responses.copy())
        except Exception as e:
            _logger.error(f"Error in early response callback: {e}")

    if not specialists:
        timing.end("specialists_calls")
        return specialist_responses

    # Create tasks with timeout management
    timeout_per_specialist = 45.0  # Maximum time per specialist
    total_timeout = min(120.0, len(specialists) * 30.0)  # Total timeout with cap

    try:
        # Use asyncio.wait_for to enforce total timeout
        specialist_responses_new = await asyncio.wait_for(
            _call_specialists_parallel(
                specialists,
                text,
                conversation_id,
                checkpoint,
                context,
                timing,
                early_response_callback
            ),
            timeout=total_timeout
        )

        specialist_responses.update(specialist_responses_new)

    except asyncio.TimeoutError:
        _logger.error(f"Specialists call timed out after {total_timeout}s")
        # Add timeout errors for missing specialists
        for spec in specialists:
            if spec not in specialist_responses:
                specialist_responses[spec] = {
                    "error": f"Specialist timed out after {total_timeout}s",
                    "status": "timeout"
                }

    timing.end("specialists_calls")
    return specialist_responses

async def _call_specialists_parallel(
    specialists: List[str],
    text: str,
    conversation_id: str,
    checkpoint: str,
    context: dict,
    timing: TimingMetrics,
    early_response_callback=None
) -> Dict[str, dict]:
    """Helper function to call specialists in parallel with proper error handling."""

    # Create tasks for all specialists
    tasks = {}
    for spec in specialists:
        task = asyncio.create_task(
            _call_specialist(spec, text, conversation_id, checkpoint, context, timing)
        )
        tasks[spec] = task

    specialist_responses = {}

    # Wait for tasks to complete
    while tasks:
        try:
            # Wait for next completion with timeout
            done, pending = await asyncio.wait(
                tasks.values(),
                return_when=asyncio.FIRST_COMPLETED,
                timeout=45.0  # Timeout for any single specialist
            )

            # Handle timeouts
            if not done:
                _logger.warning("Some specialists are taking too long, continuing with available results")
                # Cancel pending tasks
                for task in pending:
                    task.cancel()
                break

            # Process completed tasks
            completed_specs = []
            for spec_name, task in tasks.items():
                if task in done:
                    completed_specs.append(spec_name)
                    try:
                        result = await task
                        specialist_responses[spec_name] = result
                        _logger.info(f"✓ Specialist {spec_name} completed successfully")

                        # Early callback
                        if early_response_callback:
                            try:
                                await early_response_callback(specialist_responses.copy())
                            except Exception as e:
                                _logger.error(f"Error in callback for {spec_name}: {e}")

                    except Exception as e:
                        _logger.error(f"✗ Specialist {spec_name} failed: {e}")
                        specialist_responses[spec_name] = {
                            "error": str(e),
                            "status": "error"
                        }

            # Remove completed tasks
            for spec in completed_specs:
                del tasks[spec]

        except Exception as e:
            _logger.error(f"Error in specialist processing: {e}")
            break

    return specialist_responses

async def _call_specialist(
    specialist: str,
    text: str,
    conversation_id: str,
    checkpoint: str,
    context: dict,
    timing: TimingMetrics
) -> dict:
    """
    Helper function to call a single specialist with optimized error handling.
    """
    timing.start(f"specialist_{specialist}")

    try:
        payload = {
            "text": text,
            "conversation_id": conversation_id,
            "checkpoint": checkpoint,
            "context": context
        }

        url = get_service_url(specialist)
        _logger.debug(f"Calling specialist {specialist} at {url}")

        # Special handling for privacy service
        if settings.PRIVACY_SERVICE_URL in url:
            _logger.debug("Adding privacy-specific payload data")
            # Add any privacy-specific data if needed
            # payload["fullname"] = "Anoop Yadav"
            # payload["number"] = 8299891902
            # payload["dob"] = "26/12/2000"

        result = await call_service(
            url,
            payload,
            timing,
            specialist
        )

        _logger.debug(f"Specialist {specialist} returned result")
        return result

    except Exception as e:
        _logger.error(f"Failed to call specialist {specialist}: {e}")
        raise
    finally:
        timing.end(f"specialist_{specialist}")

async def call_primary_with_enrichment(
    text: str,
    conversation_id: str,
    checkpoint: str,
    context: dict,
    checkpoint_complete: bool,
    specialist_responses: Dict[str, dict],
    async_agent_results: Dict[str, AgentResult],
    timing: TimingMetrics
) -> dict:
    """
    Call primary agent with specialist enrichments.
    """
    timing.start("primary_enriched")

    # Ensure context is a list as expected by the primary service
    if context is not None and not isinstance(context, list):
        if isinstance(context, dict):
            context = [context]
        else:
            context = []

    # Convert async_agent_results to dict format
    api_agent_results = {}
    for agent_id, agent_result in async_agent_results.items():
        if isinstance(agent_result, AgentResult):
            api_agent_results[agent_id] = {
                "agent_name": agent_result.agent_name,
                "status": agent_result.status,
                "result_payload": agent_result.result_payload,
                "message_to_user": agent_result.message_to_user,
                "action_required": agent_result.action_required,
                "timestamp": agent_result.timestamp.isoformat(),
                "consumed": agent_result.consumed
            }
        else:
            api_agent_results[agent_id] = agent_result

    try:
        # Use longer timeout for primary service
        result = await call_service(
            PRIMARY_URL,
            {
                "text": text,
                "conversation_id": conversation_id,
                "checkpoint": checkpoint,
                "context": context,
                "checkpoint_complete": checkpoint_complete,
                "specialist_responses": specialist_responses,
                "async_agent_results": api_agent_results
            },
            timing,
            "primary_enriched",
            timeout=httpx.Timeout(30.0)  # Increased timeout for primary service to 30 seconds
        )
        return result
    finally:
        timing.end("primary_enriched")

# Utility function to check service health
async def check_service_health(service_name: str) -> bool:
    """Check if a service is healthy and responding."""
    try:
        url = get_service_url(service_name)
        health_url = url.replace("/process", "/health")

        ensure_http_client()
        response = await http_client.get(health_url, timeout=5.0)
        return response.status_code == 200
    except Exception as e:
        _logger.warning(f"Health check failed for {service_name}: {e}")
        return False
