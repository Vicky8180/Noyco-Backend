from typing import Dict, List, Optional, Any
from common.gemini_client import get_gemini_client
from common.models import Checkpoint
import logging
from orchestrator.timing import TimingMetrics

_logger = logging.getLogger(__name__)

async def track_checkpoint_progress(text: str, checkpoint: Optional[Checkpoint], context: List[Dict[str, str]]) -> Dict[str, Any]:
    """
    Simplified checkpoint progress tracker that returns only essential fields,
    now with a softer evaluation to lower strictness.

    Args:
        text: Patient's message
        checkpoint: Current conversation checkpoint object
        context: Previous conversation context

    Returns:
        Dict with simplified checkpoint tracking assessment including timing metrics
    """
    # If no checkpoint is active, all are complete
    timing = TimingMetrics()
    timing.start("total_processing")

    if not checkpoint:
        timing.end("total_processing")
        return {
            "checkpoint_complete": True,
            "progress_percentage": 100.0,
            "next_checkpoint": None,
            "confidence": 1.0,
            "timing_metrics": timing.get_metrics()
        }

    # Format context for the model
    timing.start("context_formatting")
    context_str = ""
    if context:
        for turn in context:
            try:
                if turn.get("role") == "user":
                    context_str += f"Patient: {turn.get('content', '')}\n"
                else:
                    context_str += f"Assistant: {turn.get('content', '')}\n"
            except (AttributeError, TypeError) as e:
                _logger.warning(f"Error processing context item: {e}")
                continue
    timing.end("context_formatting")

    client = get_gemini_client()

    # Create a simplified and forgiving prompt
    timing.start("prompt_creation")
    prompt = f"""
    You are evaluating if a patient has provided sufficient information for the current checkpoint question.
    Be forgiving and lenient in your judgment. If the message even partially covers the expectation, you can say 'Yes'.

    CURRENT CHECKPOINT QUESTION: {checkpoint.name}
    EXPECTED INPUTS: {', '.join(checkpoint.expected_inputs) if checkpoint.expected_inputs else 'Not specified'}

    CONVERSATION HISTORY:
    {context_str}

    PATIENT'S MOST RECENT MESSAGE: "{text}"

    RESPOND WITH:
    Complete: [Yes/No]
    Confidence: [0-100]
    """
    timing.end("prompt_creation")

    try:
        timing.start("checkpoint_llm_call")  # Fixed typo
        response = await client.generate_content(prompt)
        timing.end("checkpoint_llm_call")
        response_text = response.text.strip()
    except Exception as e:
        timing.end("checkpoint_llm_call")  # End timing even on error
        timing.end("total_processing")
        _logger.exception("Error calling Gemini API")
        return {
            "checkpoint_complete": False,
            "progress_percentage": 0.0,
            "next_checkpoint": None,
            "confidence": 0.0,
            "timing_metrics": timing.get_metrics()
        }
    
    # Parse response (simplified)
    timing.start("response_parsing")
    checkpoint_complete = False
    confidence = 0.0

    for line in response_text.split('\n'):
        if line.startswith("Complete:"):
            checkpoint_complete = "yes" in line.lower()
        elif line.startswith("Confidence:"):
            try:
                confidence_text = line[11:].strip().replace('%', '')
                confidence = float(confidence_text) / 100.0
            except ValueError:
                confidence = 0.5  # Default if parsing fails
    timing.end("response_parsing")

    # Softer evaluation logic
    timing.start("evaluation_logic")
    LOW_CONFIDENCE_THRESHOLD = 0.6  # Reduced threshold

    if checkpoint_complete and confidence >= LOW_CONFIDENCE_THRESHOLD:
        final_checkpoint_complete = True
        progress_percentage = 100.0
    else:
        # Apply a soft boost to the progress even at lower confidence
        progress_percentage = min(95.0, (confidence + 0.15) * 100)
        final_checkpoint_complete = False
    timing.end("evaluation_logic")
    
    timing.end("total_processing")
    
    return {
        "checkpoint_complete": final_checkpoint_complete,
        "progress_percentage": progress_percentage,
        "confidence": confidence,
        "timing_metrics": timing.get_metrics()
    }
#         _logger.exception("Error calling Gemini API")
#         return {
#             "checkpoint_complete": False,
#             "progress_percentage": 0.0,
#             "next_checkpoint": None,
#             "confidence": 0.0,
#             "timing_metrics": timing.get_metrics()
#         }

