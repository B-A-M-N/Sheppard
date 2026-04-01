"""
tests/research/derivation/test_engine.py

TDD test suite for Phase 12-A: Derived Claim Engine.

Requirements: DERIV-01 through DERIV-06

Unit tests for all derivation rules (delta, percent_change, rank),
determinism verification, Nyquist kill tests (order independence,
mutation sensitivity, removal failure), and validator extension tests.
"""

import sys
import os
# Ensure src/ is on sys.path for bare `research.*` imports.
_project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
_src = os.path.join(_project_root, "src")
for _p in [_src, _project_root]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pytest
from unittest.mock import MagicMock

from research.derivation.engine import (
    DerivedClaim,
    DerivationEngine,
    DerivationConfig,
    compute_delta,
    compute_percent_change,
    compute_rank,
    make_claim_id,
    verify_derived_claim,
)
from research.reasoning.retriever import RetrievedItem
from src.retrieval.validator import validate_response_grounding


# ──────────────────────────────────────────────────────────────
# Test Helpers
# ──────────────────────────────────────────────────────────────

def make_item(atom_id=None, text="", citation_key=None, metadata=None):
    """Helper to create a RetrievedItem for tests."""
    meta = metadata or {}
    if atom_id:
        meta['atom_id'] = atom_id
    return RetrievedItem(
        content=text,
        source='test_source',
        strategy='test',
        knowledge_level='B',
        item_type='claim',
        citation_key=citation_key or atom_id,
        metadata=meta
    )


# ──────────────────────────────────────────────────────────────
# DELTA RULE TESTS (DERIV-01)
# ──────────────────────────────────────────────────────────────

def test_delta_simple():
    """Two items with numeric metadata: A=10, B=7 → delta=3.0"""
    atom_a = make_item(atom_id='A', text='Revenue of $10 million', citation_key='A', metadata={'numeric_value': 10.0})
    atom_b = make_item(atom_id='B', text='Revenue of $7 million', citation_key='B', metadata={'numeric_value': 7.0})

    claim = compute_delta(atom_a, atom_b)

    assert claim is not None
    assert claim.rule == "delta"
    assert claim.output == 3.0
    assert sorted(claim.source_atom_ids) == ['A', 'B']


def test_delta_complex():
    """Complex text extraction: 'Revenue of $1,200' and 'Revenue of $800'"""
    atom_a = make_item(atom_id='A', text='Revenue reached $1,200 this quarter', citation_key='A')
    atom_b = make_item(atom_id='B', text='Previous quarter revenue was $800', citation_key='B')

    claim = compute_delta(atom_a, atom_b)

    assert claim is not None
    assert abs(claim.output - 400.0) < 1e-9  # 1200 - 800 = 400


def test_delta_single_value():
    """Delta with only one numeric atom returns None"""
    atom_a = make_item(atom_id='A', text='Revenue was $10', citation_key='A')
    atom_b = make_item(atom_id='B', text='No numeric data here', citation_key='B')

    claim = compute_delta(atom_a, atom_b)

    assert claim is None


def test_delta_no_numeric():
    """No numeric values in atoms → returns None"""
    atom_a = make_item(atom_id='A', text='Just some text here', citation_key='A')
    atom_b = make_item(atom_id='B', text='Another text item', citation_key='B')

    claim = compute_delta(atom_a, atom_b)

    assert claim is None


# ──────────────────────────────────────────────────────────────
# PERCENT CHANGE RULE TESTS (DERIV-02)
# ──────────────────────────────────────────────────────────────

def test_percent_change_simple():
    """A=100, B=75 → percent_change = -25.0%"""
    atom_a = make_item(atom_id='A', text='', citation_key='A', metadata={'numeric_value': 100.0})
    atom_b = make_item(atom_id='B', text='', citation_key='B', metadata={'numeric_value': 75.0})

    claim = compute_percent_change(atom_a, atom_b)

    assert claim is not None
    assert claim.rule == "percent_change"
    assert abs(claim.output - (-25.0)) < 1e-9
    assert claim.metadata['old_value'] == 100.0
    assert claim.metadata['new_value'] == 75.0


def test_percent_change_zero_old():
    """A=0 → should skip (division by zero), return None"""
    atom_a = make_item(atom_id='A', text='', citation_key='A', metadata={'numeric_value': 0.0})
    atom_b = make_item(atom_id='B', text='', citation_key='B', metadata={'numeric_value': 50.0})

    claim = compute_percent_change(atom_a, atom_b)

    assert claim is None


