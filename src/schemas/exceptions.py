"""
Schema-specific exceptions.
"""

class SchemaError(Exception):
    """Base exception for schema-related errors."""
    def __init__(self, message: str = "Schema operation failed"):
        super().__init__(f"Schema Error: {message}")

class ValidationError(SchemaError):
    """Raised when schema validation fails."""
    def __init__(self, message: str = "Validation failed"):
        super().__init__(f"Validation Error: {message}")

class ProcessingError(SchemaError):
    """Raised when schema processing fails."""
    def __init__(self, message: str = "Processing failed"):
        super().__init__(f"Processing Error: {message}")
