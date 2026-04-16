"""
cmk/integration.py — Wires CMK into Sheppard's retrieval + response pipeline.

Provides:
  - CMKIntegration: Main integration class that creates CMKRuntime and connects
    it to existing Postgres/Redis adapters
  - cmk_query(): Drop-in replacement for flat vector retrieval
  - cmk_generate_messages(): Builds LLM messages with constrained evidence prompt

Usage in V3Retriever:
  1. Initialize CMKIntegration with your adapter
  2. Call cmk_query(user_query) instead of raw Chroma vector search
  3. Get back EvidencePack → use build_cmk_prompt() → send to LLM

Usage in ResponseGenerator:
  1. Replace _build_messages() with cmk_generate_messages()
  2. Pass evidence_pack + intent to the prompt builder
"""

import logging
from typing import List, Dict, Any, Optional

from .runtime import CMKRuntime
from .config import CMKConfig
from .types import CMKAtom
from .evidence_pack import EvidencePack
from .intent_profiler import IntentProfile
from .prompt_contract import build_cmk_prompt

logger = logging.getLogger(__name__)


class CMKIntegration:
    """
    Integration bridge between CMK and Sheppard's existing infrastructure.

    Connects CMKRuntime to:
      - Existing Postgres pool (for concept persistence)
      - Existing Redis client (for embedding cache)
      - Existing Ollama client (for embeddings — uses same host/model config)
    """

    def __init__(
        self,
        config: Optional[CMKConfig] = None,
        redis_client=None,
        pg_pool=None,
        ollama_host: str = "http://localhost:11434",
        ollama_embed_model: str = "nomic-embed-text",
    ):
        """
        Args:
            config: CMK configuration (auto-detects from env if None)
            redis_client: Existing Redis client from your adapter
            pg_pool: Existing asyncpg pool from your adapter
            ollama_host: Ollama host URL
            ollama_embed_model: Ollama embedding model name
        """
        if config is None:
            config = CMKConfig.from_env()

        # Override embedding config if explicit params provided
        if ollama_host:
            config.embedding.host = ollama_host
        if ollama_embed_model:
            config.embedding.model = ollama_embed_model

        self.config = config
        self.runtime = CMKRuntime(
            config=config,
            redis_client=redis_client,
            pg_pool=pg_pool,
        )

        self._initialized = False

    async def initialize(self) -> bool:
        """
        Initialize CMK integration.

        1. Load existing concepts from Postgres
        2. Verify embedding model is available

        Returns:
            True if initialized successfully
        """
        try:
            # Try to load existing concepts
            concept_count = await self.runtime.load_concepts()

            self._initialized = True
            logger.info(
                f"[CMKIntegration] Initialized: "
                f"{len(self.runtime.atoms)} atoms, "
                f"{concept_count} concepts loaded"
            )
            return True
        except Exception as e:
            logger.error(f"[CMKIntegration] Initialization failed: {e}")
            return False

    async def ingest_atoms(self, atoms: List[CMKAtom]) -> int:
        """
        Ingest atoms into CMK (typically called after extraction pipeline).

        Args:
            atoms: List of CMKAtoms from extraction

        Returns:
            Number of atoms ingested
        """
        return await self.runtime.ingest(atoms)

    async def cmk_query(
        self,
        user_query: str,
        topic_filter: Optional[str] = None,
        mission_filter: Optional[str] = None,
        use_concepts: bool = True,
    ) -> tuple[EvidencePack, IntentProfile]:
        """
        Full CMK query: intent → plan → retrieval → scoring → evidence pack.

        Drop-in replacement for flat vector retrieval.

        Args:
            user_query: User's query string
            topic_filter: Optional topic ID filter
            mission_filter: Optional mission ID filter
            use_concepts: If True, use concept-level retrieval (requires built concepts)

        Returns:
            (evidence_pack, intent_profile) — tiered evidence + classified intent
        """
        if not self._initialized:
            await self.initialize()

        # Profile intent
        intent = self.runtime.intent_profiler.profile(user_query)

        # Build evidence plan
        plan = self.runtime.evidence_planner.plan(intent)

        # Retrieve
        if use_concepts and self.config.enable_concepts and self.runtime.concept_retriever:
            pack = await self.runtime.query_with_concepts(
                user_query,
                top_k_concepts=self.config.retrieval.top_k_concepts,
                topic_filter=topic_filter,
                mission_filter=mission_filter,
            )
        else:
            pack = await self.runtime.query(
                user_query,
                topic_filter=topic_filter,
                mission_filter=mission_filter,
            )

        return pack, intent

    def build_messages(
        self,
        evidence_pack: EvidencePack,
        user_query: str,
        intent: Optional[IntentProfile] = None,
        conversation_history: Optional[List[dict]] = None,
    ) -> List[dict]:
        """
        Build LLM messages with constrained evidence prompt.

        Args:
            evidence_pack: EvidencePack from cmk_query()
            user_query: User's query string
            intent: IntentProfile from cmk_query()
            conversation_history: Prior conversation messages

        Returns:
            List of messages ready for LLM generation
        """
        return build_cmk_prompt(
            evidence_pack=evidence_pack,
            user_query=user_query,
            intent=intent,
            conversation_history=conversation_history,
        )

    async def rebuild_concepts(self) -> int:
        """
        Rebuild concept clusters from all ingested atoms.

        Should be called periodically (nightly or after major ingestion).

        Returns:
            Number of concepts built
        """
        return await self.runtime.rebuild_concepts()

    def record_feedback(
        self,
        evidence_pack: EvidencePack,
        response_quality: float,
        response_id: str = "",
    ) -> Dict[str, float]:
        """
        Record feedback for atoms used in a response.

        Call this after the response is generated and evaluated.

        Args:
            evidence_pack: EvidencePack that was used in the response
            response_quality: Quality score (0.0-1.0)
            response_id: Optional response identifier

        Returns:
            Dict of atom_id → reliability delta
        """
        atoms_used = evidence_pack.usable_atoms
        return self.runtime.record_feedback(atoms_used, response_quality, response_id)

    def get_stats(self) -> Dict[str, Any]:
        """Get CMK integration statistics."""
        return self.runtime.get_stats()

    async def close(self):
        """Clean up CMK resources."""
        self.runtime.close()
