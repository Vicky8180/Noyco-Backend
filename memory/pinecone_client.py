# memory/pinecone_client.py

import logging
import asyncio
from typing import List, Dict, Any, Optional
from pinecone import Pinecone
from datetime import datetime
import hashlib
from sentence_transformers import SentenceTransformer

# Global embedding cache with TTL
_embedding_cache = {}
_cache_timestamps = {}
_cache_max_size = 500
_cache_ttl = 3600  # 1 hour

class PineconeMemory:
    def __init__(self, api_key: Optional[str] = None, environment: str = "us-west1-gcp"):
        self.api_key = api_key
        self.environment = environment
        self.pc = None
        self.index = None
        self.embedding_model = None
        self.initialized = False
        self._connection_pool = None

    async def check_connection(self):
        """Fast connection check with retry logic"""
        max_retries = 2
        for attempt in range(max_retries):
            try:
                if not self.initialized:
                    await self.initialize()

                # Quick ping test
                stats = await asyncio.get_event_loop().run_in_executor(
                    None, self.index.describe_index_stats
                )
                logging.info(f"✅ Pinecone connected. Vectors: {stats.get('total_vector_count', 0)}")
                return True

            except Exception as e:
                if attempt == max_retries - 1:
                    logging.error(f"❌ Pinecone connection failed after {max_retries} attempts: {str(e)}")
                    raise
                await asyncio.sleep(0.5)  # Brief retry delay

    async def initialize(self):
        """Initialize with better error handling and faster embedding model"""
        try:
            # Skip initialization if no API key is provided
            if not self.api_key:
                logging.warning("⚠️ Pinecone API key not provided, skipping initialization")
                return
            
            # Initialize Pinecone client with configured API key
            self.pc = Pinecone(
                api_key=self.api_key
            )

            # Check if index exists
            indexes = await asyncio.get_event_loop().run_in_executor(
                None, lambda: self.pc.list_indexes().names()
            )

            if "medical-conversations" not in indexes:
                await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: self.pc.create_index(
                        name="medical-conversations",
                        dimension=768,  # Match your existing index dimension
                        metric="cosine"
                    )
                )
                await asyncio.sleep(2)  # Wait for index creation

            self.index = self.pc.Index("medical-conversations")

            # Load embedding model that produces 768 dimensions
            self.embedding_model = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: SentenceTransformer('all-mpnet-base-v2')  # Produces 768 dimensions
            )

            self.initialized = True
            logging.info("✅ Pinecone initialized with optimized embedding model")

        except Exception as e:
            logging.error(f"❌ Pinecone initialization failed: {str(e)}")
            raise

    async def _get_embedding_fast(self, text: str) -> List[float]:
        """Ultra-fast embedding generation with caching"""
        # Create cache key
        cache_key = hashlib.md5(text.encode()).hexdigest()
        current_time = datetime.now().timestamp()

        # Check cache with TTL
        if (cache_key in _embedding_cache and
            cache_key in _cache_timestamps and
            current_time - _cache_timestamps[cache_key] < _cache_ttl):
            return _embedding_cache[cache_key]

        try:
            # Generate embedding using efficient model
            embedding = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self.embedding_model.encode([text[:512]])[0].tolist()  # Produces 768 dimensions
            )

            # Update cache with size management
            if len(_embedding_cache) >= _cache_max_size:
                # Remove oldest entries
                oldest_keys = sorted(_cache_timestamps.keys(),
                                   key=lambda k: _cache_timestamps[k])[:50]
                for old_key in oldest_keys:
                    _embedding_cache.pop(old_key, None)
                    _cache_timestamps.pop(old_key, None)

            _embedding_cache[cache_key] = embedding
            _cache_timestamps[cache_key] = current_time

            return embedding

        except Exception as e:
            logging.error(f"Embedding generation error: {str(e)}")
            # Return zero vector as fallback
            return [0.0] * 768

    async def store_message(self, conversation_id: str, role: str, content: str,
                           checkpoint_id: Optional[str] = None,
                           task_id: Optional[str] = None) -> None:
        """Optimized message storage with batch processing"""
        if not self.initialized:
            await self.initialize()

        try:
            # Quick content validation
            if not content or not content.strip():
                return

            embedding = await self._get_embedding_fast(content)
            message_id = f"{conversation_id}:{role}:{datetime.now().timestamp()}"

            metadata = {
                "conversation_id": conversation_id,
                "individual_id": conversation_id,
                "role": role,
                "content": content[:800],  # Reduced metadata size
                "type": "message",
                "timestamp": datetime.now().isoformat()
            }

            if checkpoint_id:
                metadata["checkpoint_id"] = checkpoint_id
            if task_id:
                metadata["task_id"] = task_id

            # Async upsert
            await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self.index.upsert(vectors=[(message_id, embedding, metadata)])
            )

        except Exception as e:
            logging.error(f"Store message error: {str(e)}")
            # Don't raise - allow conversation to continue

    async def search_optimized(self, individual_id: str, query: str, limit: int = 30,
                              filters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """Ultra-fast optimized search"""
        if not self.initialized:
            await self.initialize()

        try:
            # Fast embedding generation
            query_embedding = await self._get_embedding_fast(query)

            # Minimal filter for speed
            search_filter = {"individual_id": individual_id, "type": "message"}
            if filters:
                search_filter.update(filters)

            # Async search with timeout
            search_task = asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self.index.query(
                    vector=query_embedding,
                    top_k=min(limit, 50),  # Cap limit for performance
                    include_metadata=True,
                    filter=search_filter,
                    include_values=False
                )
            )

            # 5 second timeout for search
            search_results = await asyncio.wait_for(search_task, timeout=5.0)

            # Fast result processing
            results = []
            for match in search_results.matches:
                metadata = match.metadata
                if metadata and metadata.get("role") and metadata.get("content"):
                    results.append({
                        "role": metadata["role"],
                        "content": metadata["content"],
                        "score": match.score,
                        "timestamp": metadata.get("timestamp", "")
                    })

            # Sort by timestamp for conversation flow
            results.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
            return results

        except asyncio.TimeoutError:
            logging.warning(f"Search timeout for individual: {individual_id}")
            return []
        except Exception as e:
            logging.error(f"Search error: {str(e)}")
            return []

    async def search_with_context_awareness(self, individual_id: str, query: str,
                                          current_conversation_id: str, limit: int = 30) -> List[Dict[str, Any]]:
        """Fast context-aware search with fallback"""
        try:
            # Try optimized search first
            results = await self.search_optimized(
                individual_id=individual_id,
                query=query,
                limit=limit,
                filters={"conversation_id": current_conversation_id}
            )

            # If insufficient results, expand search
            if len(results) < limit // 2:
                additional_results = await self.search_optimized(
                    individual_id=individual_id,
                    query=query,
                    limit=limit - len(results)
                )

                # Merge and deduplicate
                seen_content = {r["content"][:100] for r in results}
                for result in additional_results:
                    if result["content"][:100] not in seen_content:
                        results.append(result)
                        if len(results) >= limit:
                            break

            return results[:limit]

        except Exception as e:
            logging.error(f"Context-aware search error: {str(e)}")
            return []

    async def store_messages_batch(self, messages: List[Dict[str, Any]]) -> None:
        """Efficient batch storage"""
        if not self.initialized or not messages:
            return

        try:
            vectors_to_upsert = []

            # Process messages in chunks to avoid memory issues
            chunk_size = 10
            for i in range(0, len(messages), chunk_size):
                chunk = messages[i:i + chunk_size]

                for msg_data in chunk:
                    conversation_id = msg_data["conversation_id"]
                    role = msg_data["role"]
                    content = msg_data["content"]

                    if not content or not content.strip():
                        continue

                    embedding = await self._get_embedding_fast(content)
                    message_id = f"{conversation_id}:{role}:{i}:{datetime.now().timestamp()}"

                    metadata = {
                        "conversation_id": conversation_id,
                        "individual_id": conversation_id,
                        "role": role,
                        "content": content[:800],
                        "type": "message",
                        "timestamp": datetime.now().isoformat()
                    }

                    vectors_to_upsert.append((message_id, embedding, metadata))

                # Batch upsert for each chunk
                if vectors_to_upsert:
                    await asyncio.get_event_loop().run_in_executor(
                        None,
                        lambda: self.index.upsert(vectors=vectors_to_upsert)
                    )
                    vectors_to_upsert = []

            logging.info(f"✅ Batch stored {len(messages)} messages")

        except Exception as e:
            logging.error(f"Batch storage error: {str(e)}")

    # Fallback method for when Pinecone is unavailable
    async def search_fallback(self, individual_id: str, query: str, limit: int = 30) -> List[Dict[str, Any]]:
        """Fallback search when Pinecone is unavailable"""
        logging.warning("Using fallback search - Pinecone unavailable")
        return []
