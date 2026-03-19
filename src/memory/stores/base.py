"""
Base interface for memory storage implementations with proper async support.
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, Set
from datetime import datetime

from src.memory.models import Memory, MemorySearchResult

class MemoryStoreException(Exception):
    """Base exception for memory store errors."""
    def __init__(self, message: str):
        super().__init__(f"Memory Store Error: {message}")

class StoreInitializationError(MemoryStoreException):
    """Raised when store initialization fails."""
    def __init__(self, message: str):
        super().__init__(f"Initialization Error: {message}")

class StoreOperationError(MemoryStoreException):
    """Raised when a store operation fails."""
    def __init__(self, message: str):
        super().__init__(f"Operation Error: {message}")

class BaseMemoryStore(ABC):
    """
    Abstract base class for memory storage implementations.
    
    This class defines the interface that all memory storage implementations
    must follow. It provides async methods for storing, retrieving, and
    searching memories.
    
    Properties:
        initialized (bool): Whether the store has been initialized.
    """
    
    def __init__(self):
        """Initialize base memory store."""
        self._initialized = False
        self._stored_memories: Set[str] = set()
    
    @property
    def initialized(self) -> bool:
        """Check if store is initialized."""
        return self._initialized
    
    @abstractmethod
    async def initialize(self) -> None:
        """
        Initialize the storage system.
        
        This method should handle all setup required for the storage system,
        including establishing connections, creating tables/collections,
        and loading any existing data.
        
        Raises:
            StoreInitializationError: If initialization fails
        """
        pass
    
    @abstractmethod
    async def store(self, memory: Memory) -> str:
        """
        Store a memory and return its ID.
        
        Args:
            memory: Memory to store
            
        Returns:
            str: ID of stored memory
            
        Raises:
            StoreOperationError: If storage fails
        """
        pass
    
    @abstractmethod
    async def retrieve(self, memory_id: str) -> Optional[Memory]:
        """
        Retrieve a specific memory by ID.
        
        Args:
            memory_id: ID of memory to retrieve
            
        Returns:
            Optional[Memory]: Retrieved memory if found
            
        Raises:
            StoreOperationError: If retrieval fails
        """
        pass
    
    @abstractmethod
    async def search(
        self,
        query: str,
        limit: int = 5,
        metadata_filter: Optional[Dict[str, Any]] = None
    ) -> List[MemorySearchResult]:
        """
        Search for relevant memories.
        
        Args:
            query: Search query
            limit: Maximum number of results
            metadata_filter: Optional metadata filter
            
        Returns:
            List[MemorySearchResult]: Search results
            
        Raises:
            StoreOperationError: If search fails
        """
        pass
    
    @abstractmethod
    async def cleanup(self) -> None:
        """
        Clean up resources.
        
        This method should handle proper cleanup of all resources,
        including closing connections and cleaning up temporary files.
        """
        pass
    
    async def batch_store(self, memories: List[Memory]) -> List[str]:
        """
        Store multiple memories efficiently.
        
        Default implementation stores one at a time. Subclasses should
        override this for better batch performance if supported.
        
        Args:
            memories: List of memories to store
            
        Returns:
            List[str]: List of stored memory IDs
            
        Raises:
            StoreOperationError: If batch storage fails
        """
        try:
            memory_ids = []
            for memory in memories:
                memory_id = await self.store(memory)
                memory_ids.append(memory_id)
            return memory_ids
        except Exception as e:
            raise StoreOperationError(f"Batch storage failed: {str(e)}")
    
    async def batch_retrieve(self, memory_ids: List[str]) -> List[Optional[Memory]]:
        """
        Retrieve multiple memories efficiently.
        
        Default implementation retrieves one at a time. Subclasses should
        override this for better batch performance if supported.
        
        Args:
            memory_ids: List of memory IDs to retrieve
            
        Returns:
            List[Optional[Memory]]: List of retrieved memories
            
        Raises:
            StoreOperationError: If batch retrieval fails
        """
        try:
            memories = []
            for memory_id in memory_ids:
                memory = await self.retrieve(memory_id)
                memories.append(memory)
            return memories
        except Exception as e:
            raise StoreOperationError(f"Batch retrieval failed: {str(e)}")
    
    def validate_memory(self, memory: Memory) -> None:
        """
        Validate a memory before storage.
        
        Args:
            memory: Memory to validate
            
        Raises:
            ValueError: If memory is invalid
        """
        if not memory.content:
            raise ValueError("Memory content cannot be empty")
        
        if not memory.embedding_id:
            raise ValueError("Memory must have an embedding ID")
            
        if 'timestamp' not in memory.metadata:
            raise ValueError("Memory metadata must include timestamp")
    
    def get_stored_count(self) -> int:
        """
        Get count of stored memories.
        
        Returns:
            int: Number of stored memories
        """
        return len(self._stored_memories)
    
    def memory_exists(self, memory_id: str) -> bool:
        """
        Check if a memory exists.
        
        Args:
            memory_id: Memory ID to check
            
        Returns:
            bool: Whether memory exists
        """
        return memory_id in self._stored_memories
    
    async def verify_integrity(self) -> Dict[str, Any]:
        """
        Verify store integrity.
        
        Returns:
            Dict[str, Any]: Integrity check results
            
        Raises:
            StoreOperationError: If verification fails
        """
        try:
            results = {
                'total_memories': self.get_stored_count(),
                'verified_count': 0,
                'missing_count': 0,
                'errors': []
            }
            
            # Check each stored memory
            for memory_id in self._stored_memories:
                try:
                    memory = await self.retrieve(memory_id)
                    if memory:
                        results['verified_count'] += 1
                    else:
                        results['missing_count'] += 1
                        results['errors'].append(f"Memory {memory_id} not found")
                except Exception as e:
                    results['errors'].append(f"Error verifying memory {memory_id}: {str(e)}")
            
            # Add verification timestamp
            results['verified_at'] = datetime.now().isoformat()
            return results
            
        except Exception as e:
            raise StoreOperationError(f"Store integrity verification failed: {str(e)}")
    
    def __str__(self) -> str:
        """Get string representation of store."""
        status = "initialized" if self._initialized else "not initialized"
        count = self.get_stored_count()
        return f"{self.__class__.__name__} ({status}, {count} memories)"
    
    def __repr__(self) -> str:
        """Get detailed string representation of store."""
        return f"{self.__class__.__name__}(initialized={self._initialized}, stored_count={self.get_stored_count()})"
