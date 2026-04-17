"""
cmk/contradiction_detector.py — Identifies conflicting atoms.

Uses:
  - Content similarity (embedding cosine) + sentiment/polarity check
  - Keyword-based contradiction patterns
  - Explicit graph edges (contradicts field)
"""

import logging
from enum import Enum
from typing import List, Dict, Any, Optional

from .types import CMKAtom

logger = logging.getLogger(__name__)


class ContradictionType(str, Enum):
    DIRECT = "direct"
    QUALIFIED = "qualified"
    SCOPE_MISMATCH = "scope_mismatch"
    DEGREE_MISMATCH = "degree_mismatch"
    TEMPORAL_MISMATCH = "temporal_mismatch"
    TERMINOLOGY_MISMATCH = "terminology_mismatch"
    NO_CONTRADICTION = "no_contradiction"


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
                            **_typed_conflict(atom.content, other.content, default_type=ContradictionType.DIRECT.value),
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
                    typed = _typed_conflict(atom_a.content, atom_b.content)
                    contradictions.append({
                        "atom_a": atom_a.id,
                        "atom_b": atom_b.id,
                        "description": _describe_conflict(atom_a.content, atom_b.content),
                        **typed,
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


def _typed_conflict(text_a: str, text_b: str, default_type: str = ContradictionType.DIRECT.value) -> Dict[str, Any]:
    joined = f"{text_a} {text_b}".lower()
    contradiction_type = default_type
    why = "The claims appear incompatible."
    can_both_be_true = False
    resolution_hint = "Check the scope and qualifiers."
    if any(token in joined for token in ("version", "before", "after", "current", "previous")):
        contradiction_type = ContradictionType.TEMPORAL_MISMATCH.value
        why = "The disagreement appears tied to different time periods or versions."
        can_both_be_true = True
        resolution_hint = "Align the version or time window."
    elif any(token in joined for token in ("environment", "linux", "windows", "staging", "production")):
        contradiction_type = ContradictionType.SCOPE_MISMATCH.value
        why = "The claims apply to different environments or scopes."
        can_both_be_true = True
        resolution_hint = "Separate the environments or scopes before adjudicating."
    elif any(token in joined for token in ("usually", "sometimes", "often", "rarely", "always", "never")):
        contradiction_type = ContradictionType.QUALIFIED.value
        why = "Qualifiers differ across the two claims."
        can_both_be_true = True
        resolution_hint = "Preserve qualifiers and compare exact bounds."
    elif any(token in joined for token in ("higher", "lower", "faster", "slower", "more", "less")):
        contradiction_type = ContradictionType.DEGREE_MISMATCH.value
        why = "The claims disagree on degree rather than absolute truth."
        can_both_be_true = True
        resolution_hint = "Check the baseline, metric, and magnitude."
    elif any(token in joined for token in ("called", "definition", "means", "term")):
        contradiction_type = ContradictionType.TERMINOLOGY_MISMATCH.value
        why = "The disagreement may be terminological."
        can_both_be_true = True
        resolution_hint = "Normalize terminology first."
    return {
        "type": contradiction_type,
        "why": why,
        "claim_a_scope": text_a,
        "claim_b_scope": text_b,
        "can_both_be_true": can_both_be_true,
        "resolution_hint": resolution_hint,
    }
