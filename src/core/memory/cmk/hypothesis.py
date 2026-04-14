"""
cmk/hypothesis.py — Hypothesis Engine + Missing Edge Discovery.

Detects gaps in the belief graph and generates testable hypotheses.

4 types of graph tension signals:
  1. Semantic proximity without relation — two similar nodes not connected
  2. Unresolved contradictions — conflicting claims with no resolution
  3. Causal asymmetry gaps — A frequently co-occurs with B but no causal link
  4. Cross-domain analogies — same pattern in different domains, no mapping

Hypotheses are NOT truth. They're predicted missing structure.
"""

import logging
import uuid
import json
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum

from .belief_graph import BeliefGraph, BeliefNode, BeliefEdge, RelationType

logger = logging.getLogger(__name__)


class HypothesisType(str, Enum):
    CAUSAL = "causal"              # A causes B
    ANALOGICAL = "analogical"      # A is analogous to B across domains
    CORRECTIVE = "corrective"      # A needs correction based on new evidence
    RELATIONAL = "relational"      # A is related to B (missing edge)


class HypothesisStatus(str, Enum):
    PENDING = "pending"
    TESTING = "testing"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"
    REFINED = "refined"


@dataclass
class Hypothesis:
    """A predicted missing structure in the belief graph."""
    id: str
    node_a: str
    node_b: str
    hypothesis_type: str
    confidence: float = 0.0
    score: float = 0.0
    status: str = "pending"
    evidence: Optional[Dict[str, Any]] = None
    test_result: Optional[Dict[str, Any]] = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    tested_at: Optional[datetime] = None
    reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "node_a": self.node_a,
            "node_b": self.node_b,
            "hypothesis_type": self.hypothesis_type,
            "confidence": self.confidence,
            "score": self.score,
            "status": self.status,
            "reason": self.reason,
            "evidence": self.evidence,
            "test_result": self.test_result,
        }


