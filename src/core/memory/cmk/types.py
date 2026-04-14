"""
cmk/types.py — Core data structures for the Cognitive Memory Kernel.

Defines:
  - CMKAtom: enriched atom with embedding + quality signals
  - Concept: clustered concept node with centroid + relationships
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any


@dataclass
class CMKAtom:
    """
    Enriched atom with embedding and quality signals.
    Replaces flat 0.5/0.5 with dynamic, context-sensitive scoring.
    """
    id: str
    content: str
    embedding: Optional[List[float]] = None

    # Semantic role
    atom_type: str = "claim"  # fact, definition, mechanism, claim, example, contradiction

    # Belief state — ONLY 'observed' atoms can support generalization
    atom_state: str = "observed"  # observed | inferred | speculative

    # Quality signals (0.0-1.0)
    reliability: float = 0.5
    specificity: float = 0.5
    centrality: float = 0.5
    recency: float = 0.5

    # Lineage
    source_id: str = ""
    mission_id: str = ""
    topic_id: str = ""
    confidence: float = 0.5

    # Graph hooks (atom IDs)
    supports: List[str] = field(default_factory=list)
    contradicts: List[str] = field(default_factory=list)
    refines: List[str] = field(default_factory=list)

    # Legacy fields (for backward compat)
    importance: float = 0.5
    novelty: float = 0.5

    # Chroma metadata (for retrieval)
    chroma_metadata: Dict[str, Any] = field(default_factory=dict)

    # Usage tracking (for scoring boost)
    usage_count: int = 0

    @classmethod
    def classify_state(cls, atom_dict: Dict[str, Any]) -> str:
        """
        Classify atom belief state from extraction metadata.

        - 'observed': directly extracted from source, single-source
        - 'inferred': derived from multiple atoms (has parent_objects)
        - 'speculative': weak confidence or single-source with low reliability
        """
        confidence = float(atom_dict.get("confidence", 0.5))
        source_count = len(atom_dict.get("source_ids", []))
        has_parents = bool(atom_dict.get("lineage", {}).get("parent_objects", []))

        if confidence < 0.4:
            return "speculative"
        if has_parents or source_count >= 2:
            return "inferred"
        if confidence >= 0.7:
            return "observed"
        return "speculative"

    @classmethod
    def from_knowledge_unit(cls, ku_dict: Dict[str, Any], embedding: Optional[List[float]] = None) -> "CMKAtom":
        """
        Convert a KnowledgeUnit dict (from pipeline extraction) into a CMKAtom.
        Extracts quality signals from existing fields.
        """
        atom_type = ku_dict.get("atom_type", ku_dict.get("type", "claim"))
        content = ku_dict.get("text", ku_dict.get("content", ""))

        # Derive specificity from content length (longer = more specific, up to a point)
        specificity = min(1.0, len(content) / 200.0) if content else 0.3

        return cls(
            id=ku_dict.get("id", ""),
            content=content,
            embedding=embedding,
            atom_type=atom_type,
            reliability=float(ku_dict.get("confidence", 0.5)),
            specificity=specificity,
            centrality=float(ku_dict.get("importance", 0.5)),
            recency=0.5,  # Will be updated with timestamp
            source_id=ku_dict.get("source", ""),
            topic_id=ku_dict.get("topic", ""),
            confidence=float(ku_dict.get("confidence", 0.5)),
            importance=float(ku_dict.get("importance", 0.5)),
            novelty=float(ku_dict.get("novelty", 0.5)),
            chroma_metadata=ku_dict.get("metadata", {}),
        )

    @classmethod
    def from_knowledge_atom(cls, ka_dict: Dict[str, Any], embedding: Optional[List[float]] = None) -> "CMKAtom":
        """
        Convert legacy KnowledgeAtom dict into CMKAtom.
        """
        content = ka_dict.get("statement", ka_dict.get("title", ""))
        specificity = min(1.0, len(content) / 200.0) if content else 0.3

        return cls(
            id=ka_dict.get("atom_id", ""),
            content=content,
            embedding=embedding,
            atom_type=ka_dict.get("atom_type", "claim"),
            reliability=float(ka_dict.get("confidence", 0.5)),
            specificity=specificity,
            centrality=float(ka_dict.get("importance", 0.5)),
            recency=0.5,
            source_id=ka_dict.get("source", ""),
            mission_id=ka_dict.get("mission_id", ""),
            topic_id=ka_dict.get("topic_id", ""),
            confidence=float(ka_dict.get("confidence", 0.5)),
            importance=float(ka_dict.get("importance", 0.5)),
            novelty=float(ka_dict.get("novelty", 0.5)),
        )


@dataclass
class Concept:
    """
    Clustered concept node — the primary retrieval unit in CMK v2+.

    Built from multiple CMKAtoms that share semantic similarity.
    """
    id: str
    name: str
    summary: str

    # Member atoms
    atom_ids: List[str]

    # Centroid vector (mean of member embeddings)
    centroid: List[float]

    # Aggregate quality
    reliability: float
    centrality: float

    # Graph relationships to other concepts (concept IDs)
    relationships: Dict[str, List[str]] = field(default_factory=lambda: {
        "supports": [],
        "contradicts": [],
        "refines": [],
    })

    # Lineage
    topic_id: str = ""
    mission_id: str = ""

    @classmethod
    def from_cluster(cls, concept_id: str, atoms: List[CMKAtom], centroid: List[float]) -> "Concept":
        """
        Build a Concept from a cluster of CMKAtoms and their centroid vector.
        """
        import numpy as np

        reliability = float(np.mean([a.reliability for a in atoms])) if atoms else 0.5
        centrality = float(np.mean([a.centrality for a in atoms])) if atoms else 0.5

        # Summary: concatenate top 5 atoms, capped at 1200 chars
        sorted_atoms = sorted(atoms, key=lambda a: a.reliability, reverse=True)
        summary = " ".join(a.content for a in sorted_atoms[:5])[:1200]

        # Name: derived from atom types
        types = set(a.atom_type for a in atoms)
        name = " / ".join(types)[:50] or "concept"

        topic_id = atoms[0].topic_id if atoms else ""
        mission_id = atoms[0].mission_id if atoms else ""

        return cls(
            id=concept_id,
            name=name,
            summary=summary,
            atom_ids=[a.id for a in atoms],
            centroid=centroid,
            reliability=reliability,
            centrality=centrality,
            topic_id=topic_id,
            mission_id=mission_id,
        )
