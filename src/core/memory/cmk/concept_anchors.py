"""
cmk/concept_anchors.py — Cross-domain abstraction hubs.

Concept anchors are reusable abstractions that connect domains:
  "optimization" → physics, ML, economics, biology
  "feedback loop" → control systems, ecology, psychology
  "compression" → information theory, neuroscience, ML
  "tradeoff" → engineering, economics, evolution

They are the bridges that enable cross-domain reasoning.
"""

import logging
import uuid
from typing import List, Dict, Any, Optional, Set, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


@dataclass
class ConceptAnchor:
    """
    A cross-domain abstraction hub.

    Links belief nodes from different domains that share the same
    underlying structural pattern.
    """
    id: str
    name: str
    description: str = ""
    embedding: Optional[List[float]] = None
    domains: Set[str] = field(default_factory=set)
    belief_ids: List[str] = field(default_factory=list)
    authority_score: float = 0.0
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def domain_count(self) -> int:
        return len(self.domains)

    @property
    def belief_count(self) -> int:
        return len(self.belief_ids)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "domains": sorted(self.domains),
            "belief_ids": self.belief_ids,
            "authority_score": self.authority_score,
            "domain_count": self.domain_count,
            "belief_count": self.belief_count,
        }


# Canonical concept anchors — seeded cross-domain abstractions
CANONICAL_CONCEPTS = [
    ("optimization", "Finding the best solution within constraints — appears in physics (energy minimization), ML (gradient descent), economics (utility maximization), biology (fitness landscapes)"),
    ("feedback_loop", "Output feeds back as input — appears in control systems (PID controllers), ecology (predator-prey cycles), psychology (behavioral reinforcement), engineering (thermostat regulation)"),
    ("compression", "Reducing information while preserving structure — appears in information theory (lossy compression), neuroscience (sensory filtering), ML (dimensionality reduction), linguistics (grammaticalization)"),
    ("tradeoff", "Improving one aspect degrades another — appears in engineering (speed vs accuracy), economics (efficiency vs equity), evolution (reproduction vs survival), computing (space vs time)"),
    ("emergence", "Complex behavior from simple rules — appears in physics (phase transitions), biology (swarm intelligence), economics (market dynamics), CS (cellular automata)"),
    ("energy_minimization", "Systems evolve toward lower energy states — appears in thermodynamics (entropy), ML (loss landscapes), physics (ground states), neuroscience (predictive coding)"),
    ("signal_vs_noise", "Separating meaningful patterns from randomness — appears in statistics (hypothesis testing), communications (SNR), ML (overfitting), biology (gene expression)"),
    ("phase_transition", "Sudden qualitative change at critical threshold — appears in physics (water boiling), ML (grokking), sociology (tipping points), ecology (ecosystem collapse)"),
    ("hierarchical_organization", "Structure at multiple scales — appears in biology (cell→tissue→organ), CS (abstraction layers), physics (effective field theories), linguistics (morpheme→word→sentence)"),
    ("adaptation", "Adjusting to environmental pressures — appears in biology (natural selection), ML (fine-tuning), economics (market adaptation), psychology (cognitive flexibility)"),
    ("resonance", "Amplification at matching frequency — appears in physics (mechanical resonance), neuroscience (neural oscillations), social dynamics (viral content), chemistry (molecular resonance)"),
    ("duality", "Two perspectives on the same structure — appears in math (primal/dual optimization), physics (wave-particle), CS (time/frequency domain), logic (De Morgan's laws)"),
]


