"""
Centralized configuration management for Sheppard V3.

All configurable values should be defined here with environment variable overrides.
This eliminates hardcoded values scattered throughout the codebase.
"""
import os
from typing import Optional
from dataclasses import dataclass, field
from pydantic_settings import BaseSettings
from pydantic import Field


class SheppardSettings(BaseSettings):
    """
    Centralized settings for Sheppard V3.
    
    All settings can be overridden via environment variables.
    Example: SHEPPARD_FIRECRAWL_URL=http://localhost:3002
    """
    
    # =========================================================================
    # External Service URLs
    # =========================================================================
    
    # Firecrawl (web scraping)
    firecrawl_url: str = Field(
        default="http://127.0.0.1:3002",
        env="SHEPPARD_FIRECRAWL_URL",
        description="Firecrawl local instance URL"
    )
    
    # Firecrawl extraction model (for markdown extraction)
    firecrawl_model: str = Field(
        default="qwen2.5-7b",
        env="SHEPPARD_FIRECRAWL_MODEL",
        description="Model used by Firecrawl for content extraction"
    )
    
    # SearXNG (metasearch)
    searxng_url: str = Field(
        default="http://127.0.0.1:8080",
        env="SHEPPARD_SEARXNG_URL",
        description="SearXNG local instance URL"
    )
    
    # Ollama (LLM inference)
    ollama_chat_url: str = Field(
        default="http://127.0.0.1:11434",
        env="SHEPPARD_OLLAMA_CHAT_URL",
        description="Ollama chat endpoint URL"
    )
    ollama_embed_url: str = Field(
        default="http://127.0.0.1:11434",
        env="SHEPPARD_OLLAMA_EMBED_URL",
        description="Ollama embedding endpoint URL"
    )
    
    # =========================================================================
    # Model Configuration
    # =========================================================================
    
    # Embedding model
    embedding_model: str = Field(
        default="mxbai-embed-large",
        env="SHEPPARD_EMBEDDING_MODEL",
        description="Model for generating embeddings"
    )
    
    # Chat model
    chat_model: str = Field(
        default="llama3.1:8b",
        env="SHEPPARD_CHAT_MODEL",
        description="Default model for chat/synthesis"
    )
    
    # Synthesis model (can be higher quality)
    synthesis_model: str = Field(
        default="llama3.1:8b",
        env="SHEPPARD_SYNTHESIS_MODEL",
        description="Model for synthesis tasks"
    )
    
    # =========================================================================
    # Scraping Configuration
    # =========================================================================
    
    # Worker configuration
    vampire_workers: int = Field(
        default=8,
        env="SHEPPARD_VAMPIRE_WORKERS",
        ge=1,
        le=32,
        description="Number of concurrent scraping workers"
    )
    
    # Scraping depth
    max_scrape_depth: int = Field(
        default=5,
        env="SHEPPARD_MAX_SCRAPE_DEPTH",
        ge=1,
        le=10,
        description="Maximum recursive link discovery depth"
    )
    
    # Retry configuration
    max_retries: int = Field(
        default=3,
        env="SHEPPARD_MAX_RETRIES",
        ge=1,
        le=10,
        description="Maximum retry attempts for failed operations"
    )
    
    retry_backoff_base: float = Field(
        default=1.0,
        env="SHEPPARD_RETRY_BACKOFF_BASE",
        ge=0.5,
        le=5.0,
        description="Base seconds for exponential backoff"
    )
    
    # =========================================================================
    # Knowledge Pipeline Configuration
    # =========================================================================
    
    # Condensation batch size
    condensation_batch_size: int = Field(
        default=5,
        env="SHEPPARD_CONDENSATION_BATCH_SIZE",
        ge=1,
        le=20,
        description="Number of sources to process per condensation batch"
    )
    
    # Knowledge atom extraction
    atom_confidence_threshold: float = Field(
        default=0.7,
        env="SHEPPARD_ATOM_CONFIDENCE_THRESHOLD",
        ge=0.0,
        le=1.0,
        description="Minimum confidence for extracted atoms"
    )
    
    # =========================================================================
    # Database Configuration
    # =========================================================================
    
    # PostgreSQL
    postgres_url: str = Field(
        default="postgresql://sheppard:1234@localhost:5432/sheppard_v3",
        env="SHEPPARD_POSTGRES_URL",
        description="PostgreSQL connection URL"
    )
    postgres_pool_size: int = Field(
        default=10,
        env="SHEPPARD_POSTGRES_POOL_SIZE",
        ge=1,
        le=50,
        description="PostgreSQL connection pool size"
    )
    
    # Redis
    redis_url: str = Field(
        default="redis://localhost:6379/0",
        env="SHEPPARD_REDIS_URL",
        description="Redis connection URL"
    )
    
    # ChromaDB
    chroma_persist_dir: str = Field(
        default="./chroma_storage",
        env="SHEPPARD_CHROMA_PERSIST_DIR",
        description="ChromaDB persistence directory"
    )
    
    # =========================================================================
    # Mission Configuration
    # =========================================================================
    
    # Budget defaults
    default_budget_bytes: int = Field(
        default=10_000_000,  # 10MB
        env="SHEPPARD_DEFAULT_BUDGET_BYTES",
        ge=1_000_000,
        le=100_000_000,
        description="Default mission byte budget"
    )
    
    # Saturation threshold
    saturation_threshold: int = Field(
        default=50_000,  # 50KB
        env="SHEPPARD_SATURATION_THRESHOLD",
        ge=10_000,
        le=1_000_000,
        description="Bytes threshold for mission saturation"
    )
    
    # =========================================================================
    # Retrieval Configuration
    # =========================================================================
    
    # Retrieval limits
    max_retrieval_results: int = Field(
        default=12,
        env="SHEPPARD_MAX_RETRIEVAL_RESULTS",
        ge=5,
        le=50,
        description="Maximum number of retrieval results"
    )
    
    max_definitions: int = Field(
        default=3,
        env="SHEPPARD_MAX_DEFINITIONS",
        ge=1,
        le=10,
        description="Maximum definition items in retrieval"
    )
    
    max_evidence: int = Field(
        default=5,
        env="SHEPPARD_MAX_EVIDENCE",
        ge=1,
        le=20,
        description="Maximum evidence items in retrieval"
    )
    
    max_contradictions: int = Field(
        default=2,
        env="SHEPPARD_MAX_CONTRADICTIONS",
        ge=0,
        le=10,
        description="Maximum contradiction items in retrieval"
    )
    
    # =========================================================================
    # Health Monitoring
    # =========================================================================
    
    # Circuit breaker settings
    circuit_breaker_failure_threshold: int = Field(
        default=5,
        env="SHEPPARD_CB_FAILURE_THRESHOLD",
        ge=3,
        le=20,
        description="Failures before circuit breaker opens"
    )
    
    circuit_breaker_recovery_timeout: float = Field(
        default=30.0,
        env="SHEPPARD_CB_RECOVERY_TIMEOUT",
        ge=5.0,
        le=120.0,
        description="Seconds before circuit breaker tries again"
    )
    
    circuit_breaker_success_threshold: int = Field(
        default=2,
        env="SHEPPARD_CB_SUCCESS_THRESHOLD",
        ge=1,
        le=10,
        description="Successes needed to close circuit breaker"
    )
    
    # Health check interval
    health_check_interval: float = Field(
        default=30.0,
        env="SHEPPARD_HEALTH_CHECK_INTERVAL",
        ge=5.0,
        le=120.0,
        description="Seconds between health checks"
    )
    
    # =========================================================================
    # SearXNG Search Engine Configuration
    # =========================================================================

    # General search engines
    searxng_general_engines: list[str] = Field(
        default_factory=lambda: ["bing", "qwant", "brave", "duckduckgo"],
        env="SHEPPARD_SEARXNG_GENERAL_ENGINES",
        description="General web search engines enabled in SearXNG"
    )

    # Academic search engines
    searxng_academic_engines: list[str] = Field(
        default_factory=lambda: [
            "google_scholar", "arxiv", "pubmed", "semantic_scholar",
            "crossref", "core", "base"
        ],
        env="SHEPPARD_SEARXNG_ACADEMIC_ENGINES",
        description="Academic/scholarly search engines enabled in SearXNG"
    )

    # Combined engines list (auto-generated, do not override)
    @property
    def searxng_all_engines(self) -> str:
        """Comma-separated string of all enabled engines for SearXNG queries."""
        all_engines = self.searxng_academic_engines + self.searxng_general_engines
        return ",".join(all_engines)

    # =========================================================================
    # Academic Filter Configuration
    # =========================================================================
    
    academic_whitelist_domains: list[str] = Field(
        default_factory=lambda: [
            ".edu", ".gov", ".ac.uk", ".ac.jp", ".edu.au",
            "arxiv.org", "nature.com", "ieee.org", "pubmed.ncbi.nlm.nih.gov",
            "scholar.google.com", "jstor.org", "springer.com",
            "sciencedirect.com", "tandfonline.com", "wiley.com"
        ],
        env="SHEPPARD_ACADEMIC_DOMAINS",
        description="Trusted academic domains"
    )
    
    # =========================================================================
    # Logging Configuration
    # =========================================================================
    
    log_level: str = Field(
        default="INFO",
        env="SHEPPARD_LOG_LEVEL",
        description="Logging level (DEBUG, INFO, WARNING, ERROR)"
    )
    
    log_format: str = Field(
        default="json",
        env="SHEPPARD_LOG_FORMAT",
        description="Log format (json, text)"
    )
    
    class Config:
        env_prefix = "SHEPPARD_"
        case_sensitive = False


# Global settings instance (lazy loaded)
_settings: Optional[SheppardSettings] = None


def get_settings() -> SheppardSettings:
    """Get global settings instance (singleton pattern)."""
    global _settings
    if _settings is None:
        _settings = SheppardSettings()
    return _settings


def reload_settings() -> SheppardSettings:
    """Reload settings from environment (useful for testing)."""
    global _settings
    _settings = SheppardSettings()
    return _settings


# Convenience access
settings = SheppardSettings()
