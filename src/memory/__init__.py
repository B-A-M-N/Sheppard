"""
Memory management system for persistent chat memory.
"""

# Import base exceptions first
from src.core.base_exceptions import (
    ChatSystemError,
    InitializationError,
    ConfigurationError,
    ResourceError,
    ValidationError
)

# Base classes and models
from .base import BaseMemory, BaseMemoryProcessor, BaseMemoryStore
from .models import Memory, MemorySearchResult

# Memory-specific exceptions
from .exceptions import (
    MemoryError,
    StorageError,
    RetrievalError,
    MemoryValidationError,
    MemoryNotFoundError,
    MemoryStoreConnectionError,
    MemoryStorageFullError,
    MemoryIndexError,
    MemorySerializationError,
    MemorySearchError,
    MemoryMaintenanceError
)

def get_memory_manager():
    """Get configured MemoryManager class."""
    from .manager import MemoryManager
    return MemoryManager

def get_memory_processor():
    """Get configured MemoryProcessor class with dependencies."""
    from .processor import MemoryProcessor
    return MemoryProcessor

# Export all public interfaces
__all__ = [
    # Base Classes
    'BaseMemory',
    'BaseMemoryProcessor',
    'BaseMemoryStore',
    
    # Models
    'Memory',
    'MemorySearchResult',
    
    # Exceptions
    'MemoryError',
    'StorageError',
    'RetrievalError',
    'MemoryValidationError',
    'MemoryNotFoundError',
    'MemoryStoreConnectionError',
    'MemoryStorageFullError',
    'MemoryIndexError',
    'MemorySerializationError',
    'MemorySearchError',
    'MemoryMaintenanceError',
    
    # Factory Functions
    'get_memory_manager',
    'get_memory_processor'
]

# Version information
__version__ = '0.2.0'
__description__ = 'Memory management system with persistent storage'
