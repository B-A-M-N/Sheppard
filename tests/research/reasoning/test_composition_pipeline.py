"""
tests/research/reasoning/test_composition_pipeline.py

TDD tests for Phase 12-E: Multi-Pass Composition Pipeline.
LLM is mocked — tests verify pipeline logic, gating, and output structure.
"""

import sys, os
_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
for _p in [os.path.join(_root, "src"), _root]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pytest
from unittest.mock import AsyncMock, MagicMock

from research.reasoning.section_planner import SectionMode, EnrichedSectionPlan
from research.reasoning.synthesis_service_v2 import (
    MultiPassSynthesisService,
    SectionDraft,
    ReportDraft,
    EXPANSION_THRESHOLD,
)


# ──────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────

def make_plan(title="Test Section", atom_count=4, refusal=False, mode=SectionMode.DESCRIPTIVE):
    atom_ids = [f"[A{i:03d}]" for i in range(atom_count)]
    return EnrichedSectionPlan(
        title=title,
        purpose="Test purpose",
        mode=mode,
        evidence_budget=atom_count,
        required_atom_ids=atom_ids,
        allowed_derived_claim_ids=[],
        contradiction_obligation=None,
        contradiction_atom_ids=None,
        target_length_range=(300, 1500),
        refusal_required=refusal,
        forbidden_extrapolations=[],
        order=1,
    )

def make_packet():
    from types import SimpleNamespace
    return SimpleNamespace(atoms=[], derived_claims=[], analytical_bundles=[],
                           contradictions=[], evidence_graph=None)

def make_llm(response="Draft text about the topic [A001]."):
    llm = MagicMock()
    llm.complete = AsyncMock(return_value=response)
    return llm


# ──────────────────────────────────────────────────────────────
# Tests
# ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_pipeline_produces_section_draft():
    """compose_section returns a SectionDraft with text and pass_log."""
    svc = MultiPassSynthesisService(make_llm())
    plan = make_plan(atom_count=4)
    draft = await svc.compose_section(plan, make_packet())
    assert isinstance(draft, SectionDraft)
    assert isinstance(draft.text, str)
    assert len(draft.text) > 0
    assert isinstance(draft.pass_log, list)


@pytest.mark.asyncio
async def test_pass_log_records_all_passes():
    """pass_log contains entries for each pass that ran."""
    svc = MultiPassSynthesisService(make_llm())
    plan = make_plan(atom_count=4)  # above threshold → expansion runs
    draft = await svc.compose_section(plan, make_packet())
    assert "pass1_draft" in draft.pass_log
    assert "pass2_expanded" in draft.pass_log
    assert "pass3_transitions" in draft.pass_log
    assert "pass4_repair" in draft.pass_log
    assert "pass5_pending" in draft.pass_log


@pytest.mark.asyncio
async def test_expansion_skipped_below_threshold():
    """Pass 2 skipped when atom count < EXPANSION_THRESHOLD."""
    svc = MultiPassSynthesisService(make_llm())
    plan = make_plan(atom_count=EXPANSION_THRESHOLD - 1)
    draft = await svc.compose_section(plan, make_packet())
    assert "pass2_skipped" in draft.pass_log
    assert "pass2_expanded" not in draft.pass_log
    assert draft.was_expanded is False


@pytest.mark.asyncio
async def test_expansion_runs_above_threshold():
    """Pass 2 runs when atom count >= EXPANSION_THRESHOLD."""
    svc = MultiPassSynthesisService(make_llm())
    plan = make_plan(atom_count=EXPANSION_THRESHOLD)
    draft = await svc.compose_section(plan, make_packet())
    assert "pass2_expanded" in draft.pass_log
    assert draft.was_expanded is True


@pytest.mark.asyncio
async def test_refusal_section_skips_passes_if_refusal_required():
    """refusal_required=True → placeholder emitted, no LLM calls."""
    llm = make_llm()
    svc = MultiPassSynthesisService(llm)
    plan = make_plan(atom_count=1, refusal=True)
    draft = await svc.compose_section(plan, make_packet())
    assert "[INSUFFICIENT EVIDENCE]" in draft.text
    llm.complete.assert_not_called()
    assert "pass1_draft" not in draft.pass_log


@pytest.mark.asyncio
async def test_report_draft_contains_all_sections():
    """compose_report produces ReportDraft with one SectionDraft per plan."""
    svc = MultiPassSynthesisService(make_llm())
    plans = [make_plan(f"Section {i}", atom_count=4) for i in range(3)]
    report = await svc.compose_report(plans, make_packet(), "Test Topic")
    assert isinstance(report, ReportDraft)
    assert len(report.sections) == 3
    assert report.topic_name == "Test Topic"


@pytest.mark.asyncio
async def test_pipeline_calls_llm_for_each_pass():
    """LLM is called at least 3 times per section (pass1, pass2, pass4) when expanded."""
    llm = make_llm()
    svc = MultiPassSynthesisService(llm)
    plan = make_plan(atom_count=EXPANSION_THRESHOLD)
    await svc.compose_section(plan, make_packet())
    # Pass 1 + Pass 2 (expanded) + Pass 4 = 3 minimum (Pass 3 skipped on first section)
    assert llm.complete.call_count >= 3


@pytest.mark.asyncio
async def test_section_draft_has_was_expanded_flag():
    """SectionDraft.was_expanded reflects whether Pass 2 ran."""
    svc = MultiPassSynthesisService(make_llm())
    plan_small = make_plan(atom_count=1, refusal=False)
    plan_large = make_plan(atom_count=EXPANSION_THRESHOLD)
    draft_small = await svc.compose_section(plan_small, make_packet())
    draft_large = await svc.compose_section(plan_large, make_packet())
    assert draft_small.was_expanded is False
    assert draft_large.was_expanded is True