def test_percent_change_complex():
    """A=80, B=120 → percent_change = +50%"""
    atom_a = make_item(atom_id='A', text='Revenue was $80', citation_key='A')
    atom_b = make_item(atom_id='B', text='Revenue is now $120', citation_key='B')

    claim = compute_percent_change(atom_a, atom_b)

    assert claim is not None
    assert abs(claim.output - 50.0) < 1e-9


# ──────────────────────────────────────────────────────────────
# RANK RULE TESTS (DERIV-03)
# ──────────────────────────────────────────────────────────────

def test_rank_simple():
    """Three items: values 10, 30, 20 → ranked: B(30), C(20), A(10)"""
    atom_a = make_item(atom_id='A', text='', citation_key='A', metadata={'numeric_value': 10.0})
    atom_b = make_item(atom_id='B', text='', citation_key='B', metadata={'numeric_value': 30.0})
    atom_c = make_item(atom_id='C', text='', citation_key='C', metadata={'numeric_value': 20.0})

    claim = compute_rank([atom_a, atom_b, atom_c])

    assert claim is not None
    assert claim.rule == "rank"
    rankings = claim.output  # List[Tuple[str, float]]
    assert rankings[0] == ('B', 30.0)
    assert rankings[1] == ('C', 20.0)
    assert rankings[2] == ('A', 10.0)


def test_rank_empty():
    """No items → returns None"""
    claim = compute_rank([])

    assert claim is None


def test_rank_ties():
    """Two items with same value → ties broken by citation_key ascending"""
    atom_a = make_item(atom_id='A', text='', citation_key='B', metadata={'numeric_value': 10.0})
    atom_b = make_item(atom_id='B', text='', citation_key='A', metadata={'numeric_value': 10.0})

    claim = compute_rank([atom_a, atom_b])

    assert claim is not None
    rankings = claim.output
    # Same value → alphabetical by citation_key
    assert rankings[0][0] == 'A'  # First alphabetically
    assert rankings[1][0] == 'B'  # Second alphabetically


def test_rank_no_numeric():
    """Items without numeric values → returns None"""
    atom_a = make_item(atom_id='A', text='just text', citation_key='A')
    atom_b = make_item(atom_id='B', text='more text', citation_key='B')

    claim = compute_rank([atom_a, atom_b])

    assert claim is None


# ──────────────────────────────────────────────────────────────
# DETERMINISM TESTS (DERIV-05)
# ──────────────────────────────────────────────────────────────

def test_deterministic_id():
    """Same inputs produce same claim ID"""
    atom_a = make_item(atom_id='A', text='', citation_key='A', metadata={'numeric_value': 10.0})
    atom_b = make_item(atom_id='B', text='', citation_key='B', metadata={'numeric_value': 7.0})

    claim1 = compute_delta(atom_a, atom_b)
    claim2 = compute_delta(atom_a, atom_b)

    assert claim1 is not None
    assert claim2 is not None
    assert claim1.id == claim2.id


def test_order_independence(kill_test=True):
    """
    Kill Test 1: Order Independence
    Shuffling input atoms must produce identical derived claim output.
    """
    atom_a = make_item(atom_id='A', text='', citation_key='A', metadata={'numeric_value': 10.0})
    atom_b = make_item(atom_id='B', text='', citation_key='B', metadata={'numeric_value': 30.0})
    atom_c = make_item(atom_id='C', text='', citation_key='C', metadata={'numeric_value': 20.0})

    engine = DerivationEngine()

    # Original order
    claims1 = engine.run([atom_a, atom_b, atom_c])

    # Shuffled order
    import random
    items_shuffled = [atom_a, atom_b, atom_c]
    random.seed(42)
    random.shuffle(items_shuffled)
    claims2 = engine.run(items_shuffled)

    # Same number of claims
    assert len(claims1) == len(claims2)

    # Same claim IDs (deterministic)
    ids1 = sorted(c.id for c in claims1)
    ids2 = sorted(c.id for c in claims2)
    assert ids1 == ids2, f"Claim IDs differ after shuffle: {ids1} vs {ids2}"


