"""
Utility functions and classes.
"""

# Export validation functions
from .validation import (
    validate_message_content,
    validate_metadata,
    validate_user_preferences
)

# Export any other utilities
from .validation import (
    validate_content,
    validate_embedding,
    validate_memory_content,
    validate_file_path,
    validate_url,
    validate_timestamp,
    validate_dict_fields,
    sanitize_filename
)

# Export text processing functions if they exist
try:
    from .text_processing import (
        sanitize_text,
        clean_string
    )
except ImportError:
    # Define fallbacks if needed
    def sanitize_text(text):
        """Fallback sanitize text function."""
        return text.strip() if text else ""
        
    def clean_string(text):
        """Fallback clean string function."""
        return text.strip() if text else ""

# Export all available utilities
__all__ = [
    # Validators
    'validate_message_content',
    'validate_metadata',
    'validate_user_preferences',
    
    # Validation
    'validate_content',
    'validate_embedding',
    'validate_memory_content',
    'validate_file_path',
    'validate_url',
    'validate_timestamp',
    'validate_dict_fields',
    'sanitize_filename',
    
    # Text processing
    'sanitize_text',
    'clean_string'
]
