# orchestrator/utils.py

"""
Utility functions for the orchestrator service.
Contains helper functions used throughout the orchestrator.
"""

import logging
from typing import Optional, Dict, List
import asyncio
from datetime import datetime
from orchestrator.state_manager import ConversationState
from orchestrator.timing import TimingMetrics
from orchestrator.services import call_service, CHECKPOINT_URL
from common.models import Conversation, Task, Checkpoint, CheckpointType, CheckpointStatus

_logger = logging.getLogger(__name__)

async def get_conversation_state(conversation_id: str, individual_id: Optional[str] = None) -> ConversationState:
    """
    Helper function to fetch or create a conversation state.

    Args:
        conversation_id: The conversation ID
        individual_id: The individual ID (optional)

    Returns:
        The conversation state object
    """
    return await ConversationState.get_or_create(conversation_id, individual_id)

async def generate_checkpoints(
    text: str,
    conversation_id: str,
    timing: TimingMetrics
) -> List[Checkpoint]:
    """
    Generate checkpoints for a new conversation.

    Args:
        text: The initial text
        conversation_id: The conversation ID
        timing: The timing metrics tracker

    Returns:
        List of generated checkpoints as Checkpoint objects
    """
    timing.start("checkpoint_generation")

    try:
        checkpoint_result = await call_service(
            CHECKPOINT_URL,
            {
                "text": text,
                "conversation_id": conversation_id
            },
            timing,
            "checkpoint_generator"
        )

        raw_checkpoints = checkpoint_result.get("checkpoints", [])
        _logger.info(f"Generated {len(raw_checkpoints)} checkpoints for new conversation")

        # Convert raw checkpoint strings to Checkpoint objects
        checkpoints = []
        for i, cp in enumerate(raw_checkpoints):
            checkpoint_id = f"cp{i+1}"
            checkpoints.append(
                Checkpoint(
                    id=checkpoint_id,
                    label=cp,
                    type=CheckpointType.Main,
                    status=CheckpointStatus.pending,
                    expected_inputs=[],
                    collected_inputs={},
                    start_time=None,
                    end_time=None
                )
            )

        return checkpoints
    finally:
        timing.end("checkpoint_generation")

def create_initial_task(checkpoints: List[Checkpoint], task_id: str = "main") -> Task:
    """
    Create the initial task from generated checkpoints.

    Args:
        checkpoints: List of checkpoint objects
        task_id: Optional task ID (defaults to "main")

    Returns:
        Task object with checkpoints
    """
    return Task(
        task_id=task_id,
        label="Main Conversation Flow",
        source=CheckpointType.Main,
        checklist=checkpoints,
        current_checkpoint_index=0,
        is_active=True,
        created_at=datetime.now(),
        updated_at=datetime.now()
    )

class ResponseState:
    """Helper class to track response state for background processing."""
    def __init__(self):
        self.enriched_response = None
        self.specialists_called = False
        self.requires_human = False
