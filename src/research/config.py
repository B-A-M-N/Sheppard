"""
Research system configuration with validation and error handling.
File: src/research/config.py
"""

import os
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List, Union, Set, Tuple
from pathlib import Path
from datetime import datetime
import logging
from enum import Enum

logger = logging.getLogger(__name__)

@dataclass
class BrowserConfig:
    """Browser configuration."""
    headless: bool = True
    window_size: tuple[int, int] = (1920, 1080)
    screenshot_dir: Optional[Path] = None
    download_dir: Optional[Path] = None
    timeout: int = 30
    retry_attempts: int = 3
    retry_delay: float = 1.0
    options: Dict[str, Any] = field(default_factory=lambda: {
        "no-sandbox": None,
        "disable-dev-shm-usage": None,
        "disable-gpu": None,
        "disable-extensions": None,
        "disable-notifications": None
    })
    request_headers: Dict[str, str] = field(default_factory=lambda: {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "DNT": "1"
    })

    def __post_init__(self):
        """Validate and initialize browser configuration."""
        if self.screenshot_dir is not None and isinstance(self.screenshot_dir, str):
            self.screenshot_dir = Path(self.screenshot_dir)
        if self.download_dir is not None and isinstance(self.download_dir, str):
            self.download_dir = Path(self.download_dir)
        
        # Validate timeout and retry settings
        if self.timeout < 0:
            raise ValueError("Timeout must be non-negative")
        if self.retry_attempts < 0:
            raise ValueError("Retry attempts must be non-negative")
        if self.retry_delay < 0:
            raise ValueError("Retry delay must be non-negative")

    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to dictionary."""
        return {
            'headless': self.headless,
            'window_size': self.window_size,
            'screenshot_dir': str(self.screenshot_dir) if self.screenshot_dir else None,
            'download_dir': str(self.download_dir) if self.download_dir else None,
            'timeout': self.timeout,
            'retry_attempts': self.retry_attempts,
            'retry_delay': self.retry_delay,
            'options': self.options,
            'request_headers': self.request_headers
        }

@dataclass
class NavigationConfig:
    """Navigation settings."""
    max_depth: int = 3
    follow_internal_links: bool = True
    follow_external_links: bool = False
    max_links_per_page: int = 20
    delay_between_requests: float = 0.5
    allowed_domains: Set[str] = field(default_factory=set)
    excluded_paths: Set[str] = field(default_factory=set)
    url_patterns: Set[str] = field(default_factory=set)
    requires_javascript: bool = False
    handle_redirects: bool = True
    respect_robots_txt: bool = True
    verify_ssl: bool = True

    def __post_init__(self):
        """Validate navigation configuration."""
        if self.max_depth < 1:
            raise ValueError("Maximum depth must be at least 1")
        if self.max_links_per_page < 1:
            raise ValueError("Maximum links per page must be at least 1")
        if self.delay_between_requests < 0:
            raise ValueError("Delay between requests must be non-negative")

    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to dictionary."""
        return {
            'max_depth': self.max_depth,
            'follow_internal_links': self.follow_internal_links,
            'follow_external_links': self.follow_external_links,
            'max_links_per_page': self.max_links_per_page,
            'delay_between_requests': self.delay_between_requests,
            'allowed_domains': list(self.allowed_domains),
            'excluded_paths': list(self.excluded_paths),
            'url_patterns': list(self.url_patterns),
            'requires_javascript': self.requires_javascript,
            'handle_redirects': self.handle_redirects,
            'respect_robots_txt': self.respect_robots_txt,
            'verify_ssl': self.verify_ssl
        }

