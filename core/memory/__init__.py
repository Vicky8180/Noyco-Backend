"""
Memory module integrated into core service
Provides direct access to Redis, MongoDB, and Pinecone without HTTP overhead
"""

from .redis_client import RedisMemory
from .mongo_client import MongoMemory
# from .pinecone_client import PineconeMemory
from .memory_manager import MemoryManager

__all__ = ['RedisMemory', 'MongoMemory', 'MemoryManager']
