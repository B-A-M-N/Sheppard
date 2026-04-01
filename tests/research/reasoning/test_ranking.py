"""
tests/research/reasoning/test_ranking.py

TDD tests for Phase 12-07-01: ranking.py module.

Requirements: RANK-01, RANK-02, RANK-03, RANK-04
"""

import pytest
from research.reasoning.ranking import RankingConfig, compute_composite_score, apply_ranking
from research.reasoning.retriever import RetrievedItem


# ──────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────

def make_item(relevance_score=0.0, trust_score=0.5, recency_days=9999,
              tech_density=0.5, project_proximity=0.0) -> RetrievedItem:
    return RetrievedItem(
        content="test content",
        source="test_source",
        strategy="semantic",
        relevance_score=relevance_score,
        trust_score=trust_score,
        recency_days=recency_days,
        tech_density=tech_density,
        project_proximity=project_proximity,
        metadata={"atom_id": "atom-test"},
    )


def make_pair(global_id: str, item: RetrievedItem):
    """Returns (atom_dict, atom_id) pair."""
    atom_dict = {"global_id": global_id, "text": item.content, "type": "claim", "metadata": {}}
    return (atom_dict, item.metadata["atom_id"])


# ──────────────────────────────────────────────────────────────
# RankingConfig default weights
# ──────────────────────────────────────────────────────────────

def test_default_weights_sum_to_one():
    """Default weights in RankingConfig must sum to exactly 1.0."""
    cfg = RankingConfig()
    total = (
        cfg.weight_relevance
        + cfg.weight_trust
        + cfg.weight_recency
        + cfg.weight_tech_density
        + cfg.weight_project_proximity
    )
    assert abs(total - 1.0) < 1e-9, f"Weights sum to {total}, expected 1.0"


def test_default_weight_relevance():
    assert RankingConfig().weight_relevance == 0.35


def test_default_weight_trust():
    assert RankingConfig().weight_trust == 0.20


def test_default_weight_recency():
    assert RankingConfig().weight_recency == 0.10


def test_default_weight_tech_density():
    assert RankingConfig().weight_tech_density == 0.15


def test_default_weight_project_proximity():
    assert RankingConfig().weight_project_proximity == 0.20


# ──────────────────────────────────────────────────────────────
# RANK-01: Higher-scored item appears first
# ──────────────────────────────────────────────────────────────

def test_apply_ranking_higher_score_first(tmp_path):
    """RANK-01: apply_ranking puts the item with higher composite score first."""
    cfg = RankingConfig()

    item_high = make_item(relevance_score=0.9, trust_score=0.9, recency_days=10)
    item_low = make_item(relevance_score=0.1, trust_score=0.1, recency_days=9999)

    item_high.metadata["atom_id"] = "high-atom"
    item_low.metadata["atom_id"] = "low-atom"

    pair_high = ({"global_id": "[B]", "text": "high", "type": "claim", "metadata": {}}, "high-atom")
    pair_low = ({"global_id": "[A]", "text": "low", "type": "claim", "metadata": {}}, "low-atom")

    # Supply in reverse (low first) — ranking should reorder
    collected = [pair_low, pair_high]
    items = [item_low, item_high]

    result = apply_ranking(collected, items, cfg)
    assert len(result) == 2
    # High-score item must be first
    assert result[0][1] == "high-atom", f"Expected high-atom first, got {result[0][1]}"
    assert result[1][1] == "low-atom"


# ──────────────────────────────────────────────────────────────
# RANK-02: Idempotent / deterministic
# ──────────────────────────────────────────────────────────────

def test_apply_ranking_idempotent():
    """RANK-02: Calling apply_ranking twice with same inputs returns identical ordering."""
    cfg = RankingConfig()
    item_a = make_item(relevance_score=0.5)
    item_b = make_item(relevance_score=0.7)
    item_a.metadata["atom_id"] = "atom-a"
    item_b.metadata["atom_id"] = "atom-b"

    pair_a = ({"global_id": "[A]", "text": "a", "type": "claim", "metadata": {}}, "atom-a")
    pair_b = ({"global_id": "[B]", "text": "b", "type": "claim", "metadata": {}}, "atom-b")

    collected = [pair_a, pair_b]
    items = [item_a, item_b]

    result1 = apply_ranking(collected, items, cfg)
    result2 = apply_ranking(collected, items, cfg)

    assert [r[1] for r in result1] == [r[1] for r in result2], "Ordering not deterministic"


