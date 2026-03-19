"""
Memory-specific exceptions.
These exceptions extend the base system exceptions for memory-related errors.
File: src/memory/exceptions.py
"""

from src.core.base_exceptions import ChatSystemError

class MemoryError(ChatSystemError):
    """Base exception for memory-related errors."""
    def __init__(self, message: str = "Memory operation failed"):
        super().__init__(f"Memory Error: {message}")

class StorageError(MemoryError):
    """Raised when memory storage operations fail."""
    def __init__(self, message: str = "Failed to store memory"):
        super().__init__(f"Storage Error: {message}")

class RetrievalError(MemoryError):
    """Raised when memory retrieval operations fail."""
    def __init__(self, message: str = "Failed to retrieve memory"):
        super().__init__(f"Retrieval Error: {message}")

class MemoryValidationError(MemoryError):
    """Raised when memory validation fails."""
    def __init__(self, message: str = "Memory validation failed"):
        super().__init__(f"Validation Error: {message}")

class MemoryNotFoundError(MemoryError):
    """Raised when a requested memory is not found."""
    def __init__(self, memory_id: str):
        super().__init__(f"Memory not found: {memory_id}")

class MemoryStoreConnectionError(MemoryError):
    """Raised when connection to a memory store fails."""
    def __init__(self, store_type: str, details: str = ""):
        message = f"Failed to connect to {store_type} store"
        if details:
            message += f": {details}"
        super().__init__(message)

class MemoryStorageFullError(MemoryError):
    """Raised when memory storage capacity is exceeded."""
    def __init__(self, store_type: str):
        super().__init__(f"Storage capacity exceeded for {store_type}")

class MemoryIndexError(MemoryError):
    """Raised when there are issues with memory indexing."""
    def __init__(self, message: str = "Memory indexing failed"):
        super().__init__(f"Index Error: {message}")

class MemorySerializationError(MemoryError):
    """Raised when memory serialization or deserialization fails."""
    def __init__(self, operation: str = "serialize", details: str = ""):
        message = f"Failed to {operation} memory data"
        if details:
            message += f": {details}"
        super().__init__(message)

class MemorySearchError(MemoryError):
    """Raised when memory search operations fail."""
    def __init__(self, message: str = "Memory search failed", details: str = ""):
        full_message = f"Search Error: {message}"
        if details:
            full_message += f" ({details})"
        super().__init__(full_message)

class MemoryMaintenanceError(MemoryError):
    """Raised during memory maintenance operations."""
    def __init__(self, operation: str, details: str = ""):
        message = f"Maintenance operation '{operation}' failed"
        if details:
            message += f": {details}"
        super().__init__(message)

class MemoryEmbeddingError(MemoryError):
    """Raised when memory embedding operations fail."""
    def __init__(self, operation: str, details: str = ""):
        message = f"Embedding operation failed: {operation}"
        if details:
            message += f" ({details})"
        super().__init__(message)

class MemoryStoreInitializationError(MemoryError):
    """Raised when memory store initialization fails."""
    def __init__(self, store_type: str, details: str = ""):
        message = f"Failed to initialize {store_type} store"
        if details:
            message += f": {details}"
        super().__init__(message)

class MemoryStoreSyncError(MemoryError):
    """Raised when synchronization between memory stores fails."""
    def __init__(self, source: str, target: str, details: str = ""):
        message = f"Failed to sync from {source} to {target}"
        if details:
            message += f": {details}"
        super().__init__(message)

class MemoryCleanupError(MemoryError):
    """Raised when memory cleanup operations fail."""
    def __init__(self, operation: str, details: str = ""):
        message = f"Cleanup operation failed: {operation}"
        if details:
            message += f": {details}"
        super().__init__(message)

class MemoryContextError(MemoryError):
    """Raised when there are issues with memory context."""
    def __init__(self, message: str, details: str = ""):
        full_message = f"Context Error: {message}"
        if details:
            full_message += f" ({details})"
        super().__init__(full_message)

class MemoryQuotaError(MemoryError):
    """Raised when memory quotas are exceeded."""
    def __init__(self, quota_type: str, current: int, maximum: int):
        message = f"Memory quota exceeded for {quota_type}: {current}/{maximum}"
        super().__init__(message)

class MemoryVersionError(MemoryError):
    """Raised when there are memory version incompatibilities."""
    def __init__(self, current: str, required: str, details: str = ""):
        message = f"Memory version mismatch: current={current}, required={required}"
        if details:
            message += f" ({details})"
        super().__init__(message)

class ProcessingError(Exception):
    """Exception raised for errors during memory processing."""
    def __init__(self, message: str, details: str = ""):
        full_message = f"Processing Error: {message}"
        if details:
            full_message += f" ({details})"
        super().__init__(full_message)