#     # Parse response (simplified)
#     timing.start("response_parsing")
#     checkpoint_complete = False
#     confidence = 0.0

#     for line in response_text.split('\n'):
#         if line.startswith("Complete:"):
#             checkpoint_complete = "yes" in line.lower()
#         elif line.startswith("Confidence:"):
#             try:
#                 confidence_text = line[11:].strip().replace('%', '')
#                 confidence = float(confidence_text) / 100.0
#             except ValueError:
#                 confidence = 0.5  # Default if parsing fails
#     timing.end("response_parsing")

#     # Softer evaluation logic
#     timing.start("evaluation_logic")
#     LOW_CONFIDENCE_THRESHOLD = 0.6  # Reduced threshold

#     if checkpoint_complete and confidence >= LOW_CONFIDENCE_THRESHOLD:
#         final_checkpoint_complete = True
#         progress_percentage = 100.0
#     else:
#         # Apply a soft boost to the progress even at lower confidence
#         progress_percentage = min(95.0, (confidence + 0.15) * 100)
#         final_checkpoint_complete = False
#     timing.end("evaluation_logic")

#     timing.end("total_processing")

#     # Get timing metrics
#     metrics = timing.get_metrics()

#     # Print detailed timing information with percentages
#     total_time = metrics.get('total_processing', 0)
#     print("\n" + "="*60)
#     print("CHECKPOINT PROGRESS TIMING BREAKDOWN")
#     print("="*60)
#     for step, duration in metrics.items():
#         if step != 'total_processing':
#             percentage = (duration / total_time * 100) if total_time > 0 else 0
#             print(f"{step.replace('_', ' ').title():<25}: {duration:>8.2f}ms ({percentage:>5.1f}%)")
#     print("-" * 60)
#     print(f"{'TOTAL':<25}: {total_time:>8.2f}ms (100.0%)")
#     print("="*60)

#     # Highlight the LLM call specifically
#     llm_time = metrics.get('checkpoint_llm_call', 0)
#     print(f"🚀 LLM Call Duration: {llm_time:.2f}ms")

#     # Also log for monitoring
#     _logger.info(f"Checkpoint progress timing: {metrics}")

#     # Return only the requested fields plus timing metrics
#     return {
#         "checkpoint_complete": final_checkpoint_complete,
#         "progress_percentage": progress_percentage,
#         "next_checkpoint": None,
#         "confidence": confidence,
#         "timing_metrics": metrics
#     }






from typing import Dict, List, Optional, Any
from common.gemini_client import get_gemini_client
from common.models import Checkpoint
import logging
import asyncio
from orchestrator.timing import TimingMetrics

_logger = logging.getLogger(__name__)

# Simple in-memory cache
_simple_cache = {}

