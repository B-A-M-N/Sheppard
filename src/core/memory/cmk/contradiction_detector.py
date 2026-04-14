"""
cmk/contradiction_detector.py — Identifies conflicting atoms.

Uses:
  - Content similarity (embedding cosine) + sentiment/polarity check
  - Keyword-based contradiction patterns
  - Explicit graph edges (contradicts field)
"""

import logging
from typing import List, Dict, Any, Optional

from .types import CMKAtom

logger = logging.getLogger(__name__)


# Contradiction signal patterns
_CONTRADICTION_PATTERNS = [
    ("not", "is"),
    ("never", "always"),
    ("true", "false"),
    ("increases", "decreases"),
    ("supports", "opposes"),
    ("enables", "prevents"),
    ("causes", "prevents"),
    ("correct", "incorrect"),
    ("valid", "invalid"),
    ("possible", "impossible"),
    ("required", "optional"),
    ("safe", "unsafe"),
    ("works", "fails"),
    ("better", "worse"),
]

# Similarity threshold for contradiction candidate pairs
_SIMILARITY_THRESHOLD = 0.75


class ContradictionDetector:
    """
    Detects contradictory atoms within a set.

    Two atoms are contradictory if:
      1. They are semantically similar (high embedding cosine)
      2. But express opposing claims (polarity mismatch)
    """

    def detect(
        self,
        atoms: List[CMKAtom],
        similarity_threshold: float = _SIMILARITY_THRESHOLD,
    ) -> List[Dict[str, Any]]:
        """
        Find contradictory pairs within the atom set.

        Args:
            atoms: List of atoms to check
            similarity_threshold: Minimum cosine similarity to consider as candidate

        Returns:
            List of contradiction dicts with atom_a, atom_b, description
        """
        if len(atoms) < 2:
            return []

        contradictions = []
        checked_pairs = set()

        # Check explicit graph edges first
        for atom in atoms:
            for contradicts_id in atom.contradicts:
                other = next((a for a in atoms if a.id == contradicts_id), None)
                if other:
                    pair_key = tuple(sorted([atom.id, other.id]))
                    if pair_key not in checked_pairs:
                        checked_pairs.add(pair_key)
                        contradictions.append({
                            "atom_a": atom.id,
                            "atom_b": other.id,
                            "description": _describe_conflict(atom.content, other.content),
                            "type": "explicit",
                        })

        # Check embedding-based contradictions
        atoms_with_embeddings = [a for a in atoms if a.embedding is not None]
        if len(atoms_with_embeddings) < 2:
            return contradictions

        import numpy as np

        for i in range(len(atoms_with_embeddings)):
            for j in range(i + 1, len(atoms_with_embeddings)):
                atom_a = atoms_with_embeddings[i]
                atom_b = atoms_with_embeddings[j]

                pair_key = tuple(sorted([atom_a.id, atom_b.id]))
                if pair_key in checked_pairs:
                    continue
                checked_pairs.add(pair_key)

                # Compute similarity
                sim = _cosine(atom_a.embedding, atom_b.embedding)
                if sim < similarity_threshold:
                    continue

                # Check for contradiction patterns
                if _has_polarity_conflict(atom_a.content, atom_b.content):
                    contradictions.append({
                        "atom_a": atom_a.id,
                        "atom_b": atom_b.id,
                        "description": _describe_conflict(atom_a.content, atom_b.content),
                        "type": "semantic",
                        "similarity": sim,
                    })

        return contradictions


def _cosine(a: List[float], b: List[float]) -> float:
    """Cosine similarity between two vectors."""
    import numpy as np
    a_np = np.array(a, dtype=float)
    b_np = np.array(b, dtype=float)

    norm_a = np.linalg.norm(a_np)
    norm_b = np.linalg.norm(b_np)

    if norm_a == 0 or norm_b == 0:
        return 0.0

    return float(np.dot(a_np, b_np) / (norm_a * norm_b))


def _has_polarity_conflict(text_a: str, text_b: str) -> bool:
    """
    Check if two texts express opposing claims.

    Uses keyword-based pattern matching.
    """
    text_a_lower = text_a.lower()
    text_b_lower = text_b.lower()

    for pos_word, neg_word in _CONTRADICTION_PATTERNS:
        a_has_pos = pos_word in text_a_lower
        a_has_neg = neg_word in text_a_lower
        b_has_pos = pos_word in text_b_lower
        b_has_neg = neg_word in text_b_lower

        # Check if one has positive and other has negative form
        if (a_has_pos and b_has_neg) or (a_has_neg and b_has_pos):
            return True

        # Check for negation patterns
        if _is_negated(text_a_lower, pos_word) and _is_affirmative(text_b_lower, pos_word):
            return True
        if _is_affirmative(text_a_lower, pos_word) and _is_negated(text_b_lower, pos_word):
            return True

    return False


def _is_negated(text: str, word: str) -> bool:
    """Check if a word appears in negated context."""
    negation_words = ["not", "no", "never", "neither", "n't", "cannot", "can't", "won't", "don't", "doesn't", "didn't"]

    words = text.split()
    for i, w in enumerate(words):
        if word in w:
            # Check preceding words for negation
            context_window = words[max(0, i-3):i]
            if any(neg in " ".join(context_window) for neg in negation_words):
                return True
    return False


def _is_affirmative(text: str, word: str) -> bool:
    """Check if a word appears in affirmative context (not negated)."""
    return word in text and not _is_negated(text, word)


def _describe_conflict(text_a: str, text_b: str) -> str:
    """Generate a brief description of the conflict."""
    # Truncate for readability
    a_preview = text_a[:100] + "..." if len(text_a) > 100 else text_a
    b_preview = text_b[:100] + "..." if len(text_b) > 100 else text_b

    return f'"{a_preview}" vs "{b_preview}"'
