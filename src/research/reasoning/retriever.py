"""
reasoning/retriever.py  (Revised)

4-stage retrieval stack with role-based context assembly.

Stage order:
  1. Lexical prefilter    — exact/near-exact match for tech names, error strings,
                            library names, acronyms. Fast, runs first.
  2. Semantic retrieval   — ChromaDB vector similarity across all knowledge levels
  3. Structural retrieval — same session, same source cluster, same project subsystem,
                            same concept family
  4. Re-ranking           — scores by: query relevance, source trust, recency,
                            tech density, project proximity, contradiction value

Context is assembled by ROLE, not just top-K score:
  2-3 definitions
  3-5 strongest evidence items
  2 contrasting viewpoints / contradictions
  2 project-linked artifacts
  1-2 unresolved issues

This produces far better reasoning than "top 12 nearest chunks."
"""

import asyncio
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────
# Retrieval data structures
# ──────────────────────────────────────────────────────────────

@dataclass
class RetrievedItem:
    """One item from any retrieval stage, normalized."""
    content: str
    source: str
    strategy: str                           # lexical | semantic | structural | project
    knowledge_level: str = "B"              # A | B | C | D
    item_type: str = "claim"                # atom_type, synthesis_type, or "brief"
    relevance_score: float = 0.0
    trust_score: float = 0.5
    recency_days: int = 9999                # days since captured
    tech_density: float = 0.5              # proxy for technical content richness
    project_proximity: float = 0.0          # 0 if not project-linked
    is_contradiction: bool = False
    citation_key: Optional[str] = None
    concept_name: Optional[str] = None
    metadata: Dict = field(default_factory=dict)

    @property
    def composite_score(self) -> float:
        """
        Re-ranking composite score.
        Weights tuned to prioritize project-linked, high-trust, recent items.
        """
        recency_factor = max(0.2, 1.0 - (self.recency_days / 365))
        return (
            self.relevance_score * 0.35
            + self.trust_score * 0.20
            + recency_factor * 0.10
            + self.tech_density * 0.15
            + self.project_proximity * 0.20
        )


@dataclass
class RetrievalQuery:
    text: str
    project_filter: Optional[str] = None
    topic_filter: Optional[str] = None
    mission_filter: Optional[str] = None
    max_results: int = 12
    # Role-based slot sizes
    max_definitions: int = 3
    max_evidence: int = 5
    max_contradictions: int = 2
    max_project_artifacts: int = 2
    max_unresolved: int = 2
    # Stage controls
    lexical_prefilter: bool = True
    graph_depth: int = 2
    knowledge_levels: List[str] = field(
        default_factory=lambda: ["B", "C", "D"]
    )


@dataclass
class RoleBasedContext:
    """The assembled context block, organized by role."""
    definitions: List[RetrievedItem] = field(default_factory=list)
    evidence: List[RetrievedItem] = field(default_factory=list)
    contradictions: List[RetrievedItem] = field(default_factory=list)
    project_artifacts: List[RetrievedItem] = field(default_factory=list)
    unresolved: List[RetrievedItem] = field(default_factory=list)

    @property
    def all_items(self) -> List[RetrievedItem]:
        return (
            self.definitions
            + self.evidence
            + self.contradictions
            + self.project_artifacts
            + self.unresolved
        )

    @property
    def is_empty(self) -> bool:
        return len(self.all_items) == 0


# ──────────────────────────────────────────────────────────────
# Main retriever class
# ──────────────────────────────────────────────────────────────

