#src/utils/exceptions.py

"""
Exception classes for the chat system.
"""

class ChatSystemError(Exception):
    """Base exception for all system errors."""
    def __init__(self, message: str = "Chat system error occurred"):
        super().__init__(message)

class ChatInitError(ChatSystemError):
    """Raised when chat initialization fails."""
    def __init__(self, details: str = ""):
        message = f"Chat initialization failed"
        if details:
            message += f": {details}"
        super().__init__(message)

class PersonaNotFoundError(ChatSystemError):
    """Raised when a persona is not found."""
    def __init__(self, persona_id: str):
        super().__init__(f"Persona not found: {persona_id}")

class UnauthorizedError(ChatSystemError):
    """Raised when unauthorized access is attempted."""
    def __init__(self, message: str = "Unauthorized access"):
        super().__init__(message)

class ValidationError(ChatSystemError):
    """Raised when validation fails."""
    def __init__(self, message: str = "Validation failed"):
        super().__init__(message)

class ResearchError(ChatSystemError):
    """Raised when research operations fail."""
    def __init__(self, message: str = "Research operation failed"):
        super().__init__(message)
