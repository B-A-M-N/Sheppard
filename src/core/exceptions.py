"""
Core exceptions for the chat system.
Extends base exceptions with chat-specific error cases.
"""

from .base_exceptions import (
    ChatSystemError,
    InitializationError,
    ConfigurationError,
    ResourceError,
    ValidationError
)

class ModelNotAvailableError(ChatSystemError):
    """Raised when a required model is not available."""
    def __init__(self, model_name: str):
        super().__init__(f"Model not available: {model_name}")

class ShutdownError(ChatSystemError):
    """Raised when system shutdown encounters issues."""
    def __init__(self, component: str, details: str = ""):
        message = f"Error during {component} shutdown"
        if details:
            message += f": {details}"
        super().__init__(message)

class SystemStateError(ChatSystemError):
    """Raised when the system is in an invalid state."""
    def __init__(self, details: str):
        super().__init__(f"Invalid system state: {details}")

class CommandError(ChatSystemError):
    """Raised when command handling fails."""
    def __init__(self, message: str = "Command error occurred"):
        super().__init__(f"Command error: {message}")

class ContextError(ChatSystemError):
    """Raised when there are issues with conversation context."""
    def __init__(self, message: str = "Context error occurred"):
        super().__init__(f"Context error: {message}")

class PreferenceError(ChatSystemError):
    """Raised when there are issues with user preferences."""
    def __init__(self, message: str = "Preference error occurred"):
        super().__init__(f"Preference error: {message}")

class ToolError(ChatSystemError):
    """Raised when tool execution fails."""
    def __init__(self, tool_name: str, details: str = ""):
        message = f"Tool execution failed: {tool_name}"
        if details:
            message += f" ({details})"
        super().__init__(message)

class RateLimitError(ChatSystemError):
    """Raised when rate limits are exceeded."""
    def __init__(self, limit_type: str, current: int, maximum: int):
        super().__init__(
            f"Rate limit exceeded for {limit_type}: "
            f"{current}/{maximum} requests"
        )

class TimeoutError(ChatSystemError):
    """Raised when an operation times out."""
    def __init__(self, operation: str, timeout: float):
        super().__init__(
            f"Operation timed out: {operation} "
            f"(exceeded {timeout} seconds)"
        )

class AuthenticationError(ChatSystemError):
    """Raised when authentication fails."""
    def __init__(self, message: str = "Authentication failed"):
        super().__init__(f"Authentication error: {message}")

class PermissionError(ChatSystemError):
    """Raised when permission is denied."""
    def __init__(self, operation: str, details: str = ""):
        message = f"Permission denied for operation: {operation}"
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

class DataError(ChatSystemError):
    """Raised when there are issues with data handling."""
    def __init__(self, message: str = "Data error occurred"):
        super().__init__(f"Data error: {message}")

class SerializationError(ChatSystemError):
    """Raised when serialization or deserialization fails."""
    def __init__(self, operation: str = "serialize"):
        super().__init__(f"Failed to {operation} data")

class MaintenanceError(ChatSystemError):
    """Raised during system maintenance operations."""
    def __init__(self, operation: str, details: str = ""):
        message = f"Maintenance operation failed: {operation}"
        if details:
            message += f" ({details})"
        super().__init__(message)

# Export all exceptions
__all__ = [
    'ChatSystemError',
    'InitializationError',
    'ConfigurationError',
    'ResourceError',
    'ValidationError',
    'ModelNotAvailableError',
    'ShutdownError',
    'SystemStateError',
    'CommandError',
    'ContextError',
    'PreferenceError',
    'ToolError',
    'RateLimitError',
    'TimeoutError',
    'AuthenticationError',
    'PermissionError',
    'NetworkError',
    'DataError',
    'SerializationError',
    'MaintenanceError'
]
