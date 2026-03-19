# src/research/__init__.py
"""
Research system with autonomous task management and browser control.
"""

from .system import ResearchSystem
from .browser_control import AutonomousBrowser
from .content_processor import ContentProcessor
from .task_manager import ResearchTaskManager
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
from .validators import (
    SourceValidator,
    ContentValidator,
    ReferenceValidator,
    DataValidator,
    ContextValidator
)
from .exceptions import (
    ResearchError,
    InitializationError,
    BrowserError,
    TaskError,
    ProcessingError,
    TaskNotFoundError,
    DependencyError,
    ExtractionError,
    ResearchTimeout,
    BrowserTimeout,
    ValidationError,
    ConfigurationError,
    ResourceError,
    SessionError
)
from .extractors import (
    ContentExtractor,
    DataExtractor,
    TableExtractor,
    ListExtractor,
    CodeExtractor
)
from .processors import (
    ResearchProcessor,
    DataProcessor,
    ContentProcessor,
    ResultProcessor,
    SummaryGenerator
)

# Export API
__all__ = [
    # Core Components
    'ResearchSystem',
    'AutonomousBrowser',
    'ContentProcessor',
    'ResearchTaskManager',
    
    # Models
    'ResearchTask',
    'TaskStatus',
    'TaskPriority',
    'ResearchType',
    'ResearchSession',
    'ResearchFinding',
    'ResearchSource',
    'SourceType',
    'SourceReliability',
    'ValidationLevel',
    
    # Validators
    'SourceValidator',
    'ContentValidator',
    'ReferenceValidator',
    'DataValidator',
    'ContextValidator',
    
    # Extractors
    'ContentExtractor',
    'DataExtractor',
    'TableExtractor',
    'ListExtractor',
    'CodeExtractor',
    
    # Processors
    'ResearchProcessor',
    'DataProcessor',
    'ContentProcessor',
    'ResultProcessor',
    'SummaryGenerator',
    
    # Exceptions
    'ResearchError',
    'InitializationError',
    'BrowserError',
    'TaskError',
    'ProcessingError',
    'TaskNotFoundError',
    'DependencyError',
    'ExtractionError',
    'ResearchTimeout',
    'BrowserTimeout',
    'ValidationError',
    'ConfigurationError',
    'ResourceError',
    'SessionError'
]