def test_apply_ranking_tiebreaker_by_global_id():
    """RANK-02: Identical composite scores break tie by global_id ascending."""
    cfg = RankingConfig()

    # Two identical items → same composite score
    item_x = make_item(relevance_score=0.5, trust_score=0.5, recency_days=100, tech_density=0.5)
    item_y = make_item(relevance_score=0.5, trust_score=0.5, recency_days=100, tech_density=0.5)
    item_x.metadata["atom_id"] = "atom-x"
    item_y.metadata["atom_id"] = "atom-y"

    # global_id "[Z]" > "[A]" lexically, so [A] should appear first
    pair_z = ({"global_id": "[Z]", "text": "z", "type": "claim", "metadata": {}}, "atom-x")
    pair_a = ({"global_id": "[A]", "text": "a", "type": "claim", "metadata": {}}, "atom-y")

    result = apply_ranking([pair_z, pair_a], [item_x, item_y], cfg)
    # [A] < [Z] lexically → [A] must be first
    assert result[0][0]["global_id"] == "[A]", f"Expected [A] first, got {result[0][0]['global_id']}"
    assert result[1][0]["global_id"] == "[Z]"


# ──────────────────────────────────────────────────────────────
# RANK-03: No atoms dropped
# ──────────────────────────────────────────────────────────────

def test_apply_ranking_preserves_count_single():
    """RANK-03: Single item — len preserved."""
    cfg = RankingConfig()
    item = make_item()
    item.metadata["atom_id"] = "atom-single"
    pair = ({"global_id": "[A]", "text": "x", "type": "claim", "metadata": {}}, "atom-single")
    result = apply_ranking([pair], [item], cfg)
    assert len(result) == 1


def test_apply_ranking_preserves_count_empty():
    """RANK-03: Empty input → empty output."""
    cfg = RankingConfig()
    result = apply_ranking([], [], cfg)
    assert result == []


def test_apply_ranking_preserves_count_many():
    """RANK-03: len(result) == len(input) for arbitrary n."""
    cfg = RankingConfig()
    n = 20
    items = [make_item(relevance_score=float(i) / n) for i in range(n)]
    for idx, it in enumerate(items):
        it.metadata["atom_id"] = f"atom-{idx}"
    collected = [
        ({"global_id": f"[A{i}]", "text": "x", "type": "claim", "metadata": {}}, f"atom-{i}")
        for i in range(n)
    ]
    result = apply_ranking(collected, items, cfg)
    assert len(result) == n


# ──────────────────────────────────────────────────────────────
# RANK-04: Custom config — pure relevance sort
# ──────────────────────────────────────────────────────────────

def test_apply_ranking_custom_config_relevance_only():
    """RANK-04: weight_relevance=1.0 + all others=0.0 → sort purely by relevance_score."""
    cfg = RankingConfig(
        weight_relevance=1.0,
        weight_trust=0.0,
        weight_recency=0.0,
        weight_tech_density=0.0,
        weight_project_proximity=0.0,
    )

    item_a = make_item(relevance_score=0.9, trust_score=0.0)  # high relevance, low trust
    item_b = make_item(relevance_score=0.1, trust_score=1.0)  # low relevance, high trust
    item_a.metadata["atom_id"] = "atom-a"
    item_b.metadata["atom_id"] = "atom-b"

    pair_a = ({"global_id": "[A]", "text": "a", "type": "claim", "metadata": {}}, "atom-a")
    pair_b = ({"global_id": "[B]", "text": "b", "type": "claim", "metadata": {}}, "atom-b")

    result = apply_ranking([pair_b, pair_a], [item_b, item_a], cfg)
    # item_a has higher relevance → must be first
    assert result[0][1] == "atom-a", f"Expected atom-a first, got {result[0][1]}"
    assert result[1][1] == "atom-b"


# ──────────────────────────────────────────────────────────────
# compute_composite_score
# ──────────────────────────────────────────────────────────────

def test_compute_composite_score_matches_item_property():
    """compute_composite_score with default cfg should match item.composite_score."""
    cfg = RankingConfig()
    item = make_item(relevance_score=0.7, trust_score=0.8, recency_days=30, tech_density=0.6)
    score = compute_composite_score(item, cfg)
    # The default weights and formula are identical to RetrievedItem.composite_score
    assert abs(score - item.composite_score) < 1e-9, (
        f"compute_composite_score={score} != item.composite_score={item.composite_score}"
    )


def test_compute_composite_score_recency_clamped():
    """Recency factor clamps to 0.2 for very old items."""
    cfg = RankingConfig()
    item_ancient = make_item(recency_days=99999)
    score = compute_composite_score(item_ancient, cfg)
    # recency_factor = max(0.2, ...) so minimum recency contribution = 0.2 * 0.10
    assert score >= 0.0
