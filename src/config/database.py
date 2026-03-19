# src/config/database.py

import os
from pathlib import Path
from typing import Dict, Any

# Base directory setup
ROOT_DIR = Path(__file__).parent.parent.parent.absolute()
DATA_DIR = os.path.join(ROOT_DIR, 'data')
LOGS_DIR = os.path.join(ROOT_DIR, 'logs')

class DatabaseConfig:
    """Database configuration settings"""
    
    # Ensure required directories exist
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(LOGS_DIR, exist_ok=True)
    
    # Directory paths
    CONVERSATIONS_DIR = os.path.join(DATA_DIR, 'conversations')
    CHROMA_DIR = os.path.join(DATA_DIR, 'chroma_persistence')
    EMBEDDINGS_DIR = os.path.join(DATA_DIR, 'embeddings')
    STATS_DIR = os.path.join(DATA_DIR, 'stats')
    TOOLS_DIR = os.path.join(DATA_DIR, 'tools')
    MEMORY_DIR = os.path.join(DATA_DIR, 'memory')
    
    # Create subdirectories
    os.makedirs(CONVERSATIONS_DIR, exist_ok=True)
    os.makedirs(CHROMA_DIR, exist_ok=True)
    os.makedirs(EMBEDDINGS_DIR, exist_ok=True)
    os.makedirs(STATS_DIR, exist_ok=True)
    os.makedirs(TOOLS_DIR, exist_ok=True)
    os.makedirs(MEMORY_DIR, exist_ok=True)

    # Memory layer directories
    MEMORY_LAYERS = {
        "episodic": os.path.join(MEMORY_DIR, 'episodic'),
        "semantic": os.path.join(MEMORY_DIR, 'semantic'),
        "contextual": os.path.join(MEMORY_DIR, 'contextual'),
        "general": os.path.join(MEMORY_DIR, 'general'),
        "abstracted": os.path.join(MEMORY_DIR, 'abstracted')
    }
    
    # Create memory layer directories
    for directory in MEMORY_LAYERS.values():
        os.makedirs(directory, exist_ok=True)

    # PostgreSQL database URLs
    DB_URLS = {
        "episodic_memory": "postgresql://sheppard:1234@localhost:5432/episodic_memory",
        "semantic_memory": "postgresql://sheppard:1234@localhost:5432/semantic_memory",
        "contextual_memory": "postgresql://sheppard:1234@localhost:5432/contextual_memory",
        "general_memory": "postgresql://sheppard:1234@localhost:5432/general_memory",
        "abstracted_memory": "postgresql://sheppard:1234@localhost:5432/abstracted_memory"
    }

    # Redis configuration for different memory layers
    REDIS_CONFIG = {
        "ephemeral": {
            "host": "localhost",
            "port": 6370,
            "db": 0
        },
        "contextual": {
            "host": "localhost", 
            "port": 6371,
            "db": 0
        },
        "episodic": {
            "host": "localhost",
            "port": 6372,
            "db": 0
        },
        "semantic": {
            "host": "localhost",
            "port": 6373,
            "db": 0
        },
        "abstracted": {
            "host": "localhost",
            "port": 6374,
            "db": 0
        }
    }

    # Memory system configuration
    MEMORY_SYSTEMS = {
        "episodic": {
            "type": "long_term",
            "storage": ["postgresql", "redis", "vector"],
            "retention_period": 365,
            "importance_threshold": 0.3
        },
        "semantic": {
            "type": "long_term",
            "storage": ["postgresql", "redis", "vector"],
            "retention_period": None,
            "importance_threshold": 0.4
        },
        "contextual": {
            "type": "short_term",
            "storage": ["redis", "vector"],
            "retention_period": 1,
            "importance_threshold": 0.2
        },
        "working": {
            "type": "ephemeral",
            "storage": ["redis"],
            "retention_period": 0.042,
            "importance_threshold": 0.1
        }
    }

    # ChromaDB settings
    CHROMA_SETTINGS = {
        "persist_directory": CHROMA_DIR,
        "anonymized_telemetry": False,
        "allow_reset": True
    }

    # Connection pool settings
    POOL_SETTINGS = {
        "min_size": 5,
        "max_size": 20,
        "max_queries": 50000,
        "max_inactive_connection_lifetime": 300.0
    }

    # Query timeouts
    TIMEOUTS = {
        "connect": 5,
        "command": 30,
        "pool_timeout": 30
    }

    @classmethod
    def get_redis_url(cls, memory_type: str) -> str:
        """Get Redis URL for specific memory type"""
        config = cls.REDIS_CONFIG.get(memory_type)
        if config:
            return f"redis://{config['host']}:{config['port']}/{config['db']}"
        return ""

    @classmethod
    def get_memory_config(cls, memory_type: str) -> Dict[str, Any]:
        """Get configuration for specific memory type"""
        return cls.MEMORY_SYSTEMS.get(memory_type, {})

    @classmethod
    def get_storage_path(cls, memory_type: str) -> str:
        """Get storage path for specific memory type"""
        return cls.MEMORY_LAYERS.get(memory_type, "")
