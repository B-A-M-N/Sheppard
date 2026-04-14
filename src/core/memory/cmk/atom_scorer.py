"""
cmk/atom_scorer.py — Dynamic, context-sensitive atom scoring.

Replaces flat 0.5/0.5 with scoring that depends on:
  - atom quality signals (reliability, specificity, centrality, recency)
  - query match (keyword overlap, type match)
  - intent context (which atom types matter for this query)

Score formula:
  effective_score = (
    0.35 * reliability +
    0.20 * specificity +
    0.15 * centrality +
    0.10 * recency +
    0.20 * query_relevance
  )

Weights can be adjusted per intent type.
"""

import re
from typing import Dict, Any

from .types import CMKAtom
from .intent_profiler import IntentProfile
from .evidence_planner import EvidencePlan


# Default scoring weights
DEFAULT_WEIGHTS = {
    "reliability": 0.35,
    "specificity": 0.20,
    "centrality": 0.15,
    "recency": 0.10,
    "query_relevance": 0.20,
}

# Intent-specific weight adjustments
INTENT_WEIGHTS = {
    "factual": {
        "reliability": 0.45,
        "query_relevance": 0.25,
        "specificity": 0.15,
        "centrality": 0.10,
        "recency": 0.05,
    },
    "comparative": {
        "reliability": 0.30,
        "query_relevance": 0.30,
        "specificity": 0.20,
        "centrality": 0.10,
        "recency": 0.10,
    },
    "procedural": {
        "reliability": 0.40,
        "query_relevance": 0.25,
        "specificity": 0.15,
        "centrality": 0.15,
        "recency": 0.05,
    },
    "conceptual": {
        "reliability": 0.25,
        "query_relevance": 0.20,
        "specificity": 0.25,
        "centrality": 0.20,
        "recency": 0.10,
    },
    "exploratory": {
        "reliability": 0.20,
        "query_relevance": 0.20,
        "specificity": 0.20,
        "centrality": 0.20,
        "recency": 0.20,
    },
}


def score_atom(
    atom: CMKAtom,
    query: str,
    intent: IntentProfile | None = None,
    plan: EvidencePlan | None = None,
    weights: Dict[str, float] | None = None,
) -> float:
    """
    Compute effective score for an atom given the query context.

    Args:
        atom: The CMKAtom to score
        query: The user's query string
        intent: Optional intent profile for weight adjustment
        plan: Optional evidence plan for type boosting
        weights: Optional custom weights (overrides intent-based weights)

    Returns:
        Score between 0.0 and 1.0
    """
    # Select weights based on intent
    if weights is None:
        if intent is not None:
            intent_weights = INTENT_WEIGHTS.get(intent.type, DEFAULT_WEIGHTS)
            # Merge: start with defaults, override with intent-specific
            weights = dict(DEFAULT_WEIGHTS)
            weights.update(intent_weights)
        else:
            weights = dict(DEFAULT_WEIGHTS)

    # Compute individual components
    reliability = _clamp(atom.reliability)
    specificity = _clamp(atom.specificity)
    centrality = _clamp(atom.centrality)
    recency = _clamp(atom.recency)
    query_relevance = _query_relevance(atom, query)

    # Apply plan boosts
    type_boost = 1.0
    if plan and atom.atom_type in plan.boost_types:
        type_boost = 1.3  # 30% boost for preferred types

    # Penalize excluded types
    if plan and atom.atom_type in plan.exclude:
        return 0.0

    # Compute weighted score
    score = (
        weights["reliability"] * reliability +
        weights["specificity"] * specificity +
        weights["centrality"] * centrality +
        weights["recency"] * recency +
        weights["query_relevance"] * query_relevance
    )

    # Apply type boost
    score *= type_boost

    return _clamp(score)


def _query_relevance(atom: CMKAtom, query: str) -> float:
    """
    Compute how well the atom's content matches the query.

    Simple heuristic: keyword overlap ratio.
    """
    if not query or not atom.content:
        return 0.0

    query_lower = query.lower()
    content_lower = atom.content.lower()

    # Extract meaningful query terms (filter stopwords)
    stopwords = {
        'the', 'a', 'an', 'is', 'are', 'was', 'were', 'be', 'been',
        'being', 'have', 'has', 'had', 'do', 'does', 'did', 'will',
        'would', 'could', 'should', 'may', 'might', 'shall', 'can',
        'to', 'of', 'in', 'for', 'on', 'with', 'at', 'by', 'from',
        'as', 'into', 'through', 'during', 'before', 'after', 'above',
        'below', 'between', 'under', 'again', 'further', 'then', 'once',
        'and', 'but', 'or', 'nor', 'not', 'so', 'yet', 'both', 'either',
        'neither', 'each', 'every', 'all', 'any', 'few', 'more', 'most',
        'other', 'some', 'such', 'no', 'only', 'own', 'same', 'than',
        'too', 'very', 'just', 'about', 'what', 'how', 'why', 'who',
        'which', 'that', 'this', 'these', 'those', 'it', 'its',
    }

    query_terms = set(
        w for w in re.findall(r'\b\w{3,}\b', query_lower)
        if w not in stopwords
    )

    if not query_terms:
        return 0.5  # No meaningful terms, neutral score

    # Count how many query terms appear in content
    matches = sum(1 for term in query_terms if term in content_lower)

    return matches / len(query_terms)


def _clamp(value: float) -> float:
    """Clamp value to [0.0, 1.0]."""
    return max(0.0, min(1.0, value))


class AtomScorer:
    """
    Stateful scorer that caches weights and supports batch scoring.
    """

    def __init__(self, weights: Dict[str, float] | None = None):
        """
        Args:
            weights: Optional default weights
        """
        self.weights = weights or dict(DEFAULT_WEIGHTS)

    def score(
        self,
        atom: CMKAtom,
        query: str,
        intent: IntentProfile | None = None,
        plan: EvidencePlan | None = None,
    ) -> float:
        """Score a single atom."""
        return score_atom(atom, query, intent, plan, self.weights)

    def score_batch(
        self,
        atoms: list[CMKAtom],
        query: str,
        intent: IntentProfile | None = None,
        plan: EvidencePlan | None = None,
        min_score: float = 0.0,
    ) -> list[tuple[CMKAtom, float]]:
        """
        Score a batch of atoms and return sorted by score descending.

        Args:
            atoms: List of atoms to score
            query: The user query
            intent: Optional intent profile
            plan: Optional evidence plan
            min_score: Minimum score threshold for filtering

        Returns:
            List of (atom, score) tuples, sorted by score descending
        """
        scored = []
        for atom in atoms:
            s = self.score(atom, query, intent, plan)
            if s >= min_score:
                scored.append((atom, s))

        scored.sort(key=lambda x: x[1], reverse=True)
        return scored
