"""
Component factory to avoid circular imports and implement lazy loading.
"""

import logging
from typing import Dict, Any, Optional, Type

logger = logging.getLogger(__name__)

class ResearchComponentFactory:
    """Factory for lazily creating research components."""
    
    _components: Dict[str, Any] = {}
    
    @classmethod
    def get_browser_manager(cls, config=None):
        """Get or create browser manager instance."""
        if "browser_manager" not in cls._components:
            from src.research.browser_manager import BrowserManager
            cls._components["browser_manager"] = BrowserManager(config=config)
        return cls._components["browser_manager"]
    
    @classmethod
    def get_task_manager(cls, memory_manager=None, ollama_client=None, config=None):
        """Get or create task manager instance."""
        if "task_manager" not in cls._components:
            from src.research.task_manager import ResearchTaskManager
            cls._components["task_manager"] = ResearchTaskManager(
                memory_manager=memory_manager,
                ollama_client=ollama_client,
                max_concurrent_tasks=getattr(config, 'max_concurrent_tasks', 5) if config else 5,
                task_timeout=getattr(config, 'task_timeout', 300) if config else 300,
                results_dir=getattr(config, 'results_dir', None) if config else None
            )
        return cls._components["task_manager"]
    
    @classmethod
    def get_content_processor(cls, ollama_client=None, firecrawl_config=None):
        """Get or create content processor instance."""
        if "content_processor" not in cls._components:
            from src.research.content_processor import ContentProcessor
            cls._components["content_processor"] = ContentProcessor(
                ollama_client=ollama_client,
                firecrawl_config=firecrawl_config
            )
        return cls._components["content_processor"]
        
    @classmethod
    def get_research_system(cls):
        """Get or create research system instance."""
        if "research_system" not in cls._components:
            from src.research.system import ResearchSystem
            cls._components["research_system"] = ResearchSystem()
        return cls._components["research_system"]
    
    @classmethod
    def cleanup_all(cls):
        """Cleanup all components."""
        for component in cls._components.values():
            if hasattr(component, 'cleanup') and callable(component.cleanup):
                component.cleanup()
        cls._components.clear()