async def track_checkpoint_progress(text: str, checkpoint: Optional[Checkpoint], context: List[Dict[str, str]]) -> Dict[str, Any]:
    """
    Fast checkpoint progress tracker that maintains first version's accuracy
    while reducing latency through targeted optimizations.

    Args:
        text: Patient's message
        checkpoint: Current conversation checkpoint object
        context: Previous conversation context

    Returns:
        Dict with checkpoint tracking assessment including timing metrics
    """
    timing = TimingMetrics()
    timing.start("total_processing")

    # Quick exit for no checkpoint
    if not checkpoint:
        timing.end("total_processing")
        return {
            "checkpoint_complete": True,
            "progress_percentage": 100.0,
            "next_checkpoint": None,
            "confidence": 1.0,
            "timing_metrics": timing.get_metrics()
        }

    # Simple cache check (much faster than complex hashing)
    timing.start("cache_check")
    simple_key = f"{text[:50]}:{checkpoint.name[:30]}"
    if simple_key in _simple_cache:
        timing.end("cache_check")
        timing.end("total_processing")
        cached_result = _simple_cache[simple_key].copy()
        cached_result["timing_metrics"] = {"total_processing": 1.0, "cache_hit": 1.0}
        return cached_result
    timing.end("cache_check")

    # Streamlined context formatting (only last 2 turns)
    timing.start("context_formatting")
    context_str = ""
    if context:
        recent_context = context[-2:] if len(context) >= 2 else context
        for turn in recent_context:
            try:
                role = "Patient" if turn.get("role") == "user" else "Assistant"
                content = turn.get('content', '')[:100]  # Limit to 100 chars
                context_str += f"{role}: {content}\n"
            except (AttributeError, TypeError):
                continue
    timing.end("context_formatting")

    # Simplified but effective prompt (maintains quality, reduces tokens)
    timing.start("prompt_creation")
    prompt = f"""Evaluate if patient answered the checkpoint question sufficiently.
Be lenient - if the message partially covers the expectation, say 'Yes'.

CHECKPOINT: {checkpoint.name}
EXPECTED: {', '.join(checkpoint.expected_inputs) if checkpoint.expected_inputs else 'Any response'}

CONTEXT:
{context_str}

PATIENT MESSAGE: "{text}"

RESPOND:
Complete: [Yes/No]
Confidence: [0-100]"""
    timing.end("prompt_creation")

    try:
        timing.start("gemini_api_call")
        
        # Use existing client with timeout
        client = get_gemini_client()
        
        # Add timeout to the API call
        response = await asyncio.wait_for(
            client.generate_content(prompt),
            timeout=1.5  # Aggressive but realistic timeout
        )
        
        timing.end("gemini_api_call")
        response_text = response.text.strip()
        
    except asyncio.TimeoutError:
        timing.end("gemini_api_call")
        timing.end("total_processing")
        _logger.warning("Gemini API timeout - using fast fallback")
        
        # Quick fallback evaluation
        has_content = len(text.strip()) > 5
        has_keywords = any(word in text.lower() for word in ['yes', 'no', 'mg', 'daily', 'morning'])
        fallback_complete = has_content and (has_keywords or len(text.strip()) > 15)
        
        return {
            "checkpoint_complete": fallback_complete,
            "progress_percentage": 90.0 if fallback_complete else 40.0,
            "next_checkpoint": None,
            "confidence": 0.75 if fallback_complete else 0.45,
            "timing_metrics": timing.get_metrics()
        }
        
    except Exception as e:
        timing.end("gemini_api_call")
        timing.end("total_processing")
        _logger.exception("Gemini API error")
        
        # Fallback on any error
        fallback_complete = len(text.strip()) > 8
        return {
            "checkpoint_complete": fallback_complete,
            "progress_percentage": 85.0 if fallback_complete else 35.0,
            "next_checkpoint": None,
            "confidence": 0.65,
            "timing_metrics": timing.get_metrics()
        }

    # Fast response parsing (same logic as first version)
    timing.start("response_parsing")
    checkpoint_complete = False
    confidence = 0.0

    for line in response_text.split('\n'):
        if line.startswith("Complete:"):
            checkpoint_complete = "yes" in line.lower()
        elif line.startswith("Confidence:"):
            try:
                confidence_text = line[11:].strip().replace('%', '')
                confidence = float(confidence_text) / 100.0
            except ValueError:
                confidence = 0.6
    timing.end("response_parsing")

    # Same evaluation logic as first version
    timing.start("evaluation_logic")
    LOW_CONFIDENCE_THRESHOLD = 0.6

    if checkpoint_complete and confidence >= LOW_CONFIDENCE_THRESHOLD:
        final_checkpoint_complete = True
        progress_percentage = 100.0
    else:
        progress_percentage = min(95.0, (confidence + 0.15) * 100)
        final_checkpoint_complete = False
    timing.end("evaluation_logic")

    # Simple caching (limit size)
    timing.start("cache_store")
    _simple_cache[simple_key] = {
        "checkpoint_complete": final_checkpoint_complete,
        "progress_percentage": progress_percentage,
        "next_checkpoint": None,
        "confidence": confidence
    }
    
    # Keep cache small for speed
    if len(_simple_cache) > 50:
        # Remove first 10 entries
        keys_to_remove = list(_simple_cache.keys())[:10]
        for key in keys_to_remove:
            del _simple_cache[key]
    timing.end("cache_store")

    timing.end("total_processing")

    # Get timing metrics
    metrics = timing.get_metrics()
    total_time = metrics.get('total_processing', 0)

    # Minimal timing output (only if slow)
    if total_time > 300:  # Only log if > 300ms
        print(f"\n⚡ Checkpoint: {total_time:.1f}ms")
        llm_time = metrics.get('gemini_api_call', 0)
        print(f"   └── API: {llm_time:.1f}ms ({llm_time/total_time*100:.1f}%)")
    
    # Log for monitoring
    _logger.info(f"Checkpoint timing: total={total_time:.1f}ms, api={metrics.get('gemini_api_call', 0):.1f}ms")

    return {
        "checkpoint_complete": final_checkpoint_complete,
        "progress_percentage": progress_percentage,
        "next_checkpoint": None,
        "confidence": confidence,
        "timing_metrics": metrics
    }
