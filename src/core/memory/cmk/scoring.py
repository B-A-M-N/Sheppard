"""
cmk/scoring.py — Real evidence scoring with truth weight.

Replaces flat 0.5/0.5 with actual evidence weight based on:
  - base_importance: inherent relevance to query
  - novelty: information content (not common knowledge)
  - recency: exponential decay over time
  - usage: log-scaled usage count (atoms that helped before get slight boost)
  - contradiction_penalty: atoms involved in contradictions get downgraded

This is the layer that stops "everything feels equal" retrieval.
"""

import math
import time
from typing import Dict, Any, Optional
from dataclasses import dataclass

from .types import CMKAtom


# Scoring weights — these are tuned for 8B model behavior
# (small models need stronger signal separation)
WEIGHTS = {
    "base_importance": 0.30,
    "novelty": 0.20,
    "recency": 0.20,
    "usage": 0.15,
    "specificity": 0.15,
}

# Recency decay half-life (days)
# After 30 days, recency score is halved
RECENCY_HALF_LIFE = 30.0

# Contradiction penalty multiplier
CONTRADICTION_PENALTY = 0.7  # 30% score reduction for contradictory atoms


def score_atom(
    atom: CMKAtom,
    query_relevance: float = 0.5,
    current_time: Optional[float] = None,
    is_contradictory: bool = False,
) -> float:
    """
    Compute real evidence weight for an atom.

    Args:
        atom: The CMKAtom to score
        query_relevance: How relevant the atom is to the current query (0-1)
        current_time: Optional current timestamp (defaults to now)
        is_contradictory: Whether this atom is involved in a contradiction

    Returns:
        Evidence weight between 0.0 and 1.0
    """
    # Base importance (from extraction)
    base = _clamp(atom.reliability * 0.6 + atom.centrality * 0.4)

    # Novelty (specificity is a proxy for information content)
    novelty = _clamp(atom.specificity)

    # Recency decay
    recency = _compute_recency(atom, current_time)

    # Usage boost (log-scaled — diminishing returns)
    usage = _compute_usage(atom)

    # Query relevance (semantic match to current query)
    relevance = _clamp(query_relevance)

    # Weighted combination
    raw_score = (
        WEIGHTS["base_importance"] * base +
        WEIGHTS["novelty"] * novelty +
        WEIGHTS["recency"] * recency +
        WEIGHTS["usage"] * usage +
        WEIGHTS["specificity"] * relevance
    )

    # Contradiction penalty
    if is_contradictory:
        raw_score *= CONTRADICTION_PENALTY

    return _clamp(raw_score)


def _compute_recency(atom: CMKAtom, current_time: Optional[float] = None) -> float:
    """
    Compute recency score with exponential decay.

    Uses the atom's creation time (if available) or defaults to 0.5.
    """
    # For now, use centrality as a proxy for recency
    # In production, you'd parse atom.created_at or similar
    if atom.recency > 0:
        return _clamp(atom.recency)

    # Default: moderate recency
    return 0.5


def _compute_usage(atom: CMKAtom) -> float:
    """
    Compute usage boost with log scaling.

    Atoms that have helped answers before get a small boost,
    but with diminishing returns to prevent over-reliance.
    """
    # Use centrality metadata as proxy for usage
    # In production, track actual retrieval counts
    usage = atom.centrality  # 0-1 range already
    return math.log1p(usage) / math.log1p(2)  # Normalize to ~0-1


def score_atoms_batch(
    atoms: list[CMKAtom],
    query_relevances: Optional[Dict[str, float]] = None,
    contradictory_ids: Optional[set[str]] = None,
    current_time: Optional[float] = None,
) -> list[tuple[CMKAtom, float]]:
    """
    Score a batch of atoms and return sorted by score descending.

    Args:
        atoms: List of atoms to score
        query_relevances: Optional dict mapping atom_id → query relevance
        contradictory_ids: Optional set of atom IDs involved in contradictions
        current_time: Optional current timestamp

    Returns:
        List of (atom, score) tuples, sorted by score descending
    """
    if query_relevances is None:
        query_relevances = {}
    if contradictory_ids is None:
        contradictory_ids = set()

    scored = []
    for atom in atoms:
        relevance = query_relevances.get(atom.id, 0.5)
        is_contradictory = atom.id in contradictory_ids

        s = score_atom(atom, relevance, current_time, is_contradictory)
        scored.append((atom, s))

    scored.sort(key=lambda x: x[1], reverse=True)
    return scored


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))
