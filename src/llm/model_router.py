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
    temperature: float = 0.4

class ModelRouter:
    def __init__(self):
        # Default mapping using your local models
        from src.config.settings import settings
        chat_model = settings.OLLAMA_MODEL
        embed_model = settings.OLLAMA_EMBED_MODEL
        
        self._map: Dict[TaskType, ModelConfig] = {
            TaskType.CHAT: ModelConfig(chat_model, 0.7),
            TaskType.EMBEDDING: ModelConfig(embed_model, 0),
            TaskType.SUMMARIZATION: ModelConfig(chat_model, 0.3),
            TaskType.SYNTHESIS: ModelConfig(chat_model, 0.4),
            TaskType.CONTRADICTION_DETECTION: ModelConfig(chat_model, 0.1),
            TaskType.EXTRACT_ATOMS: ModelConfig(chat_model, 0.2),
            TaskType.DECOMPOSITION: ModelConfig(chat_model, 0.2),
            TaskType.QUERY_EXPANSION: ModelConfig(chat_model, 0.5),
        }

    def get(self, task: TaskType) -> ModelConfig:
        return self._map.get(task, self._map[TaskType.CHAT])

    def get_model_name(self, task: TaskType) -> str:
        return self.get(task).model_name

    def summary(self) -> dict:
        return {task.value: cfg.model_name for task, cfg in self._map.items()}
