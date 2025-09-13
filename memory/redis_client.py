from redis.asyncio import Redis
from redis.exceptions import RedisError
from typing import Dict, List, Optional, Any, Literal
import json
import logging
import asyncio
from datetime import datetime

# Import new types from models
from common.models import AgentResponseStatus, CheckpointType, CheckpointStatus

import json

class DateTimeEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()  # Convert datetime to ISO format string
        return super().default(obj)

class RedisMemory:
    def __init__(self, redis_url: str = "redis://localhost:6379"):
        logging.debug("🔵 Initializing Redis client...")
        # Parse Redis URL to extract components
        from urllib.parse import urlparse
        parsed = urlparse(redis_url)
        
        # Use low socket timeouts so failing Redis doesn't block API
        self.redis = Redis(
            host=parsed.hostname or '127.0.0.1',
            port=parsed.port or 6379,
            db=0,
            socket_connect_timeout=1,  # seconds
            socket_timeout=2
        )

    async def check_connection(self):
        try:
            if await self.redis.ping():
                logging.info("✅ Redis connected successfully")
                return True
        except RedisError as e:
            logging.critical(f"❌ Redis connection failed: {str(e)}")
            raise

    async def set_conversation_state(self, conversation_id: str, state: Dict[str, Any]) -> None:
        try:
            key = f"conversation:{conversation_id}:state"
            for k, v in state.items():
                if asyncio.iscoroutine(v):
                    state[k] = await v

        # Use the custom encoder
            await self.redis.set(key, json.dumps(state, cls=DateTimeEncoder), ex=600)
            logging.info(f"✅ Saved conversation state in Redis for ID: {conversation_id}")
        except Exception as e:
            logging.error(f"❌ Error setting conversation state: {str(e)}")
            raise

    async def get_conversation_state(self, conversation_id: str) -> Optional[Dict[str, Any]]:
        try:
            key = f"conversation:{conversation_id}:state"
            data = await self.redis.get(key)
            if data:
                logging.info(f"✅ Retrieved conversation state from Redis for ID: {conversation_id}")
                return json.loads(data)
            return None
        except Exception as e:
            logging.error(f"❌ Error getting conversation state redis: {str(e)}")
            raise

    async def set_conversation_context(self, conversation_id: str, context: List[Dict[str, str]]) -> None:
        try:
            key = f"conversation:{conversation_id}:context"
            await self.redis.set(key, json.dumps(context), ex=3600)
            logging.info(f"✅ Saved conversation context in Redis for ID: {conversation_id}")
        except Exception as e:
            logging.error(f"❌ Error setting conversation context: {str(e)}")
            raise


    async def update_patient_verification_status(self, conversation_id: str, verified_status: bool):
        """
        Update patient verification status in Redis
        """
        try:
            key = f"conversation:{conversation_id}:patient_verified"
            await self.redis.set(key, json.dumps(verified_status), ex=3600)
            logging.info(f"✅ Updated patient verification status in Redis for ID: {conversation_id}")
        except Exception as e:
            logging.error(f"❌ Error updating patient verification status in Redis: {str(e)}")
            raise

    async def get_conversation_context(self, conversation_id: str) -> Optional[List[Dict[str, str]]]:
        try:
            key = f"conversation:{conversation_id}:context"
            data = await self.redis.get(key)
            if data:
                logging.info(f"✅ Retrieved conversation context from Redis for ID: {conversation_id}")
                return json.loads(data)
            return None
        except Exception as e:
            logging.error(f"❌ Error getting conversation context: {str(e)}")
            raise

    # Updated to use new AgentResult model format
    async def set_agent_result(self, conversation_id: str, agent_name: str,
                              status: AgentResponseStatus,
                              result_payload: Dict[str, Any],
                              message_to_user: Optional[str] = None,
                              action_required: bool = False) -> None:
        """Store agent result in Redis using the new AgentResult model format"""
        try:
            # Create the agent result using the new model structure
            result = {
                "agent_name": agent_name,
                "status": status,
                "result_payload": result_payload,
                "message_to_user": message_to_user,
                "action_required": action_required,
                "timestamp": datetime.now().isoformat(),
                "consumed": False
            }

            # First get existing conversation state if any
            state = await self.get_conversation_state(conversation_id) or {}

            # Initialize sync_agent_results if not present (using new field name)
            if 'sync_agent_results' not in state:
                state['sync_agent_results'] = {}

            # Add the new agent result
            state['sync_agent_results'][agent_name] = result

            # Update the conversation state with new agent results
            await self.set_conversation_state(conversation_id, state)

            # Also store agent result separately for quicker access
            key = f"conversation:{conversation_id}:agent:{agent_name}"
            await self.redis.set(key, json.dumps(result), ex=3600)

            logging.info(f"✅ Saved agent result in Redis for ID: {conversation_id}, agent: {agent_name}")
        except Exception as e:
            logging.error(f"❌ Error setting agent result: {str(e)}")
            raise


    async def set_sync_agent_result(self, conversation_id: str, agent_name: str,
                              status: AgentResponseStatus,
                              result_payload: Dict[str, Any],
                              message_to_user: Optional[str] = None,
                              action_required: bool = False) -> None:
        try:
        # Create the agent result using the new model structure
            result = {
            "agent_name": agent_name,
            "status": status,
            "result_payload": result_payload,
            "message_to_user": message_to_user,
            "action_required": action_required,
            "timestamp": datetime.now().isoformat(),
            "consumed": False
        }

        # First get existing conversation state if any
            state = await self.get_conversation_state(conversation_id) or {}

        # Initialize sync_agent_results if not present (using new field name)
            if 'sync_agent_results' not in state:
                state['sync_agent_results'] = {}

        # Add the new agent result
            state['sync_agent_results'][agent_name] = result

        # Update the conversation state with new agent results
            await self.set_conversation_state(conversation_id, state)

        # Also store agent result separately for quicker access
            key = f"conversation:{conversation_id}:sync_agent:{agent_name}"
            await self.redis.set(key, json.dumps(result), ex=3600)

            logging.info(f"✅ Saved sync agent result in Redis for ID: {conversation_id}, agent: {agent_name}")
        except Exception as e:
            logging.error(f"❌ Error setting sync agent result: {str(e)}")
            raise

    async def get_agent_result(self, conversation_id: str, agent_name: str) -> Optional[Dict[str, Any]]:
        """Get stored agent result from Redis"""
        try:
            key = f"conversation:{conversation_id}:agent:{agent_name}"
            data = await self.redis.get(key)
            if data:
                logging.info(f"✅ Retrieved agent result from Redis for ID: {conversation_id}, agent: {agent_name}")
                return json.loads(data)
            return None
        except Exception as e:
            logging.error(f"❌ Error getting agent result: {str(e)}")
            raise

    # New methods for Task and Checkpoint management
    async def set_task(self, conversation_id: str, task_id: str, task_data: Dict[str, Any]) -> None:
        """Store a task in Redis"""
        try:
            key = f"conversation:{conversation_id}:task:{task_id}"
            await self.redis.set(key, json.dumps(task_data), ex=3600)
            logging.info(f"✅ Saved task in Redis for ID: {conversation_id}, task: {task_id}")
        except Exception as e:
            logging.error(f"❌ Error setting task: {str(e)}")
            raise

    async def get_task(self, conversation_id: str, task_id: str) -> Optional[Dict[str, Any]]:
        """Get a task from Redis"""
        try:
            key = f"conversation:{conversation_id}:task:{task_id}"
            data = await self.redis.get(key)
            if data:
                logging.info(f"✅ Retrieved task from Redis for ID: {conversation_id}, task: {task_id}")
                return json.loads(data)
            return None
        except Exception as e:
            logging.error(f"❌ Error getting task: {str(e)}")
            raise

    async def update_checkpoint_status(self, conversation_id: str, checkpoint_id: str,
                                      status: CheckpointStatus,
                                      collected_inputs: Optional[Dict[str, str]] = None) -> None:
        """Update a checkpoint's status and collected inputs"""
        try:
            # Get existing state
            state = await self.get_conversation_state(conversation_id) or {}

            # Initialize the nested structure if needed
            if 'task_stack' not in state:
                state['task_stack'] = []

            # Find and update the checkpoint across all tasks in the stack
            checkpoint_found = False
            for task in state.get('task_stack', []):
                for checkpoint in task.get('checklist', []):
                    if checkpoint.get('id') == checkpoint_id:
                        checkpoint['status'] = status
                        if collected_inputs:
                            if 'collected_inputs' not in checkpoint:
                                checkpoint['collected_inputs'] = {}
                            checkpoint['collected_inputs'].update(collected_inputs)

                        # Update timestamps based on status
                        if status == "in_progress" and not checkpoint.get('start_time'):
                            checkpoint['start_time'] = datetime.now().isoformat()
                        elif status == "complete" and not checkpoint.get('end_time'):
                            checkpoint['end_time'] = datetime.now().isoformat()

                        checkpoint_found = True
                        break
                if checkpoint_found:
                    break

            # Also update the flattened checkpoint_progress view
            if 'checkpoint_progress' not in state:
                state['checkpoint_progress'] = {}
            state['checkpoint_progress'][checkpoint_id] = (status == "complete")

            # Save updated state
            await self.set_conversation_state(conversation_id, state)
            logging.info(f"✅ Updated checkpoint status in Redis for ID: {conversation_id}, checkpoint: {checkpoint_id}")
        except Exception as e:
            logging.error(f"❌ Error updating checkpoint status: {str(e)}")
            raise

    async def set_task_stack(self, conversation_id: str, task_stack: List[Dict[str, Any]]) -> None:
        """Update the entire task stack for a conversation"""
        try:
            # Get existing state
            state = await self.get_conversation_state(conversation_id) or {}

            # Update task stack
            state['task_stack'] = task_stack

            # Also update the flattened checkpoint views
            checkpoints = []
            checkpoint_progress = {}
            type_of_checkpoints = []

            for task in task_stack:
                task_source = task.get('source', 'Main')
                for checkpoint in task.get('checklist', []):
                    checkpoint_id = checkpoint.get('id')
                    checkpoints.append(checkpoint_id)
                    checkpoint_progress[checkpoint_id] = (checkpoint.get('status') == "complete")
                    type_of_checkpoints.append(task_source)

            state['checkpoints'] = checkpoints
            state['checkpoint_progress'] = checkpoint_progress
            state['type_of_checkpoints'] = type_of_checkpoints

            # Save updated state
            await self.set_conversation_state(conversation_id, state)
            logging.info(f"✅ Updated task stack in Redis for conversation ID: {conversation_id}")
        except Exception as e:
            logging.error(f"❌ Error setting task stack: {str(e)}")
            raise

    async def set_complete_context(self, conversation_id: str, complete_context: List[Dict[str, str]]) -> None:
        """Store the complete conversation context in Redis"""
        try:
            key = f"conversation:{conversation_id}:complete_context"
            await self.redis.set(key, json.dumps(complete_context), ex=3600 * 24)  # Longer expiry for complete logs
            logging.info(f"✅ Saved complete conversation context in Redis for ID: {conversation_id}")
        except Exception as e:
            logging.error(f"❌ Error setting complete conversation context: {str(e)}")
            raise

    async def get_complete_context(self, conversation_id: str) -> Optional[List[Dict[str, str]]]:
        """Get the complete conversation context from Redis"""
        try:
            key = f"conversation:{conversation_id}:complete_context"
            data = await self.redis.get(key)
            if data:
                logging.info(f"✅ Retrieved complete conversation context from Redis for ID: {conversation_id}")
                return json.loads(data)
            return None
        except Exception as e:
            logging.error(f"❌ Error getting complete conversation context: {str(e)}")
            raise

    def _datetime_serializer(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        raise TypeError(f"Object of type {type(obj)} is not JSON serializable")
