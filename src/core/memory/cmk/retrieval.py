"""
cmk/retrieval.py — Concept-level retrieval → atom expansion.

Replaces flat vector dump with:
  1. Query → concept-level retrieval (via centroid similarity)
  2. Concept → atom expansion (grounding)
  3. Return structured (concept, atoms) pairs
"""

import logging
from typing import List, Dict, Optional, Tuple

from .types import CMKAtom, Concept

logger = logging.getLogger(__name__)


def cosine_similarity(a: List[float], b: List[float]) -> float:
    """Compute cosine similarity between two vectors."""
    import numpy as np
    a_np = np.array(a, dtype=float)
    b_np = np.array(b, dtype=float)

    norm_a = np.linalg.norm(a_np)
    norm_b = np.linalg.norm(b_np)

    if norm_a == 0 or norm_b == 0:
        return 0.0

    return float(np.dot(a_np, b_np) / (norm_a * norm_b))


class CMKRetriever:
    """
    Concept-level retriever.

    Retrieval flow:
      query_vec → score concepts by centroid similarity → expand top concepts → return atoms
    """

    def __init__(
        self,
        concepts: List[Concept],
        atom_store: Dict[str, CMKAtom],
    ):
        """
        Args:
            concepts: List of Concept nodes
            atom_store: Dict mapping atom_id → CMKAtom (for expansion)
        """
        self.concepts = concepts
        self.atom_store = atom_store

    def retrieve(
        self,
        query_vec: List[float],
        top_k: int = 5,
        min_reliability: float = 0.0,
    ) -> List[Tuple[Concept, float]]:
        """
        Retrieve top-k concepts by centroid similarity to query.

        Args:
            query_vec: Query embedding vector
            top_k: Number of concepts to return
            min_reliability: Minimum concept reliability threshold

        Returns:
            List of (concept, score) pairs, sorted by score descending
        """
        if not self.concepts:
            return []

        scored = []
        for concept in self.concepts:
            if not concept.centroid:
                continue

            if concept.reliability < min_reliability:
                continue

            score = cosine_similarity(concept.centroid, query_vec) * concept.reliability
            scored.append((concept, score))

        scored.sort(key=lambda x: x[1], reverse=True)

        return scored[:top_k]

    def expand_concept(self, concept: Concept) -> List[CMKAtom]:
        """
        Expand a concept into its member atoms.

        Args:
            concept: Concept to expand

        Returns:
            List of CMKAtoms belonging to this concept
        """
        atoms = []
        for atom_id in concept.atom_ids:
            atom = self.atom_store.get(atom_id)
            if atom is not None:
                atoms.append(atom)
        return atoms

    def retrieve_and_expand(
        self,
        query_vec: List[float],
        top_k: int = 5,
        min_reliability: float = 0.0,
    ) -> Tuple[List[Tuple[Concept, float]], List[CMKAtom]]:
        """
        Retrieve concepts and expand to atoms in one call.

        Returns:
            (concept_scores, expanded_atoms)
        """
        concept_scores = self.retrieve(query_vec, top_k, min_reliability)

        expanded: List[CMKAtom] = []
        seen_ids = set()
        for concept, _ in concept_scores:
            for atom in self.expand_concept(concept):
                if atom.id not in seen_ids:
                    expanded.append(atom)
                    seen_ids.add(atom.id)

        return concept_scores, expanded

    def retrieve_direct(
        self,
        query_vec: List[float],
        top_k: int = 20,
        min_reliability: float = 0.0,
    ) -> List[Tuple[CMKAtom, float]]:
        """
        Direct atom retrieval (fallback when concepts aren't available).

        Scores atoms directly by cosine similarity to query.

        Returns:
            List of (atom, score) pairs
        """
        if not self.atom_store:
            return []

        scored = []
        for atom in self.atom_store.values():
            if atom.embedding is None:
                continue

            if atom.reliability < min_reliability:
                continue

            score = cosine_similarity(atom.embedding, query_vec) * atom.reliability
            scored.append((atom, score))

        scored.sort(key=lambda x: x[1], reverse=True)

        return scored[:top_k]
