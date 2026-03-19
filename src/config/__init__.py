# src/config/__init__.py
"""
Configuration management for the chat system.
"""

from .settings import settings, Settings
from .logging import setup_logging, get_logger

# Define version and metadata
__version__ = "0.2.0"
__description__ = "Enhanced chat system with research capabilities"

# Export API
__all__ = [
    # Settings
    'settings',
    'Settings',
    
    # Logging
    'setup_logging',
    'get_logger',
    
    # Version Info
    '__version__',
    '__description__'
]
