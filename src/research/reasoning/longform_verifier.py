"""
src/research/reasoning/longform_verifier.py

LongformVerifier — Phase 12-F.

7 deterministic gates that prevent synthesis drift.
Operates on section_text + EnrichedSectionPlan + EvidencePacket.

Gate 1: sentence_grounding      — every claim has ≥1 citation [HARD]
Gate 2: derived_recomputation   — numeric derived claims verified [HARD]
Gate 3: contradiction_obligation — both conflict atom IDs cited [HARD]
Gate 4: evidence_threshold      — cites ≥ plan.evidence_budget unique atoms [HARD]
Gate 5: no_uncited_abstraction  — comparative language requires ≥2 citations [HARD]
Gate 6: expansion_budget        — no citation outside plan budget [SOFT — warning only]
Gate 7: quality_metrics         — compute metrics (never fails) [METRICS]
"""

from __future__ import annotations

import re
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from retrieval.validator import validate_response_grounding, COMPARATIVE_PATTERNS

logger = logging.getLogger(__name__)

_CITATION_RE = re.compile(r'\[[A-Za-z0-9]+\]')
_SENTENCE_RE = re.compile(r'(?<=[.!?])\s+')


# ──────────────────────────────────────────────────────────────
# Output dataclasses
# ──────────────────────────────────────────────────────────────

@dataclass
class GateResult:
    gate: str
    passed: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


@dataclass
class VerificationReport:
    is_valid: bool
    gate_results: List[GateResult]
    quality_metrics: Dict[str, float] = field(default_factory=dict)
    repair_hints: List[str] = field(default_factory=list)


# ──────────────────────────────────────────────────────────────
# Verifier
# ──────────────────────────────────────────────────────────────

class LongformVerifier:
    """
    Deterministic 7-gate verifier for synthesized sections.

    Usage:
        report = LongformVerifier().verify(section_text, plan, packet)
    """

    def verify(
        self,
        section_text: str,
        plan,
        packet,
        retrieved_items: Optional[List] = None,
    ) -> VerificationReport:
        if retrieved_items is None:
            retrieved_items = []

        # Single grounding call covers gates 1 + 2
        grounding = validate_response_grounding(section_text, retrieved_items)

        gate_results = [
            self._gate1_sentence_grounding(grounding),
            self._gate2_derived_recomputation(grounding),
            self._gate3_contradiction_obligation(section_text, plan),
            self._gate4_evidence_threshold(section_text, plan),
            self._gate5_no_uncited_abstraction(section_text),
            self._gate6_expansion_budget(section_text, plan),
        ]

        quality_metrics = self._gate7_quality_metrics(section_text)

        # Hard gates: 1-5 (indices 0-4); Gate 6 is soft
        is_valid = all(g.passed for g in gate_results[:5])

        repair_hints = [
            err
            for g in gate_results
            for err in g.errors
        ]

        return VerificationReport(
            is_valid=is_valid,
            gate_results=gate_results,
            quality_metrics=quality_metrics,
            repair_hints=repair_hints,
        )

    # ── private gate implementations ──────────────────────────

    def _gate1_sentence_grounding(self, grounding: Dict) -> GateResult:
        """Gate 1 (HARD): every claim segment must have ≥1 citation."""
        errors = [
            d.get("claim", "")[:80]
            for d in grounding.get("details", [])
            if d.get("error") == "missing_citation"
        ]
        return GateResult(gate="sentence_grounding", passed=len(errors) == 0, errors=errors)

    def _gate2_derived_recomputation(self, grounding: Dict) -> GateResult:
        """Gate 2 (HARD): numeric derived claims must recompute correctly."""
        errors = [
            d.get("detail", d.get("claim", ""))[:80]
            for d in grounding.get("details", [])
            if d.get("error") == "derived_mismatch"
        ]
        return GateResult(gate="derived_recomputation", passed=len(errors) == 0, errors=errors)

    def _gate3_contradiction_obligation(self, text: str, plan) -> GateResult:
        """Gate 3 (HARD): if contradiction_atom_ids set, both must appear in text."""
        atom_ids = plan.contradiction_atom_ids
        if not atom_ids:
            return GateResult(gate="contradiction_obligation", passed=True)

        missing = [aid for aid in atom_ids if aid not in text]
        errors = [f"Contradiction obligation unmet: {aid} not cited" for aid in missing]
        return GateResult(gate="contradiction_obligation", passed=len(errors) == 0, errors=errors)

    def _gate4_evidence_threshold(self, text: str, plan) -> GateResult:
        """Gate 4 (HARD): section must cite ≥ plan.evidence_budget unique atoms."""
        cited = set(_extract_citations(text))
        budget = plan.evidence_budget
        count = len(cited)
        if count >= budget:
            return GateResult(gate="evidence_threshold", passed=True)
        errors = [f"Cites {count} unique atoms; required ≥ {budget}"]
        return GateResult(gate="evidence_threshold", passed=False, errors=errors)

    def _gate5_no_uncited_abstraction(self, text: str) -> GateResult:
        """Gate 5 (HARD): comparative/analytical language requires ≥2 citations per sentence."""
        errors = []
        for sentence in _split_sentences(text):
            has_comparative = any(
                re.search(p, sentence, re.IGNORECASE) for p in COMPARATIVE_PATTERNS
            )
            if not has_comparative:
                continue
            cites = _extract_citations(sentence)
            if len(cites) < 2:
                errors.append(f"Comparative claim lacks multi-citation: '{sentence[:80]}'")
        return GateResult(gate="no_uncited_abstraction", passed=len(errors) == 0, errors=errors)

    def _gate6_expansion_budget(self, text: str, plan) -> GateResult:
        """Gate 6 (SOFT): warn on citations outside required_atom_ids + allowed_derived_claim_ids."""
        allowed = set(plan.required_atom_ids) | set(plan.allowed_derived_claim_ids)
        cited = set(_extract_citations(text))
        out_of_budget = cited - allowed
        if not out_of_budget:
            return GateResult(gate="expansion_budget", passed=True)
        warnings = [f"Citation outside budget: {cid}" for cid in sorted(out_of_budget)]
        return GateResult(gate="expansion_budget", passed=False, warnings=warnings)

    def _gate7_quality_metrics(self, text: str) -> Dict[str, float]:
        """Gate 7 (METRICS): compute citation_density and unsupported_rate."""
        sentences = _split_sentences(text)
        if not sentences:
            return {"citation_density": 0.0, "unsupported_rate": 0.0}

        cited_sentences = sum(1 for s in sentences if _extract_citations(s))
        total = len(sentences)
        citation_density = cited_sentences / total
        unsupported_rate = 1.0 - citation_density
        return {
            "citation_density": round(citation_density, 4),
            "unsupported_rate": round(unsupported_rate, 4),
        }


# ──────────────────────────────────────────────────────────────
# Private helpers
# ──────────────────────────────────────────────────────────────

def _extract_citations(text: str) -> List[str]:
    return _CITATION_RE.findall(text)


def _split_sentences(text: str) -> List[str]:
    parts = _SENTENCE_RE.split(text.strip())
    return [s.strip() for s in parts if s.strip()]
