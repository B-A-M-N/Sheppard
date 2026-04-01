"""
tests/research/reasoning/test_longform_verification.py

TDD tests for Phase 12-F: LongformVerifier — 7-gate synthesis drift prevention.
Gates 1-2 mock validate_response_grounding; gates 3-7 use real text parsing.
"""

import sys, os
_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
for _p in [os.path.join(_root, "src"), _root]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pytest
from types import SimpleNamespace
from unittest.mock import patch

from research.reasoning.section_planner import SectionMode, EnrichedSectionPlan
from research.reasoning.longform_verifier import (
    LongformVerifier,
    GateResult,
    VerificationReport,
)


# ──────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────

def make_plan(
    atom_ids=None,
    derived_ids=None,
    contradiction_atom_ids=None,
    evidence_budget=None,
):
    if atom_ids is None:
        atom_ids = ["[A001]", "[A002]"]
    if derived_ids is None:
        derived_ids = []
    budget = evidence_budget if evidence_budget is not None else len(atom_ids)
    return EnrichedSectionPlan(
        title="Test Section",
        purpose="Test",
        mode=SectionMode.DESCRIPTIVE,
        evidence_budget=budget,
        required_atom_ids=atom_ids,
        allowed_derived_claim_ids=derived_ids,
        contradiction_obligation=None,
        contradiction_atom_ids=contradiction_atom_ids,
        target_length_range=(300, 1500),
        refusal_required=False,
        forbidden_extrapolations=[],
        order=1,
    )


def make_packet():
    return SimpleNamespace(atoms=[], derived_claims=[], analytical_bundles=[], contradictions=[])


def grounding_ok():
    return {"is_valid": True, "errors": [], "details": []}


def grounding_missing_citation():
    return {
        "is_valid": False,
        "errors": ["Uncited claim: 'Some claim...'"],
        "details": [{"error": "missing_citation", "claim": "Some uncited claim."}],
    }


def grounding_derived_mismatch():
    return {
        "is_valid": False,
        "errors": ["derived mismatch"],
        "details": [{"error": "derived_mismatch", "claim": "50% more", "detail": "expected 25.0, got 50.0"}],
    }


MOCK_PATH = "research.reasoning.longform_verifier.validate_response_grounding"

# ──────────────────────────────────────────────────────────────
# Gate 1: sentence_grounding
# ──────────────────────────────────────────────────────────────

@patch(MOCK_PATH)
def test_gate1_passes_when_all_sentences_cited(mock_grnd):
    mock_grnd.return_value = grounding_ok()
    verifier = LongformVerifier()
    plan = make_plan()
    report = verifier.verify("All cited text [A001].", plan, make_packet())
    gate = next(g for g in report.gate_results if g.gate == "sentence_grounding")
    assert gate.passed is True


@patch(MOCK_PATH)
def test_gate1_fails_uncited_declarative_sentence(mock_grnd):
    mock_grnd.return_value = grounding_missing_citation()
    verifier = LongformVerifier()
    plan = make_plan()
    report = verifier.verify("Some uncited claim.", plan, make_packet())
    gate = next(g for g in report.gate_results if g.gate == "sentence_grounding")
    assert gate.passed is False
    assert report.is_valid is False


# ──────────────────────────────────────────────────────────────
# Gate 2: derived_recomputation
# ──────────────────────────────────────────────────────────────

@patch(MOCK_PATH)
def test_gate2_fails_wrong_derived_math(mock_grnd):
    mock_grnd.return_value = grounding_derived_mismatch()
    verifier = LongformVerifier()
    plan = make_plan()
    report = verifier.verify("X is 50% more than Y [A001][A002].", plan, make_packet())
    gate = next(g for g in report.gate_results if g.gate == "derived_recomputation")
    assert gate.passed is False
    assert report.is_valid is False


