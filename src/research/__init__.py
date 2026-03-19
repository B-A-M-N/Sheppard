# src/research/__init__.py
"""
Research system with autonomous task management and browser control.
"""
# Only export the necessary elements
__version__ = '0.2.0'
__description__ = 'Research system with autonomous task management and browser control'

# Only import models to avoid cycles
from .models import (
    ResearchTask,
    TaskStatus,
    TaskPriority,
    ResearchType,
    ResearchSession,
    ResearchFinding,
    ResearchSource,
    SourceType,
    SourceReliability,
    ValidationLevel
)

from .exceptions import (
    ResearchError,
    BrowserError,
    TaskError,
    ProcessingError
)

# Don't directly import system, browser_control, etc.
# Import these inside functions that use them
