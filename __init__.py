# src/__init__.py
"""
Chat system with memory integration and preference management.
"""

__version__ = "0.2.0"
__description__ = "A chat system with persistent memory and LLM integration."

from src.core import ChatApp
from src.config import settings, setup_logging

__all__ = [
    'ChatApp',
    'settings',
    'setup_logging',
]
