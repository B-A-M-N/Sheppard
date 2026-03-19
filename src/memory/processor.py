"""
Enhanced memory processor with context awareness and proper initialization.
File: src/memory/processor.py
"""

import logging
from typing import Optional, Dict, Any, List, AsyncGenerator, Union, Tuple
from datetime import datetime

from src.memory.stores.base import BaseMemoryStore
from src.memory.models import Memory, MemorySearchResult
from src.preferences.store import PreferenceStore
from src.research.content_processor import ContentProcessor
from src.llm.client import OllamaClient
from src.memory.exceptions import ProcessingError

logger = logging.getLogger(__name__)

class MemoryProcessor:
    """Processes and manages memory operations with context awareness."""
    
    def __init__(
        self,
        memory_store: BaseMemoryStore,
        ollama_client: OllamaClient,
        max_context_length: int = 2048,
        min_relevance_score: float = 0.6,
        preference_store: Optional[PreferenceStore] = None,
        content_processor: Optional[ContentProcessor] = None
    ):
        """
        Initialize memory processor.
        
        Args:
            memory_store: Base memory store instance
            ollama_client: Ollama client for embeddings/completions
            max_context_length: Maximum context length in tokens
            min_relevance_score: Minimum relevance score for context
            preference_store: Optional preference store
            content_processor: Optional content processor instance
        """
        self.store = memory_store
        self.client = ollama_client
        self.max_context_length = max_context_length
        self.min_relevance_score = min_relevance_score
        self.preference_store = preference_store
        
        # Use provided content processor or create new one
        self.content_processor = content_processor or ContentProcessor(ollama_client=ollama_client)
        
        # Conversation tracking
        self.current_conversation_id: Optional[str] = None
        self.conversation_start_time: Optional[str] = None
        self.conversation_turns: List[Dict[str, Any]] = []
    
    async def process_input(
        self,
        content: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Tuple[List[str], Dict[str, Any]]:
        """
        Process and store input content.
        
        Args:
            content: Content to process
            metadata: Optional metadata
            
        Returns:
            Tuple[List[str], Dict[str, Any]]: (memory_ids, processed_data)
            
        Raises:
            ProcessingError: If processing fails
        """
        try:
            memory_ids = []
            timestamp = datetime.now().isoformat()
            
            # Create base processed data
            processed_data = {
                "timestamp": timestamp,
                "content": content,
                "metadata": metadata or {},
                "context": [],
                "preference_updates": {}
            }
            
            # Process content through content processor
            processed_content = await self.content_processor.process_content(content)
            if processed_content:
                processed_data["processed_content"] = processed_content
            
            # Generate embedding if client available
            if self.client:
                try:
                    embedding = await self.client.generate_embedding(content)
                    processed_data["embedding"] = embedding
                except Exception as e:
                    logger.warning(f"Failed to generate embedding: {str(e)}")
            
            # Create and store memory
            memory = Memory(
                content=processed_content or content,
                metadata={
                    "timestamp": timestamp,
                    "embedding": processed_data.get("embedding"),
                    **(metadata or {})
                }
            )
            
            memory_id = await self.store.store(memory)
            memory_ids.append(memory_id)
            processed_data["memory_id"] = memory_id
            
            # Get relevant context
            try:
                context_results = await self.get_context(
                    content,
                    limit=5,
                    min_relevance=self.min_relevance_score
                )
                processed_data["context"] = context_results
            except Exception as e:
                logger.warning(f"Failed to get context: {str(e)}")
            
            return memory_ids, processed_data
            
        except Exception as e:
            raise ProcessingError(f"Failed to process input: {str(e)}")
    
    async def get_context(
        self,
        query: str,
        limit: int = 5,
        min_relevance: Optional[float] = None
    ) -> List[Dict[str, Any]]:
        """
        Get relevant context for a query.
        
        Args:
            query: Context query
            limit: Maximum number of context items
            min_relevance: Optional minimum relevance score
            
        Returns:
            List[Dict[str, Any]]: Relevant context items
            
        Raises:
            ProcessingError: If context retrieval fails
        """
        try:
            min_relevance = min_relevance or self.min_relevance_score
            
            # Search for relevant memories
            results = await self.store.search(
                query,
                limit=limit,
                metadata_filter={"type": "conversation"}
            )
            
            # Filter and format results
            context_items = []
            for result in results:
                if result.relevance_score >= min_relevance:
                    context_items.append({
                        "content": result.content,
                        "relevance": result.relevance_score,
                        "timestamp": result.timestamp,
                        "type": result.metadata.get("type", "unknown"),
                        "memory_id": result.embedding_id
                    })
            
            return context_items
            
        except Exception as e:
            raise ProcessingError(f"Failed to get context: {str(e)}")
    
    async def summarize_content(
        self,
        content: str,
        max_length: Optional[int] = None
    ) -> str:
        """
        Summarize content using available client.
        
        Args:
            content: Content to summarize
            max_length: Optional maximum summary length
            
        Returns:
            str: Summarized content
        """
        if not self.client:
            return content[:max_length] if max_length else content
        
        try:
            return await self.client.summarize_text(content, max_length)
        except Exception as e:
            logger.warning(f"Summarization failed: {str(e)}")
            return content[:max_length] if max_length else content
    
    async def clear(self) -> None:
        """Clear processed memories."""
        try:
            # This would typically involve clearing any local caches
            # The actual memories remain in the store
            pass
        except Exception as e:
            raise ProcessingError(f"Failed to clear processor state: {str(e)}")
    
    async def get_memory_timeline(
        self,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Get timeline of memories within time range.
        
        Args:
            start_time: Optional start time (ISO format)
            end_time: Optional end time (ISO format)
            limit: Maximum number of memories to return
            
        Returns:
            List[Dict[str, Any]]: Memory timeline
        """
        try:
            # Search with time range filter
            metadata_filter = {}
            if start_time:
                metadata_filter["timestamp__gte"] = start_time
            if end_time:
                metadata_filter["timestamp__lte"] = end_time
            
            results = await self.store.search(
                query="",  # Empty query to match all
                limit=limit,
                metadata_filter=metadata_filter
            )
            
            # Sort by timestamp
            timeline = []
            for result in results:
                timeline.append({
                    "content": result.content,
                    "timestamp": result.timestamp,
                    "type": result.metadata.get("type", "unknown"),
                    "memory_id": result.embedding_id,
                    "metadata": result.metadata
                })
            
            timeline.sort(key=lambda x: x["timestamp"])
            return timeline
            
        except Exception as e:
            raise ProcessingError(f"Failed to get memory timeline: {str(e)}")
