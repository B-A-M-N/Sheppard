"""
Storage Manager for Cognitive Architecture
Manages different types of memory storage that mirror human cognitive memory systems:
- Episodic Memory: Personal experiences and events
- Semantic Memory: General knowledge and facts
- Procedural Memory: Skills and procedures
- Working Memory: Current context and active processing
- Emotional Memory: Affective states and associations
"""

import asyncio
import logging
from typing import Optional, Any, Dict, List
from datetime import datetime
from ...trust_call import call

from .connection import ConnectionManager
from ...exceptions import StorageError, ValidationError
from ....config.database import DatabaseConfig

logger = logging.getLogger(__name__)

class StorageManager:
    """
    Manages cognitive memory storage systems.
    Implements a multi-layer memory architecture similar to human memory systems.
    """

    def __init__(self, validation_schemas=None):
        self.connection_manager = ConnectionManager()
        self.validation_schemas = validation_schemas
        self._initialized = False
        self._lock = asyncio.Lock()

    @call
    async def initialize(self) -> bool:
        """Initialize all memory systems."""
        async with self._lock:
            if self._initialized:
                return True

            try:
                logger.info("Initializing cognitive memory systems...")
                
                # Initialize connection manager for all memory types
                if not await self.connection_manager.initialize():
                    logger.error("Failed to initialize memory connections")
                    return False

                # Verify memory system structures
                if not await self._verify_memory_structures():
                    logger.error("Failed to verify memory structures")
                    return False

                self._initialized = True
                logger.info("Cognitive memory systems initialized successfully")
                return True

            except Exception as e:
                logger.error(f"Failed to initialize memory systems: {e}", exc_info=True)
                await self.cleanup()
                return False

    @call
    async def store_episodic_memory(self, memory_data: Dict[str, Any]) -> str:
        """
        Store an episodic memory (personal experience/event).
        
        Args:
            memory_data: Memory data including:
                - content: The actual experience
                - timestamp: When it occurred
                - emotions: Associated emotional states
                - context: Environmental/situational context
        
        Returns:
            str: Memory ID
        """
        await self._validate_memory('episodic', memory_data)
        memory_id = await self._store_memory('episodic_memory', memory_data)
        
        # Create associative links
        await self._create_memory_associations(
            memory_id,
            memory_data.get('context', {}),
            memory_data.get('emotions', {})
        )
        
        return memory_id

    @call
    async def store_semantic_memory(self, memory_data: Dict[str, Any]) -> str:
        """
        Store semantic memory (facts, concepts, relationships).
        
        Args:
            memory_data: Memory data including:
                - content: The knowledge/concept
                - category: Knowledge category
                - relationships: Connected concepts
                - confidence: Confidence level in the knowledge
        """
        await self._validate_memory('semantic', memory_data)
        memory_id = await self._store_memory('semantic_memory', memory_data)
        
        # Update knowledge graph
        await self._update_knowledge_graph(
            memory_id,
            memory_data.get('relationships', {}),
            memory_data.get('category')
        )
        
        return memory_id

    @call
    async def store_working_memory(self, memory_data: Dict[str, Any]) -> str:
        """
        Store working memory (current context and active processing).
        This is typically short-lived and highly volatile.
        """
        await self._validate_memory('working', memory_data)
        
        # Store with short TTL in Redis
        memory_id = await self._store_memory(
            'working_memory',
            memory_data,
            ttl=300  # 5 minutes default TTL
        )
        
        return memory_id

    @call
    async def retrieve_memory_by_context(
        self,
        context: Dict[str, Any],
        memory_type: str = 'episodic',
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Retrieve memories based on contextual similarity.
        Implements a form of associative memory retrieval.
        """
        try:
            # Get vector embedding for context
            context_embedding = await self._get_context_embedding(context)
            
            # Perform similarity search
            similar_memories = await self._find_similar_memories(
                context_embedding,
                memory_type,
                limit
            )
            
            return similar_memories

        except Exception as e:
            logger.error(f"Error retrieving memories by context: {e}", exc_info=True)
            raise StorageError(f"Memory retrieval failed: {str(e)}")

    @call
    async def _create_memory_associations(
        self,
        memory_id: str,
        context: Dict[str, Any],
        emotions: Dict[str, float]
    ):
        """Create associative links between memories."""
        try:
            # Store context associations
            context_key = f"context:{memory_id}"
            await self.connection_manager.store_associations(context_key, context)
            
            # Store emotional associations
            emotion_key = f"emotions:{memory_id}"
            await self.connection_manager.store_associations(emotion_key, emotions)

        except Exception as e:
            logger.error(f"Error creating memory associations: {e}", exc_info=True)
            raise StorageError("Failed to create memory associations")

    @call
    async def _update_knowledge_graph(
        self,
        memory_id: str,
        relationships: Dict[str, List[str]],
        category: str
    ):
        """Update semantic knowledge graph with new relationships."""
        try:
            graph_key = f"knowledge_graph:{category}"
            
            # Add new node
            await self.connection_manager.add_graph_node(graph_key, memory_id)
            
            # Add relationships
            for rel_type, related_ids in relationships.items():
                for related_id in related_ids:
                    await self.connection_manager.add_graph_edge(
                        graph_key,
                        memory_id,
                        related_id,
                        rel_type
                    )

        except Exception as e:
            logger.error(f"Error updating knowledge graph: {e}", exc_info=True)
            raise StorageError("Failed to update knowledge graph")

    @call
    async def consolidate_memories(self, time_threshold: int = 3600):
        """
        Periodically consolidate and optimize memory storage.
        Similar to human memory consolidation during rest/sleep.
        """
        try:
            # Find memories for consolidation
            memories = await self._get_memories_for_consolidation(time_threshold)
            
            for memory in memories:
                # Analyze memory importance
                importance = await self._calculate_memory_importance(memory)
                
                # Update storage strategy based on importance
                await self._optimize_memory_storage(memory, importance)
                
                # Create abstractions and patterns
                await self._generate_memory_abstractions(memory)

        except Exception as e:
            logger.error(f"Error during memory consolidation: {e}", exc_info=True)
            raise StorageError("Memory consolidation failed")

    # Additional cognitive memory management methods would go here...

    @call
    async def cleanup(self):
        """Clean up memory systems."""
        try:
            logger.info("Starting memory systems cleanup")
            
            # Consolidate important memories before shutdown
            await self.consolidate_memories()
            
            # Clean up connections
            await self.connection_manager.cleanup()
            
            self._initialized = False
            logger.info("Memory systems cleanup completed")

        except Exception as e:
            logger.error(f"Error during memory systems cleanup: {e}", exc_info=True)
            raise StorageError(f"Failed to cleanup memory systems: {str(e)}")
