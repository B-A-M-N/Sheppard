"""
cmk/builder.py — Core CMK pipeline: atoms → embeddings → clusters → concepts.

Orchestrates the full concept building pipeline:
  1. Embed atoms (if not already embedded)
  2. Cluster embeddings
  3. Build Concept nodes
"""

import logging
from typing import List, Tuple

from .types import CMKAtom, Concept
from .embedder import OllamaEmbedder
from .clustering import cluster_kmeans
from .concepts import build_concepts_from_clusters

logger = logging.getLogger(__name__)


class ConceptBuilder:
    """
    Builds Concepts from raw CMKAtoms.

    Pipeline:
      atoms → embed → cluster → concepts
    """

    def __init__(
        self,
        embedder: OllamaEmbedder | None = None,
        k: int = 12,
        require_embedding: bool = True,
    ):
        """
        Args:
            embedder: OllamaEmbedder instance (creates default if None)
            k: Number of clusters for KMeans
            require_embedding: If True, skips atoms without embeddings
        """
        self.embedder = embedder or OllamaEmbedder()
        self.k = k
        self.require_embedding = require_embedding

    def build(self, atoms: List[CMKAtom]) -> Tuple[List[Concept], List[CMKAtom]]:
        """
        Build Concepts from a list of CMKAtoms.

        Args:
            atoms: Raw atoms (may or may not have embeddings)

        Returns:
            (concepts, embedded_atoms) — concepts built + atoms that were successfully embedded
        """
        if not atoms:
            return [], []

        # Step 1: Embed atoms that don't have embeddings
        atoms_to_embed = [a for a in atoms if a.embedding is None]
        if atoms_to_embed:
            logger.info(f"[ConceptBuilder] Embedding {len(atoms_to_embed)} atoms without embeddings")
            self.embedder.embed_atoms(atoms_to_embed)

        # Filter to atoms with embeddings
        embedded_atoms = [a for a in atoms if a.embedding is not None]
        if not embedded_atoms:
            logger.warning("[ConceptBuilder] No atoms with embeddings, returning empty")
            return [], []

        # Step 2: Extract vectors and cluster
        vectors = [a.embedding for a in embedded_atoms]

        # Adaptive k: don't request more clusters than atoms
        adaptive_k = min(self.k, len(embedded_atoms))
        if adaptive_k < 2:
            # Single cluster
            from .clustering import compute_centroid
            centroid = compute_centroid(vectors)
            concept = build_concept_from_atoms(embedded_atoms, centroid)
            return [concept], embedded_atoms

        clusters, centroids = cluster_kmeans(vectors, adaptive_k)

        # Step 3: Build concepts
        concepts = build_concepts_from_clusters(clusters, embedded_atoms, centroids)

        logger.info(f"[ConceptBuilder] Built {len(concepts)} concepts from {len(embedded_atoms)} atoms")

        return concepts, embedded_atoms

    def build_incremental(
        self,
        new_atoms: List[CMKAtom],
        existing_concepts: List[Concept],
    ) -> Tuple[List[Concept], List[CMKAtom]]:
        """
        Incrementally add new atoms to existing concepts.

        For each new atom, find nearest concept centroid and add to it.
        If no concept is close enough (threshold), create new concept.

        Args:
            new_atoms: New atoms to integrate
            existing_concepts: Current concept set

        Returns:
            (updated_concepts, embedded_atoms)
        """
        if not existing_concepts:
            return self.build(new_atoms)

        if not new_atoms:
            return existing_concepts, []

        # Embed new atoms
        atoms_to_embed = [a for a in new_atoms if a.embedding is None]
        if atoms_to_embed:
            self.embedder.embed_atoms(atoms_to_embed)

        embedded_new = [a for a in new_atoms if a.embedding is not None]
        if not embedded_new:
            return existing_concepts, []

        # Assign each new atom to nearest concept
        import numpy as np

        for atom in embedded_new:
            best_concept = None
            best_score = -1.0

            for concept in existing_concepts:
                if not concept.centroid:
                    continue

                # Cosine similarity
                a = np.array(atom.embedding, dtype=float)
                c = np.array(concept.centroid, dtype=float)

                norm_a = np.linalg.norm(a)
                norm_c = np.linalg.norm(c)
                if norm_a == 0 or norm_c == 0:
                    continue

                score = float(np.dot(a, c) / (norm_a * norm_c))

                if score > best_score:
                    best_score = score
                    best_concept = concept

            if best_concept and best_score > 0.5:  # Threshold for "close enough"
                best_concept.atom_ids.append(atom.id)
                # Recompute centroid (approximate: blend old + new)
                # For accuracy, should re-embed all atoms, but this is fast approx
                atom_embedding = atom.embedding
                old_centroid = best_concept.centroid
                n = len(best_concept.atom_ids)
                best_concept.centroid = [
                    (old_centroid[i] * (n - 1) + atom_embedding[i]) / n
                    for i in range(len(old_centroid))
                ]
                best_concept.reliability = (
                    best_concept.reliability * (n - 1) + atom.reliability
                ) / n
            else:
                # Create new single-atom concept
                from .clustering import compute_centroid
                centroid = compute_centroid([atom.embedding])
                new_concept = build_concept_from_atoms([atom], centroid)
                existing_concepts.append(new_concept)

        return existing_concepts, embedded_new

    def close(self):
        """Cleanup resources."""
        self.embedder.close()


def build_concept_from_atoms(atoms: List[CMKAtom], centroid: List[float], concept_id: str | None = None) -> Concept:
    """Helper: build single Concept from atoms + centroid."""
    from .concepts import build_concept
    return build_concept(atoms, centroid, concept_id)
