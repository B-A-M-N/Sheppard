"""
Base interface for memory operations.
Defines the core contract that all memory implementations must fulfill.
"""

from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List, AsyncGenerator
from datetime import datetime

class BaseMemory(ABC):
    """Abstract base class for memory operations."""
    
    @abstractmethod
    async def initialize(self) -> None:
        """Initialize the memory system."""
        pass

    @abstractmethod
    async def store(self, content: str, metadata: Optional[Dict[str, Any]] = None) -> str:
        """
        Store a memory.
        
        Args:
            content: Content to store
            metadata: Optional metadata
            
        Returns:
            str: Memory ID
        """
        pass

    @abstractmethod
    async def retrieve(self, memory_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve a memory by ID.
        
        Args:
            memory_id: ID of memory to retrieve
            
        Returns:
            Optional[Dict[str, Any]]: Retrieved memory if found
        """
        pass
        
    @abstractmethod
    async def search(
        self,
        query: str,
        limit: Optional[int] = None,
        metadata_filter: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Search for memories.
        
        Args:
            query: Search query
            limit: Optional result limit
            metadata_filter: Optional metadata filter
            
        Returns:
            List[Dict[str, Any]]: Search results
        """
        pass

    @abstractmethod
    async def cleanup(self) -> None:
        """Clean up memory system resources."""
        pass

class BaseMemoryProcessor:
    """Base class for memory processing operations."""
    
    @abstractmethod
    async def process_input(
        self,
        content: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Process and store input content.
        
        Args:
            content: Content to process
            metadata: Optional metadata
            
        Yields:
            Dict[str, Any]: Processing results
        """
        pass

    @abstractmethod
    async def get_context(
        self,
        query: str,
        limit: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Get relevant context for a query.
        
        Args:
            query: Context query
            limit: Maximum number of context items
            
        Returns:
            List[Dict[str, Any]]: Relevant context
        """
        pass

    @abstractmethod
    async def clear(self) -> None:
        """Clear all processed memories."""
        pass

class BaseMemoryStore(ABC):
    """Abstract base class for memory storage implementations."""
    
    @abstractmethod
    async def initialize(self) -> None:
        """Initialize the storage system."""
        pass

    @abstractmethod
    async def store(self, memory: Any) -> str:
        """
        Store a memory.
        
        Args:
            memory: Memory to store
            
        Returns:
            str: Memory ID
        """
        pass

    @abstractmethod
    async def retrieve(self, memory_id: str) -> Optional[Any]:
        """
        Retrieve a memory.
        
        Args:
            memory_id: Memory ID
            
        Returns:
            Optional[Any]: Retrieved memory if found
        """
        pass

    @abstractmethod
    async def search(
        self,
        query: str,
        limit: Optional[int] = None,
        metadata_filter: Optional[Dict[str, Any]] = None
    ) -> List[Any]:
        """
        Search for memories.
        
        Args:
            query: Search query
            limit: Optional result limit
            metadata_filter: Optional metadata filter
            
        Returns:
            List[Any]: Search results
        """
        pass

    @abstractmethod
    async def cleanup(self) -> None:
        """Clean up storage resources."""
        pass