@dataclass
class ScrapingConfig:
    """Web scraping settings."""
    user_agent: str = "Sheppard-Research-Bot/1.0"
    enable_javascript: bool = False
    extract_text_only: bool = True
    enable_images: bool = False
    enable_videos: bool = False
    max_scrape_time: int = 60
    wait_for_selectors: List[str] = field(default_factory=list)
    extract_metadata: bool = True
    preserve_formatting: bool = True
    remove_ads: bool = True
    remove_navigation: bool = True
    remove_social: bool = True
    extract_schema_org: bool = True
    extract_opengraph: bool = True
    extract_microdata: bool = True
    text_content_selectors: List[str] = field(default_factory=lambda: [
        "article", "main", "[role='main']",
        ".content", "#content", ".article"
    ])
    ignore_elements: Set[str] = field(default_factory=lambda: {
        "script", "style", "noscript", "iframe",
        "header", "footer", "nav", "aside"
    })

    def __post_init__(self):
        """Validate scraping configuration."""
        if self.max_scrape_time < 1:
            raise ValueError("Maximum scrape time must be at least 1 second")
        if not self.user_agent:
            raise ValueError("User agent cannot be empty")

    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to dictionary."""
        return {
            'user_agent': self.user_agent,
            'enable_javascript': self.enable_javascript,
            'extract_text_only': self.extract_text_only,
            'enable_images': self.enable_images,
            'enable_videos': self.enable_videos,
            'max_scrape_time': self.max_scrape_time,
            'wait_for_selectors': self.wait_for_selectors,
            'extract_metadata': self.extract_metadata,
            'preserve_formatting': self.preserve_formatting,
            'remove_ads': self.remove_ads,
            'remove_navigation': self.remove_navigation,
            'remove_social': self.remove_social,
            'extract_schema_org': self.extract_schema_org,
            'extract_opengraph': self.extract_opengraph,
            'extract_microdata': self.extract_microdata,
            'text_content_selectors': self.text_content_selectors,
            'ignore_elements': list(self.ignore_elements)
        }

@dataclass
class ContentProcessingConfig:
    """Content processing settings."""
    max_content_length: int = 1000000
    chunk_size: int = 1000
    chunk_overlap: int = 100
    min_chunk_length: int = 100
    extract_metadata: bool = True
    preserve_formatting: bool = True
    remove_duplicates: bool = True
    extract_citations: bool = True
    extract_quotes: bool = True
    extract_dates: bool = True
    extract_statistics: bool = True
    normalize_whitespace: bool = True
    strip_html: bool = True
    minimum_content_length: int = 50
    maximum_content_length: int = 100000
    summarization_params: Dict[str, Any] = field(default_factory=lambda: {
        'max_length': 1000,
        'min_length': 100,
        'do_sample': False
    })

    def __post_init__(self):
        """Validate content processing configuration."""
        if self.chunk_size < 1:
            raise ValueError("Chunk size must be at least 1")
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError("Chunk overlap must be less than chunk size")
        if self.min_chunk_length < 1:
            raise ValueError("Minimum chunk length must be at least 1")
        if self.minimum_content_length < 1:
            raise ValueError("Minimum content length must be at least 1")
        if self.maximum_content_length < self.minimum_content_length:
            raise ValueError("Maximum content length must be greater than minimum content length")

    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to dictionary."""
        return {
            'max_content_length': self.max_content_length,
            'chunk_size': self.chunk_size,
            'chunk_overlap': self.chunk_overlap,
            'min_chunk_length': self.min_chunk_length,
            'extract_metadata': self.extract_metadata,
            'preserve_formatting': self.preserve_formatting,
            'remove_duplicates': self.remove_duplicates,
            'extract_citations': self.extract_citations,
            'extract_quotes': self.extract_quotes,
            'extract_dates': self.extract_dates,
            'extract_statistics': self.extract_statistics,
            'normalize_whitespace': self.normalize_whitespace,
            'strip_html': self.strip_html,
            'minimum_content_length': self.minimum_content_length,
            'maximum_content_length': self.maximum_content_length,
            'summarization_params': self.summarization_params
        }

