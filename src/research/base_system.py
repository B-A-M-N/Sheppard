"""
Base system class and core functionality for research operations.
File: src/research/base_system.py
"""

import logging
from typing import Optional, Dict, Any
from datetime import datetime

from src.research.exceptions import ResearchError
from src.research.models import ResearchConfig

logger = logging.getLogger(__name__)

class BaseResearchSystem:
    """Base class for research system functionality."""
    
    def __init__(
        self,
        memory_manager=None,
        ollama_client=None,
        config=None
    ):
        """Initialize base research system."""
        self.memory_manager = memory_manager
        self.ollama_client = ollama_client
        self.config = config or ResearchConfig()
        
        # Initialize components
        self.browser = None
        self.initialized = False
        self.active_research = False
        
        # Configure settings
        self._init_settings()
    
    def _init_settings(self):
        """Initialize system settings from config."""
        # Default values
        self.max_retries = 3
        self.retry_delay = 2.0
        self.max_pages = 5
        self.min_reliability = 0.7
        self.chunk_size = 1000
        self.chunk_overlap = 100

        # Update from config if available
        if hasattr(self.config, 'max_retries'):
            self.max_retries = self.config.max_retries
        if hasattr(self.config, 'retry_delay'):
            self.retry_delay = self.config.retry_delay
        if hasattr(self.config, 'max_pages'):
            self.max_pages = self.config.max_pages
        if hasattr(self.config, 'min_reliability'):
            self.min_reliability = self.config.min_reliability
        if hasattr(self.config, 'chunk_size'):
            self.chunk_size = self.config.chunk_size
        if hasattr(self.config, 'chunk_overlap'):
            self.chunk_overlap = self.config.chunk_overlap
    
    async def initialize(self) -> None:
        """Initialize base system components."""
        try:
            # This method is intended to be overridden by subclasses
            # The base implementation just sets the initialized flag
            self.initialized = True
            logger.info("Base research system initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize base research system: {str(e)}")
            await self.cleanup()
            raise
    
    async def cleanup(self) -> None:
        """Clean up system resources."""
        try:
            # Reset state
            self.initialized = False
            self.active_research = False
            logger.info("Base system cleanup completed")
        except Exception as e:
            logger.error(f"Error during cleanup: {str(e)}")
    
    def is_initialized(self) -> bool:
        """Check if system is initialized."""
        return self.initialized
    
    def is_active(self) -> bool:
        """Check if research is active."""
        return self.active_research
    
    def __str__(self) -> str:
        """Get string representation."""
        status = "initialized" if self.initialized else "not initialized"
        state = "active" if self.active_research else "inactive"
        return f"{self.__class__.__name__}({status}, {state})"
