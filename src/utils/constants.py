"""
Constants for system configuration and behavior.
File: src/utils/constants.py
"""

from src.research.models import ResponseType

# Message limits
MAX_MESSAGE_LENGTH = 10000
MAX_CONTEXT_MESSAGES = 100

# Response settings
DEFAULT_RESPONSE_TYPE = ResponseType.NORMAL

# Persona identifiers
SYSTEM_PERSONA_ID = "system"

# Content limits
MAX_CONTENT_LENGTH = 100000
MIN_CONTENT_LENGTH = 10

# Memory settings
MAX_MEMORY_RESULTS = 50
DEFAULT_SIMILARITY_THRESHOLD = 0.7

# System timeouts
DEFAULT_TIMEOUT = 30  # seconds
LONG_OPERATION_TIMEOUT = 60  # seconds

# File operations
ALLOWED_EXTENSIONS = [".txt", ".md", ".json", ".csv"]
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB

# Security
TOKEN_EXPIRY = 86400  # 24 hours in seconds
