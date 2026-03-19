# src/core/__init__.py
"""
Core chat system functionality.
"""

from .chat import ChatApp
from .exceptions import (
    ChatSystemError,
    InitializationError,
    ModelNotAvailableError,
    ConfigurationError,
    ResourceError,
    ShutdownError,
    SystemStateError,
    CommandError
)
from .constants import (
    WELCOME_TEXT,
    COMMANDS,
    HELP_CATEGORIES,
    ERROR_MESSAGES,
    RESEARCH_SETTINGS,
    STYLES
)
from .commands import CommandHandler

__all__ = [
    # Core App
    'ChatApp',
    'CommandHandler',
    
    # Core Exceptions
    'ChatSystemError',
    'InitializationError',
    'ModelNotAvailableError',
    'ConfigurationError',
    'ResourceError',
    'ShutdownError',
    'SystemStateError',
    'CommandError',
    
    # Constants
    'WELCOME_TEXT',
    'COMMANDS',
    'HELP_CATEGORIES',
    'ERROR_MESSAGES',
    'RESEARCH_SETTINGS',
    'STYLES'
]
