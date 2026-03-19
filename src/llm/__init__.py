"""
Language model integration and management.
"""

from src.core.base_exceptions import (
    ChatSystemError,
    InitializationError,
    ConfigurationError,
    ResourceError,
    ValidationError
)

from .exceptions import (
    LLMError,
    ModelNotFoundError,
    APIError,
    RequestError,
    ResponseError,
    TokenLimitError,
    ContextLengthError,
    ModelLoadError,
    TimeoutError
)

from .models import (
    ChatMessage,
    ChatResponse
)

# Import validation classes directly as they should be dependency-free
from .validators import (
    ChatResponseValidator,
    SchemaValidator,
    EmbeddingValidator
)

# Factory functions for implementation classes
def get_ollama_client():
    """Get the OllamaClient class."""
    from .client import OllamaClient
    return OllamaClient

# Export all public interfaces
__all__ = [
    # Exceptions
    'LLMError',
    'ModelNotFoundError',
    'APIError',
    'RequestError',
    'ResponseError',
    'TokenLimitError',
    'ContextLengthError',
    'ModelLoadError',
    'TimeoutError',
    
    # Models
    'ChatMessage',
    'ChatResponse',
    
    # Validators
    'ChatResponseValidator',
    'SchemaValidator',
    'EmbeddingValidator',
    
    # Factory Functions
    'get_ollama_client'
]

# Version information
__version__ = '0.2.0'
__author__ = 'Your Name'
__email__ = 'your.email@example.com'
__description__ = 'LLM integration with Ollama API'
