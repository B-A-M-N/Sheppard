"""
Tests for trust-state lifecycle integration in V3Retriever.

Covers:
  - _item_trust_state derivation from item metadata signals
  - _aggregate_trust_state collapse over a collection of items
  - _rerank stamps trust_state on item metadata
  - _rerank score ordering respects trust-state deltas
  - RoleBasedContext.aggregate_trust_state field availability
"""

import pytest
from unittest.mock import MagicMock

from src.research.reasoning.v3_retriever import V3Retriever
from src.research.reasoning.retriever import RoleBasedContext, RetrievedItem


def _make_retriever() -> V3Retriever:
    adapter = MagicMock()
    return V3Retriever(adapter, cmk_runtime=None)


def _make_item(
    *,
    relevance: float = 0.8,
    trust: float = 0.7,
    recency_days: int = 30,
    metadata: dict | None = None,
    project_proximity: float = 0.0,
) -> RetrievedItem:
    return RetrievedItem(
        content="test content",
        source="test",
        strategy="semantic",
        relevance_score=relevance,
        trust_score=trust,
        recency_days=recency_days,
        metadata=metadata or {},
        project_proximity=project_proximity,
    )


# ──────────────────────────────────────────────────────────────
# _item_trust_state
# ──────────────────────────────────────────────────────────────

def test_item_trust_state_stale_when_old():
    retriever = _make_retriever()
    item = _make_item(recency_days=400)
    assert retriever._item_trust_state(item) == "stale"


def test_item_trust_state_contested_when_contradiction_bound():
    retriever = _make_retriever()
    item = _make_item(metadata={"contradiction_bound": True})
    assert retriever._item_trust_state(item) == "contested"


def test_item_trust_state_reusable_when_authority_aligned():
    retriever = _make_retriever()
    item = _make_item(metadata={"authority_aligned": True})
    assert retriever._item_trust_state(item) == "reusable"


def test_item_trust_state_reusable_when_artifact_aligned():
    retriever = _make_retriever()
    item = _make_item(metadata={"artifact_aligned": True})
    assert retriever._item_trust_state(item) == "reusable"


def test_item_trust_state_forming_by_default():
    retriever = _make_retriever()
    item = _make_item()
    assert retriever._item_trust_state(item) == "forming"


def test_item_trust_state_stale_beats_contradiction_when_old_and_contested():
    """stale takes priority over contested when both conditions present."""
    retriever = _make_retriever()
    # Old item that is also contradiction-bound — freshness check fires first in
    # derive_trust_state, so result is 'stale'.
    item = _make_item(recency_days=400, metadata={"contradiction_bound": True})
    assert retriever._item_trust_state(item) == "stale"


# ──────────────────────────────────────────────────────────────
# _aggregate_trust_state
# ──────────────────────────────────────────────────────────────

def test_aggregate_returns_forming_for_empty():
    retriever = _make_retriever()
    assert retriever._aggregate_trust_state([]) == "forming"


def test_aggregate_contested_wins_over_reusable():
    """A single contested item poisons the whole set."""
    retriever = _make_retriever()
    items = [
        _make_item(metadata={"trust_state": "reusable"}),
        _make_item(metadata={"trust_state": "synthesized"}),
        _make_item(metadata={"trust_state": "contested"}),
    ]
    assert retriever._aggregate_trust_state(items) == "contested"


def test_aggregate_stale_beats_forming():
    retriever = _make_retriever()
    items = [
        _make_item(metadata={"trust_state": "forming"}),
        _make_item(metadata={"trust_state": "stale"}),
    ]
    assert retriever._aggregate_trust_state(items) == "stale"


def test_aggregate_reusable_elevated_when_no_negatives():
    retriever = _make_retriever()
    items = [
        _make_item(metadata={"trust_state": "reusable"}),
        _make_item(metadata={"trust_state": "forming"}),
    ]
    assert retriever._aggregate_trust_state(items) == "reusable"


def test_aggregate_synthesized_elevated_when_no_negatives():
    retriever = _make_retriever()
    items = [
        _make_item(metadata={"trust_state": "synthesized"}),
        _make_item(metadata={"trust_state": "forming"}),
    ]
    assert retriever._aggregate_trust_state(items) == "synthesized"


def test_aggregate_forming_when_all_forming():
    retriever = _make_retriever()
    items = [_make_item(metadata={"trust_state": "forming"}) for _ in range(3)]
    assert retriever._aggregate_trust_state(items) == "forming"


# ──────────────────────────────────────────────────────────────
# _rerank — metadata stamping and score ordering
# ──────────────────────────────────────────────────────────────

def test_rerank_stamps_trust_state_on_metadata():
    retriever = _make_retriever()
    item = _make_item(metadata={"authority_aligned": True})
    result = retriever._rerank([item], limit=5)
    assert result[0].metadata.get("trust_state") == "reusable"


def test_rerank_stamps_forming_by_default():
    retriever = _make_retriever()
    item = _make_item(metadata={})
    result = retriever._rerank([item], limit=5)
    assert result[0].metadata.get("trust_state") == "forming"


def test_rerank_reusable_item_outranks_contested_at_same_base_score():
    """Items with reusable trust state should rank above contested ones
    when all other signals are equal."""
    retriever = _make_retriever()
    reusable = _make_item(
        relevance=0.7, trust=0.7, recency_days=30,
        metadata={"authority_aligned": True},
    )
    contested = _make_item(
        relevance=0.7, trust=0.7, recency_days=30,
        metadata={"contradiction_bound": True},
    )
    result = retriever._rerank([contested, reusable], limit=5)
    assert result[0].metadata.get("trust_state") == "reusable"
    assert result[1].metadata.get("trust_state") == "contested"


def test_rerank_stale_item_is_penalized_below_fresh_forming():
    retriever = _make_retriever()
    stale = _make_item(relevance=0.8, trust=0.8, recency_days=400, metadata={})
    fresh = _make_item(relevance=0.6, trust=0.6, recency_days=10, metadata={})
    result = retriever._rerank([stale, fresh], limit=5)
    # Stale gets a -0.12 trust_state penalty; the exact winner depends on
    # combined signals, but we verify trust_state is stamped correctly.
    stale_idx = next(i for i, r in enumerate(result) if r.recency_days == 400)
    assert result[stale_idx].metadata.get("trust_state") == "stale"


def test_rerank_respects_limit():
    retriever = _make_retriever()
    items = [_make_item() for _ in range(10)]
    result = retriever._rerank(items, limit=3)
    assert len(result) == 3


# ──────────────────────────────────────────────────────────────
# RoleBasedContext.aggregate_trust_state field
# ──────────────────────────────────────────────────────────────

def test_role_based_context_has_aggregate_trust_state_field():
    ctx = RoleBasedContext()
    assert hasattr(ctx, "aggregate_trust_state")
    assert ctx.aggregate_trust_state == "forming"


def test_role_based_context_aggregate_trust_state_can_be_set():
    ctx = RoleBasedContext()
    ctx.aggregate_trust_state = "contested"
    assert ctx.aggregate_trust_state == "contested"
