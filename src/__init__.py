"""
Sheppard: Chat system with memory integration and research capabilities.
"""

__version__ = "0.2.0"
__description__ = "A chat system with persistent memory and LLM integration"
__author__ = "Your Name"

from src.core import ChatApp
from src.config import settings, setup_logging

__all__ = [
    'ChatApp',
    'settings',
    'setup_logging',
]