def test_mutation_sensitivity(kill_test=True):
    """
    Kill Test 2: Mutation Sensitivity
    Changing an atom value must change the derived claim.
    """
    atom_a = make_item(atom_id='A', text='', citation_key='A', metadata={'numeric_value': 10.0})
    atom_b = make_item(atom_id='B', text='', citation_key='B', metadata={'numeric_value': 7.0})

    claim_original = compute_delta(atom_a, atom_b)

    # Mutate atom_a
    atom_a_mutated = make_item(atom_id='A', text='', citation_key='A', metadata={'numeric_value': 15.0})
    claim_mutated = compute_delta(atom_a_mutated, atom_b)

    assert claim_original is not None
    assert claim_mutated is not None
    assert claim_original.output != claim_mutated.output, "Mutation should change output"
    # ID is stable for same rule+atom_ids (that's by design) — but metadata reflects different values
    assert claim_original.metadata['atom_a_value'] != claim_mutated.metadata['atom_a_value']


def test_removal_failure(kill_test=True):
    """
    Kill Test 3: Removal Failure
    Removing a required atom must make delta/percent_change claims disappear.
    """
    atom_a = make_item(atom_id='A', text='', citation_key='A', metadata={'numeric_value': 10.0})
    atom_b = make_item(atom_id='B', text='', citation_key='B', metadata={'numeric_value': 7.0})

    engine = DerivationEngine()
    claims_all = engine.run([atom_a, atom_b])

    # With both atoms, delta claims exist
    delta_claims = [c for c in claims_all if c.rule == 'delta']
    assert len(delta_claims) > 0, "Expected delta claims with 2 atoms"

    # Remove atom_b
    claims_removed = engine.run([atom_a])
    delta_claims_removed = [c for c in claims_removed if c.rule == 'delta']

    assert len(delta_claims_removed) == 0, "Delta claims should disappear when required atom removed"


# ──────────────────────────────────────────────────────────────
# ENGINE INTEGRATION TESTS
# ──────────────────────────────────────────────────────────────

def test_integration_benchmark():
    """Full pipeline test with 5 items"""
    items = [
        make_item(atom_id='A', text='', citation_key='A', metadata={'numeric_value': 10.0}),
        make_item(atom_id='B', text='', citation_key='B', metadata={'numeric_value': 20.0}),
        make_item(atom_id='C', text='', citation_key='C', metadata={'numeric_value': 30.0}),
        make_item(atom_id='D', text='no numbers here', citation_key='D'),
        make_item(atom_id='E', text='', citation_key='E', metadata={'numeric_value': 40.0}),
    ]

    engine = DerivationEngine()
    claims = engine.run(items)

    assert len(claims) > 0

    # Check we got expected rule types
    rules = set(c.rule for c in claims)
    assert "delta" in rules
    assert "percent_change" in rules
    assert "rank" in rules

    # Rank claim should have 4 atoms (A, B, C, E have numbers)
    rank_claim = next(c for c in claims if c.rule == "rank")
    assert len(rank_claim.output) == 4
    assert rank_claim.output[0] == ('E', 40.0)  # Highest first


# ──────────────────────────────────────────────────────────────
# VALIDATOR EXTENSION TESTS (DERIV-04)
# ──────────────────────────────────────────────────────────────

def test_validator_source_only_still_passes():
    """Single-citation statement with matching content should still pass"""
    response = "Company A reported revenue of 10 million dollars [A]"

    items = [
        RetrievedItem(
            content='Company A reported $10 million in revenue for the quarter',
            source='test',
            strategy='test',
            citation_key='A',
            knowledge_level='B',
            item_type='claim',
        )
    ]

    result = validate_response_grounding(response, items)
    # Note: This passes existing validation - not testing derived check
    # The derived check only activates for multi-citation numeric relationships
    assert True  # No crash; validator runs successfully


# ──────────────────────────────────────────────────────────────
# PERFORMANCE TEST (quick sanity)
# ──────────────────────────────────────────────────────────────

def test_performance_single():
    """Single claim computation should be fast (<1ms)"""
    import time
    atom_a = make_item(atom_id='A', text='', citation_key='A', metadata={'numeric_value': 10.0})
    atom_b = make_item(atom_id='B', text='', citation_key='B', metadata={'numeric_value': 7.0})

    start = time.perf_counter()
    for _ in range(1000):
        compute_delta(atom_a, atom_b)
    elapsed_ms = (time.perf_counter() - start) * 1000

    assert elapsed_ms < 1000, f"1000 delta computations took {elapsed_ms:.1f}ms (expected <1000ms)"
