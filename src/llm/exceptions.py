"""
Exceptions specific to LLM (Language Model) operations.
File: src/llm/exceptions.py
"""

from typing import Optional, Dict, Any

class LLMError(Exception):
    """Base exception for LLM-related errors."""
    def __init__(self, message: str = "LLM operation failed", details: Optional[Dict[str, Any]] = None):
        self.details = details or {}
        formatted_message = f"LLM Error: {message}"
        if self.details:
            formatted_message += f"\nDetails: {self.details}"
        super().__init__(formatted_message)

class ModelNotFoundError(LLMError):
    """Raised when a requested model is not found or not available."""
    def __init__(self, model_name: str, details: str = ""):
        message = f"Model not found or not available: {model_name}"
        if details:
            message += f" ({details})"
        super().__init__(message)

class APIError(LLMError):
    """Raised when there are issues with the LLM API."""
    def __init__(
        self,
        message: str = "API call failed",
        status_code: Optional[int] = None,
        response_body: Optional[str] = None
    ):
        details = {}
        if status_code:
            details["status_code"] = status_code
        if response_body:
            details["response"] = response_body
        super().__init__(message, details)

class RequestError(LLMError):
    """Raised when there are issues with request formation or parameters."""
    def __init__(self, message: str = "Invalid request", details: Optional[Dict[str, Any]] = None):
        super().__init__(message, details)

class ResponseError(LLMError):
    """Raised when there are issues with the model's response."""
    def __init__(self, message: str = "Invalid response", response_data: Optional[Dict[str, Any]] = None):
        super().__init__(message, response_data)

class TokenLimitError(LLMError):
    """Raised when token limits are exceeded."""
    def __init__(self, limit: int, current: int, details: Optional[Dict[str, Any]] = None):
        message = f"Token limit exceeded: {current}/{limit}"
        super().__init__(message, details)

class ContextLengthError(LLMError):
    """Raised when context length limits are exceeded."""
    def __init__(self, limit: int, current: int, details: Optional[Dict[str, Any]] = None):
        message = f"Context length exceeded: {current}/{limit}"
        super().__init__(message, details)

class ModelLoadError(LLMError):
    """Raised when there are issues loading a model."""
    def __init__(self, model_name: str, details: str = ""):
        message = f"Failed to load model: {model_name}"
        if details:
            message += f" ({details})"
        super().__init__(message)

class ValidationError(LLMError):
    """Raised when input or output validation fails."""
    def __init__(self, message: str = "Validation failed", validation_errors: Optional[Dict[str, Any]] = None):
        super().__init__(message, validation_errors)

class TimeoutError(LLMError):
    """Raised when an LLM operation times out."""
    def __init__(
        self,
        operation: str = "operation",
        timeout: Optional[float] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        message = f"LLM {operation} timed out"
        if timeout:
            message += f" after {timeout}s"
        super().__init__(message, details)

class EmbeddingError(LLMError):
    """Raised when embedding generation fails."""
    def __init__(self, message: str = "Embedding generation failed", details: Optional[Dict[str, Any]] = None):
        super().__init__(message, details)

class ModelConfigurationError(LLMError):
    """Raised when there are model configuration issues."""
    def __init__(self, message: str = "Model configuration error", config_details: Optional[Dict[str, Any]] = None):
        super().__init__(message, config_details)

class StreamError(LLMError):
    """Raised when there are issues with streaming responses."""
    def __init__(self, message: str = "Streaming error occurred", stream_details: Optional[Dict[str, Any]] = None):
        super().__init__(message, stream_details)

class ResourceExhaustedError(LLMError):
    """Raised when model resources are exhausted."""
    def __init__(
        self,
        resource_type: str,
        details: Optional[Dict[str, Any]] = None
    ):
        message = f"Resource exhausted: {resource_type}"
        super().__init__(message, details)

class GenerationError(LLMError):
    """Raised when text generation fails."""
    def __init__(self, message: str = "Generation failed", generation_details: Optional[Dict[str, Any]] = None):
        super().__init__(message, generation_details)

class InvalidModelStateError(LLMError):
    """Raised when the model is in an invalid state."""
    def __init__(self, state: str, expected_state: str, details: Optional[Dict[str, Any]] = None):
        message = f"Invalid model state: {state}, expected: {expected_state}"
        super().__init__(message, details)

class AuthenticationError(LLMError):
    """Raised when authentication with the LLM service fails."""
    def __init__(self, message: str = "Authentication failed", auth_details: Optional[Dict[str, Any]] = None):
        super().__init__(message, auth_details)

class ServiceUnavailableError(LLMError):
    """Raised when the LLM service is unavailable."""
    def __init__(self, service: str = "LLM service", details: Optional[Dict[str, Any]] = None):
        message = f"{service} is currently unavailable"
        super().__init__(message, details)

class QuotaExceededError(LLMError):
    """Raised when API quotas are exceeded."""
    def __init__(self, quota_type: str, details: Optional[Dict[str, Any]] = None):
        message = f"Quota exceeded for {quota_type}"
        super().__init__(message, details)

class RateLimitError(LLMError):
    """Raised when rate limits are exceeded."""
    def __init__(
        self,
        limit_type: str,
        current: int,
        maximum: int,
        details: Optional[Dict[str, Any]] = None
    ):
        message = f"Rate limit exceeded for {limit_type}: {current}/{maximum} requests"
        super().__init__(message, details)
