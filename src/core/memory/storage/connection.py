# src/core/memory/storage/connection.py

import asyncio
import logging
from typing import Dict, Optional, Any, List, Tuple
from datetime import datetime
from contextlib import asynccontextmanager
from dataclasses import dataclass
import numpy as np

import asyncpg
import redis.asyncio as redis
from redis.asyncio import Redis
from asyncpg.pool import Pool

from ....config.database import DatabaseConfig
from ...exceptions import ResourceError  # Fixed import: use ResourceError instead of non-existent SheppardError/ConnectionError
from ...trust_call import call

logger = logging.getLogger(__name__)

@dataclass
class MemoryConnection:
    """Represents a connection to a specific memory system."""
    pool: Optional[Pool] = None
    redis: Optional[Redis] = None
    vector_store: Optional[Any] = None  # For semantic/episodic similarity search
    last_accessed: datetime = datetime.now()

# Rest of the connection.py code remains the same...

# Rest of the file remains the same...

class ConnectionManager:
    """
    Manages connections to different memory storage systems.
    Implements a hierarchical memory architecture with different storage types
    for different kinds of memories and retrieval patterns.
    """

    def __init__(self):
        self.connections: Dict[str, MemoryConnection] = {}
        self._initialized = False
        self._lock = asyncio.Lock()
        self._closing = False

    @call
    async def initialize(self) -> bool:
        """Initialize connections to all memory systems."""
        async with self._lock:
            if self._initialized:
                return True

            try:
                logger.info("Initializing cognitive memory connections...")

                # Initialize different memory system connections
                memory_systems = [
                    # Long-term memory systems
                    'episodic_memory',
                    'semantic_memory',
                    'procedural_memory',
                    
                    # Short-term and working memory
                    'working_memory',
                    'sensory_memory',
                    
                    # Specialized memory systems
                    'emotional_memory',
                    'spatial_memory',
                    
                    # Meta-memory systems
                    'memory_index',
                    'association_network'
                ]

                for system in memory_systems:
                    connection = MemoryConnection()
                    
                    # Initialize PostgreSQL for long-term storage
                    if system in ['episodic_memory', 'semantic_memory', 'procedural_memory']:
                        connection.pool = await self._create_postgres_pool(system)
                        
                        # Initialize vector store for similarity search
                        connection.vector_store = await self._initialize_vector_store(system)

                    # Initialize Redis for fast access and working memory
                    connection.redis = await self._create_redis_client(system)
                    
                    self.connections[system] = connection

                self._initialized = True
                logger.info("Memory connections initialized successfully")
                return True

            except Exception as e:
                logger.error(f"Failed to initialize memory connections: {e}", exc_info=True)
                await self.cleanup()
                return False

    @call
    async def store_associations(self, key: str, associations: Dict[str, Any]):
        """Store memory associations in the association network."""
        try:
            connection = self.connections.get('association_network')
            if not connection or not connection.redis:
                raise ResourceError("Association network not initialized")

            # Store associations with scores
            async with self.get_redis_connection('association_network') as redis:
                for assoc_type, value in associations.items():
                    score = self._calculate_association_strength(value)
                    await redis.zadd(f"assoc:{key}:{assoc_type}", {str(value): score})

        except Exception as e:
            logger.error(f"Failed to store associations: {e}", exc_info=True)
            raise ResourceError(f"Association storage failed: {str(e)}")

    @call
    async def add_graph_node(self, graph_key: str, node_id: str, properties: Dict[str, Any] = None):
        """Add a node to the knowledge graph."""
        try:
            connection = self.connections.get('semantic_memory')
            if not connection or not connection.pool:
                raise ResourceError("Semantic memory not initialized")

            async with self.get_postgres_connection('semantic_memory') as conn:
                await conn.execute(
                    """
                    INSERT INTO knowledge_graph_nodes (node_id, graph_key, properties)
                    VALUES ($1, $2, $3)
                    ON CONFLICT (node_id, graph_key) DO UPDATE
                    SET properties = EXCLUDED.properties,
                        updated_at = CURRENT_TIMESTAMP
                    """,
                    node_id, graph_key, properties or {}
                )

        except Exception as e:
            logger.error(f"Failed to add graph node: {e}", exc_info=True)
            raise ResourceError(f"Graph node creation failed: {str(e)}")

    @call
    async def add_graph_edge(
        self,
        graph_key: str,
        from_id: str,
        to_id: str,
        edge_type: str,
        properties: Dict[str, Any] = None
    ):
        """Add an edge to the knowledge graph."""
        try:
            connection = self.connections.get('semantic_memory')
            if not connection or not connection.pool:
                raise ResourceError("Semantic memory not initialized")

            async with self.get_postgres_connection('semantic_memory') as conn:
                await conn.execute(
                    """
                    INSERT INTO knowledge_graph_edges 
                    (graph_key, from_id, to_id, edge_type, properties)
                    VALUES ($1, $2, $3, $4, $5)
                    ON CONFLICT (graph_key, from_id, to_id, edge_type) DO UPDATE
                    SET properties = EXCLUDED.properties,
                        updated_at = CURRENT_TIMESTAMP
                    """,
                    graph_key, from_id, to_id, edge_type, properties or {}
                )

        except Exception as e:
            logger.error(f"Failed to add graph edge: {e}", exc_info=True)
            raise ResourceError(f"Graph edge creation failed: {str(e)}")

    @call
    @asynccontextmanager
    async def get_postgres_connection(self, memory_type: str):
        """Get a PostgreSQL connection for a specific memory type."""
        connection = self.connections.get(memory_type)
        if not connection or not connection.pool:
            raise ResourceError(f"No PostgreSQL pool for memory type: {memory_type}")

        connection.last_accessed = datetime.now()
        async with connection.pool.acquire() as conn:
            try:
                yield conn
            except Exception as e:
                logger.error(f"Error during PostgreSQL operation: {e}", exc_info=True)
                raise

    @call
    @asynccontextmanager
    async def get_redis_connection(self, memory_type: str):
        """Get a Redis connection for a specific memory type."""
        connection = self.connections.get(memory_type)
        if not connection or not connection.redis:
            raise ResourceError(f"No Redis client for memory type: {memory_type}")

        connection.last_accessed = datetime.now()
        try:
            yield connection.redis
        except Exception as e:
            logger.error(f"Error during Redis operation: {e}", exc_info=True)
            raise

    @call
    async def get_similar_memories(
        self,
        memory_type: str,
        embedding: np.ndarray,
        limit: int = 10,
        threshold: float = 0.7
    ) -> List[Tuple[str, float]]:
        """Find similar memories using vector similarity search."""
        try:
            connection = self.connections.get(memory_type)
            if not connection or not connection.vector_store:
                raise ResourceError(f"No vector store for memory type: {memory_type}")

            results = await connection.vector_store.search(
                embedding,
                limit=limit,
                threshold=threshold
            )
            
            return [(memory_id, score) for memory_id, score in results]

        except Exception as e:
            logger.error(f"Error during similarity search: {e}", exc_info=True)
            raise ResourceError(f"Similarity search failed: {str(e)}")

    def _calculate_association_strength(self, value: Any) -> float:
        """Calculate association strength score."""
        if isinstance(value, dict):
            # For emotional associations, use emotion intensity
            if 'intensity' in value:
                return float(value['intensity'])
            # For context associations, use relevance score
            if 'relevance' in value:
                return float(value['relevance'])
        # Default strength
        return 1.0

    @call
    async def cleanup(self):
        """Clean up all memory system connections."""
        async with self._lock:
            if self._closing:
                return

            self._closing = True
            logger.info("Starting memory connections cleanup")
            
            try:
                # Clean up each memory system
                for memory_type, connection in self.connections.items():
                    try:
                        # Close PostgreSQL pool
                        if connection.pool:
                            await connection.pool.close()
                            logger.info(f"Closed PostgreSQL pool for {memory_type}")

                        # Close Redis client
                        if connection.redis:
                            await connection.redis.close()
                            logger.info(f"Closed Redis client for {memory_type}")

                        # Close vector store
                        if connection.vector_store:
                            await connection.vector_store.close()
                            logger.info(f"Closed vector store for {memory_type}")

                    except Exception as e:
                        logger.error(f"Error closing {memory_type} connections: {e}")

                self.connections.clear()
                self._initialized = False
                
                logger.info("Memory connections cleanup completed")

            except Exception as e:
                logger.error(f"Error during connections cleanup: {e}", exc_info=True)
                raise
            finally:
                self._closing = False

    async def _initialize_vector_store(self, memory_type: str) -> Any:
        """Initialize vector store for similarity search."""
        # Implementation depends on your chosen vector similarity search solution
        # Could use FAISS, Annoy, or other vector similarity search libraries
        pass
