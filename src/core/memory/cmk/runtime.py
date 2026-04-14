"""
cmk/runtime.py — The CMK brain. Ties all modules together.

Main entry point for the Cognitive Memory Kernel.
Provides:
  - ingest(): Add atoms to the knowledge substrate
  - query(): Retrieve knowledge for a user query
  - rebuild(): Rebuild concept clusters
  - get_context(): Build prompt-ready evidence pack
  - activate(): Reinforce atom activation on retrieval
  - consolidate(): Run episodic → semantic compression
"""

import logging
import time
from typing import List, Dict, Any, Optional

from .config import CMKConfig
from .types import CMKAtom, Concept
from .embedder import OllamaEmbedder
from .intent_profiler import IntentProfiler, IntentProfile
from .evidence_planner import EvidencePlanner, EvidencePlan
from .atom_scorer import AtomScorer, score_atom
from .evidence_pack import EvidencePackBuilder, EvidencePack
from .contradiction_detector import ContradictionDetector
from .feedback_loop import FeedbackLoop
from .builder import ConceptBuilder
from .retrieval import CMKRetriever
from .store import CMKStore
from .activation import ActivationMemory
from .authority import CanonicalKnowledgeStore

logger = logging.getLogger(__name__)


class CMKRuntime:
    """
    The Cognitive Memory Kernel runtime.

    Full pipeline:
      Query → Intent Profile → Evidence Plan → Dynamic Scoring
      → Evidence Pack → Constrained Context → LLM

    Concept layer (v2):
      Atoms → Embeddings → Clusters → Concepts → Concept-level Retrieval
    """

    def __init__(
        self,
        config: Optional[CMKConfig] = None,
        redis_client=None,
        pg_pool=None,
    ):
        """
        Args:
            config: CMK configuration (creates default from env if None)
            redis_client: Existing Redis client
            pg_pool: Existing asyncpg pool
        """
        self.config = config or CMKConfig.from_env()

        # Core modules
        self.embedder = OllamaEmbedder(
            model=self.config.embedding.model,
            host=self.config.embedding.host,
        )
        self.intent_profiler = IntentProfiler()
        self.evidence_planner = EvidencePlanner()
        self.atom_scorer = AtomScorer(weights=self.config.scoring.weights)
        self.evidence_pack_builder = EvidencePackBuilder()
        self.contradiction_detector = ContradictionDetector()
        self.feedback_loop = FeedbackLoop()

        # Concept layer
        self.concept_builder = ConceptBuilder(
            embedder=self.embedder,
            k=self.config.clustering.kmeans_k,
        )
        self.concept_retriever: Optional[CMKRetriever] = None

        # Store
        self.store = CMKStore(self.config, redis_client=redis_client, pg_pool=pg_pool)

        # Activation memory (Layer B — working memory, decays)
        self.activation = ActivationMemory(redis_client=redis_client, pg_pool=pg_pool)

        # Canonical Knowledge Store (Layer A — long-term semantic memory, never decays)
        self.cks = CanonicalKnowledgeStore(pg_pool=pg_pool)

        # Atom store (in-memory)
        self.atoms: Dict[str, CMKAtom] = {}
        self.concepts: List[Concept] = []

        # Stats
        self.query_count = 0
        self.ingest_count = 0

    # ── Ingestion ──

    async def ingest(self, atoms: List[CMKAtom]) -> int:
        """
        Ingest atoms into the CMK.

        1. Store atoms in memory
        2. Embed (if not already embedded)
        3. Cache embeddings

        Args:
            atoms: List of CMKAtoms to ingest

        Returns:
            Number of atoms successfully ingested
        """
        count = 0
        for atom in atoms:
            self.atoms[atom.id] = atom

            # Cache embedding if available
            if atom.embedding is not None:
                await self.store.cache_atom_embedding(atom.id, atom.embedding)
            count += 1

        self.ingest_count += count
        logger.info(f"[CMK] Ingested {count} atoms (total: {len(self.atoms)})")

        return count

    # ── Query ──

    async def query(
        self,
        user_query: str,
        topic_filter: Optional[str] = None,
        mission_filter: Optional[str] = None,
    ) -> EvidencePack:
        """
        Full CMK query pipeline.

        User query → Intent Profile → Evidence Plan → Retrieval → Scoring → Evidence Pack

        Args:
            user_query: The user's query string
            topic_filter: Optional topic ID filter
            mission_filter: Optional mission ID filter

        Returns:
            EvidencePack with tiered knowledge ready for LLM injection
        """
        t_start = time.perf_counter()
        self.query_count += 1

        # Step 1: Intent profiling
        intent = None
        plan = None

        if self.config.enable_intent_profiling:
            intent = self.intent_profiler.profile(user_query)

            if self.config.enable_evidence_planning:
                plan = self.evidence_planner.plan(intent)

        # Step 2: Embed query
        query_vec = self.embedder.embed(user_query)

        # Step 3: Retrieval
        candidate_atoms = await self._retrieve(
            user_query, query_vec, topic_filter, mission_filter
        )

        # Step 4: Dynamic scoring with contradiction awareness
        # Build set of contradictory atom IDs
        contradictory_ids = set()
        if self.config.enable_contradiction_detection:
            contradictions = self.contradiction_detector.detect(candidate_atoms)
            for c in contradictions:
                contradictory_ids.add(c.get("atom_a", ""))
                contradictory_ids.add(c.get("atom_b", ""))

        from .scoring import score_atoms_batch
        scored_atoms = score_atoms_batch(
            candidate_atoms,
            contradictory_ids=contradictory_ids if self.config.enable_contradiction_detection else None,
        )

        # Apply query relevance filtering + RETRIEVAL FUSION
        # final_score = vector_sim * 0.40 + authority * 0.35 + recency_bias * 0.15 + context * 0.10
        from .atom_scorer import score_atom as query_score
        scored_with_fusion = []
        for atom, base_score in scored_atoms:
            # Query relevance (context alignment)
            qr = query_score(atom, user_query, intent, plan)

            # Activation score (working memory / recency)
            act_score = await self.activation.get_activation(atom.id)

            # Retrieve fusion scoring
            fused = self.activation.compute_retrieval_score(
                vector_similarity=base_score,
                authority_score=atom.reliability,
                activation_score=act_score,
                context_alignment=qr,
            )

            if fused >= self.config.scoring.min_score_threshold:
                scored_with_fusion.append((atom, fused))

            # Reinforce activation for retrieved atoms (working memory boost)
            if fused >= 0.5:
                await self.activation.activate(atom.id, amount=0.1)

        scored_with_fusion.sort(key=lambda x: x[1], reverse=True)

        # Step 5: Build evidence pack with grounding enforcement
        pack = self.evidence_pack_builder.build(
            scored_with_fusion,
            plan=plan,
            concepts=self.concepts if self.config.enable_concepts else None,
        )

        elapsed_ms = (time.perf_counter() - t_start) * 1000
        logger.info(
            f"[CMK] Query: {len(candidate_atoms)} candidates → "
            f"{len(scored_atoms)} scored → "
            f"{len(pack.usable_atoms)} usable "
            f"({elapsed_ms:.0f}ms)"
        )

        return pack

    async def query_with_concepts(
        self,
        user_query: str,
        top_k_concepts: int = 5,
    ) -> EvidencePack:
        """
        Query using concept-level retrieval (v2).

        Requires concepts to be built first via rebuild().

        Args:
            user_query: The user's query
            top_k_concepts: Number of concepts to retrieve

        Returns:
            EvidencePack with concept-grounded atoms
        """
        if not self.config.enable_concepts or not self.concept_retriever:
            # Fallback to standard query
            return await self.query(user_query)

        # Embed query
        query_vec = self.embedder.embed(user_query)

        # Concept-level retrieval
        concept_scores, concept_atoms = self.concept_retriever.retrieve_and_expand(
            query_vec, top_k=top_k_concepts
        )

        # Build evidence pack from expanded atoms
        scored_atoms = [(atom, atom.reliability) for atom in concept_atoms]
        pack = self.evidence_pack_builder.build(scored_atoms)

        logger.info(
            f"[CMK] Concept query: {len(concept_scores)} concepts → "
            f"{len(concept_atoms)} atoms"
        )

        return pack

    # ── Concept building ──

    async def rebuild_concepts(self) -> int:
        """
        Rebuild concept clusters from all atoms.

        Runs the full pipeline: atoms → embed → cluster → concepts → store

        Returns:
            Number of concepts built
        """
        if not self.config.enable_concepts:
            return 0

        atoms_list = list(self.atoms.values())
        if len(atoms_list) < 2:
            logger.info("[CMK] Not enough atoms to build concepts")
            return 0

        logger.info(f"[CMK] Rebuilding concepts from {len(atoms_list)} atoms")

        concepts, _ = self.concept_builder.build(atoms_list)
        self.concepts = concepts

        # Initialize concept retriever
        self.concept_retriever = CMKRetriever(concepts, self.atoms)

        # Persist to store
        saved = await self.store.save_concepts(concepts)
        logger.info(f"[CMK] Built {len(concepts)} concepts, saved {saved} to Postgres")

        return len(concepts)

    async def load_concepts(self, topic_filter: Optional[str] = None) -> int:
        """
        Load concepts from persistence.

        Args:
            topic_filter: Optional topic filter

        Returns:
            Number of concepts loaded
        """
        if not self.config.enable_concepts:
            return 0

        concepts = await self.store.load_concepts(topic_id=topic_filter)
        if concepts:
            self.concepts = concepts
            self.concept_retriever = CMKRetriever(concepts, self.atoms)
            logger.info(f"[CMK] Loaded {len(concepts)} concepts from store")

        return len(concepts)

    # ── Feedback ──

    def record_feedback(
        self,
        atoms_used: List[CMKAtom],
        response_quality: float,
        response_id: str = "",
    ) -> Dict[str, float]:
        """
        Record feedback for atoms used in a response.

        Args:
            atoms_used: Atoms that were included in the response
            response_quality: Quality score of the response (0.0-1.0)
            response_id: Optional response identifier

        Returns:
            Dict of atom_id → reliability delta
        """
        if not self.config.enable_feedback_loop:
            return {}

        updates = self.feedback_loop.record_usage(
            atoms_used, response_quality, response_id
        )

        # Apply updates to in-memory store
        if updates:
            self.feedback_loop.apply_updates(self.atoms, updates)

        return updates

    # ── Stats ──

    def get_stats(self) -> Dict[str, Any]:
        """Get CMK runtime statistics."""
        return {
            "atoms": len(self.atoms),
            "concepts": len(self.concepts),
            "query_count": self.query_count,
            "ingest_count": self.ingest_count,
            "feedback": self.feedback_loop.get_stats(),
            "config": self.config.to_dict(),
        }

    # ── Internal retrieval ──

    async def _retrieve(
        self,
        query: str,
        query_vec: List[float],
        topic_filter: Optional[str],
        mission_filter: Optional[str],
    ) -> List[CMKAtom]:
        """
        Retrieve candidate atoms for scoring.

        Uses concept-level retrieval if concepts are available,
        otherwise falls back to direct atom retrieval.
        """
        if self.config.enable_concepts and self.concept_retriever:
            # Concept-level retrieval
            _, atoms = self.concept_retriever.retrieve_and_expand(
                query_vec,
                top_k=self.config.retrieval.top_k_concepts,
            )
            return atoms
        else:
            # Direct atom retrieval (fallback)
            scored = self.concept_retriever.retrieve_direct(
                query_vec,
                top_k=self.config.retrieval.max_total_atoms,
            ) if self.concept_retriever else []

            return [atom for atom, _ in scored]

    # ── Activation & Consolidation ──

    async def activate_atom(self, atom_id: str, amount: float = 1.0) -> float:
        """
        Reinforce an atom's activation (called externally for manual boosting).

        Returns new activation score.
        """
        return await self.activation.activate(atom_id, amount)

    async def consolidate_topic(
        self,
        topic_id: str,
        atoms: List[CMKAtom] | None = None,
        llm_client=None,
        llm_model: str = "mistral",
    ) -> List[str]:
        """
        Run episodic → semantic compression for a topic.

        Converts raw atoms into distilled canonical claims.

        Args:
            topic_id: Topic to consolidate
            atoms: Atoms to consolidate (loads from self.atoms if None)
            llm_client: Optional LLM client for synthesis
            llm_model: Model to use for synthesis

        Returns:
            List of canonical claim IDs created/updated
        """
        if atoms is None:
            atoms = [a for a in self.atoms.values() if a.topic_id == topic_id]

        if not atoms:
            return []

        from .consolidation import ConsolidationPipeline

        pipeline = ConsolidationPipeline(
            cks=self.cks,
            embedder=self.embedder,
            llm_client=llm_client,
            llm_model=llm_model,
        )

        return await pipeline.consolidate_topic(topic_id, atoms)

    async def run_consolidation(
        self,
        llm_client=None,
        llm_model: str = "mistral",
    ) -> Dict[str, List[str]]:
        """
        Run consolidation across all topics.

        Returns:
            Dict mapping topic_id → list of canonical claim IDs
        """
        # Group atoms by topic
        topics: Dict[str, List[CMKAtom]] = {}
        for atom in self.atoms.values():
            if atom.topic_id:
                topics.setdefault(atom.topic_id, []).append(atom)

        results = {}
        for topic_id, atoms in topics.items():
            claim_ids = await self.consolidate_topic(
                topic_id, atoms, llm_client, llm_model
            )
            results[topic_id] = claim_ids

        logger.info(f"[CMK] Consolidation complete: {len(results)} topics processed")
        return results

    async def decay_activation(self):
        """Apply decay to activation memory (call periodically)."""
        return await self.activation.decay_all()

    # ── Cleanup ──

    def close(self):
        """Close CMK resources."""
        self.embedder.close()
