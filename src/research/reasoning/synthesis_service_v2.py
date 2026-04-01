"""
src/research/reasoning/synthesis_service_v2.py

Multi-Pass Composition Pipeline — Phase 12-E.

Transforms EnrichedSectionPlans + EvidencePackets into coherent long-form prose
via a 5-pass pipeline. synthesis_service.py (v1) is NOT modified.

Passes:
  1. First-pass draft    — constrained LLM call with required atom IDs
  2. Expansion           — conditional on EXPANSION_THRESHOLD
  3. Transition coherence — prepend transition from previous section
  4. Grounding repair    — remove/cite unsupported comparative claims
  5. Placeholder         — reserved for 12-F LongformVerifier
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from llm.model_router import TaskType

logger = logging.getLogger(__name__)

EXPANSION_THRESHOLD = 3  # minimum required_atom_ids to trigger Pass 2


# ──────────────────────────────────────────────────────────────
# Output dataclasses
# ──────────────────────────────────────────────────────────────

@dataclass
class SectionDraft:
    section_title: str
    text: str
    pass_log: List[str]
    was_expanded: bool
    grounding_report: Dict = field(default_factory=dict)


@dataclass
class ReportDraft:
    sections: List[SectionDraft]
    topic_name: str
    total_passes: int
    quality_metrics: Dict = field(default_factory=dict)


# ──────────────────────────────────────────────────────────────
# Service
# ──────────────────────────────────────────────────────────────

class MultiPassSynthesisService:
    """
    5-pass composition pipeline.

    Usage:
        svc = MultiPassSynthesisService(ollama_client)
        draft = await svc.compose_section(plan, packet)
        report = await svc.compose_report(plans, packet, topic_name)
    """

    def __init__(self, client: Any) -> None:
        self._client = client

    # ── public entry points ────────────────────────────────────

    async def compose_section(
        self,
        plan,
        packet,
        previous_text: Optional[str] = None,
    ) -> SectionDraft:
        """Run all 5 passes for a single section."""
        if plan.refusal_required:
            return SectionDraft(
                section_title=plan.title,
                text="[INSUFFICIENT EVIDENCE] This section cannot be written due to lack of supporting evidence.",
                pass_log=["refusal"],
                was_expanded=False,
                grounding_report={},
            )

        pass_log: List[str] = []
        was_expanded = False

        # Pass 1: first-pass draft
        text = await self._pass1_draft(plan)
        pass_log.append("pass1_draft")

        # Pass 2: expansion (conditional)
        if len(plan.required_atom_ids) >= EXPANSION_THRESHOLD:
            text = await self._pass2_expand(plan, text)
            pass_log.append("pass2_expanded")
            was_expanded = True
        else:
            pass_log.append("pass2_skipped")

        # Pass 3: transition coherence
        if previous_text is not None:
            text = await self._pass3_transition(plan, text, previous_text)
        pass_log.append("pass3_transitions")

        # Pass 4: grounding repair
        text = await self._pass4_repair(plan, text)
        pass_log.append("pass4_repair")

        # Pass 5: placeholder (12-F integration)
        pass_log.append("pass5_pending")

        return SectionDraft(
            section_title=plan.title,
            text=text,
            pass_log=pass_log,
            was_expanded=was_expanded,
            grounding_report={},
        )

    async def compose_report(
        self,
        plans: List,
        packet,
        topic_name: str,
    ) -> ReportDraft:
        """Compose all sections sequentially, threading previous_text for transitions."""
        sections: List[SectionDraft] = []
        previous_text: Optional[str] = None

        for plan in plans:
            draft = await self.compose_section(plan, packet, previous_text=previous_text)
            sections.append(draft)
            if not plan.refusal_required:
                previous_text = draft.text

        total_passes = sum(len(s.pass_log) for s in sections)
        quality_metrics = self._compute_quality_metrics(sections)

        return ReportDraft(
            sections=sections,
            topic_name=topic_name,
            total_passes=total_passes,
            quality_metrics=quality_metrics,
        )

    # ── private pass builders ──────────────────────────────────

    async def _pass1_draft(self, plan) -> str:
        prompt = self._build_draft_prompt(plan)
        return await self._client.complete(TaskType.SYNTHESIS, prompt)

    async def _pass2_expand(self, plan, text: str) -> str:
        prompt = self._build_expansion_prompt(plan, text)
        return await self._client.complete(TaskType.SYNTHESIS, prompt)

    async def _pass3_transition(self, plan, text: str, previous_text: str) -> str:
        prompt = self._build_transition_prompt(plan, text, previous_text)
        return await self._client.complete(TaskType.SYNTHESIS, prompt)

    async def _pass4_repair(self, plan, text: str) -> str:
        prompt = self._build_repair_prompt(plan, text)
        return await self._client.complete(TaskType.SYNTHESIS, prompt)

    # ── private prompt builders ────────────────────────────────

    def _build_draft_prompt(self, plan) -> str:
        atom_ids = ", ".join(plan.required_atom_ids)
        derived_ids = ", ".join(plan.allowed_derived_claim_ids) if plan.allowed_derived_claim_ids else "none"
        return (
            f"Write a {plan.mode.value} section titled '{plan.title}'.\n"
            f"Cite only: {atom_ids}\n"
            f"Derived claims allowed: {derived_ids}\n"
            f"Purpose: {plan.purpose}\n"
            f"Target length: {plan.target_length_range[0]}–{plan.target_length_range[1]} words."
        )

    def _build_expansion_prompt(self, plan, text: str) -> str:
        atom_ids = ", ".join(plan.required_atom_ids)
        derived_ids = ", ".join(plan.allowed_derived_claim_ids) if plan.allowed_derived_claim_ids else "none"
        return (
            f"Expand the following section using only the cited evidence.\n"
            f"Forbidden: introduce claims not in [{atom_ids}] or derived [{derived_ids}].\n\n"
            f"{text}"
        )

    def _build_transition_prompt(self, plan, text: str, previous_text: str) -> str:
        return (
            f"Prepend 1-2 transition sentences to the following section to connect it "
            f"smoothly from the previous section. Do not introduce new facts.\n\n"
            f"Previous section (last paragraph):\n{previous_text[-500:]}\n\n"
            f"Current section:\n{text}"
        )

    def _build_repair_prompt(self, plan, text: str) -> str:
        return (
            f"Remove or add citations to any unsupported comparative claims in the following text. "
            f"Only cite from: {', '.join(plan.required_atom_ids)}.\n\n"
            f"{text}"
        )

    def _compute_quality_metrics(self, sections: List[SectionDraft]) -> Dict:
        total_words = sum(len(s.text.split()) for s in sections)
        expanded = sum(1 for s in sections if s.was_expanded)
        total = len(sections)
        avg_passes = sum(len(s.pass_log) for s in sections) / total if total else 0.0
        return {
            "total_words": total_words,
            "expanded_sections": expanded,
            "total_sections": total,
            "avg_pass_count": avg_passes,
        }
