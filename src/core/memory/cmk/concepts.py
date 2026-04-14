"""
cmk/concepts.py — Concept construction from atom clusters.

Builds Concept nodes from clustered CMKAtoms with:
  - Centroid computation
  - Aggregate quality signals
  - Relationship stubs (for future graph traversal)
"""

import logging
import uuid
from typing import List, Dict, Any

from .types import CMKAtom, Concept

logger = logging.getLogger(__name__)


def build_concept(
    atoms: List[CMKAtom],
    centroid: List[float],
    concept_id: str | None = None,
) -> Concept:
    """
    Build a Concept from a cluster of CMKAtoms and their centroid vector.

    Args:
        atoms: List of CMKAtoms in this cluster
        centroid: Pre-computed centroid vector
        concept_id: Optional explicit ID (auto-generated if None)

    Returns:
        Concept node with aggregate quality and relationship stubs
    """
    if not atoms:
        raise ValueError("Cannot build concept from empty atom list")

    # Compute aggregate quality
    reliability = sum(a.reliability for a in atoms) / len(atoms)
    centrality = sum(a.centrality for a in atoms) / len(atoms)

    # Build summary from top atoms (sorted by reliability)
    sorted_atoms = sorted(atoms, key=lambda a: a.reliability, reverse=True)
    summary_parts = []
    char_count = 0
    for atom in sorted_atoms[:5]:
        if char_count + len(atom.content) > 1200:
            break
        summary_parts.append(atom.content)
        char_count += len(atom.content)

    summary = " ".join(summary_parts)

    # Derive name from atom types
    types = set(a.atom_type for a in atoms)
    name = " / ".join(sorted(types))[:50] or "concept"

    return Concept(
        id=concept_id or f"concept_{uuid.uuid4().hex[:8]}",
        name=name,
        summary=summary,
        atom_ids=[a.id for a in atoms],
        centroid=centroid,
        reliability=reliability,
        centrality=centrality,
        topic_id=atoms[0].topic_id,
        mission_id=atoms[0].mission_id,
        relationships={
            "supports": [],
            "contradicts": [],
            "refines": [],
        },
    )


def build_concepts_from_clusters(
    clusters: Dict[int, List[int]],
    atoms: List[CMKAtom],
    centroids: List[List[float]],
) -> List[Concept]:
    """
    Build multiple Concepts from cluster output.

    Only builds concepts from STABLE clusters (≥5 atoms, low contradiction rate).

    Args:
        clusters: Dict mapping cluster_id → atom_indices
        atoms: Full list of CMKAtoms
        centroids: List of centroid vectors (one per cluster)

    Returns:
        List of stable Concept nodes
    """
    concepts = []

    for cluster_id, indices in sorted(clusters.items()):
        cluster_atoms = [atoms[i] for i in indices if i < len(atoms)]
        if not cluster_atoms:
            continue

        # Stability check: need ≥5 atoms for a valid concept
        if len(cluster_atoms) < 5:
            continue  # Too small — no concept allowed

        # Contradiction rate check
        contradiction_rate = _contradiction_rate(cluster_atoms)
        if contradiction_rate > 0.2:
            continue  # Unstable cluster — no concept allowed

        centroid = centroids[cluster_id] if cluster_id < len(centroids) else []

        concept = build_concept(
            atoms=cluster_atoms,
            centroid=centroid,
            concept_id=f"concept_{cluster_id}",
        )
        concepts.append(concept)

    return concepts


def _contradiction_rate(atoms: List[CMKAtom]) -> float:
    """
    Estimate contradiction rate within a cluster.

    Uses the contradicts graph edges as a signal.
    """
    if len(atoms) < 2:
        return 0.0

    atom_ids = {a.id for a in atoms}
    contradiction_count = 0

    for atom in atoms:
        for contradicts_id in atom.contradicts:
            if contradicts_id in atom_ids:
                contradiction_count += 1

    # Each contradiction is counted twice (A→B and B→A)
    return contradiction_count / (2 * len(atoms))
