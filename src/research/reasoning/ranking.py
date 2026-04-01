"""
reasoning/ranking.py

Post-retrieval atom reordering for Phase 12-07 (Ranking Improvements).

Sorting occurs AFTER retrieval from Chroma; no atoms are dropped.
Ranking is opt-in via RetrievalQuery.enable_ranking (default False).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, List, Tuple

if TYPE_CHECKING:
    from research.reasoning.retriever import RetrievedItem

# ──────────────────────────────────────────────────────────────
# Configuration
# ──────────────────────────────────────────────────────────────

@dataclass
class RankingConfig:
    """
    Weight configuration for composite scoring.

    Defaults replicate the weights in RetrievedItem.composite_score so
    that enable_ranking=True with default config produces the same
    relative ordering as the existing property — just exposed as
    configurable parameters.

    project_proximity is intentionally left at full weight (0.20) even
    though V3Retriever always sets it to 0.0 for now. A future phase
    will populate it; zero-value inputs have zero effect.
    """
    weight_relevance: float = 0.35
    weight_trust: float = 0.20
    weight_recency: float = 0.10
    weight_tech_density: float = 0.15
    weight_project_proximity: float = 0.20
    recency_halflife_days: int = 365


# ──────────────────────────────────────────────────────────────
# Scoring
# ──────────────────────────────────────────────────────────────

def compute_composite_score(item: "RetrievedItem", cfg: RankingConfig) -> float:
    """
    Compute a composite relevance score for a single RetrievedItem using
    caller-supplied weight configuration.

    recency_factor is clamped to a minimum of 0.2 so that very old atoms
    still contribute rather than being zeroed out.

    Does NOT mutate item.
    """
    recency_factor = max(0.2, 1.0 - (item.recency_days / cfg.recency_halflife_days))
    return (
        item.relevance_score      * cfg.weight_relevance
        + item.trust_score        * cfg.weight_trust
        + recency_factor          * cfg.weight_recency
        + item.tech_density       * cfg.weight_tech_density
        + item.project_proximity  * cfg.weight_project_proximity
    )


# ──────────────────────────────────────────────────────────────
# Sorting
# ──────────────────────────────────────────────────────────────

def apply_ranking(
    collected: List[Tuple[dict, str]],
    items_parallel: List["RetrievedItem"],
    cfg: RankingConfig,
) -> List[Tuple[dict, str]]:
    """
    Reorder collected (atom_dict, atom_id) pairs by composite score.

    Sort key: (-composite_score, global_id)
      - Descending score: highest-ranked atom first.
      - Ascending global_id as tiebreaker: deterministic across equal scores.

    Guarantees:
      - Returns exactly len(collected) pairs (no filtering).
      - Pure function: does not mutate collected or items_parallel.
      - Deterministic: equal scores resolved by lexical global_id sort.

    Args:
        collected:       List of (atom_dict, atom_id) pairs from the dedup loop.
        items_parallel:  Parallel list of RetrievedItem objects (same order as collected).
        cfg:             RankingConfig supplying scoring weights.

    Returns:
        New sorted list of (atom_dict, atom_id) pairs.
    """
    if not collected:
        return []

    scored: List[Tuple[Tuple[dict, str], float]] = [
        (pair, compute_composite_score(item, cfg))
        for pair, item in zip(collected, items_parallel)
    ]
    # Stable sort: primary = score descending, secondary = global_id ascending
    scored.sort(key=lambda x: (-x[1], x[0][0]["global_id"]))
    return [pair for pair, _ in scored]
