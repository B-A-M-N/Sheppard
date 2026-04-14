"""
cmk/inference.py — Cross-Domain Inference Engine + Global Coherence Scoring.

Cross-domain inference:
  Query → retrieve local beliefs → expand via concept anchors →
  traverse analogy edges → collect convergent structures → synthesize

Global coherence scoring:
  intra_cluster_consistency + cross_cluster_support - contradiction_spread + concept_connectivity

This is what enables structural explanations across domains:
  "Why do neural networks generalize?"
  → ML beliefs → concept "compression" → thermodynamics → biology → information theory
  → merge shared structure → unified explanation
"""

import logging
from typing import List, Dict, Any, Optional, Set, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timezone

from .belief_graph import BeliefGraph, BeliefNode, BeliefEdge, RelationType
from .concept_anchors import ConceptAnchorStore, ConceptAnchor

logger = logging.getLogger(__name__)


@dataclass
class InferenceResult:
    """Result of a cross-domain inference query."""
    query: str
    local_beliefs: List[BeliefNode]
    expanded_beliefs: List[BeliefNode]
    traversed_concepts: List[ConceptAnchor]
    convergent_structures: List[Dict[str, Any]]
    synthesis: str  # Summary of the inference
    coherence_score: float
    domains_covered: Set[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "query": self.query,
            "local_beliefs": len(self.local_beliefs),
            "expanded_beliefs": len(self.expanded_beliefs),
            "traversed_concepts": [c.name for c in self.traversed_concepts],
            "convergent_structures": len(self.convergent_structures),
            "coherence_score": self.coherence_score,
            "domains_covered": sorted(self.domains_covered),
            "synthesis": self.synthesis,
        }


class CrossDomainInferenceEngine:
    """
    Cross-domain inference engine.

    Enables structural reasoning across all domains via concept anchors.
    """

    def __init__(self, graph: BeliefGraph, concept_store: ConceptAnchorStore):
        self.graph = graph
        self.concept_store = concept_store

    def infer(
        self,
        query: str,
        seed_belief_ids: List[str],
        max_hops: int = 3,
        max_concepts: int = 5,
    ) -> InferenceResult:
        """
        Run cross-domain inference from seed beliefs.

        Args:
            query: The original query
            seed_belief_ids: Starting belief node IDs
            max_hops: Maximum graph traversal depth
            max_concepts: Maximum concept anchors to traverse through

        Returns:
            InferenceResult with expanded beliefs, traversed concepts,
            convergent structures, and coherence score.
        """
        # Step 1: Get local beliefs (seed nodes)
        local_beliefs = []
        for bid in seed_belief_ids:
            node = self.graph.get_node(bid)
            if node:
                local_beliefs.append(node)

        if not local_beliefs:
            return InferenceResult(
                query=query,
                local_beliefs=[],
                expanded_beliefs=[],
                traversed_concepts=[],
                convergent_structures=[],
                synthesis="No seed beliefs found for inference.",
                coherence_score=0.0,
                domains_covered=set(),
            )

        # Step 2: Expand via concept anchors
        expanded_ids = set()
        traversed_concepts = []
        domain_beliefs: Dict[str, List[BeliefNode]] = {}

        for seed in local_beliefs:
            expanded_ids.add(seed.id)
            domain_beliefs.setdefault(seed.domain, []).append(seed)

            # Get concepts linked to this belief
            concepts = self.concept_store.get_concepts_for_belief(seed.id)
            for concept in concepts[:max_concepts]:
                if concept not in traversed_concepts:
                    traversed_concepts.append(concept)

                # Get beliefs from OTHER domains linked to this concept
                cross_beliefs = self.concept_store.get_cross_domain_beliefs(
                    concept.id, exclude_domain=seed.domain
                )
                for domain, belief_ids in cross_beliefs.items():
                    for bid in belief_ids:
                        if bid not in expanded_ids:
                            node = self.graph.get_node(bid)
                            if node:
                                expanded_ids.add(bid)
                                domain_beliefs.setdefault(domain, []).append(node)

        # Step 3: Also expand via graph edges
        for seed in local_beliefs:
            graph_neighbors = self.graph.expand_from(
                seed.id, max_hops=max_hops, min_strength=0.4
            )
            for nid in graph_neighbors:
                if nid not in expanded_ids:
                    node = self.graph.get_node(nid)
                    if node:
                        expanded_ids.add(nid)
                        domain_beliefs.setdefault(node.domain, []).append(node)

        expanded_beliefs = [self.graph.get_node(nid) for nid in expanded_ids]
        expanded_beliefs = [n for n in expanded_beliefs if n is not None]

        # Step 4: Find convergent structures (shared patterns across domains)
        convergent = self._find_convergent_structures(domain_beliefs, traversed_concepts)

        # Step 5: Compute coherence score
        coherence = self._compute_coherence(expanded_beliefs, traversed_concepts)

        # Step 6: Synthesize
        synthesis = self._synthesize(query, domain_beliefs, convergent, traversed_concepts)

        domains_covered = set(domain_beliefs.keys())

        return InferenceResult(
            query=query,
            local_beliefs=local_beliefs,
            expanded_beliefs=expanded_beliefs,
            traversed_concepts=traversed_concepts,
            convergent_structures=convergent,
            synthesis=synthesis,
            coherence_score=coherence,
            domains_covered=domains_covered,
        )

    def _find_convergent_structures(
        self,
        domain_beliefs: Dict[str, List[BeliefNode]],
        concepts: List[ConceptAnchor],
    ) -> List[Dict[str, Any]]:
        """
        Find structural patterns that appear across multiple domains.

        A convergent structure is a concept anchor that links beliefs
        from 2+ domains with similar reasoning patterns.
        """
        structures = []

        for concept in concepts:
            if concept.domain_count >= 2:
                # This concept bridges multiple domains
                domains_with_beliefs = []
                for domain in concept.domains:
                    beliefs_in_domain = [
                        b for b in domain_beliefs.get(domain, [])
                        if b.id in concept.belief_ids
                    ]
                    if beliefs_in_domain:
                        domains_with_beliefs.append({
                            "domain": domain,
                            "beliefs": [b.claim for b in beliefs_in_domain],
                        })

                if len(domains_with_beliefs) >= 2:
                    structures.append({
                        "concept": concept.name,
                        "domains": domains_with_beliefs,
                        "authority": concept.authority_score,
                    })

        structures.sort(key=lambda s: s["authority"], reverse=True)
        return structures

    def _compute_coherence(
        self,
        beliefs: List[BeliefNode],
        concepts: List[ConceptAnchor],
    ) -> float:
        """
        Compute global coherence score:
          intra_cluster_consistency + cross_cluster_support - contradiction_spread + concept_connectivity
        """
        if not beliefs:
            return 0.0

        # Intra-cluster consistency (avg authority within domains)
        domains: Dict[str, List[BeliefNode]] = {}
        for b in beliefs:
            domains.setdefault(b.domain, []).append(b)

        intra_consistency = sum(
            sum(b.authority_score for b in domain_beliefs) / len(domain_beliefs)
            for domain_beliefs in domains.values()
        ) / max(1, len(domains))

        # Cross-cluster support (edges between domains)
        cross_support_count = 0
        total_cross_pairs = 0
        domain_list = list(domains.keys())
        for i in range(len(domain_list)):
            for j in range(i + 1, len(domain_list)):
                total_cross_pairs += 1
                for b1 in domains[domain_list[i]]:
                    for b2 in domains[domain_list[j]]:
                        if self.graph._edges:
                            # Check if edge exists
                            for e in self.graph._edges.values():
                                if (e.from_node == b1.id and e.to_node == b2.id) or \
                                   (e.from_node == b2.id and e.to_node == b1.id):
                                    if e.relation_type in ("supports", "analogous_to"):
                                        cross_support_count += e.strength

        cross_support = cross_support_count / max(1, total_cross_pairs * 10)  # Normalize

        # Contradiction spread
        contradiction_count = sum(
            1 for b in beliefs if b.contradiction_pressure > 0.3
        )
        contradiction_spread = contradiction_count / max(1, len(beliefs))

        # Concept connectivity
        concept_links = sum(
            1 for b in beliefs
            if self.concept_store.get_concepts_for_belief(b.id)
        )
        concept_connectivity = concept_links / max(1, len(beliefs))

        coherence = (
            0.30 * intra_consistency +
            0.25 * min(1.0, cross_support) +
            0.25 * (1.0 - contradiction_spread) +
            0.20 * concept_connectivity
        )

        return max(0.0, min(1.0, coherence))

    def _synthesize(
        self,
        query: str,
        domain_beliefs: Dict[str, List[BeliefNode]],
        convergent: List[Dict[str, Any]],
        concepts: List[ConceptAnchor],
    ) -> str:
        """Generate a synthesis of the cross-domain inference."""
        if not domain_beliefs:
            return "No cross-domain evidence found."

        parts = []

        # Local domain beliefs
        for domain, beliefs in domain_beliefs.items():
            top_claims = [b.claim for b in beliefs[:3]]
            parts.append(f"{domain.upper()}: {'; '.join(top_claims)}")

        # Convergent structures
        if convergent:
            parts.append("\nConvergent patterns:")
            for s in convergent[:3]:
                domain_names = ", ".join(d["domain"] for d in s["domains"])
                parts.append(f"  {s['concept']} → {domain_names}")

        return "\n".join(parts)


