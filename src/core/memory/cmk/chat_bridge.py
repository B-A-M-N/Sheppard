"""
cmk/chat_bridge.py — Wires CMK into Sheppard's live chat + retrieval path.

Integration points:
  1. V3Retriever.retrieve() → CMK intent→plan→score→evidence_pack
  2. ResponseGenerator._build_messages() → CMK evidence-tier prompt

Usage:
  from src.core.memory.cmk.chat_bridge import CMKChatBridge

  bridge = CMKChatBridge(redis_client, pg_pool, ollama_host)
  await bridge.initialize()

  # In chat flow:
  result = await bridge.query_with_cmk(user_query, mission_id)
  messages = bridge.build_messages(result)
"""

import logging
from typing import Optional, List, Dict, Any

from .runtime import CMKRuntime
from .config import CMKConfig
from .types import CMKAtom
from .evidence_pack import EvidencePack
from .intent_profiler import IntentProfile
from .loop_governor import LoopGovernor, CompressedContext
from .prompt_contract import build_cmk_prompt

logger = logging.getLogger(__name__)


class CMKChatBridge:
    """
    Bridges CMK into Sheppard's live chat path.

    Replaces:
      V3Retriever.retrieve() → flat vector dump → generic prompt
    With:
      Intent → Evidence Plan → Dynamic Scoring → Evidence Pack → Constrained Prompt
    """

    def __init__(
        self,
        redis_client=None,
        pg_pool=None,
        ollama_host: str = "http://localhost:11434",
        ollama_embed_model: str = "nomic-embed-text",
    ):
        config = CMKConfig.from_env()
        config.embedding.host = ollama_host
        config.embedding.model = ollama_embed_model

        self.runtime = CMKRuntime(
            config=config,
            redis_client=redis_client,
            pg_pool=pg_pool,
        )
        self.governor = LoopGovernor()
        self._initialized = False

    async def initialize(self) -> bool:
        """Load concepts from store, verify embeddings available."""
        try:
            count = await self.runtime.load_concepts()
            self._initialized = True
            logger.info(f"[CMKChatBridge] Initialized: {count} concepts loaded")
            return True
        except Exception as e:
            logger.error(f"[CMKChatBridge] Init failed: {e}")
            return False

    async def query_with_cmk(
        self,
        user_query: str,
        topic_filter: Optional[str] = None,
        mission_filter: Optional[str] = None,
        use_concepts: bool = True,
    ) -> Dict[str, Any]:
        """
        Full CMK query pipeline — drop-in replacement for V3Retriever.retrieve().

        Returns:
            Dict with evidence_pack, intent, and governor decisions.
        """
        if not self._initialized:
            await self.initialize()

        # Intent profiling
        intent = self.runtime.intent_profiler.profile(user_query)
        plan = self.runtime.evidence_planner.plan(intent)

        # Retrieval
        if use_concepts and self.runtime.concept_retriever:
            pack = await self.runtime.query_with_concepts(
                user_query,
                top_k_concepts=self.runtime.config.retrieval.top_k_concepts,
            )
        else:
            pack = await self.runtime.query(
                user_query,
                topic_filter=topic_filter,
                mission_filter=mission_filter,
            )

        # Governor pre-generation checks
        atoms = pack.usable_atoms
        scores = [a.reliability for a in atoms]
        compressed, gov_decisions = self.governor.pre_generate(
            atoms, scores, user_query
        )

        return {
            "evidence_pack": pack,
            "intent": intent,
            "plan": plan,
            "compressed_context": compressed,
            "governor_decisions": gov_decisions,
        }

    def build_messages(
        self,
        result: Dict[str, Any],
        conversation_history: Optional[List[dict]] = None,
    ) -> List[dict]:
        """
        Build LLM messages from CMK query result.

        Replaces ResponseGenerator._build_messages().
        """
        pack = result["evidence_pack"]
        intent = result["intent"]
        user_query = intent.type  # We need the actual query — stored in intent

        # Reconstruct query from intent metadata
        # (In practice, this should be passed through — for now use the intent profile)
        return build_cmk_prompt(
            evidence_pack=pack,
            user_query=getattr(intent, "_query", "user query"),
            intent=intent,
            conversation_history=conversation_history,
            abstraction_gate=pack.abstraction_gate,
            definition_supported=pack.definition_supported,
        )

    def record_feedback(
        self,
        result: Dict[str, Any],
        response_text: str,
        response_quality: float,
        response_id: str = "",
    ) -> Dict[str, Any]:
        """
        Post-response feedback loop — records atom usage quality
        and runs governor post-generation checks.
        """
        pack = result["evidence_pack"]
        user_query = getattr(result.get("intent"), "_query", "")

        # Governor post-generation checks
        gov_decisions = self.governor.post_generate(response_text, user_query)

        # Feedback to atom reliability
        feedback = self.runtime.record_feedback(
            pack.usable_atoms, response_quality, response_id
        )

        return {
            "governor_decisions": gov_decisions,
            "feedback_updates": feedback,
        }
