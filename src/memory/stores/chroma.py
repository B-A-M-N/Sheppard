"""
ChromaDB implementation of memory storage with proper dimension handling.
File: src/memory/stores/chroma.py
"""

import logging
import shutil
import os
import math
from typing import Dict, Any, List, Optional, Union
from datetime import datetime
import chromadb
from chromadb.config import Settings as ChromaSettings

from src.config.settings import settings
from src.memory.models import Memory, MemorySearchResult
from src.memory.stores.base import BaseMemoryStore, StoreOperationError
from src.memory.exceptions import MemoryStoreConnectionError
from src.llm.client import OllamaClient

logger = logging.getLogger(__name__)

class ChromaMemoryStore(BaseMemoryStore):
    """ChromaDB-based memory storage implementation."""
    
    def __init__(self):
        """Initialize ChromaDB store."""
        super().__init__()
        self.client = None
        self.collection = None
        self.ollama_client = None
        self.embedding_dimension = settings.EMBEDDING_DIMENSION  # Fixed dimension
        self._persist_dir = settings.CHROMADB_PERSIST_DIRECTORY
        self._initialized = False

    async def initialize(self, ollama_client: OllamaClient) -> None:
        """Initialize ChromaDB connection and collection."""
        if self._initialized:
            return

        try:
            # Ensure persistence directory exists
            os.makedirs(self._persist_dir, exist_ok=True)
            
            # Configure ChromaDB settings
            chroma_settings = ChromaSettings(
                anonymized_telemetry=False,
                allow_reset=True,
                is_persistent=True,
                persist_directory=self._persist_dir
            )
            
            # Initialize client
            self.client = chromadb.PersistentClient(
                path=self._persist_dir,
                settings=chroma_settings
            )
            
            # Store the Ollama client
            self.ollama_client = ollama_client
            
            # Create or get collection with explicit dimension
            self.collection = self.client.get_or_create_collection(
                name=settings.CHROMADB_COLLECTION_NAME,
                metadata={
                    "hnsw:space": settings.CHROMADB_DISTANCE_FUNC,
                    "dimension": self.embedding_dimension
                }
            )
            
            self._initialized = True
            logger.info(f"ChromaDB store initialized successfully")
            
        except Exception as e:
            await self.cleanup()
            raise MemoryStoreConnectionError("ChromaDB", str(e))

    async def store(self, memory: Memory) -> str:
        """Store a memory in ChromaDB."""
        if not self._initialized:
            raise StoreOperationError("ChromaDB store not initialized")
            
        try:
            # Generate embedding if not present
            if not memory.embedding and self.ollama_client:
                memory.embedding = await self.ollama_client.generate_embedding(memory.content)
            
            if not memory.embedding:
                raise StoreOperationError("Failed to generate embedding")
            
            # Verify embedding dimension
            if len(memory.embedding) != self.embedding_dimension:
                raise StoreOperationError(
                    f"Embedding dimension mismatch: got {len(memory.embedding)}, "
                    f"expected {self.embedding_dimension}"
                )
            
            # Add to ChromaDB
            self.collection.add(
                documents=[memory.content],
                embeddings=[memory.embedding],
                metadatas=[memory.metadata],
                ids=[memory.embedding_id]
            )
            
            return memory.embedding_id
            
        except Exception as e:
            logger.error(f"Failed to store memory in ChromaDB: {str(e)}")
            raise StoreOperationError(f"Failed to store memory: {str(e)}")

    async def retrieve(self, memory_id: str) -> Optional[Memory]:
        """Retrieve a memory by ID."""
        if not self._initialized:
            raise StoreOperationError("ChromaDB store not initialized")
            
        try:
            result = self.collection.get(
                ids=[memory_id],
                include=["documents", "metadatas", "embeddings"]
            )
            
            if not result or not result['ids']:
                return None
            
            return Memory(
                content=result['documents'][0],
                embedding_id=memory_id,
                metadata=result['metadatas'][0] if result['metadatas'] else {},
                embedding=result['embeddings'][0] if result['embeddings'] else None
            )
            
        except Exception as e:
            logger.error(f"Failed to retrieve memory from ChromaDB: {str(e)}")
            raise StoreOperationError(f"Failed to retrieve memory: {str(e)}")

    async def search(
        self,
        query: str,
        limit: Optional[int] = None,
        metadata_filter: Optional[Dict[str, Any]] = None,
        min_relevance: float = 0.0
    ) -> List[MemorySearchResult]:
        """Search for relevant memories."""
        if not self._initialized:
            raise StoreOperationError("ChromaDB store not initialized")
            
        try:
            # Generate query embedding
            query_embedding = None
            if self.ollama_client:
                try:
                    query_embedding = await self.ollama_client.generate_embedding(query)
                except Exception as e:
                    logger.warning(f"Failed to generate query embedding: {str(e)}")
                    # Continue with text search if embedding fails
            
            # Prepare search parameters
            search_params = {
                "query_embeddings": [query_embedding] if query_embedding else None,
                "query_texts": [query] if not query_embedding else None,
                "n_results": limit if limit else 10,
                "include": ["documents", "metadatas", "distances", "embeddings"]
            }
            
            # Add metadata filtering if provided
            if metadata_filter:
                search_params["where"] = metadata_filter
            
            # Perform search
            results = self.collection.query(**search_params)
            
            # Process results
            search_results = []
            if results["ids"] and len(results["ids"][0]) > 0:
                for i, doc_id in enumerate(results["ids"][0]):
                    distance = results["distances"][0][i] if results["distances"] else 0.0
                    similarity = self._distance_to_similarity(distance)
                    
                    if similarity >= min_relevance:
                        metadata = results["metadatas"][0][i] if results["metadatas"] else {}
                        
                        # Get content safely with fallback
                        content = ""
                        if results["documents"] and len(results["documents"][0]) > i:
                            content = results["documents"][0][i] or ""
                        
                        # Skip empty content results
                        if not content:
                            logger.warning(f"Empty content for document ID: {doc_id}, skipping")
                            continue
                        
                        # Create result with validated content
                        result = MemorySearchResult(
                            content=content,
                            embedding_id=doc_id,
                            relevance_score=similarity,
                            timestamp=metadata.get('timestamp', datetime.now().isoformat()),
                            metadata=metadata
                        )
                        search_results.append(result)
            
            return search_results
            
        except ValueError as ve:
            # Handle specifically the "Result content cannot be empty" error
            if "content cannot be empty" in str(ve):
                logger.warning(f"ChromaDB returned empty content: {str(ve)}")
                return []  # Return empty results instead of raising error
            else:
                logger.error(f"Failed to search memories in ChromaDB: {str(ve)}")
                raise StoreOperationError(f"Failed to search memories: {str(ve)}")
        except Exception as e:
            logger.error(f"Failed to search memories in ChromaDB: {str(e)}")
            raise StoreOperationError(f"Failed to search memories: {str(e)}")

    def _distance_to_similarity(self, distance: float) -> float:
        """Convert distance to similarity score."""
        if settings.CHROMADB_DISTANCE_FUNC == "cosine":
            # Cosine distance to similarity conversion
            return max(0.0, min(1.0, 1.0 - distance))
        else:
            # For other distance metrics (l2, ip)
            # Use exponential decay for L2 distance
            return max(0.0, min(1.0, math.exp(-distance)))

    async def delete(self, memory_id: str) -> bool:
        """Delete a memory by ID."""
        if not self._initialized:
            raise StoreOperationError("ChromaDB store not initialized")
            
        try:
            self.collection.delete(ids=[memory_id])
            return True
        except Exception as e:
            logger.error(f"Failed to delete memory from ChromaDB: {str(e)}")
            raise StoreOperationError(f"Failed to delete memory: {str(e)}")

    async def cleanup(self) -> None:
        """Clean up ChromaDB resources."""
        try:
            if hasattr(self, 'collection') and self.collection:
                try:
                    # Attempt to gracefully close the collection
                    self.collection = None
                except Exception as e:
                    logger.warning(f"Error closing collection: {str(e)}")
            
            if hasattr(self, 'client') and self.client:
                try:
                    # Close the client connection
                    self.client = None
                except Exception as e:
                    logger.warning(f"Error closing client: {str(e)}")
            
            self.ollama_client = None
            self._initialized = False
            
            # Clean up persistence directory if empty
            if (self._persist_dir and os.path.exists(self._persist_dir) and 
                not os.listdir(self._persist_dir)):
                try:
                    shutil.rmtree(self._persist_dir)
                except Exception as e:
                    logger.warning(f"Failed to remove empty persist directory: {str(e)}")
            
            logger.info("ChromaDB store cleanup completed")
            
        except Exception as e:
            logger.error(f"Error during ChromaDB cleanup: {str(e)}")
            # Don't raise during cleanup
    
    async def get_collection_stats(self) -> Dict[str, Any]:
        """Get collection statistics."""
        if not self._initialized:
            raise StoreOperationError("ChromaDB store not initialized")
            
        try:
            count = self.collection.count()
            
            return {
                "total_memories": count,
                "name": self.collection.name,
                "metadata": self.collection.metadata,
                "embedding_dimension": self.embedding_dimension,
                "distance_function": settings.CHROMADB_DISTANCE_FUNC,
                "persist_directory": self._persist_dir,
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Failed to get ChromaDB collection stats: {str(e)}")
            raise StoreOperationError(f"Failed to get collection stats: {str(e)}")

    def __str__(self) -> str:
        """Get string representation."""
        return (
            f"ChromaMemoryStore("
            f"initialized={self._initialized}, "
            f"collection={self.collection.name if self.collection else 'none'}, "
            f"dimension={self.embedding_dimension})"
        )
