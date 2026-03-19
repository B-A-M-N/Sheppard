"""
Redis implementation of memory storage with proper statistics handling.
File: src/memory/stores/redis.py
"""

import json
import logging
from typing import List, Optional, Dict, Any
import redis.asyncio as redis
from datetime import datetime

from src.config.settings import settings
from src.memory.models import Memory, MemorySearchResult
from src.memory.stores.base import BaseMemoryStore, StoreInitializationError, StoreOperationError

logger = logging.getLogger(__name__)

class RedisMemoryStore(BaseMemoryStore):
    """Redis-based memory storage implementation with proper cleanup."""
    
    def __init__(self):
        """Initialize Redis store."""
        super().__init__()
        self.redis_client: Optional[redis.Redis] = None
        self.memories: Dict[str, Memory] = {}

    async def initialize(self) -> None:
        """Initialize Redis connection and load existing memories."""
        if self._initialized:
            return
            
        try:
            # Create Redis connection
            self.redis_client = await redis.from_url(
                settings.redis_url,
                encoding="utf-8",
                decode_responses=True,
                db=settings.REDIS_DB,
                socket_timeout=5.0,  # Add timeout for operations
                socket_connect_timeout=5.0  # Add connection timeout
            )
            
            # Test connection
            await self.redis_client.ping()
            
            # Load existing memories
            await self._load_existing_memories()
            
            self._initialized = True
            logger.info("Redis store initialized successfully")
            
        except redis.ConnectionError as e:
            await self.cleanup()
            raise StoreInitializationError(f"Failed to connect to Redis: {str(e)}")
        except Exception as e:
            await self.cleanup()
            raise StoreInitializationError(f"Failed to initialize Redis store: {str(e)}")
    
    async def _load_existing_memories(self) -> None:
        """Load all existing memories from Redis."""
        try:
            # Get all memory keys
            all_keys = await self.redis_client.keys(f"{settings.REDIS_PREFIX}memory:*")
            if not all_keys:
                logger.info("No existing memories found in Redis")
                return
            
            # Use pipeline for efficient batch retrieval
            pipeline = self.redis_client.pipeline()
            for key in all_keys:
                pipeline.get(key)
            
            # Execute pipeline and process results
            results = await pipeline.execute()
            loaded_count = 0
            
            for key, value in zip(all_keys, results):
                if value:
                    try:
                        memory_data = json.loads(value)
                        memory_id = key.split(":", 2)[2]  # Remove prefix and 'memory:'
                        self.memories[memory_id] = Memory(**memory_data)
                        loaded_count += 1
                    except (json.JSONDecodeError, ValueError) as e:
                        logger.warning(f"Failed to load memory {key}: {str(e)}")
            
            logger.info(f"Loaded {loaded_count} memories from Redis")
            
        except Exception as e:
            logger.error(f"Failed to load memories from Redis: {str(e)}")
            raise StoreOperationError(f"Failed to load memories from Redis: {str(e)}")
    
    async def store(self, memory: Memory) -> str:
        """Store a memory in Redis."""
        if not self._initialized:
            raise StoreOperationError("Redis store not initialized")
            
        try:
            memory_id = f"{settings.REDIS_PREFIX}memory:{memory.embedding_id}"
            import json
            memory_data = json.dumps(memory.to_dict())
            
            # Store in Redis with pipeline
            pipeline = self.redis_client.pipeline()
            pipeline.set(memory_id, memory_data)
            pipeline.sadd(f"{settings.REDIS_PREFIX}memory_ids", memory.embedding_id)  # Track memory IDs
            await pipeline.execute()
            
            # Update local cache
            self.memories[memory.embedding_id] = memory
            
            return memory.embedding_id
            
        except Exception as e:
            logger.error(f"Failed to store memory in Redis: {str(e)}")
            raise StoreOperationError(f"Failed to store memory in Redis: {str(e)}")
    
    async def retrieve(self, memory_id: str) -> Optional[Memory]:
        """Retrieve a specific memory from Redis."""
        if not self._initialized:
            raise StoreOperationError("Redis store not initialized")
            
        try:
            # Check local cache first
            if memory_id in self.memories:
                return self.memories[memory_id]
            
            # Try Redis if not in cache
            key = f"{settings.REDIS_PREFIX}memory:{memory_id}"
            value = await self.redis_client.get(key)
            if value:
                memory_data = json.loads(value)
                memory = Memory(**memory_data)
                self.memories[memory_id] = memory  # Update cache
                return memory
                
            return None
            
        except Exception as e:
            logger.error(f"Failed to retrieve memory from Redis: {str(e)}")
            raise StoreOperationError(f"Failed to retrieve memory from Redis: {str(e)}")
    
    async def get_all(self) -> List[Memory]:
        """Get all memories from Redis.
        
        Returns:
            List[Memory]: All stored memories
        """
        if not self._initialized:
            raise StoreOperationError("Redis store not initialized")
            
        try:
            # Get all memory keys
            all_keys = await self.redis_client.keys(f"{settings.REDIS_PREFIX}memory:*")
            if not all_keys:
                return []
            
            # Use pipeline for efficient batch retrieval
            pipeline = self.redis_client.pipeline()
            for key in all_keys:
                pipeline.get(key)
            
            # Execute pipeline and process results
            results = await pipeline.execute()
            memories = []
            
            for key, value in zip(all_keys, results):
                if value:
                    try:
                        memory_data = json.loads(value)
                        memory_id = key.split(":", 2)[2]  # Remove prefix and 'memory:'
                        memories.append(Memory.from_dict(memory_data))
                    except (json.JSONDecodeError, ValueError) as e:
                        logger.warning(f"Failed to load memory {key}: {str(e)}")
            
            return memories
            
        except Exception as e:
            logger.error(f"Failed to get all memories from Redis: {str(e)}")
            raise StoreOperationError(f"Failed to get all memories from Redis: {str(e)}")
    
    async def search(
        self,
        query: str,
        limit: int = 5,
        metadata_filter: Optional[Dict[str, Any]] = None
    ) -> List[MemorySearchResult]:
        """Basic search implementation for Redis."""
        if not self._initialized:
            raise StoreOperationError("Redis store not initialized")
            
        try:
            results = []
            query_lower = query.lower()
            
            # Get all memory IDs
            memory_ids = await self.redis_client.smembers(f"{settings.REDIS_PREFIX}memory_ids")
            
            # Search through memories
            for memory_id in memory_ids:
                memory = await self.retrieve(memory_id)
                if memory:
                    # Check content match
                    if query_lower in memory.content.lower():
                        # Check metadata filter if provided
                        if metadata_filter:
                            matches_filter = all(
                                memory.metadata.get(k) == v
                                for k, v in metadata_filter.items()
                            )
                            if not matches_filter:
                                continue
                        
                        # Add to results
                        results.append(
                            MemorySearchResult(
                                content=memory.content,
                                embedding_id=memory_id,
                                relevance_score=1.0,  # Simple match score
                                timestamp=memory.metadata.get('timestamp', datetime.now().isoformat()),
                                metadata=memory.metadata
                            )
                        )
                        
                        if len(results) >= limit:
                            break
            
            return results
            
        except Exception as e:
            logger.error(f"Failed to search memories in Redis: {str(e)}")
            raise StoreOperationError(f"Failed to search memories in Redis: {str(e)}")
    
    async def delete(self, memory_id: str) -> bool:
        """Delete a memory from Redis."""
        if not self._initialized:
            raise StoreOperationError("Redis store not initialized")
            
        try:
            key = f"{settings.REDIS_PREFIX}memory:{memory_id}"
            
            # Delete from Redis with pipeline
            pipeline = self.redis_client.pipeline()
            pipeline.delete(key)
            pipeline.srem(f"{settings.REDIS_PREFIX}memory_ids", memory_id)
            results = await pipeline.execute()
            
            # Remove from local cache
            if memory_id in self.memories:
                del self.memories[memory_id]
            
            return bool(results[0])  # Return True if key was deleted
            
        except Exception as e:
            logger.error(f"Failed to delete memory from Redis: {str(e)}")
            raise StoreOperationError(f"Failed to delete memory from Redis: {str(e)}")
    
    async def get_collection_stats(self) -> Dict[str, Any]:
        """Get statistics about the Redis collection."""
        if not self._initialized:
            raise StoreOperationError("Redis store not initialized")
        
        try:
            # Get memory count by pattern matching
            memory_keys = await self.redis_client.keys(f"{settings.REDIS_PREFIX}memory:*")
            memory_count = len(memory_keys)
            
            # Get some sample memories for analysis
            sample_size = min(10, memory_count)
            sample_memories = []
            
            if sample_size > 0:
                sample_keys = memory_keys[:sample_size]
                pipeline = self.redis_client.pipeline()
                for key in sample_keys:
                    pipeline.get(key)
                
                # Execute pipeline and process results
                results = await pipeline.execute()
                for value in results:
                    if value:
                        try:
                            memory_data = json.loads(value)
                            sample_memories.append(memory_data)
                        except json.JSONDecodeError:
                            continue
            
            return {
                'total_memories': memory_count,
                'type': 'redis',
                'connection_info': {
                    'host': settings.REDIS_HOST,
                    'port': settings.REDIS_PORT,
                    'db': settings.REDIS_DB
                },
                'sample_size': len(sample_memories),
                'status': 'connected' if self.redis_client else 'disconnected'
            }
            
        except Exception as e:
            logger.error(f"Failed to get Redis collection stats: {str(e)}")
            raise StoreOperationError(f"Failed to get collection stats: {str(e)}")
    
    async def cleanup(self) -> None:
        """Clean up Redis connection and resources."""
        try:
            if self.redis_client:
                try:
                    await self.redis_client.close()
                except Exception as e:
                    logger.warning(f"Error closing Redis connection: {str(e)}")
                finally:
                    self.redis_client = None
            
            self.memories.clear()
            self._initialized = False
            
            logger.info("Redis store cleanup completed")
            
        except Exception as e:
            logger.error(f"Error during Redis cleanup: {str(e)}")
            # Don't re-raise as this is cleanup

    def __str__(self) -> str:
        """Get string representation."""
        return (
            f"RedisMemoryStore("
            f"initialized={self._initialized}, "
            f"memories={len(self.memories)})"
        )