@dataclass
class FirecrawlConfig:
    """Firecrawl integration settings."""
    api_key: str = field(default_factory=lambda: os.getenv('FIRECRAWL_API_KEY', ''))
    base_url: str = "https://api.firecrawl.dev"
    version: str = "v1"
    formats: List[str] = field(default_factory=lambda: ["markdown"])
    max_pages: int = 100
    timeout: int = 300
    poll_interval: int = 30
    exclude_paths: List[str] = field(default_factory=list)
    request_headers: Dict[str, str] = field(default_factory=lambda: {
        "User-Agent": "Sheppard-Research-Bot/1.0",
        "Accept": "application/json"
    })
    scrape_options: Dict[str, Any] = field(default_factory=lambda: {
        "waitFor": 2000,
        "timeout": 30000,
        "removeScripts": True,
        "removeStyles": True,
        "removeTracking": True
    })
    retries: int = 3
    retry_delay: float = 1.0
    concurrent_limit: int = 5

    def __post_init__(self):
        """Validate Firecrawl configuration."""
        if self.max_pages < 1:
            raise ValueError("Maximum pages must be at least 1")
        if self.timeout < 1:
            raise ValueError("Timeout must be at least 1 second")
        if self.poll_interval < 1:
            raise ValueError("Poll interval must be at least 1 second")
        if self.retries < 0:
            raise ValueError("Retries must be non-negative")
        if self.retry_delay < 0:
            raise ValueError("Retry delay must be non-negative")
        if self.concurrent_limit < 1:
            raise ValueError("Concurrent limit must be at least 1")

    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to dictionary."""
        return {
            'api_key': self.api_key,
            'base_url': self.base_url,
            'version': self.version,
            'formats': self.formats,
            'max_pages': self.max_pages,
            'timeout': self.timeout,
            'poll_interval': self.poll_interval,
            'exclude_paths': self.exclude_paths,
            'request_headers': self.request_headers,
            'scrape_options': self.scrape_options,
            'retries': self.retries,
            'retry_delay': self.retry_delay,
            'concurrent_limit': self.concurrent_limit
        }

@dataclass
class ResearchConfig:
    """Main research system configuration."""
    browser: BrowserConfig = field(default_factory=BrowserConfig)
    navigation: NavigationConfig = field(default_factory=NavigationConfig)
    scraping: ScrapingConfig = field(default_factory=ScrapingConfig)
    content: ContentProcessingConfig = field(default_factory=ContentProcessingConfig)
    firecrawl: Optional[FirecrawlConfig] = None
    
    # System settings
    max_retries: int = 3
    retry_delay: float = 2.0
    max_pages: int = 5
    min_reliability: float = 0.7
    chunk_size: int = 1000
    chunk_overlap: int = 100
    max_concurrent_tasks: int = 5
    task_timeout: int = 600
    embed_findings: bool = True
    save_results: bool = True
    results_dir: Optional[Path] = None
    log_level: str = "INFO"
    auto_save_interval: int = 300  # 5 minutes
    max_memory_usage: int = 1024  # MB
    cleanup_interval: int = 3600  # 1 hour
    max_task_history: int = 1000
    enable_diagnostics: bool = True
    diagnostic_interval: int = 60  # 1 minute
    error_threshold: int = 5  # Max consecutive errors before fallback
    fallback_mode: bool = True
    recovery_delay: int = 300  # 5 minutes
    max_recovery_attempts: int = 3

    def __post_init__(self):
        """Validate and initialize research configuration."""
        # Validate system settings
        if self.max_retries < 0:
            raise ValueError("Maximum retries must be non-negative")
        if self.retry_delay < 0:
            raise ValueError("Retry delay must be non-negative")
        if self.max_pages < 1:
            raise ValueError("Maximum pages must be at least 1")
        if not (0 <= self.min_reliability <= 1):
            raise ValueError("Minimum reliability must be between 0 and 1")
        if self.chunk_size < 1:
            raise ValueError("Chunk size must be at least 1")
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError("Chunk overlap must be less than chunk size")
        if self.max_concurrent_tasks < 1:
            raise ValueError("Maximum concurrent tasks must be at least 1")
        if self.task_timeout < 1:
            raise ValueError("Task timeout must be at least 1 second")
        if self.auto_save_interval < 1:
            raise ValueError("Auto save interval must be at least 1 second")
        if self.max_memory_usage < 1:
            raise ValueError("Maximum memory usage must be at least 1 MB")
        if self.cleanup_interval < 1:
            raise ValueError("Cleanup interval must be at least 1 second")
        if self.max_task_history < 1:
            raise ValueError("Maximum task history must be at least 1")
        if self.diagnostic_interval < 1:
            raise ValueError("Diagnostic interval must be at least 1 second")
        if self.error_threshold < 1:
            raise ValueError("Error threshold must be at least 1")
        if self.recovery_delay < 1:
            raise ValueError("Recovery delay must be at least 1 second")
        if self.max_recovery_attempts < 0:
            raise ValueError("Maximum recovery attempts must be non-negative")

        # Convert paths
        if self.results_dir is not None and isinstance(self.results_dir, str):
            self.results_dir = Path(self.results_dir)

        # Validate log level
        valid_log_levels = {'DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'}
        if self.log_level.upper() not in valid_log_levels:
            raise ValueError(f"Invalid log level. Must be one of: {', '.join(valid_log_levels)}")

    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to dictionary."""
        return {
            'browser': self.browser.to_dict(),
            'navigation': self.navigation.to_dict(),
            'scraping': self.scraping.to_dict(),
            'content': self.content.to_dict(),
            'firecrawl': self.firecrawl.to_dict() if self.firecrawl else None,
            'max_retries': self.max_retries,
            'retry_delay': self.retry_delay,
            'max_pages': self.max_pages,
            'min_reliability': self.min_reliability,
            'chunk_size': self.chunk_size,
            'chunk_overlap': self.chunk_overlap,
            'max_concurrent_tasks': self.max_concurrent_tasks,
            'task_timeout': self.task_timeout,
            'embed_findings': self.embed_findings,
            'save_results': self.save_results,
            'results_dir': str(self.results_dir) if self.results_dir else None,
            'log_level': self.log_level,
            'auto_save_interval': self.auto_save_interval,
            'max_memory_usage': self.max_memory_usage,
            'cleanup_interval': self.cleanup_interval,
            'max_task_history': self.max_task_history,
            'enable_diagnostics': self.enable_diagnostics,
            'diagnostic_interval': self.diagnostic_interval,
            'error_threshold': self.error_threshold,
            'fallback_mode': self.fallback_mode,
            'recovery_delay': self.recovery_delay,
            'max_recovery_attempts': self.max_recovery_attempts
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ResearchConfig':
        """Create configuration from dictionary."""
        # Convert nested configurations
        if 'browser' in data:
            data['browser'] = BrowserConfig(**data['browser'])
        if 'navigation' in data:
            data['navigation'] = NavigationConfig(**data['navigation'])
        if 'scraping' in data:
            data['scraping'] = ScrapingConfig(**data['scraping'])
        if 'content' in data:
            data['content'] = ContentProcessingConfig(**data['content'])
        if 'firecrawl' in data and data['firecrawl']:
            data['firecrawl'] = FirecrawlConfig(**data['firecrawl'])
        
        return cls(**data)

    def validate(self) -> Tuple[bool, List[str]]:
        """
        Validate entire configuration.
        
        Returns:
            Tuple[bool, List[str]]: (is_valid, error_messages)
        """
        errors = []
        
        try:
            # Validate each component
            self.__post_init__()
        except ValueError as e:
            errors.append(str(e))

        # Check component relationships
        if self.chunk_overlap >= self.chunk_size:
            errors.append("Chunk overlap must be less than chunk size")

        if self.navigation.max_depth > 10 and not self.navigation.follow_external_links:
            errors.append("High depth crawling requires external link following")

        # Resource constraints
        if self.max_concurrent_tasks * self.max_memory_usage > 8192:  # 8GB limit
            errors.append("Total potential memory usage exceeds system limits")

        # Timing constraints
        if self.task_timeout <= self.recovery_delay:
            errors.append("Task timeout should be greater than recovery delay")

        return len(errors) == 0, errors

    def get_logging_config(self) -> Dict[str, Any]:
        """Get logging configuration."""
        return {
            'level': self.log_level,
            'format': '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            'datefmt': '%Y-%m-%d %H:%M:%S',
            'filename': str(self.results_dir / 'research.log') if self.results_dir else None,
            'filemode': 'a'
        }

    def get_resource_limits(self) -> Dict[str, Any]:
        """Get resource limitation settings."""
        return {
            'max_memory': self.max_memory_usage,
            'max_tasks': self.max_concurrent_tasks,
            'max_retries': self.max_retries,
            'timeout': self.task_timeout
        }

    def __str__(self) -> str:
        """Get string representation."""
        return (
            f"ResearchConfig("
            f"max_tasks={self.max_concurrent_tasks}, "
            f"reliability={self.min_reliability}, "
            f"fallback={'enabled' if self.fallback_mode else 'disabled'})"
        )
