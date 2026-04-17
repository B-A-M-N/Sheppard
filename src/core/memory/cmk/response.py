"""
cmk/response.py — CMK-aware response generator (SUPERSEDED).

DEPRECATION NOTICE
------------------
CMKResponseGenerator is no longer a primary call path.

The canonical response generation + retrieval path is SystemManager.chat(),
which handles CMK reasoning overlays via chat_bridge internally.  The legacy
Sheppard shell (src/core/sheppard/response.py) delegates retrieval to
SystemManager.query() and generates responses through its own Ollama clients.

This module is retained for reference and potential offline testing only.
Nothing in the active V3 path should import CMKResponseGenerator.generate_with_cmk()
as a live code path.

Original docstring (historical):
  Replaces src/core/sheppard/response.py's _build_messages() with
  evidence-tier constrained prompts when CMK is available.
"""

import logging
import json
from typing import Dict, Any, List, Optional
from datetime import datetime

from .runtime import CMKRuntime
from .config import CMKConfig
from .prompt_contract import build_cmk_prompt

logger = logging.getLogger(__name__)


class CMKResponseGenerator:
    """
    CMK-aware response generator.

    Falls back to standard behavior when CMK is unavailable or disabled.
    """

    def __init__(
        self,
        main_client=None,
        main_model: str = "mistral",
        short_context_client=None,
        short_model: str = "mistral",
        long_context_client=None,
        long_model: str = "mistral",
        system_prompt: str = "You are Sheppard, a knowledgeable AI assistant.",
        redis_client=None,
        pg_pool=None,
        max_context_length: int = 4000,
        cmk_enabled: bool = True,
    ):
        self.main_client = main_client
        self.main_model = main_model
        self.short_context_client = short_context_client or main_client
        self.short_model = short_model
        self.long_context_client = long_context_client or main_client
        self.long_model = long_model
        self.system_prompt = system_prompt
        self.max_context_length = max_context_length

        # CMK runtime
        self.cmk_enabled = cmk_enabled
        self.cmk_runtime: Optional[CMKRuntime] = None

        # Infrastructure for CMK
        self._redis_client = redis_client
        self._pg_pool = pg_pool

        # Stats
        self.response_stats = {
            "total_responses": 0,
            "cached_responses": 0,
            "cmk_responses": 0,
            "fallback_responses": 0,
            "average_length": 0.0,
            "model_usage": {"main": 0, "short": 0, "long": 0},
        }

        # Cache
        self.response_cache: Dict[str, Dict[str, Any]] = {}
        self.cache_ttl = 300  # 5 minutes

    async def initialize(self) -> bool:
        """Initialize CMK runtime and load concepts."""
        if not self.cmk_enabled:
            logger.info("[CMKResponse] CMK disabled, using standard mode")
            return True

        try:
            config = CMKConfig.from_env()
            self.cmk_runtime = CMKRuntime(
                config=config,
                redis_client=self._redis_client,
                pg_pool=self._pg_pool,
            )

            # Load concepts from store
            count = await self.cmk_runtime.load_concepts()
            logger.info(f"[CMKResponse] CMK initialized: {count} concepts loaded")
            return True
        except Exception as e:
            logger.warning(f"[CMKResponse] CMK init failed: {e}, falling back to standard")
            self.cmk_enabled = False
            return False

    async def generate_with_cmk(
        self,
        user_input: str,
        memories: Dict[str, Any],
        conversation_history: List[Dict[str, str]],
        tool_analysis: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Generate response using CMK pipeline when available.

        Falls back to standard generation if CMK is disabled or fails.
        """
        if not self.cmk_enabled or not self.cmk_runtime:
            return await self._generate_standard(
                user_input, memories, conversation_history, tool_analysis
            )

        try:
            # CMK query pipeline
            intent = self.cmk_runtime.intent_profiler.profile(user_input)
            plan = self.cmk_runtime.evidence_planner.plan(intent)

            # Retrieve with CMK
            if self.cmk_runtime.concept_retriever:
                pack = await self.cmk_runtime.query_with_concepts(user_input)
            else:
                pack = await self.cmk_runtime.query(user_input)

            # Build CMK-constrained messages
            messages = build_cmk_prompt(
                evidence_pack=pack,
                user_query=user_input,
                intent=intent,
                conversation_history=conversation_history[-5:] if conversation_history else None,
                abstraction_gate=pack.abstraction_gate,
                definition_supported=pack.definition_supported,
            )

            # Get response
            response = await self._get_model_response(messages)

            self.response_stats["cmk_responses"] += 1
            self.response_stats["total_responses"] += 1
            self._update_length_stats(len(response))

            return response

        except Exception as e:
            logger.warning(f"[CMKResponse] CMK generation failed: {e}, falling back")
            self.response_stats["fallback_responses"] += 1
            return await self._generate_standard(
                user_input, memories, conversation_history, tool_analysis
            )

    async def _generate_standard(
        self,
        user_input: str,
        memories: Dict[str, Any],
        conversation_history: List[Dict[str, str]],
        tool_analysis: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Standard generation without CMK (fallback)."""
        # Build context summary from memories
        context_summary = await self._summarize_context(memories)

        # Build standard messages
        messages = [
            {"role": "system", "content": self.system_prompt},
        ]

        if context_summary:
            messages.append({
                "role": "system",
                "content": f"Relevant Context:\n{context_summary}",
            })

        if tool_analysis:
            messages.append({
                "role": "system",
                "content": f"Tool Analysis: {json.dumps(tool_analysis)}",
            })

        messages.extend(conversation_history[-5:])
        messages.append({"role": "user", "content": user_input})

        return await self._get_model_response(messages)

    async def _summarize_context(self, memories: Dict[str, Any]) -> str:
        """Summarize memory context (standard fallback)."""
        try:
            memory_texts = []
            for layer, layer_memories in memories.items():
                if isinstance(layer_memories, list):
                    for memory in layer_memories[:3]:  # Limit to 3 per layer
                        if isinstance(memory, dict):
                            input_text = memory.get("input", "")
                            response_text = memory.get("response", "")
                            importance = memory.get("importance_score", 0.0)

                            if input_text or response_text:
                                memory_texts.append(
                                    f"{layer.upper()} [importance: {importance:.2f}]:\n"
                                    f"Input: {input_text}\n"
                                    f"Response: {response_text}"
                                )

            if not memory_texts:
                return ""

            return "\n\n".join(memory_texts[:10])  # Cap at 10 memory blocks
        except Exception as e:
            logger.error(f"Error summarizing context: {e}")
            return ""

    async def _get_model_response(self, messages: List[Dict[str, str]]) -> str:
        """Get response from appropriate model based on context length."""
        total_length = sum(len(m.get("content", "")) for m in messages)

        if total_length > self.max_context_length:
            self.response_stats["model_usage"]["long"] += 1
            client = self.long_context_client or self.main_client
            model = self.long_model
        else:
            self.response_stats["model_usage"]["main"] += 1
            client = self.main_client
            model = self.main_model

        if not client:
            raise ValueError("No Ollama client available for response generation")

        response = await client.chat(model=model, messages=messages)

        if isinstance(response, dict) and "message" in response:
            return response["message"]["content"]
        elif isinstance(response, dict) and "content" in response:
            return response["content"]
        elif isinstance(response, str):
            return response

        raise ValueError(f"Unexpected response format: {type(response)}")

    def _update_length_stats(self, response_length: int):
        """Update response length statistics."""
        total = self.response_stats["total_responses"]
        if total > 0:
            prev_total = self.response_stats["average_length"] * (total - 1)
            self.response_stats["average_length"] = (prev_total + response_length) / total
        else:
            self.response_stats["average_length"] = float(response_length)

    def get_stats(self) -> Dict[str, Any]:
        """Get response generation statistics."""
        return {
            **self.response_stats,
            "cmk_enabled": self.cmk_enabled,
            "cmk_runtime_active": self.cmk_runtime is not None,
        }
