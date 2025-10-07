import logging
import datetime
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError
from typing import Dict, List, Optional, Any
from datetime import datetime
class MongoMemory:
    def __init__(self, uri: str = None, db_name: str = None):
        # Import from core orchestrator config instead
        if __name__ == "__main__" and __package__ is None:
            from orchestrator.config import get_settings
        else:
            from ..orchestrator.config import get_settings
        settings = get_settings()
        self.uri = uri or settings.MONGODB_URI
        self.db_name = db_name or settings.DATABASE_NAME
        self.client = None
        self.db = None
        self.collection = None
        self.conversations = None
        # Removed patient-specific collections as part of decoupling
        self.summaries = None
        self.agent_results = None
        self.tasks = None  # New collection for tasks
        self.initialized = False

    async def initialize(self):
        """Initialize MongoDB connection"""
        try:
            self.client = MongoClient(self.uri)
            # Try to connect to trigger errors early
            self.client.admin.command('ping')
            self.db = self.client[self.db_name]
            self.collection = self.db["conversations"]
            # Initialize collections for new functionalities
            self.conversations = self.db["conversations"]
            # Removed patient-specific collections as part of decoupling
            self.summaries = self.db["summaries"]
            self.agent_results = self.db["agent_results"]
            self.tasks = self.db["tasks"]  # Initialize collection for tasks
            self.initialized = True
            logging.info("✅ Successfully connected to MongoDB")
        except ConnectionFailure as e:
            logging.error(f"❌ Failed to connect to MongoDB: {str(e)}")
            raise

    async def check_connection(self):
        """Check MongoDB connection"""
        try:
            if not hasattr(self, 'initialized') or not self.initialized:
                await self.initialize()

            # The ismaster command is cheap and does not require auth
            self.client.admin.command('ismaster')
            logging.info("✅ MongoDB connected successfully")
            return True
        except (ConnectionFailure, ServerSelectionTimeoutError) as e:
            logging.critical(f"❌ MongoDB connection failed: {str(e)}")
            raise
        except Exception as e:
            logging.critical(f"❌ MongoDB connection error: {str(e)}")
            raise

    async def save_agent_result(self, conversation_id: str, agent_name: str, result: Dict[str, Any]) -> None:
        """Save agent result to MongoDB"""
        try:
            # Create filter for upsert
            filter_query = {
                "conversation_id": conversation_id,
                "agent_name": agent_name
            }

            # Document to save or update
            document = {
                "conversation_id": conversation_id,
                "agent_name": agent_name,
                "result": result,
                "timestamp": datetime.datetime.utcnow()  # Use Python's datetime instead of server time
            }

            # Insert or update agent result
            self.agent_results.update_one(
                filter_query,
                {"$set": document},
                upsert=True
            )

            # Update the main conversation document
            # Handle both async and sync agent results based on consumed flag
            if result.get("consumed", False):
                self.conversations.update_one(
                    {"conversation_id": conversation_id},
                    {"$set": {f"sync_agent_results.{agent_name}": result}},
                    upsert=True
                )
            else:
                self.conversations.update_one(
                    {"conversation_id": conversation_id},
                    {"$set": {f"async_agent_results.{agent_name}": result}},
                    upsert=True
                )

            logging.info(f"✅ Saved agent result in MongoDB for conversation {conversation_id}, agent {agent_name}")
        except Exception as e:
            logging.error(f"❌ Error saving agent result to MongoDB: {e}")
            # Don't raise exception to prevent orchestration failures


    async def update_task_stack(self, conversation_id: str, task_stack: List[Dict[str, Any]]) -> None:
        """
    Update just the task_stack for a conversation in MongoDB.

    Args:
        conversation_id: The conversation ID
        task_stack: The updated task stack
    """
        try:
            result =  self.conversations.update_one(
            {"conversation_id": conversation_id},
            {"$set": {
                "task_stack": task_stack,
                "updated_at": datetime.now()
            }}
        )

            if result.matched_count == 0:
                logging.warning(f"No conversation found with ID {conversation_id} to update task stack")
            else:
                logging.info(f"Updated task stack for conversation {conversation_id}")

        except Exception as e:
            logging.error(f"Failed to update task stack in MongoDB: {e}")
            raise

    async def save_sync_agent_result(self, conversation_id: str, agent_name: str, result: Dict[str, Any]) -> None:
        try:
            existing_conversation = self.conversations.find_one(
            {"conversation_id": conversation_id}
        )

            if existing_conversation and "sync_agent_results" in existing_conversation and agent_name in existing_conversation["sync_agent_results"]:
            # If the agent already exists in sync_agent_results, update only that field
                self.conversations.update_one(
                {"conversation_id": conversation_id},
                {"$set": {f"sync_agent_results.{agent_name}": result}}
            )
            else:
            # If the agent doesn't exist, add it to sync_agent_results without updating other fields
                self.conversations.update_one(
                {"conversation_id": conversation_id},
                {"$set": {f"sync_agent_results.{agent_name}": result}},
                upsert=True
            )


            logging.info(f"✅ Updated sync agent result in MongoDB for conversation {conversation_id}, agent {agent_name}")
        except Exception as e:
            logging.error(f"❌ Error updating sync agent result in MongoDB: {e}")
        # Don't raise exception to prevent orchestration failures
    async def get_agent_result(self, conversation_id: str, agent_name: str) -> Optional[Dict[str, Any]]:
        """Get agent result from MongoDB"""
        try:
            result = self.agent_results.find_one({
                "conversation_id": conversation_id,
                "agent_name": agent_name
            })

            if result:
                # Remove MongoDB _id field
                result.pop("_id", None)
                return result

            return None
        except Exception as e:
            logging.error(f"❌ Error getting agent result from MongoDB: {e}")
            return None

    async def save_conversation_state(self, state: Dict[str, Any]) -> None:
        """Save conversation state to MongoDB"""
        try:
            # Create filter for upsert
            conversation_filter = {"conversation_id": state["conversation_id"]}


            # Update or insert - synchronous operation, no await
            self.conversations.update_one(
                conversation_filter,
                {"$set": state},
                upsert=True
            )

            # Save tasks separately (if any)
            if "task_stack" in state and state["task_stack"]:
                for task in state["task_stack"]:
                    task_doc = {
                        "conversation_id": state["conversation_id"],
                        **task
                    }
                    self.tasks.update_one(
                        {"task_id": task["task_id"]},
                        {"$set": task_doc},
                        upsert=True
                    )

                    # Save checkpoints for this task
                    if "checklist" in task and task["checklist"]:
                        for checkpoint in task["checklist"]:
                            checkpoint_doc = {
                                "conversation_id": state["conversation_id"],
                                "task_id": task["task_id"],
                                **checkpoint
                            }


            logging.info(f"✅ Saved conversation state for {state['conversation_id']}")
        except Exception as e:
            logging.error(f"❌ Error saving conversation state: {e}")

    async def get_conversation_state(self, conversation_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve conversation state from MongoDB"""
        if self.conversations is None:
            logging.error("MongoDB conversations collection is None")
            return None

        try:
            if not conversation_id:
                logging.error("Invalid conversation ID")
                return None

            # Ensure we have a proper string for the query
            conversation_id_str = str(conversation_id)
            logging.debug(f"Retrieving conversation: {conversation_id_str}")

            # No await - PyMongo is synchronous
            conversation = self.conversations.find_one({"conversation_id": conversation_id_str})

            if conversation is not None:
                conversation_dict = dict(conversation)
                conversation_dict.pop("_id", None)
                return conversation_dict

            return None
        except Exception as e:
            logging.error(f"Error retrieving conversation {conversation_id}: {e}")
            return None

    async def update_conversation_context(self, conversation_id: str, context: List[Dict[str, str]], individual_id: Optional[str] = None) -> None:
        """Update conversation context in MongoDB"""
        try:
            # Update conversation context - PyMongo is synchronous
            self.conversations.update_one(
                {"conversation_id": conversation_id},
                {
                    "$set": {
                        "context": context,
                        "complete_context": context  # Also update complete_context
                    }
                },
                upsert=True
            )

            logging.info(f"✅ Updated conversation context for {conversation_id}")
        except Exception as e:
            logging.error(f"❌ Error updating conversation context: {e}")

    async def get_individual_conversations(self, individual_id: str) -> List[Dict[str, Any]]:
        """Get all conversations for an individual"""
        try:
            # Find conversations by individual_id directly
            conversations = []

            # Get conversations matching the individual_id
            for conversation in self.conversations.find({"individual_id": individual_id}):
                # Remove MongoDB _id field
                conversation.pop("_id", None)
                conversations.append(conversation)

            return conversations
        except Exception as e:
            logging.error(f"❌ Error getting patient conversations: {e}")
            return []


    async def update_patient_verification_status(self, conversation_id: str, verified_status: bool):
        """
        Update patient verification status in MongoDB
        """
        try:
            print(verified_status, conversation_id, "in monogo")
            # Update conversation with patient verification status - PyMongo is synchronous
            self.conversations.update_one(
                {"conversation_id": conversation_id},
                {
                    "$set": {
                        "patient_verified": verified_status,
                        "updated_at": datetime.utcnow()
                    }
                },
                upsert=True
            )
            logging.info(f"✅ Updated patient verification status for {conversation_id}")
        except Exception as e:
            logging.error(f"❌ Error updating patient verification status: {e}")
            raise




    async def find_one_and_update_conversation_state(self, conversation_id: str):
        """Find conversation and return it (no unset operation anymore)"""
        try:
            # PyMongo is synchronous, so don't use await
            result = self.conversations.find_one(
                {"conversation_id": conversation_id}
            )

            if result:
                # Convert _id to string for JSON serialization
                if "_id" in result:
                    result["_id"] = str(result["_id"])
                return result
            return None
        except Exception as e:
            logging.exception(f"Error in find_one_and_update_conversation_state: {e}")
            raise

    async def save_conversation_summary(self, summary: Dict[str, Any]) -> None:
        """Save conversation summary to MongoDB"""
        try:
            # Create filter for upsert
            summary_filter = {"conversation_id": summary["conversation_id"]}

            # Update or insert - no await
            self.summaries.update_one(
                summary_filter,
                {"$set": summary},
                upsert=True
            )

            # Update conversation document with summary fields
            summary_update = {
                "has_summary": True
            }

            # Add optional summary fields if present
            if "summary" in summary:
                summary_update["summary"] = summary["summary"]
            if "key_points" in summary:
                summary_update["key_points"] = summary["key_points"]
            if "tags" in summary:
                summary_update["tags"] = summary["tags"]

            self.conversations.update_one(
                {"conversation_id": summary["conversation_id"]},
                {"$set": summary_update}
            )
            logging.info(f"✅ Saved conversation summary for {summary['conversation_id']}")
        except Exception as e:
            logging.error(f"❌ Error saving conversation summary: {e}")

    async def update_task(self, conversation_id: str, task_id: str, task_data: Dict[str, Any]) -> None:
        """Update a specific task in a conversation"""
        try:
            # Update the task
            self.tasks.update_one(
                {"task_id": task_id, "conversation_id": conversation_id},
                {"$set": task_data},
                upsert=True
            )

            # Also update the task in the conversation's task_stack
            self.conversations.update_one(
                {"conversation_id": conversation_id, "task_stack.task_id": task_id},
                {"$set": {"task_stack.$": task_data}}
            )

            logging.info(f"✅ Updated task {task_id} in conversation {conversation_id}")
        except Exception as e:
            logging.error(f"❌ Error updating task: {e}")

    async def update_checkpoint(self, conversation_id: str, checkpoint_id: str, checkpoint_data: Dict[str, Any]) -> None:
        """Update a specific checkpoint status"""
        try:
            # Update the checkpoint
            self.checkpoints.update_one(
                {"id": checkpoint_id, "conversation_id": conversation_id},
                {"$set": checkpoint_data},
                upsert=True
            )

            # Find which task contains this checkpoint
            task = self.tasks.find_one({
                "conversation_id": conversation_id,
                "checklist.id": checkpoint_id
            })

            if task:
                # Update the checkpoint in the task's checklist
                self.tasks.update_one(
                    {"task_id": task["task_id"], "checklist.id": checkpoint_id},
                    {"$set": {"checklist.$": checkpoint_data}}
                )

                # Also update the checkpoint_progress in the conversation
                self.conversations.update_one(
                    {"conversation_id": conversation_id},
                    {"$set": {f"checkpoint_progress.{checkpoint_id}": checkpoint_data.get("status") == "complete"}}
                )

            logging.info(f"✅ Updated checkpoint {checkpoint_id} in conversation {conversation_id}")
        except Exception as e:
            logging.error(f"❌ Error updating checkpoint: {e}")
