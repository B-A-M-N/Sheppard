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
import uuid
from typing import List, Dict, Any, Optional, Set

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
from .belief_graph import BeliefGraph, BeliefNode, BeliefEdge, RelationType
from .concept_anchors import ConceptAnchorStore, ConceptAnchor, CANONICAL_CONCEPTS
from .hypothesis import HypothesisEngine, Hypothesis
from .inference import CrossDomainInferenceEngine, InferenceResult, compute_global_coherence
from .meta_cognition import MetaCognitionLayer

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

        # Global Belief Graph (reasoning substrate — connects claims across domains)
        self.belief_graph = BeliefGraph(pg_pool=pg_pool)

        # Concept Anchors (cross-domain abstraction hubs)
        self.concept_anchors = ConceptAnchorStore(pg_pool=pg_pool)
        self.concept_anchors.initialize_canonical_concepts()

        # Hypothesis Engine (missing edge discovery)
        self.hypothesis_engine = HypothesisEngine(self.belief_graph)

        # Cross-Domain Inference Engine
        self.inference_engine = CrossDomainInferenceEngine(self.belief_graph, self.concept_anchors)

        # Meta-Cognition Layer
        self.meta_cognition = MetaCognitionLayer()

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
        topic_filter: Optional[str] = None,
        mission_filter: Optional[str] = None,
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
            return await self.query(
                user_query,
                topic_filter=topic_filter,
                mission_filter=mission_filter,
            )

        # Embed query
        query_vec = self.embedder.embed(user_query)

        # Concept-level retrieval
        concept_scores, concept_atoms = self.concept_retriever.retrieve_and_expand(
            query_vec, top_k=top_k_concepts
        )

        if topic_filter or mission_filter:
            concept_atoms = [
                atom for atom in concept_atoms
                if (not topic_filter or atom.topic_id == topic_filter)
                and (not mission_filter or atom.mission_id == mission_filter)
            ]

        if not concept_atoms:
            return await self.query(
                user_query,
                topic_filter=topic_filter,
                mission_filter=mission_filter,
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
            needed_atom_ids = {
                atom_id
                for concept in concepts
                for atom_id in concept.atom_ids
                if atom_id and atom_id not in self.atoms
            }
            if needed_atom_ids:
                loaded_atoms = await self.store.load_atoms(
                    atom_ids=sorted(needed_atom_ids),
                    topic_id=topic_filter,
                    limit=max(len(needed_atom_ids), 1),
                )
                for atom in loaded_atoms:
                    self.atoms[atom.id] = atom
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
        else:
            # Direct atom retrieval (fallback)
            retriever = self.concept_retriever or CMKRetriever([], self.atoms)
            scored = retriever.retrieve_direct(
                query_vec,
                top_k=self.config.retrieval.max_total_atoms,
            )
            atoms = [atom for atom, _ in scored]

        if topic_filter or mission_filter:
            atoms = [
                atom for atom in atoms
                if (not topic_filter or atom.topic_id == topic_filter)
                and (not mission_filter or atom.mission_id == mission_filter)
            ]

        return atoms

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

    # ── Belief Graph Operations ──

    def create_belief_node(
        self,
        claim: str,
        domain: str = "",
        authority_score: float = 0.5,
        embedding: Optional[List[float]] = None,
        canonical_id: Optional[str] = None,
    ) -> str:
        """Create a belief node in the global graph."""
        node = BeliefNode(
            id=f"belief_{uuid.uuid4().hex[:8]}",
            claim=claim,
            domain=domain,
            authority_score=authority_score,
            embedding=embedding,
            canonical_id=canonical_id,
        )
        return self.belief_graph.add_node(node)

    def link_beliefs(
        self,
        from_id: str,
        to_id: str,
        relation: str,
        strength: float,
        evidence: Optional[List[str]] = None,
        reason: str = "",
    ) -> Optional[BeliefEdge]:
        """Create a reasoning link between two belief nodes."""
        return self.belief_graph.add_edge(from_id, to_id, relation, strength, evidence, reason)

    def find_belief_paths(
        self,
        from_id: str,
        to_id: str,
        max_hops: int = 3,
    ) -> List:
        """Find reasoning paths between two belief nodes."""
        return self.belief_graph.find_paths(from_id, to_id, max_hops)

    def expand_belief_neighborhood(
        self,
        belief_id: str,
        max_hops: int = 2,
        cross_domain: bool = False,
    ) -> Set[str]:
        """
        Expand from a belief node, collecting reachable beliefs.

        If cross_domain=True, also traverses through concept anchors
        to reach beliefs in other domains.
        """
        # Graph expansion
        neighbors = self.belief_graph.expand_from(belief_id, max_hops)

        if cross_domain:
            # Also traverse via concept anchors
            concepts = self.concept_anchors.get_concepts_for_belief(belief_id)
            for concept in concepts:
                # Get beliefs from OTHER domains linked to same concept
                cross_beliefs = self.concept_anchors.get_cross_domain_beliefs(
                    concept.id, exclude_domain=""
                )
                for domain_beliefs in cross_beliefs.values():
                    neighbors.update(domain_beliefs)

        return neighbors

    def propagate_graph_authority(self, iterations: int = 3):
        """Run authority propagation across the belief graph."""
        self.belief_graph.propagate_authority(iterations=iterations)

    def propagate_contradictions(self):
        """Run contradiction propagation across the belief graph."""
        return self.belief_graph.propagate_contradictions()

    def link_belief_to_concepts(
        self,
        belief_id: str,
        concept_names: List[str],
        domain: str = "",
    ):
        """Link a belief node to concept anchors by name."""
        for name in concept_names:
            concept = self.concept_anchors.find_by_name(name)
            if concept:
                self.concept_anchors.link_belief(belief_id, concept.id, domain)
                # Also add graph edge
                concept_node_id = f"concept_node_{concept.id}"
                if concept_node_id not in self.belief_graph._nodes:
                    self.belief_graph.add_node(BeliefNode(
                        id=concept_node_id,
                        claim=f"Concept: {concept.name}",
                        domain="meta",
                        authority_score=concept.authority_score,
                    ))
                self.belief_graph.add_edge(
                    belief_id, concept_node_id,
                    RelationType.INSTANTIATES.value,
                    strength=0.7,
                )

    # ── Hypothesis Engine ──

    def detect_hypotheses(
        self,
        similarity_threshold: float = 0.75,
        max_candidates: int = 50,
    ) -> List[Hypothesis]:
        """Detect missing edges in the belief graph."""
        return self.hypothesis_engine.detect_missing_edges(similarity_threshold, max_candidates)

    async def run_hypothesis_cycle(
        self,
        llm_client=None,
        llm_model: str = "mistral",
        top_k: int = 10,
    ) -> Dict[str, Any]:
        """Run full hypothesis cycle: detect → test → apply."""
        return await self.hypothesis_engine.run_hypothesis_cycle(llm_client, llm_model, top_k)

    # ── Cross-Domain Inference ──

    def cross_domain_infer(
        self,
        query: str,
        seed_belief_ids: List[str],
        max_hops: int = 3,
    ) -> InferenceResult:
        """Run cross-domain inference from seed beliefs."""
        return self.inference_engine.infer(query, seed_belief_ids, max_hops)

    def get_global_coherence(self) -> Dict[str, float]:
        """Compute global coherence metrics for the entire belief graph."""
        return compute_global_coherence(self.belief_graph, self.concept_anchors)

    # ── Meta-Cognition ──

    def record_reasoning_step(
        self,
        step_type: str,
        input_data: Dict[str, Any],
        output_data: Dict[str, Any],
        confidence: float,
    ):
        """Record a reasoning step for meta-cognitive tracking."""
        self.meta_cognition.record_step(step_type, input_data, output_data, confidence)

    def get_meta_cognitive_stats(self) -> Dict[str, Any]:
        """Get meta-cognitive statistics."""
        return self.meta_cognition.get_stats()

    def get_blind_spots(self) -> List[Dict[str, Any]]:
        """Identify reasoning blind spots."""
        return self.meta_cognition.identify_blind_spots()

    def record_domain_outcome(self, domain: str, success: bool, authority: float = 0.5):
        """Record a domain outcome for meta-cognitive tracking."""
        self.meta_cognition.record_domain_outcome(domain, success, authority)

    # ── Autonomous Research Agenda ──

    def generate_research_agenda(
        self,
        top_k: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        Generate an autonomous research agenda based on graph tension.

        Returns prioritized research questions from:
          - High-scoring untested hypotheses
          - Unresolved contradictions
          - Low-coherence areas
          - Missing cross-domain bridges
        """
        agenda = []

        # 1. Top untested hypotheses
        hypotheses = self.hypothesis_engine.detect_missing_edges()
        untested = [h for h in hypotheses if h.status == "pending"]
        for h in untested[:top_k // 3]:
            agenda.append({
                "type": "hypothesis",
                "priority": h.score,
                "description": f"Test {h.hypothesis_type} relationship between nodes {h.node_a[:12]} and {h.node_b[:12]}",
                "reason": h.reason,
                "action": "run_hypothesis_test",
            })

        # 2. High contradiction areas
        for node in self.belief_graph._nodes.values():
            if node.contradiction_pressure > 0.4:
                agenda.append({
                    "type": "contradiction_resolution",
                    "priority": node.contradiction_pressure,
                    "description": f"Resolve contradiction in: {node.claim[:80]}",
                    "reason": f"Contradiction pressure: {node.contradiction_pressure:.2f}",
                    "action": "run_belief_correction",
                })

        # 3. Low coherence domains
        coherence = compute_global_coherence(self.belief_graph, self.concept_anchors)
        if coherence["overall"] < 0.5:
            agenda.append({
                "type": "coherence_improvement",
                "priority": 1.0 - coherence["overall"],
                "description": f"Improve global coherence (currently {coherence['overall']:.2f})",
                "reason": f"Contradiction spread: {coherence['contradiction_spread']:.2f}, "
                          f"Concept connectivity: {coherence['concept_connectivity']:.2f}",
                "action": "run_consolidation",
            })

        # 4. Missing cross-domain bridges
        for concept in self.concept_anchors._anchors.values():
            if concept.domain_count < 2:
                agenda.append({
                    "type": "cross_domain_bridge",
                    "priority": 0.5,
                    "description": f"Connect '{concept.name}' to additional domains (currently: {sorted(concept.domains)})",
                    "reason": "Single-domain concept — potential for cross-domain insight",
                    "action": "find_analogies",
                })

        # Sort by priority
        agenda.sort(key=lambda x: x["priority"], reverse=True)
        return agenda[:top_k]

    # ── Cleanup ──

    def close(self):
        """Close CMK resources."""
        self.embedder.close()
