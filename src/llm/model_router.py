"""
llm/model_router.py — Sheppard Model Router

Task → Model assignment.

Multi-machine routing is configured via environment variables:
  OLLAMA_API_HOST        — primary/fallback host (used when specialized hosts are not set)
  OLLAMA_REASONING_HOST  — synthesis, chat, contradiction (heavy reasoning)
  OLLAMA_EXTRACTION_HOST — extract_atoms, decomposition, query expansion (pipeline extraction)
  OLLAMA_SUMMARIZE_HOST  — summarization
  OLLAMA_EMBED_HOST      — embeddings (already exists)

Single-machine setup: set only OLLAMA_API_HOST. All tasks route there automatically.
Multi-machine setup: set the specialized hosts to spread work across machines.
"""

from enum import Enum
from dataclasses import dataclass
from typing import Dict, Optional


class TaskType(Enum):
    CHAT = "chat"
    EMBEDDING = "embedding"
    SUMMARIZATION = "summarization"
    SYNTHESIS = "synthesis"
    CONTRADICTION_DETECTION = "contradiction"
    EXTRACT_ATOMS = "extraction"
    DECOMPOSITION = "decomposition"
    QUERY_EXPANSION = "expansion"
    ANALYSIS = "analysis"      # Analyst: reason from evidence to a position + recommendation
    CRITIQUE = "critique"      # Adversarial Critic: challenge the Analyst's output


@dataclass
class ModelConfig:
    model_name: str
    api_host: str
    temperature: float = 0.4
    seed: Optional[int] = None


class ModelRouter:
    def __init__(self):
        from src.config.settings import settings

        def _host(raw: str) -> str:
            """Ensure host has a port number."""
            if not raw:
                return "http://localhost:11434"
            # If the part after the scheme has no colon, append default Ollama port
            scheme, _, rest = raw.partition("://")
            if ":" not in rest:
                return f"{raw}:11434"
            return raw

        reasoning_host  = _host(settings.OLLAMA_REASONING_HOST)
        extraction_host = _host(settings.OLLAMA_EXTRACTION_HOST)
        summarize_host  = _host(settings.OLLAMA_SUMMARIZE_HOST)
        embed_host      = _host(settings.OLLAMA_EMBED_HOST)

        # Reasoning model: the uncensored fine-tune for quality chat/synthesis
        reasoning_model  = "mannix/llama3.1-8b-lexi:latest"
        # Extraction model: configurable per host — local machine may have a different model
        # available. Falls back to OLLAMA_MODEL (rnj-1:8b-cloud) if not set in .env.
        extraction_model = settings.OLLAMA_EXTRACTION_MODEL
        summarize_model  = settings.OLLAMA_SUMMARIZE_MODEL
        embed_model      = settings.OLLAMA_EMBED_MODEL

        self._map: Dict[TaskType, ModelConfig] = {
            # Heavy reasoning — stays on the most capable machine
            TaskType.CHAT:                    ModelConfig(reasoning_model,  reasoning_host,  0.7),
            TaskType.SYNTHESIS:               ModelConfig(reasoning_model,  reasoning_host,  0.0, seed=12345),
            TaskType.CONTRADICTION_DETECTION: ModelConfig(reasoning_model,  reasoning_host,  0.1),

            # Extraction pipeline — offloaded so condensation workers don't compete with synthesis
            TaskType.EXTRACT_ATOMS:           ModelConfig(extraction_model, extraction_host, 0.1),
            TaskType.DECOMPOSITION:           ModelConfig(extraction_model, extraction_host, 0.2),
            TaskType.QUERY_EXPANSION:         ModelConfig(extraction_model, extraction_host, 0.5),

            # Fast/distributed
            TaskType.SUMMARIZATION:           ModelConfig(summarize_model,  summarize_host, 0.3),
            TaskType.EMBEDDING:               ModelConfig(embed_model,      embed_host,     0.0),

            # Reasoning layer (analysis + adversarial critique — stay on reasoning host)
            TaskType.ANALYSIS:                ModelConfig(reasoning_model,  reasoning_host, 0.3, seed=None),
            TaskType.CRITIQUE:                ModelConfig(reasoning_model,  reasoning_host, 0.5, seed=None),
        }

    def get(self, task: TaskType) -> ModelConfig:
        return self._map.get(task, self._map[TaskType.CHAT])

    def get_model_name(self, task: TaskType) -> str:
        return self.get(task).model_name

    def summary(self) -> dict:
        return {
            task.value: f"{cfg.model_name} @ {cfg.api_host}"
            for task, cfg in self._map.items()
        }
