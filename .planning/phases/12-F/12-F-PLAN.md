---
phase: 12-F
plan: 01
type: tdd
depends_on:
  - 12-E  # SectionDraft, ReportDraft
  - 12-D  # EnrichedSectionPlan
  - 12-B  # validator extended for derived claims
files_modified:
  - src/research/reasoning/longform_verifier.py
  - tests/research/reasoning/test_longform_verification.py
autonomous: true
---

<objective>
Build LongformVerifier — 7 deterministic gates that prevent synthesis drift.
Operates on SectionDraft + EnrichedSectionPlan + EvidencePacket.
Returns structured VerificationReport with per-gate results and quality metrics.

Output:
- src/research/reasoning/longform_verifier.py
- tests/research/reasoning/test_longform_verification.py
</objective>

<interfaces>
**Input:**
  - section_text: str (from SectionDraft.text)
  - plan: EnrichedSectionPlan (from 12-D)
  - packet: EvidencePacket (atoms, derived_claims, retrieved_items for validator)
  - retrieved_items: List[RetrievedItem] (for sentence-level grounding via existing validator)

**Output:**
  @dataclass
  class GateResult:
      gate: str
      passed: bool
      errors: List[str]
      warnings: List[str]

  @dataclass
  class VerificationReport:
      is_valid: bool                    # True only if ALL hard gates pass
      gate_results: List[GateResult]
      quality_metrics: Dict[str, float] # citation_density, unsupported_rate, etc.
      repair_hints: List[str]           # actionable fixes for failed gates

**Existing validator** (src/retrieval/validator.py):
  - validate_response_grounding(text, retrieved_items) → dict
  - Reuse for sentence-level grounding gate.

**Gate definitions:**
  Gate 1: sentence_grounding      — every declarative sentence has ≥1 citation [HARD]
                                    → powered by validate_response_grounding() from retrieval/validator.py
  Gate 2: derived_recomputation   — all numeric/comparative claims verified [HARD]
                                    → powered by validate_response_grounding() (derived_mismatch errors)
  Gate 3: contradiction_obligation — if plan.contradiction_atom_ids set, text must mention both IDs [HARD]
  Gate 4: evidence_threshold      — section cites ≥ plan.evidence_budget atoms [HARD]
  Gate 5: no_uncited_abstraction  — comparative/analytical language requires ≥2 citations [HARD]
  Gate 6: expansion_budget        — no citation outside plan.allowed_derived_claim_ids + required_atom_ids [SOFT — warning only]
  Gate 7: quality_metrics         — compute citation_density, unsupported_rate (tracked, not enforced) [METRICS]
</interfaces>

<feature>
  <name>LongformVerifier</name>
  <files>
    src/research/reasoning/longform_verifier.py
    tests/research/reasoning/test_longform_verification.py
  </files>

  <behavior>
    RED: 12 tests:
    1. test_gate1_passes_when_all_sentences_cited
    2. test_gate1_fails_uncited_declarative_sentence
    3. test_gate2_fails_wrong_derived_math
    4. test_gate2_passes_correct_derived_math
    5. test_gate3_fails_if_contradiction_obligation_unmet
    6. test_gate3_passes_if_both_conflict_atom_ids_mentioned
    7. test_gate4_fails_below_evidence_threshold
    8. test_gate4_passes_at_threshold
    9. test_gate5_fails_comparative_without_multi_citation
    10. test_gate6_warning_for_citation_outside_budget (soft, not hard fail)
    11. test_quality_metrics_returned
    12. test_failure_class_harness_all_six_phases

    GREEN: implement LongformVerifier with all 7 gates
    REFACTOR: extract sentence splitter, citation extractor helpers
  </behavior>
</feature>

<implementation>
  RED → GREEN → REFACTOR.

  All gates are deterministic.
  Hard gates (1-5): failure → is_valid=False.
  Soft gate (6): failure → warning only, is_valid unaffected.
  Gate 7: always runs, never fails.

  Sentence splitter: split on ". " or "! " or "? " — simple regex.
  Citation extractor: re.findall(r'\[[A-Za-z0-9]+\]', text)
  Comparative patterns: reuse COMPARATIVE_PATTERNS from validator.py (import).

  Failure class harness test (test 12):
    Injects synthetic failures for each phase's expected catch category.
    Each assertion: "gate X catches failure class Y."
</implementation>

<verification>
  <automated>PYTHONPATH=src python -m pytest tests/research/reasoning/test_longform_verification.py -v</automated>
  <automated>PYTHONPATH=src python -m pytest tests/research/ -x -q</automated>
</verification>

<success_criteria>
- 12 tests pass
- GateResult and VerificationReport dataclasses correct
- Gates 1-5 are HARD (fail → is_valid=False)
- Gate 6 is SOFT (fail → warning only)
- Gate 7 produces quality_metrics dict
- No regressions
</success_criteria>
