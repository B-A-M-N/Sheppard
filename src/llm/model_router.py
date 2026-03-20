"""
llm/model_router.py — Sheppard V2 Model Router

Task → Model assignment.
"""

import os
from enum import Enum
from dataclasses import dataclass
from typing import Dict

class TaskType(Enum):
    CHAT = "chat"
    EMBEDDING = "embedding"
    SUMMARIZATION = "summarization"
    SYNTHESIS = "synthesis"
    CONTRADICTION_DETECTION = "contradiction"
    EXTRACT_ATOMS = "extraction"
    DECOMPOSITION = "decomposition"
    QUERY_EXPANSION = "expansion"

@dataclass
class ModelConfig:
    model_name: str
    api_host: str
    temperature: float = 0.4

class ModelRouter:
    def __init__(self):
        from src.config.settings import settings
        
        # Define the physical locations of your hardware
        remote_host = "http://10.9.66.90:11434"
        local_host = "http://127.0.0.1:11434"
        lazy_scout_host = "http://10.9.66.45:11434"
        vampire_scout_host = "http://10.9.66.154:11434"
        
        # Explicit Task-to-Model Taxonomy
        chat_model = "mannix/llama3.1-8b-lexi:latest"  # The new uncensored reasoner
        synth_model = "mannix/llama3.1-8b-lexi:latest" # VRAM accelerated extraction
        summarize_model = "llama3.2:latest"            # Fast summarization
        embed_model = settings.OLLAMA_EMBED_MODEL
        
        self._map: Dict[TaskType, ModelConfig] = {
            # Heavy reasoning goes to the powerful remote brain (.90)
            TaskType.CHAT: ModelConfig(chat_model, remote_host, 0.7),
            TaskType.SYNTHESIS: ModelConfig(synth_model, remote_host, 0.4),
            TaskType.CONTRADICTION_DETECTION: ModelConfig(synth_model, remote_host, 0.1),
            TaskType.EXTRACT_ATOMS: ModelConfig(synth_model, remote_host, 0.1),
            TaskType.DECOMPOSITION: ModelConfig(chat_model, remote_host, 0.2),
            TaskType.QUERY_EXPANSION: ModelConfig(chat_model, remote_host, 0.5),
            
            # Fast, distributed tasks
            TaskType.SUMMARIZATION: ModelConfig(summarize_model, vampire_scout_host, 0.3),
            TaskType.EMBEDDING: ModelConfig(embed_model, local_host, 0.0),
        }

    def get(self, task: TaskType) -> ModelConfig:
        return self._map.get(task, self._map[TaskType.CHAT])

    def get_model_name(self, task: TaskType) -> str:
        return self.get(task).model_name

    def summary(self) -> dict:
        return {task.value: cfg.model_name for task, cfg in self._map.items()}
