"""
Firecrawl integration configuration.
File: src/research/models/firecrawl_config.py
"""

from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional
from pathlib import Path

@dataclass
class FirecrawlConfig:
    """Configuration for Firecrawl integration."""
    
    api_key: str = field(default="")
    base_url: str = "https://api.firecrawl.dev"
    version: str = "v1"
    formats: List[str] = field(default_factory=lambda: ["markdown"])
    max_pages: int = 100
    timeout: int = 300
    poll_interval: int = 30
    exclude_paths: List[str] = field(default_factory=list)
    
    # Request configuration
    request_headers: Dict[str, str] = field(default_factory=lambda: {
        "User-Agent": "Sheppard-Research-Bot/1.0",
        "Accept": "application/json"
    })
    
    # Scraping options
    scrape_options: Dict[str, Any] = field(default_factory=lambda: {
        "waitFor": 2000,
        "timeout": 30000,
        "removeScripts": True,
        "removeStyles": True,
        "removeTracking": True
    })
    
    # Retry configuration
    retries: int = 3
    retry_delay: float = 1.0
    concurrent_limit: int = 5
    
    # Output configuration
    markdown_options: Dict[str, Any] = field(default_factory=lambda: {
        "removeImages": False,
        "removeLinks": False,
        "cleanupFormatting": True,
        "preserveHeaderHierarchy": True
    })
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to dictionary."""
        return {
            "api_key": self.api_key,
            "base_url": self.base_url,
            "version": self.version,
            "formats": self.formats,
            "max_pages": self.max_pages,
            "timeout": self.timeout,
            "poll_interval": self.poll_interval,
            "exclude_paths": self.exclude_paths,
            "request_headers": self.request_headers,
            "scrape_options": self.scrape_options,
            "retries": self.retries,
            "retry_delay": self.retry_delay,
            "concurrent_limit": self.concurrent_limit,
            "markdown_options": self.markdown_options
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'FirecrawlConfig':
        """Create configuration from dictionary."""
        return cls(**data)
