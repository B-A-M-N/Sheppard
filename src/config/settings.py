"""
Application settings with enhanced configuration management.
File: src/config/settings.py
"""

import os
from typing import Dict, Any, Optional
from pathlib import Path
from dotenv import load_dotenv
import logging

logger = logging.getLogger(__name__)

# Load environment variables with override=True to prioritize .env over shell env
load_dotenv(override=True)

# Get project root directory
PROJECT_ROOT = Path(__file__).parent.parent.parent

class Settings:
    """Application settings and configuration."""
    
    def __init__(self):
        """Initialize settings."""
        # Model Settings
        self.OLLAMA_MODEL: str = os.getenv('OLLAMA_MODEL', 'rnj-1:8b')
        self.OLLAMA_EMBED_MODEL: str = os.getenv('OLLAMA_EMBED_MODEL', 'mxbai-embed-large:latest')
        
        # Embedding Settings
        self.EMBEDDING_DIMENSION: int = 1024  # Fixed dimension for mxbai-embed-large
        self.EMBEDDING_BATCH_SIZE: int = 32
        self.EMBEDDING_MAX_LENGTH: int = 8192
        
        # API Settings
        self.OLLAMA_API_HOST: str = os.getenv('OLLAMA_API_HOST', 'http://localhost')
        self.OLLAMA_EMBED_HOST: str = os.getenv('OLLAMA_EMBED_HOST', self.OLLAMA_API_HOST)
        self.OLLAMA_API_PORT: str = os.getenv('OLLAMA_API_PORT', '11434')

        # Multi-host routing: each falls back to OLLAMA_API_HOST if not set.
        # Single-machine setups work without setting any of these.
        _api = self.OLLAMA_API_HOST
        self.OLLAMA_REASONING_HOST: str = os.getenv('OLLAMA_REASONING_HOST', _api)
        self.OLLAMA_EXTRACTION_HOST: str = os.getenv('OLLAMA_EXTRACTION_HOST', _api)
        self.OLLAMA_SUMMARIZE_HOST: str = os.getenv('OLLAMA_SUMMARIZE_HOST', _api)

        # Per-role model overrides — fall back to OLLAMA_MODEL if not set.
        # Lets extraction_host run a different (already-available) model without
        # requiring the same model be pulled on every machine.
        _model = self.OLLAMA_MODEL
        self.OLLAMA_EXTRACTION_MODEL: str = os.getenv('OLLAMA_EXTRACTION_MODEL', _model)
        self.OLLAMA_SUMMARIZE_MODEL: str = os.getenv('OLLAMA_SUMMARIZE_MODEL', 'llama3.2:latest')
        
        # Storage Settings
        self.REDIS_HOST: str = os.getenv('REDIS_HOST', 'localhost')
        self.REDIS_PORT: int = int(os.getenv('REDIS_PORT', 6379))
        self.REDIS_DB: int = int(os.getenv('REDIS_DB', 0))
        self.REDIS_PREFIX: str = 'sheppard:'
        
        # ChromaDB Settings
        self.CHROMADB_PERSIST_DIRECTORY: str = os.getenv(
            'CHROMADB_PERSIST_DIRECTORY', 
            str(PROJECT_ROOT / 'chroma_storage')
        )
        self.CHROMADB_COLLECTION_NAME: str = os.getenv(
            'CHROMADB_COLLECTION_NAME',
            'chat_memories'
        )
        self.CHROMADB_DISTANCE_FUNC: str = "cosine"  # Options: cosine, l2, ip
        
        # Memory Settings
        self.MEMORY_RELEVANCE_COUNT: int = int(os.getenv('MEMORY_RELEVANCE_COUNT', 5))
        self.MEMORY_MIN_RELEVANCE: float = float(os.getenv('MEMORY_MIN_RELEVANCE', 0.7))
        self.MEMORY_MAX_LENGTH: int = int(os.getenv('MEMORY_MAX_LENGTH', 10000))
        self.MEMORY_CACHE_SIZE: int = int(os.getenv('MEMORY_CACHE_SIZE', 1000))
        
        # File and Directory Settings - Use PROJECT_ROOT
        self.SCREENSHOT_DIR: str = os.getenv('SCREENSHOT_DIR', str(PROJECT_ROOT / 'screenshots'))
        self.LOG_DIR: str = os.getenv('LOG_DIR', str(PROJECT_ROOT / 'logs'))
        self.DATA_DIR: str = os.getenv('DATA_DIR', str(PROJECT_ROOT / 'data'))
        self.TEMP_DIR: str = os.getenv('TEMP_DIR', str(PROJECT_ROOT / 'temp'))
        
        # Model Configuration
        self.MODELS = {
            "chat": {
                "default": "rnj-1:8b-cloud",
                "alternatives": [
                    "rnj-1:8b-cloud",
                    "rnj-1:8b",
                    "llama3:latest",
                    "mistral-nemo-instruct-2407-abliterated:IQ3_M"
                ]
            },
            "embedding": {
                "default": "mxbai-embed-large:latest",
                "alternatives": [
                    "mxbai-embed-large:latest",
                    "nomic-embed-text"
                ]
            }
        }
        
        # LLM Settings
        self.DEFAULT_TEMPERATURE: float = 0.7
        self.DEFAULT_TOP_P: float = 0.9
        self.MAX_TOKENS: int = 2048
        self.CONTEXT_WINDOW: int = 4096
        
        # GPU Settings
        self.GPU_ENABLED: bool = os.getenv('GPU_ENABLED', 'true').lower() == 'true'
        self.GPU_LAYERS: int = int(os.getenv('GPU_LAYERS', '32'))
        self.NUM_GPU: int = int(os.getenv('NUM_GPU', '1'))
        self.F16: bool = os.getenv('F16', 'true').lower() == 'true'
        
        # Timeouts and Limits (Optimized for slow local inference)
        self.REQUEST_TIMEOUT: int = int(os.getenv('REQUEST_TIMEOUT', 900))  # 15 minutes
        self.CONNECTION_TIMEOUT: int = int(os.getenv('CONNECTION_TIMEOUT', 120))  # 2 minutes
        self.MAX_RETRIES: int = int(os.getenv('MAX_RETRIES', 5))
        self.RETRY_DELAY: float = float(os.getenv('RETRY_DELAY', '5.0'))  # seconds
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get a setting value by key with optional default."""
        return getattr(self, key, default)
    
    @property
    def redis_url(self) -> str:
        """Get the Redis connection URL."""
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}"
    
    @property
    def ollama_api_base(self) -> str:
        """Get the Ollama API base URL."""
        return f"{self.OLLAMA_API_HOST}:{self.OLLAMA_API_PORT}"
    
    @property
    def gpu_config(self) -> Dict[str, Any]:
        """Get the current GPU configuration."""
        if not self.GPU_ENABLED:
            return {
                'num_gpu': 0,
                'gpu_layers': 0,
                'f16': False,
                'numa': False
            }
        
        return {
            'num_gpu': self.NUM_GPU,
            'gpu_layers': self.GPU_LAYERS,
            'f16': self.F16,
            'numa': False  # NUMA support not enabled by default
        }

# Create global settings instance
settings = Settings()

# Export settings instance and class
__all__ = ['settings', 'Settings']
