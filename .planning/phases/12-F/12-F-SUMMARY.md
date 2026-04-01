# Phase 12-F Summary — Longform Verifier

**Status:** COMPLETE
**Date:** 2026-04-01
**Milestone:** v1.2 — Derived Insight & Report Excellence Layer

## What Was Built

| File | Action | Description |
|------|--------|-------------|
| `src/research/reasoning/longform_verifier.py` | Created | LongformVerifier with 7 deterministic gates |
| `tests/research/reasoning/test_longform_verification.py` | Created | 13 TDD tests covering all gates and failure harness |

## Verifier Capabilities

Operates on `SectionDraft` + `EnrichedSectionPlan` + `EvidencePacket`.

### Gates

1. **sentence_grounding** (HARD): Every declarative sentence must have ≥1 citation.
2. **derived_recomputation** (HARD): Numeric/comparative claims with multi-citation verified by `validate_response_grounding`.
3. **contradiction_obligation** (HARD): If `plan.contradiction_atom_ids` set, both IDs must appear in text.
4. **evidence_threshold** (HARD): Section must cite ≥ `plan.evidence_budget` unique atoms.
5. **no_uncited_abstraction** (HARD): Comparative language requires ≥2 citations per sentence.
6. **expansion_budget** (SOFT): Warnings for citations outside `required_atom_ids + allowed_derived_claim_ids`.
7. **quality_metrics** (METRICS): Computes `citation_density` and `unsupported_rate`.

Returns `VerificationReport` with `GateResult`s, `is_valid`, `quality_metrics`, and `repair_hints`.

## Test Coverage

- `test_longform_verification.py`: 13 tests covering each gate's pass/fail behavior.
- Gate harness ensures each failure class is caught by the correct gate.
- Integration with `validate_response_grounding` via mock.
- All tests pass; full suite 129/129.

## Key Design Decisions

- **Reuse of validator**: Gates 1 & 2 use single call to `validate_response_grounding` and inspect `details` for error classes.
- **Deterministic parsing**: Citation extraction via regex `\[[A-Za-z0-9]+\]`; sentence splitting on `". "` equivalents.
- **Soft vs Hard**: Gate 6 only adds warnings; does not affect `is_valid`.
- **COMPARATIVE_PATTERNS** imported from `retrieval.validator` to ensure consistency across system.
- **Gateway for 12-E**: Pass 4 of the pipeline is "grounding repair" which uses Gate 5 logic conceptually; full integration deferred to future.

## Integration

- `longform_verifier.py` is ready to be called after synthesis (12-E) to produce `grounding_report` in `SectionDraft`.
- Currently `SectionDraft.grounding_report` is empty; plug-in will occur post-12-F.

## Next Steps

Milestone v1.2 complete. Future work may integrate LongformVerifier into the composition pipeline as the final pass (Pass 5).
