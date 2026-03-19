# src/preferences/__init__.py
"""
Preference management system.
"""

from .store import PreferenceStore
from .models import (
    Preference,
    PreferenceCategory,
    PreferenceType,
    PreferenceValue,
    PreferenceMetadata,
    PreferenceValidationResult
)
from .exceptions import (
    PreferenceError,
    ValidationError,
    StorageError,
    PreferenceNotFoundError,
    CategoryNotFoundError,
    InvalidPreferenceError,
    ConflictError
)
from .processors import (
    PreferenceProcessor,
    PreferenceContext,
    PreferenceRelation
)
from .schema import (
    PreferenceSchema,
    CategorySchema,
    ExtendedPreferenceSchema,
    ValidatorSchema,
    StoreSchema,
    ProcessorSchema
)

__all__ = [
    # Core Components
    'PreferenceStore',
    
    # Models
    'Preference',
    'PreferenceCategory',
    'PreferenceType',
    'PreferenceValue',
    'PreferenceMetadata',
    'PreferenceValidationResult',
    
    # Processing Components
    'PreferenceProcessor',
    'PreferenceContext',
    'PreferenceRelation',
    
    # Schemas
    'PreferenceSchema',
    'CategorySchema',
    'ExtendedPreferenceSchema',
    'ValidatorSchema',
    'StoreSchema',
    'ProcessorSchema',
    
    # Exceptions
    'PreferenceError',
    'ValidationError',
    'StorageError',
    'PreferenceNotFoundError',
    'CategoryNotFoundError',
    'InvalidPreferenceError',
    'ConflictError'
]
