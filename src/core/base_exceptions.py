"""
Base exceptions for the entire application.
These exceptions serve as the foundation for all other custom exceptions.
File: src/core/base_exceptions.py
"""

class ChatSystemError(Exception):
    """Base exception for all system errors."""
    def __init__(self, message: str = "Chat system error occurred"):
        super().__init__(message)

class InitializationError(ChatSystemError):
    """Raised when system initialization fails."""
    def __init__(self, component: str, details: str = ""):
        message = f"Failed to initialize {component}"
        if details:
            message += f": {details}"
        super().__init__(message)

class ConfigurationError(ChatSystemError):
    """Raised when there are configuration issues."""
    def __init__(self, details: str):
        super().__init__(f"Configuration error: {details}")

class ResourceError(ChatSystemError):
    """Raised when required resources are unavailable."""
    def __init__(self, resource: str, details: str = ""):
        message = f"Resource unavailable: {resource}"
        if details:
            message += f" ({details})"
        super().__init__(message)

class ValidationError(ChatSystemError):
    """Raised when validation fails."""
    def __init__(self, message: str = "Validation failed"):
        super().__init__(f"Validation error: {message}")

class MemoryStoreConnectionError(ChatSystemError):
    """Raised when memory store connection fails."""
    def __init__(self, store_type: str, details: str = ""):
        message = f"Failed to connect to {store_type} store"
        if details:
            message += f": {details}"
        super().__init__(message)

class ShutdownError(ChatSystemError):
    """Raised when system shutdown encounters issues."""
    def __init__(self, component: str, details: str = ""):
        message = f"Error during {component} shutdown"
        if details:
            message += f": {details}"
        super().__init__(message)

class DatabaseError(ChatSystemError):
    """Raised when database operations fail."""
    def __init__(self, operation: str, details: str = ""):
        message = f"Database operation failed: {operation}"
        if details:
            message += f" ({details})"
        super().__init__(message)

class NetworkError(ChatSystemError):
    """Raised when network operations fail."""
    def __init__(self, operation: str, details: str = ""):
        message = f"Network operation failed: {operation}"
        if details:
            message += f" ({details})"
        super().__init__(message)

class ModelError(ChatSystemError):
    """Raised when model operations fail."""
    def __init__(self, model: str, details: str = ""):
        message = f"Model operation failed: {model}"
        if details:
            message += f" ({details})"
        super().__init__(message)

class EmbeddingError(ChatSystemError):
    """Raised when embedding operations fail."""
    def __init__(self, operation: str, details: str = ""):
        message = f"Embedding operation failed: {operation}"
        if details:
            message += f" ({details})"
        super().__init__(message)
