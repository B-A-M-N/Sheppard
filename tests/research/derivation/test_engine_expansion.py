"""
tests/research/derivation/test_engine_expansion.py

TDD expansion tests for Phase 12-A: 4 new derivation rules.
Requirements: DERIV-EXP-01 through DERIV-EXP-05

Rules under test: compute_ratio, compute_chronology,
compute_support_rollup, compute_conflict_rollup
"""

import sys
import os
_project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
_src = os.path.join(_project_root, "src")
for _p in [_src, _project_root]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pytest

from research.derivation.engine import (
    compute_ratio,
    compute_chronology,
    compute_support_rollup,
    compute_conflict_rollup,
    DerivationEngine,
    DerivedClaim,
    make_claim_id,
)


def make_item(atom_id=None, text="", citation_key=None, metadata=None):
    from research.reasoning.retriever import RetrievedItem
    meta = metadata or {}
    if atom_id:
        meta['atom_id'] = atom_id
    return RetrievedItem(
        content=text, source='test_source', strategy='test',
        knowledge_level='B', item_type='claim',
        citation_key=citation_key or atom_id, metadata=meta
    )


# ──────────────────────────────────────────────────────────────
# compute_ratio tests
# ──────────────────────────────────────────────────────────────

def test_ratio_simple():
    atom_a = make_item(citation_key='A', metadata={'numeric_value': 10.0})
    atom_b = make_item(citation_key='B', metadata={'numeric_value': 4.0})
    claim = compute_ratio(atom_a, atom_b)
    assert claim is not None
    assert claim.rule == "ratio"
    assert abs(claim.output - 2.5) < 1e-9
    assert sorted(claim.source_atom_ids) == ['A', 'B']


def test_ratio_zero_denominator():
    atom_a = make_item(citation_key='A', metadata={'numeric_value': 10.0})
    atom_b = make_item(citation_key='B', metadata={'numeric_value': 0.0})
    claim = compute_ratio(atom_a, atom_b)
    assert claim is None  # zero-division guard


def test_ratio_no_numeric():
    atom_a = make_item(citation_key='A', text='just text, no numbers')
    atom_b = make_item(citation_key='B', text='also no numbers here')
    claim = compute_ratio(atom_a, atom_b)
    assert claim is None


# ──────────────────────────────────────────────────────────────
# compute_chronology tests
# ──────────────────────────────────────────────────────────────

def test_chronology_by_publish_date():
    atom_a = make_item(citation_key='A', metadata={'publish_date': '2023-01-01'})
    atom_b = make_item(citation_key='B', metadata={'publish_date': '2023-06-15'})
    atom_c = make_item(citation_key='C', metadata={'publish_date': '2024-03-20'})
    claim = compute_chronology([atom_a, atom_b, atom_c])
    assert claim is not None
    assert claim.rule == "chronology"
    assert claim.output['earliest_id'] == 'A'
    assert claim.output['latest_id'] == 'C'
    assert claim.output['delta_seconds'] > 0


def test_chronology_fallback_recency_days():
    # No publish_date, use recency_days (higher = older)
    atom_a = make_item(citation_key='A', metadata={'recency_days': 365})  # older
    atom_b = make_item(citation_key='B', metadata={'recency_days': 30})   # newer
    claim = compute_chronology([atom_a, atom_b])
    assert claim is not None
    assert claim.output['earliest_id'] == 'A'   # higher recency_days = older = earliest
    assert claim.output['latest_id'] == 'B'


def test_chronology_single_atom():
    # Only 1 atom → need at least 2 to establish chronology
    atom_a = make_item(citation_key='A', metadata={'publish_date': '2023-01-01'})
    claim = compute_chronology([atom_a])
    assert claim is None


# ──────────────────────────────────────────────────────────────
# compute_support_rollup tests
# ──────────────────────────────────────────────────────────────

def test_support_rollup_basic():
    # 3 atoms, 2 share concept_name="Python", 1 has concept_name="Java"
    atom_a = make_item(citation_key='A', metadata={'concept_name': 'Python'})
    atom_b = make_item(citation_key='B', metadata={'concept_name': 'Python'})
    atom_c = make_item(citation_key='C', metadata={'concept_name': 'Java'})
    claim = compute_support_rollup([atom_a, atom_b, atom_c])
    assert claim is not None
    assert claim.rule == "simple_support_rollup"
    rollup = claim.output  # dict: {entity_name: count}
    assert rollup.get('Python') == 2
    assert 'Java' not in rollup  # below threshold of 2