class ConceptAnchorStore:
    """
    Manages concept anchors and their links to belief nodes.

    Enables cross-domain traversal: belief → concept anchor → other-domain beliefs.
    """

    def __init__(self, pg_pool=None):
        self.pg_pool = pg_pool
        self._anchors: Dict[str, ConceptAnchor] = {}
        # Reverse index: belief_id → [concept_ids]
        self._belief_index: Dict[str, List[str]] = {}

    def initialize_canonical_concepts(self) -> int:
        """Seed the canonical concept anchors."""
        count = 0
        for name, description in CANONICAL_CONCEPTS:
            if name not in {a.name for a in self._anchors.values()}:
                anchor = ConceptAnchor(
                    id=f"concept_{name}",
                    name=name,
                    description=description,
                )
                self._anchors[anchor.id] = anchor
                count += 1
        return count

    def add_anchor(self, anchor: ConceptAnchor) -> str:
        """Add or update a concept anchor."""
        self._anchors[anchor.id] = anchor
        return anchor.id

    def get_anchor(self, anchor_id: str) -> Optional[ConceptAnchor]:
        return self._anchors.get(anchor_id)

    def find_by_name(self, name: str) -> Optional[ConceptAnchor]:
        for anchor in self._anchors.values():
            if anchor.name.lower() == name.lower():
                return anchor
        return None

    def link_belief(self, belief_id: str, concept_id: str, domain: str = ""):
        """
        Link a belief node to a concept anchor.

        This is how cross-domain connections form:
          belief_node → concept_anchor ← other_belief_node
        """
        anchor = self._anchors.get(concept_id)
        if not anchor:
            logger.warning(f"[ConceptAnchors] Unknown concept: {concept_id}")
            return

        if belief_id not in anchor.belief_ids:
            anchor.belief_ids.append(belief_id)

        if domain:
            anchor.domains.add(domain)

        # Update reverse index
        if belief_id not in self._belief_index:
            self._belief_index[belief_id] = []
        if concept_id not in self._belief_index[belief_id]:
            self._belief_index[belief_id].append(concept_id)

        # Recompute authority
        anchor.authority_score = min(1.0,
            0.3 * min(1.0, len(anchor.domains) / 5.0) +  # Domain diversity
            0.3 * min(1.0, len(anchor.belief_ids) / 20.0) +  # Belief coverage
            0.4 * (1.0 if len(anchor.domains) >= 2 else 0.3)  # Cross-domain bonus
        )

    def get_concepts_for_belief(self, belief_id: str) -> List[ConceptAnchor]:
        """Get all concept anchors linked to a belief."""
        concept_ids = self._belief_index.get(belief_id, [])
        return [self._anchors[cid] for cid in concept_ids if cid in self._anchors]

    def get_cross_domain_beliefs(self, concept_id: str, exclude_domain: str = "") -> Dict[str, List[str]]:
        """
        Get belief IDs organized by domain for a concept anchor.

        Used for cross-domain retrieval: "show me beliefs about 'optimization'
        from domains OTHER than ML".
        """
        anchor = self._anchors.get(concept_id)
        if not anchor:
            return {}

        # In production, we'd look up domains from belief_nodes
        # For now, return all beliefs grouped by domain from anchor metadata
        result = {}
        for domain in anchor.domains:
            if domain != exclude_domain:
                result[domain] = anchor.belief_ids[:5]  # Top 5 per domain

        return result

    def find_similar_concepts(self, query_embedding: List[float], top_k: int = 3) -> List[Tuple[ConceptAnchor, float]]:
        """Find concept anchors with similar embeddings."""
        if not query_embedding:
            return []

        import numpy as np
        scored = []
        for anchor in self._anchors.values():
            if anchor.embedding:
                a = np.array(query_embedding, dtype=float)
                b = np.array(anchor.embedding, dtype=float)
                norm_a = np.linalg.norm(a)
                norm_b = np.linalg.norm(b)
                if norm_a > 0 and norm_b > 0:
                    sim = float(np.dot(a, b) / (norm_a * norm_b))
                    scored.append((anchor, sim))

        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:top_k]

    def get_stats(self) -> Dict[str, Any]:
        return {
            "total_concepts": len(self._anchors),
            "cross_domain_concepts": sum(1 for a in self._anchors.values() if len(a.domains) >= 2),
            "linked_beliefs": len(self._belief_index),
            "avg_domains_per_concept": sum(len(a.domains) for a in self._anchors.values()) / max(1, len(self._anchors)),
            "avg_beliefs_per_concept": sum(len(a.belief_ids) for a in self._anchors.values()) / max(1, len(self._anchors)),
        }
