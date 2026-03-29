"""
Data models for retrieval system.

These define the core structures for retrieved items and context assembly.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional


@dataclass
class RetrievedItem:
    """
    A single retrieved item from the knowledge store.

    Attributes:
        content: The text content of the atom.
        source: Source identifier (e.g., URL or "v3_knowledge").
        strategy: Retrieval strategy used (e.g., "semantic").
        knowledge_level: Knowledge level (A, B, C, D); default "B".
        item_type: Type of atom (e.g., "claim", "definition").
        relevance_score: Normalized relevance (0-1) based on vector distance.
        trust_score: Trust score from metadata (0-1).
        recency_days: Days since capture; computed from timestamp.
        tech_density: Technical content density (0-1).
        citation_key: Assigned citation key like [A001]; set during build_context_block.
        metadata: Additional raw metadata from storage.
    """
    content: str
    source: str
    strategy: str
    knowledge_level: str = "B"
    item_type: str = "claim"
    relevance_score: float = 0.0
    trust_score: float = 0.5
    recency_days: int = 9999
    tech_density: float = 0.5
    citation_key: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RoleBasedContext:
    """
    Assembled context organized by role/section for synthesis.

    The retrieval layer populates these lists; the build_context_block method
    formats them into a human-readable block with sequential citations.
    """
    definitions: List[RetrievedItem] = field(default_factory=list)
    evidence: List[RetrievedItem] = field(default_factory=list)
    contradictions: List[RetrievedItem] = field(default_factory=list)
    project_artifacts: List[RetrievedItem] = field(default_factory=list)
    unresolved: List[RetrievedItem] = field(default_factory=list)

    @property
    def all_items(self) -> List[RetrievedItem]:
        """Return all items in the order they should appear in the context block."""
        return (
            self.definitions +
            self.evidence +
            self.contradictions +
            self.project_artifacts +
            self.unresolved
        )

    @property
    def is_empty(self) -> bool:
        """True if no items are present."""
        return len(self.all_items) == 0