class HypothesisEngine:
    """
    Detects missing edges and generates testable hypotheses.

    The graph incompleteness IS the signal.
    """

    def __init__(self, graph: BeliefGraph):
        self.graph = graph
        self._hypotheses: Dict[str, Hypothesis] = {}

    # ── Missing Edge Detection ──

    def detect_missing_edges(
        self,
        similarity_threshold: float = 0.75,
        max_candidates: int = 50,
    ) -> List[Hypothesis]:
        """
        Find pairs of nodes that should be connected but aren't.

        Types of missing edges:
          1. Semantic proximity — similar embeddings, no edge
          2. Cross-domain analogy — same concept, different domain, no link
          3. Causal gap — A depends_on B indirectly but no direct link
        """
        hypotheses = []
        nodes = list(self.graph._nodes.values())

        # 1. Semantic proximity without relation
        hypotheses.extend(
            self._detect_semantic_gaps(nodes, similarity_threshold)
        )

        # 2. Cross-domain analogies
        hypotheses.extend(
            self._detect_cross_domain_gaps(nodes)
        )

        # 3. Contradiction without resolution
        hypotheses.extend(
            self._detect_unresolved_contradictions(nodes)
        )

        # Sort by score, return top candidates
        hypotheses.sort(key=lambda h: h.score, reverse=True)
        return hypotheses[:max_candidates]

    def _detect_semantic_gaps(
        self,
        nodes: List[BeliefNode],
        threshold: float,
    ) -> List[Hypothesis]:
        """Find nodes with similar embeddings but no edge between them."""
        hypotheses = []

        nodes_with_embeddings = [n for n in nodes if n.embedding is not None]

        for i in range(len(nodes_with_embeddings)):
            for j in range(i + 1, len(nodes_with_embeddings)):
                a = nodes_with_embeddings[i]
                b = nodes_with_embeddings[j]

                # Check if edge already exists
                if self._edge_exists(a.id, b.id):
                    continue

                # Compute similarity
                sim = _cosine(a.embedding, b.embedding)
                if sim < threshold:
                    continue

                # Same domain = likely related; different domain = potential analogy
                if a.domain == b.domain:
                    h_type = HypothesisType.RELATIONAL.value
                    score = sim * 0.6 + min(1.0, (a.authority_score + b.authority_score) / 2) * 0.4
                else:
                    h_type = HypothesisType.ANALOGICAL.value
                    score = sim * 0.4 + 0.3 + min(1.0, a.authority_score * b.authority_score) * 0.3

                hypotheses.append(Hypothesis(
                    id=f"hyp_{uuid.uuid4().hex[:8]}",
                    node_a=a.id,
                    node_b=b.id,
                    hypothesis_type=h_type,
                    confidence=sim,
                    score=score,
                    reason=f"Semantic similarity ({sim:.2f}) without edge, {'same' if a.domain == b.domain else 'cross'} domain",
                ))

        return hypotheses

    def _detect_cross_domain_gaps(self, nodes: List[BeliefNode]) -> List[Hypothesis]:
        """
        Find nodes in different domains that share structural patterns
        but have no analogous_to edge.
        """
        hypotheses = []
        domains = {}

        for node in nodes:
            if node.domain:
                domains.setdefault(node.domain, []).append(node)

        domain_list = list(domains.keys())
        for i in range(len(domain_list)):
            for j in range(i + 1, len(domain_list)):
                domain_a = domain_list[i]
                domain_b = domain_list[j]

                for na in domains[domain_a]:
                    for nb in domains[domain_b]:
                        if self._edge_exists(na.id, nb.id, RelationType.ANALOGOUS_TO.value):
                            continue

                        # If both have high authority and share concept anchors
                        if na.authority_score > 0.6 and nb.authority_score > 0.6:
                            score = 0.3 + 0.3 * na.authority_score + 0.3 * nb.authority_score + 0.1 * _text_overlap(na.claim, nb.claim)
                            hypotheses.append(Hypothesis(
                                id=f"hyp_{uuid.uuid4().hex[:8]}",
                                node_a=na.id,
                                node_b=nb.id,
                                hypothesis_type=HypothesisType.ANALOGICAL.value,
                                confidence=score,
                                score=score,
                                reason=f"Cross-domain structural pattern ({domain_a} ↔ {domain_b}), both high authority",
                            ))

        return hypotheses

    def _detect_unresolved_contradictions(self, nodes: List[BeliefNode]) -> List[Hypothesis]:
        """Find nodes with high contradiction pressure but no resolution."""
        hypotheses = []

        for node in nodes:
            if node.contradiction_pressure > 0.3:
                # Find contradicting neighbors
                contradictions = self.graph.get_neighbors(
                    node.id, relation_type=RelationType.CONTRADICTS.value
                )

                if contradictions:
                    # Multiple contradictions = needs resolution
                    if len(contradictions) >= 2:
                        for neighbor, edge in contradictions:
                            hypotheses.append(Hypothesis(
                                id=f"hyp_{uuid.uuid4().hex[:8]}",
                                node_a=node.id,
                                node_b=neighbor.id,
                                hypothesis_type=HypothesisType.CORRECTIVE.value,
                                confidence=0.5 + node.contradiction_pressure * 0.3,
                                score=0.5 + node.contradiction_pressure * 0.5,
                                reason=f"Unresolved contradiction pressure ({node.contradiction_pressure:.2f}) with {len(contradictions)} conflicts",
                            ))

        return hypotheses

    # ── Hypothesis Testing ──

    def select_top_hypotheses(
        self,
        hypotheses: List[Hypothesis],
        top_k: int = 10,
        min_score: float = 0.3,
    ) -> List[Hypothesis]:
        """Select top hypotheses for testing."""
        filtered = [h for h in hypotheses if h.score >= min_score]
        filtered.sort(key=lambda h: h.score, reverse=True)
        return filtered[:top_k]

    async def test_hypothesis(
        self,
        hypothesis: Hypothesis,
        llm_client=None,
        llm_model: str = "mistral",
    ) -> Dict[str, Any]:
        """
        Test a hypothesis via retrieval + LLM evaluation.

        Returns:
            Test result dict with decision (confirm/reject/uncertain/refine)
        """
        node_a = self.graph.get_node(hypothesis.node_a)
        node_b = self.graph.get_node(hypothesis.node_b)

        if not node_a or not node_b:
            return {"decision": "reject", "reason": "Node not found"}

        # Gather evidence
        evidence = {
            "node_a": node_a.to_dict(),
            "node_b": node_b.to_dict(),
            "hypothesis_type": hypothesis.hypothesis_type,
        }

        if llm_client:
            result = await self._llm_evaluate_hypothesis(
                hypothesis, node_a, node_b, llm_client, llm_model
            )
        else:
            # Fallback: use heuristic evaluation
            result = self._heuristic_evaluate(hypothesis, node_a, node_b)

        hypothesis.test_result = result
        hypothesis.evidence = evidence
        hypothesis.status = result.get("status", result.get("decision", "pending"))

        return result

    async def _llm_evaluate_hypothesis(
        self,
        hypothesis: Hypothesis,
        node_a: BeliefNode,
        node_b: BeliefNode,
        llm_client,
        llm_model: str,
    ) -> Dict[str, Any]:
        """Use LLM to evaluate a hypothesis."""
        prompt = f"""You are a hypothesis evaluator.

HYPOTHESIS: {hypothesis.hypothesis_type} relationship between:
A: "{node_a.claim}" (domain: {node_a.domain}, authority: {node_a.authority_score:.2f})
B: "{node_b.claim}" (domain: {node_b.domain}, authority: {node_b.authority_score:.2f})

REASON: {hypothesis.reason}

Decide:
- "confirm" if the relationship is well-supported
- "reject" if there's no meaningful connection
- "uncertain" if more evidence is needed
- "refine" if the relationship exists but needs refinement

Return JSON ONLY:
{{"decision": "confirm|reject|uncertain|refine", "confidence": 0.0-1.0, "reason": "explanation"}}"""

        try:
            response = await llm_client.chat(
                model=llm_model,
                messages=[{"role": "user", "content": prompt}],
                format="json",
            )
            content = response.get("message", {}).get("content", "{}")
            return json.loads(content) if isinstance(content, str) else content
        except Exception as e:
            logger.debug(f"[HypothesisEngine] LLM evaluation failed: {e}")
            return self._heuristic_evaluate(hypothesis, node_a, node_b)

    def _heuristic_evaluate(
        self,
        hypothesis: Hypothesis,
        node_a: BeliefNode,
        node_b: BeliefNode,
    ) -> Dict[str, Any]:
        """Heuristic hypothesis evaluation."""
        score = hypothesis.score

        if hypothesis.hypothesis_type == HypothesisType.ANALOGICAL.value:
            if node_a.domain != node_b.domain and score > 0.5:
                return {"decision": "confirm", "confidence": score, "reason": f"Cross-domain analogy score {score:.2f}"}
            return {"decision": "uncertain", "confidence": score, "reason": "Needs LLM evaluation"}

        elif hypothesis.hypothesis_type == HypothesisType.RELATIONAL.value:
            if score > 0.6:
                return {"decision": "confirm", "confidence": score, "reason": f"Relational score {score:.2f}"}
            return {"decision": "uncertain", "confidence": score, "reason": "Weak relational signal"}

        elif hypothesis.hypothesis_type == HypothesisType.CORRECTIVE.value:
            if node_a.contradiction_pressure > 0.5:
                return {"decision": "refine", "confidence": 0.6, "reason": "High contradiction pressure needs resolution"}
            return {"decision": "uncertain", "confidence": 0.3, "reason": "Contradiction pressure insufficient"}

        return {"decision": "uncertain", "confidence": score, "reason": "Default uncertain"}

    # ── Apply Results ──

    def apply_hypothesis_result(self, hypothesis: Hypothesis) -> bool:
        """
        Apply a hypothesis test result to the graph.

        - confirmed → create edge
        - rejected → increase rejection penalty (future hypothesis scoring)
        - refined → create edge with lower strength
        """
        if hypothesis.status == "confirmed":
            strength = max(0.5, hypothesis.test_result.get("confidence", 0.6) if hypothesis.test_result else 0.5)
            edge = self.graph.add_edge(
                hypothesis.node_a,
                hypothesis.node_b,
                hypothesis.hypothesis_type,
                strength,
                reason=hypothesis.reason,
            )
            return edge is not None

        elif hypothesis.status == "refined":
            edge = self.graph.add_edge(
                hypothesis.node_a,
                hypothesis.node_b,
                hypothesis.hypothesis_type,
                strength=0.4,  # Lower strength for refined hypotheses
                reason=f"Refined: {hypothesis.reason}",
            )
            return edge is not None

        return False

    # ── Batch Pipeline ──

    async def run_hypothesis_cycle(
        self,
        llm_client=None,
        llm_model: str = "mistral",
        top_k: int = 10,
    ) -> Dict[str, Any]:
        """
        Run a full hypothesis cycle: detect → select → test → apply.

        Returns:
            Summary of the cycle results
        """
        # Detect
        candidates = self.detect_missing_edges()
        logger.info(f"[HypothesisEngine] Detected {len(candidates)} hypothesis candidates")

        # Select
        top = self.select_top_hypotheses(candidates, top_k)
        logger.info(f"[HypothesisEngine] Selected {len(top)} for testing")

        # Test
        confirmed = 0
        rejected = 0
        uncertain = 0
        refined = 0

        for hyp in top:
            result = await self.test_hypothesis(hyp, llm_client, llm_model)
            self.apply_hypothesis_result(hyp)
            self._hypotheses[hyp.id] = hyp

            if hyp.status == "confirmed":
                confirmed += 1
            elif hyp.status == "rejected":
                rejected += 1
            elif hyp.status == "uncertain":
                uncertain += 1
            elif hyp.status == "refined":
                refined += 1

        return {
            "detected": len(candidates),
            "tested": len(top),
            "confirmed": confirmed,
            "rejected": rejected,
            "uncertain": uncertain,
            "refined": refined,
            "new_edges": confirmed + refined,
        }

    # ── Helpers ──

    def _edge_exists(self, from_id: str, to_id: str, relation_type: Optional[str] = None) -> bool:
        """Check if an edge exists between two nodes."""
        for edge_id, edge in self.graph._edges.items():
            if edge.from_node == from_id and edge.to_node == to_id:
                if relation_type is None or edge.relation_type == relation_type:
                    return True
            # Check symmetric reverse
            if edge.from_node == to_id and edge.to_node == from_id:
                if edge.relation_type in ("supports", "contradicts", "analogous_to"):
                    if relation_type is None or edge.relation_type == relation_type:
                        return True
        return False

    def get_hypothesis(self, hyp_id: str) -> Optional[Hypothesis]:
        return self._hypotheses.get(hyp_id)

    def get_stats(self) -> Dict[str, Any]:
        by_type = {}
        by_status = {}
        for h in self._hypotheses.values():
            by_type[h.hypothesis_type] = by_type.get(h.hypothesis_type, 0) + 1
            by_status[h.status] = by_status.get(h.status, 0) + 1

        return {
            "total_hypotheses": len(self._hypotheses),
            "by_type": by_type,
            "by_status": by_status,
        }


def _cosine(a: List[float], b: List[float]) -> float:
    import numpy as np
    if not a or not b or len(a) != len(b):
        return 0.0
    a_np = np.array(a, dtype=float)
    b_np = np.array(b, dtype=float)
    norm_a = np.linalg.norm(a_np)
    norm_b = np.linalg.norm(b_np)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(np.dot(a_np, b_np) / (norm_a * norm_b))


def _text_overlap(a: str, b: str) -> float:
    """Simple word-level Jaccard overlap."""
    words_a = set(a.lower().split())
    words_b = set(b.lower().split())
    if not words_a or not words_b:
        return 0.0
    return len(words_a & words_b) / len(words_a | words_b)
