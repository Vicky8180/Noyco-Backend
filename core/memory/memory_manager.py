"""
Memory Manager - Provides direct access to Redis and MongoDB
Eliminates HTTP overhead by using direct database connections
"""

import logging
from typing import Dict, List, Optional, Any
from datetime import datetime
import asyncio

if __name__ == "__main__" and __package__ is None:
    from memory.redis_client import RedisMemory
    from memory.mongo_client import MongoMemory
    from orchestrator.config import get_settings
else:
    from .redis_client import RedisMemory
    from .mongo_client import MongoMemory
    from ..orchestrator.config import get_settings

logger = logging.getLogger(__name__)


class MemoryManager:
    """
    Unified memory manager providing direct database access
    Replaces HTTP calls to the memory microservice
    """
    
    _instance = None
    _lock = asyncio.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(MemoryManager, cls).__new__(cls)
        return cls._instance
    
    def __init__(self):
        if not hasattr(self, 'initialized'):
            self.redis_memory: Optional[RedisMemory] = None
            self.mongo_memory: Optional[MongoMemory] = None
            self.settings = get_settings()
            self.initialized = False
    
    async def initialize(self):
        """Initialize database connections"""
        if self.initialized:
            return
            
        async with self._lock:
            if self.initialized:
                return
                
            try:
                # Initialize Redis
                self.redis_memory = RedisMemory(redis_url=self.settings.REDIS_URL)
                await self.redis_memory.check_connection()
                logger.info("✅ Redis memory initialized")
                
                # Initialize MongoDB
                self.mongo_memory = MongoMemory(
                    uri=self.settings.MONGODB_URI,
                    db_name=self.settings.DATABASE_NAME
                )
                await self.mongo_memory.initialize()
                logger.info("✅ MongoDB memory initialized")
                
                self.initialized = True
                logger.info("✅ Memory Manager fully initialized")
                
            except Exception as e:
                logger.error(f"❌ Failed to initialize Memory Manager: {e}")
                raise
    
    async def ensure_initialized(self):
        """Ensure the manager is initialized before use"""
        if not self.initialized:
            await self.initialize()
    
    # ============= Conversation State Operations =============
    
    async def get_conversation_state(self, conversation_id: str) -> Optional[Dict[str, Any]]:
        """Get conversation state with Redis cache fallback to MongoDB"""
        await self.ensure_initialized()
        
        try:
            # Try Redis first (fast cache)
            state = await self.redis_memory.get_conversation_state(conversation_id)
            if state:
                return state
            
            # Fallback to MongoDB (persistent storage)
            state = await self.mongo_memory.get_conversation_state(conversation_id)
            if state:
                # Cache in Redis for future requests
                await self.redis_memory.set_conversation_state(conversation_id, state)
            
            return state
            
        except Exception as e:
            logger.error(f"❌ Error getting conversation state: {e}")
            return None
    
    async def save_conversation_state(self, state: Dict[str, Any]) -> bool:
        """Save conversation state to both Redis and MongoDB"""
        await self.ensure_initialized()
        
        conversation_id = state.get("conversation_id")
        if not conversation_id:
            logger.error("❌ No conversation_id provided")
            return False
        
        try:
            # Save to both Redis (fast) and MongoDB (persistent) in parallel
            await asyncio.gather(
                self.redis_memory.set_conversation_state(conversation_id, state),
                self.mongo_memory.save_conversation_state(state),
                return_exceptions=True
            )
            
            logger.info(f"✅ Saved conversation state: {conversation_id}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error saving conversation state: {e}")
            return False
    
    # ============= Context Operations =============
    
    async def update_conversation_context(
        self, 
        conversation_id: str, 
        context: List[Dict[str, str]], 
        individual_id: Optional[str] = None
    ) -> bool:
        """Update conversation context"""
        await self.ensure_initialized()
        
        try:
            # Update in parallel
            await asyncio.gather(
                self.redis_memory.set_conversation_context(conversation_id, context),
                self.mongo_memory.update_conversation_context(conversation_id, context, individual_id),
                return_exceptions=True
            )
            
            logger.info(f"✅ Updated context for conversation: {conversation_id}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error updating context: {e}")
            return False
    
    async def get_semantic_context(
        self,
        conversation_id: str,
        query: str,
        plan: str = "pro"
    ) -> Optional[str]:
        """Get semantic context (currently returns None, can be extended with vector search)"""
        await self.ensure_initialized()
        
        # This is a placeholder - original memory service had semantic search
        # Can be extended with Pinecone or other vector DB integration
        logger.info(f"Semantic context requested for: {conversation_id}")
        return None
    
    # ============= Agent Results Operations =============
    
    async def save_agent_result(
        self,
        conversation_id: str,
        agent_name: str,
        result: Dict[str, Any]
    ) -> bool:
        """Save agent result"""
        await self.ensure_initialized()
        
        try:
            status = result.get("status", "success")
            result_payload = result.get("result_payload", {})
            message = result.get("message_to_user")
            action_required = result.get("action_required", False)
            
            # Save to both storage systems in parallel
            await asyncio.gather(
                self.redis_memory.set_agent_result(
                    conversation_id, agent_name, status, 
                    result_payload, message, action_required
                ),
                self.mongo_memory.save_agent_result(conversation_id, agent_name, result),
                return_exceptions=True
            )
            
            logger.info(f"✅ Saved agent result: {agent_name} for {conversation_id}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error saving agent result: {e}")
            return False
    
    async def save_sync_agent_result(
        self,
        conversation_id: str,
        agent_name: str,
        result: Dict[str, Any]
    ) -> bool:
        """Save synchronous agent result"""
        await self.ensure_initialized()
        
        try:
            status = result.get("status", "success")
            result_payload = result.get("result_payload", {})
            message = result.get("message_to_user")
            action_required = result.get("action_required", False)
            
            # Save to both storage systems in parallel
            await asyncio.gather(
                self.redis_memory.set_sync_agent_result(
                    conversation_id, agent_name, status,
                    result_payload, message, action_required
                ),
                self.mongo_memory.save_sync_agent_result(conversation_id, agent_name, result),
                return_exceptions=True
            )
            
            logger.info(f"✅ Saved sync agent result: {agent_name} for {conversation_id}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error saving sync agent result: {e}")
            return False
    
    # ============= Task Stack Operations =============
    
    async def update_task_stack(
        self,
        conversation_id: str,
        task_stack: List[Dict[str, Any]]
    ) -> bool:
        """Update task stack"""
        await self.ensure_initialized()
        
        try:
            # Update in both storage systems in parallel
            await asyncio.gather(
                self.redis_memory.set_task_stack(conversation_id, task_stack),
                self.mongo_memory.update_task_stack(conversation_id, task_stack),
                return_exceptions=True
            )
            
            logger.info(f"✅ Updated task stack for: {conversation_id}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error updating task stack: {e}")
            return False
    
    # ============= Individual/User Operations =============
    
    async def get_individual_conversations(self, individual_id: str) -> List[Dict[str, Any]]:
        """Get all conversations for an individual"""
        await self.ensure_initialized()
        
        try:
            conversations = await self.mongo_memory.get_individual_conversations(individual_id)
            return conversations
            
        except Exception as e:
            logger.error(f"❌ Error getting individual conversations: {e}")
            return []
    
    # ============= Health Check =============
    
    async def health_check(self) -> Dict[str, Any]:
        """Check health of memory components"""
        health = {
            "redis": "unknown",
            "mongodb": "unknown",
            "initialized": self.initialized
        }
        
        if not self.initialized:
            return health
        
        try:
            # Check Redis
            if self.redis_memory:
                redis_ok = await self.redis_memory.check_connection()
                health["redis"] = "healthy" if redis_ok else "unhealthy"
        except Exception as e:
            health["redis"] = f"unhealthy: {str(e)}"
        
        try:
            # Check MongoDB
            if self.mongo_memory:
                mongo_ok = await self.mongo_memory.check_connection()
                health["mongodb"] = "healthy" if mongo_ok else "unhealthy"
        except Exception as e:
            health["mongodb"] = f"unhealthy: {str(e)}"
        
        return health
    
    async def close(self):
        """Close all connections"""
        if self.redis_memory:
            await self.redis_memory.redis.close()
        if self.mongo_memory:
            self.mongo_memory.client.close()
        
        self.initialized = False
        logger.info("✅ Memory Manager closed")


# Global singleton instance
_memory_manager = None


def get_memory_manager() -> MemoryManager:
    """Get or create the global memory manager instance"""
    global _memory_manager
    if _memory_manager is None:
        _memory_manager = MemoryManager()
    return _memory_manager
