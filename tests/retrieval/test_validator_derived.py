"""
tests/retrieval/test_validator_derived.py

TDD tests for Phase 12-B: Dual Validator Extension.

Tests verify that validate_response_grounding() correctly handles:
- Multi-atom numeric relationships (delta, percent_change)
- Correct derived claims PASS
- Incorrect derived claims FAIL
- Single-citation statements unchanged (no regression)
- Non-comparative multi-citation statements skip derived check
"""

import sys
import os
# Ensure src/ is on sys.path
_project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
_src = os.path.join(_project_root, "src")
for _p in [_src, _project_root]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pytest

from src.retrieval.validator import validate_response_grounding
from src.retrieval.validator import RetrievedItem


def make_atom(label, content, **overrides):
    """Helper to create a RetrievedItem atom for tests.
    label should be like 'A001' (without brackets).
    citation_key in validator is stored with brackets like '[A001]'.
    """
    citation_key = f'[{label}]'
    kwargs = dict(
        content=content,
        source='test_source',
        strategy='test',
        knowledge_level='B',
        item_type='claim',
        citation_key=citation_key,
    )
    kwargs.update(overrides)
    return RetrievedItem(**kwargs)


# ──────────────────────────────────────────────────────────────
# CORRECT DERIVED CLAIM TESTS
# ──────────────────────────────────────────────────────────────

def test_validator_correct_derived_delta():
    """A exceeded B by 3 [A, B] with A=10, B=7 → PASS (delta is correct)"""
    response = "Company A had a budget of 10 while Company B only spent 7, meaning A exceeded B by 3 [A] [B]"

    items = [
        make_atom('A', 'Company A budget allocation for the year was 10 million dollars'),
        make_atom('B', 'Company B reported spending of 7 million this year'),
    ]

    result = validate_response_grounding(response, items)

    # The delta (10 - 7 = 3) is correct, so validation should pass
    # Note: lexical overlap + numeric consistency should also pass
    # The derived check verifies: abs(claimed_3 - computed_3) <= epsilon
    assert result['is_valid'] is True, f"Should pass: {result['errors']}"


def test_validator_correct_derived_percent():
    """B is 25% lower than A [A, B] with A=100, B=75 → PASS (percent is correct)"""
    response = "Revenue dropped by 25% from 100 to 75, so B is 25% lower than A [A] [B]"

    items = [
        make_atom('A', 'Company A reported quarterly revenue of 100 million dollars'),
        make_atom('B', 'Company B reported 75 million in quarterly revenue'),
    ]

    result = validate_response_grounding(response, items)

    # Percent change: ((75 - 100) / 100) * 100 = -25% → "25% lower" is correct
    assert result['is_valid'] is True, f"Should pass: {result['errors']}"


def test_validator_correct_derived_delta_from_text():
    """Delta computed from numbers in atom text (not metadata)"""
    response = "The first metric was 10 and the second was 7, a difference of 3 [A] [B]"

    items = [
        make_atom('A', 'First metric reached 10 units'),
        make_atom('B', 'Second metric settled at 7 units'),
    ]

    result = validate_response_grounding(response, items)

    assert result['is_valid'] is True, f"Should pass: {result['errors']}"


# ──────────────────────────────────────────────────────────────
# INCORRECT DERIVED CLAIM TESTS (DERIVATION ERRORS)
# ──────────────────────────────────────────────────────────────

def test_validator_incorrect_derived_delta():
    """A exceeds B by 50 [A, B] with A=10, B=7 → FAIL (delta is 3, not 50)"""
    response = "Company A exceeds Company B by 50 units [A] [B]"

    items = [
        make_atom('A', 'Company A reported revenue of 10 million'),
        make_atom('B', 'Company B reported 7 million in total'),
    ]

    result = validate_response_grounding(response, items)

    assert result['is_valid'] is False, "Should fail: claimed 50, computed 3"


def test_validator_incorrect_derived_percent():
    """B is 50% higher than A [A, B] with A=100, B=75 → FAIL (should be -25%)"""
    response = "B increased by 50% compared to A [A] [B]"

    items = [
        make_atom('A', 'Company A revenue of 100 million dollars'),
        make_atom('B', 'Company B revenue reached 75 million'),
    ]

    result = validate_response_grounding(response, items)

    assert result['is_valid'] is False, "Should fail: claimed 50%, computed -25%"


# ──────────────────────────────────────────────────────────────
# NON-REGRESSION TESTS
# ──────────────────────────────────────────────────────────────

def test_validator_single_citation_still_passes():
    """Single-citation statement with matching content → passes (existing path)"""
    response = "Company A reported revenue of 10 million dollars [A]"

    items = [
        make_atom('A', 'Company A reported 10 million in revenue for the quarter'),
    ]

    result = validate_response_grounding(response, items)

    assert result['is_valid'] is True, f"Should pass: {result['errors']}"


def test_validator_non_comparative_multi_citation():
    """Two citations but no numeric relationship → existing path, passes if lexical overlap sufficient"""
    response = "Company A and Company B both operate in the technology sector [A] [B]"

    items = [
        make_atom('A', 'Company A operates in the technology sector and provides services'),
        make_atom('B', 'Company B is also in the technology sector with similar services'),
    ]

    result = validate_response_grounding(response, items)

    # No numeric relationship → derived check skipped → existing path
    assert result['is_valid'] is True, f"Should pass: {result['errors']}"


def test_validator_uncited_claim():
    """Uncited statement → FAIL (existing behavior preserved)"""
    response = "This is a claim without any citation support"

    items = [
        make_atom('A', 'Some unrelated content'),
    ]

    result = validate_response_grounding(response, items)

    assert result['is_valid'] is False, "Uncited claim should fail"


# ──────────────────────────────────────────────────────────────
# KILL TEST (MANDATORY per 12-A spec)
# ──────────────────────────────────────────────────────────────

def test_validator_kill_test_incorrect_percentage(kill_test=True):
    """
    Kill Test: Incorrect percentage caught
    "B decreased 80% from A" with A=100, B=75 → FAIL (should be 25% decrease)
    """
    response = "B decreased 80% from A [A] [B]"

    items = [
        make_atom('A', 'Company A revenue was 100 million last quarter'),
        make_atom('B', 'Company B revenue is now 75 million this quarter'),
    ]

    result = validate_response_grounding(response, items)

    assert result['is_valid'] is False, (
        f"Kill test failed: validator should catch incorrect 80% claim. "
        f"Computed should be 25% decrease (or -25%), not 80% decrease. "
        f"Result: {result['errors']}"
    )