@patch(MOCK_PATH)
def test_gate2_passes_correct_derived_math(mock_grnd):
    mock_grnd.return_value = grounding_ok()
    verifier = LongformVerifier()
    plan = make_plan()
    report = verifier.verify("X is 25% more than Y [A001][A002].", plan, make_packet())
    gate = next(g for g in report.gate_results if g.gate == "derived_recomputation")
    assert gate.passed is True


# ──────────────────────────────────────────────────────────────
# Gate 3: contradiction_obligation
# ──────────────────────────────────────────────────────────────

@patch(MOCK_PATH)
def test_gate3_fails_if_contradiction_obligation_unmet(mock_grnd):
    mock_grnd.return_value = grounding_ok()
    verifier = LongformVerifier()
    plan = make_plan(contradiction_atom_ids=["[A001]", "[A002]"])
    # Text only mentions one of the two
    report = verifier.verify("This text mentions [A001] only.", plan, make_packet())
    gate = next(g for g in report.gate_results if g.gate == "contradiction_obligation")
    assert gate.passed is False
    assert report.is_valid is False


@patch(MOCK_PATH)
def test_gate3_passes_if_both_conflict_atom_ids_mentioned(mock_grnd):
    mock_grnd.return_value = grounding_ok()
    verifier = LongformVerifier()
    plan = make_plan(contradiction_atom_ids=["[A001]", "[A002]"])
    report = verifier.verify("Text mentions [A001] and also [A002].", plan, make_packet())
    gate = next(g for g in report.gate_results if g.gate == "contradiction_obligation")
    assert gate.passed is True


# ──────────────────────────────────────────────────────────────
# Gate 4: evidence_threshold
# ──────────────────────────────────────────────────────────────

@patch(MOCK_PATH)
def test_gate4_fails_below_evidence_threshold(mock_grnd):
    mock_grnd.return_value = grounding_ok()
    verifier = LongformVerifier()
    plan = make_plan(atom_ids=["[A001]", "[A002]", "[A003]"], evidence_budget=3)
    # Text only cites 2 unique atoms
    report = verifier.verify("Text [A001] and text [A002].", plan, make_packet())
    gate = next(g for g in report.gate_results if g.gate == "evidence_threshold")
    assert gate.passed is False
    assert report.is_valid is False


@patch(MOCK_PATH)
def test_gate4_passes_at_threshold(mock_grnd):
    mock_grnd.return_value = grounding_ok()
    verifier = LongformVerifier()
    plan = make_plan(atom_ids=["[A001]", "[A002]"], evidence_budget=2)
    report = verifier.verify("Text [A001] and text [A002].", plan, make_packet())
    gate = next(g for g in report.gate_results if g.gate == "evidence_threshold")
    assert gate.passed is True


# ──────────────────────────────────────────────────────────────
# Gate 5: no_uncited_abstraction
# ──────────────────────────────────────────────────────────────

@patch(MOCK_PATH)
def test_gate5_fails_comparative_without_multi_citation(mock_grnd):
    mock_grnd.return_value = grounding_ok()
    verifier = LongformVerifier()
    plan = make_plan()
    # Comparative sentence with only 1 citation (using "more than" which is in patterns)
    report = verifier.verify("X is more than Y [A001].", plan, make_packet())
    gate = next(g for g in report.gate_results if g.gate == "no_uncited_abstraction")
    assert gate.passed is False
    assert report.is_valid is False


@patch(MOCK_PATH)
def test_gate5_passes_comparative_with_multi_citation(mock_grnd):
    mock_grnd.return_value = grounding_ok()
    verifier = LongformVerifier()
    plan = make_plan()
    # Comparative sentence with 2 citations
    report = verifier.verify("X is better than Y [A001][A002].", plan, make_packet())
    gate = next(g for g in report.gate_results if g.gate == "no_uncited_abstraction")
    assert gate.passed is True


# ──────────────────────────────────────────────────────────────
# Gate 6: expansion_budget (SOFT)
# ──────────────────────────────────────────────────────────────