def compute_global_coherence(graph: BeliefGraph, concept_store: ConceptAnchorStore) -> Dict[str, float]:
    """
    Compute global coherence metrics for the entire belief graph.

    Returns:
        Dict with coherence breakdown by component.
    """
    all_nodes = list(graph._nodes.values())
    if not all_nodes:
        return {
            "intra_consistency": 0.0,
            "cross_support": 0.0,
            "contraction_spread": 0.0,
            "concept_connectivity": 0.0,
            "overall": 0.0,
        }

    domains: Dict[str, List[BeliefNode]] = {}
    for n in all_nodes:
        domains.setdefault(n.domain or "unknown", []).append(n)

    # Intra consistency
    intra = sum(
        sum(n.authority_score for n in ns) / len(ns)
        for ns in domains.values()
    ) / max(1, len(domains))

    # Contradiction spread
    contradictions = sum(1 for n in all_nodes if n.contradiction_pressure > 0.3)
    contradiction_spread = contradictions / max(1, len(all_nodes))

    # Concept connectivity
    concept_linked = sum(
        1 for n in all_nodes if concept_store.get_concepts_for_belief(n.id)
    )
    concept_connectivity = concept_linked / max(1, len(all_nodes))

    overall = (
        0.30 * intra +
        0.25 * 0.5 +  # Placeholder cross-support (requires edge analysis)
        0.25 * (1.0 - contradiction_spread) +
        0.20 * concept_connectivity
    )

    return {
        "intra_consistency": round(intra, 3),
        "cross_support": 0.5,  # Would need full edge scan
        "contradiction_spread": round(contradiction_spread, 3),
        "concept_connectivity": round(concept_connectivity, 3),
        "overall": round(max(0.0, min(1.0, overall)), 3),
    }