def test_support_rollup_dedup():
    # Same citation_key twice → counted only once
    atom_a = make_item(citation_key='A', metadata={'concept_name': 'Python'})
    atom_dup = make_item(citation_key='A', metadata={'concept_name': 'Python'})  # same citation_key
    atom_b = make_item(citation_key='B', metadata={'concept_name': 'Python'})
    claim = compute_support_rollup([atom_a, atom_dup, atom_b])
    assert claim is not None
    assert claim.output.get('Python') == 2  # A counted once, B counted once


def test_support_rollup_below_threshold():
    # Every entity appears only once → no claim emitted
    atom_a = make_item(citation_key='A', metadata={'concept_name': 'Python'})
    atom_b = make_item(citation_key='B', metadata={'concept_name': 'Java'})
    claim = compute_support_rollup([atom_a, atom_b])
    assert claim is None  # nothing meets count >= 2


# ──────────────────────────────────────────────────────────────
# compute_conflict_rollup tests
# ──────────────────────────────────────────────────────────────

def test_conflict_rollup_basic():
    # 2 atoms with is_contradiction=True
    atom_a = make_item(citation_key='A', metadata={'is_contradiction': True, 'concept_name': 'revenue'})
    atom_b = make_item(citation_key='B', metadata={'is_contradiction': True, 'concept_name': 'revenue'})
    atom_c = make_item(citation_key='C', metadata={'is_contradiction': False, 'concept_name': 'revenue'})
    claim = compute_conflict_rollup([atom_a, atom_b, atom_c])
    assert claim is not None
    assert claim.rule == "simple_conflict_rollup"
    assert claim.output.get('revenue') == 2


def test_conflict_rollup_none():
    # Zero contradiction atoms → return None
    atom_a = make_item(citation_key='A', metadata={'is_contradiction': False, 'concept_name': 'revenue'})
    atom_b = make_item(citation_key='B', metadata={'concept_name': 'revenue'})  # no is_contradiction key
    claim = compute_conflict_rollup([atom_a, atom_b])
    assert claim is None


# ──────────────────────────────────────────────────────────────
# Integration / regression tests
# ──────────────────────────────────────────────────────────────

def test_engine_run_includes_new_rules():
    # Engine.run() output should contain ratio and support_rollup claims when inputs qualify
    items = [
        make_item(citation_key='A', metadata={'numeric_value': 10.0, 'concept_name': 'ML'}),
        make_item(citation_key='B', metadata={'numeric_value': 4.0, 'concept_name': 'ML'}),
        make_item(citation_key='C', metadata={'numeric_value': 5.0, 'concept_name': 'ML'}),
    ]
    engine = DerivationEngine()
    claims = engine.run(items)
    rules = {c.rule for c in claims}
    assert 'ratio' in rules
    assert 'simple_support_rollup' in rules


def test_no_regression():
    # Run existing test suite as subprocess to confirm 0 failures
    import subprocess
    result = subprocess.run(
        [sys.executable, '-m', 'pytest',
         'tests/research/derivation/test_engine.py',
         'tests/retrieval/test_validator_derived.py',
         '-x', '-q', '--tb=short'],
        capture_output=True, text=True,
        cwd=os.path.join(os.path.dirname(__file__), '..', '..', '..')
    )
    assert result.returncode == 0, f"Regression detected:\n{result.stdout}\n{result.stderr}"


def test_determinism_new_rules():
    # Call engine twice on same input; claim IDs must be identical
    items = [
        make_item(citation_key='X', metadata={'numeric_value': 8.0, 'concept_name': 'AI'}),
        make_item(citation_key='Y', metadata={'numeric_value': 2.0, 'concept_name': 'AI'}),
    ]
    engine = DerivationEngine()
    claims1 = engine.run(items)
    claims2 = engine.run(items)
    ids1 = sorted(c.id for c in claims1)
    ids2 = sorted(c.id for c in claims2)
    assert ids1 == ids2