@patch(MOCK_PATH)
def test_gate6_warning_for_citation_outside_budget(mock_grnd):
    """Gate 6 is soft: is_valid unaffected, but warning recorded."""
    mock_grnd.return_value = grounding_ok()
    verifier = LongformVerifier()
    plan = make_plan(atom_ids=["[A001]"], derived_ids=[])
    # Text cites [A999] which is outside budget
    report = verifier.verify("Text [A001] and also [A999].", plan, make_packet())
    gate = next(g for g in report.gate_results if g.gate == "expansion_budget")
    assert gate.passed is False          # gate failed (soft)
    assert len(gate.warnings) > 0        # warning recorded
    # is_valid NOT affected by soft gate
    assert report.is_valid is True


# ──────────────────────────────────────────────────────────────
# Gate 7: quality_metrics
# ──────────────────────────────────────────────────────────────

@patch(MOCK_PATH)
def test_quality_metrics_returned(mock_grnd):
    mock_grnd.return_value = grounding_ok()
    verifier = LongformVerifier()
    plan = make_plan()
    report = verifier.verify("Text [A001] and text [A002].", plan, make_packet())
    assert "citation_density" in report.quality_metrics
    assert "unsupported_rate" in report.quality_metrics
    assert isinstance(report.quality_metrics["citation_density"], float)


# ──────────────────────────────────────────────────────────────
# Test 12: failure class harness (one assertion per gate failure class)
# ──────────────────────────────────────────────────────────────

@patch(MOCK_PATH)
def test_failure_class_harness_all_gates(mock_grnd):
    """One assertion per gate: each gate catches its designated failure class."""
    verifier = LongformVerifier()

    # Gate 1 catches missing_citation
    mock_grnd.return_value = grounding_missing_citation()
    r = verifier.verify("Uncited.", make_plan(), make_packet())
    g1 = next(g for g in r.gate_results if g.gate == "sentence_grounding")
    assert not g1.passed, "Gate 1 must catch missing_citation"

    # Gate 2 catches derived_mismatch
    mock_grnd.return_value = grounding_derived_mismatch()
    r = verifier.verify("50% more [A001][A002].", make_plan(), make_packet())
    g2 = next(g for g in r.gate_results if g.gate == "derived_recomputation")
    assert not g2.passed, "Gate 2 must catch derived_mismatch"

    # Gate 3 catches missing contradiction atom
    mock_grnd.return_value = grounding_ok()
    r = verifier.verify("Only [A001].", make_plan(contradiction_atom_ids=["[A001]", "[A002]"]), make_packet())
    g3 = next(g for g in r.gate_results if g.gate == "contradiction_obligation")
    assert not g3.passed, "Gate 3 must catch unmet contradiction obligation"

    # Gate 4 catches insufficient citations
    mock_grnd.return_value = grounding_ok()
    r = verifier.verify("[A001].", make_plan(atom_ids=["[A001]", "[A002]"], evidence_budget=2), make_packet())
    g4 = next(g for g in r.gate_results if g.gate == "evidence_threshold")
    assert not g4.passed, "Gate 4 must catch below-threshold evidence"

    # Gate 5 catches comparative without multi-citation
    mock_grnd.return_value = grounding_ok()
    r = verifier.verify("X is more than Y [A001].", make_plan(), make_packet())
    g5 = next(g for g in r.gate_results if g.gate == "no_uncited_abstraction")
    assert not g5.passed, "Gate 5 must catch comparative without multi-citation"

    # Gate 6 (soft) catches out-of-budget citation as warning
    mock_grnd.return_value = grounding_ok()
    r = verifier.verify("Text [A001][A999].", make_plan(atom_ids=["[A001]"]), make_packet())
    g6 = next(g for g in r.gate_results if g.gate == "expansion_budget")
    assert not g6.passed, "Gate 6 must warn on out-of-budget citation"
    assert r.is_valid is True, "Gate 6 failure must not affect is_valid"
