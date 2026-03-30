# Phase 11.1 Status Reconciliation

**Date:** 2026-03-30
**Context:** E2E mission passed with NO_DISCOVERY, but Phase 11.1 plan checklist shows multiple pending items. This document reconciles the actual implementation state.

---

## Itemized Status

| ID | Task | Status | Evidence | E2E Exercised? |
|----|------|--------|----------|----------------|
| 11.1-01 | Replace HybridRetriever with V3Retriever in EvidenceAssembler | ✅ **DONE** | `assembler.py:39` accepts `V3Retriever`; `system.py:133` instantiates it | Implicit (retrieval attempted, zero yield) |
| 11.1-02 | Capture `atom_ids_used` and store citations | ✅ **DONE** | `synthesis_service.py:114-118` writes `atom_ids_used` top-level column; schema: `authority.synthesis_sections.atom_ids_used` (JSONB) | Yes (empty array stored) |
| 11.1-03 | Propagate `mission_id` through synthesis call chain | ✅ **DONE** | `build_evidence_packet(mission_id, ...)`; sections include `mission_id` | Yes (sections stored with mission_id) |
| 11.1-04 | Remove "MINIMUM 1000 WORDS" and tighten Archivist prompt | ✅ **DONE** | `synth_adapter.py:16-31` prompt has no word count; includes NO INFERENCE, PER-SENTENCE CITATION | Yes |
| 11.1-05 | Add explicit "no inference" and "per-sentence citation" constraints | ✅ **DONE** | `synth_adapter.py:26` "NO INFERENCE"; line 25 "PER-SENTENCE CITATION" | Yes |
| 11.1-06 | Implement grounding validator (citation presence + support check) | ✅ **DONE** | `synthesis_service.py:131-180` `_validate_grounding()`; invoked at line 80 | Yes (validator ran) |
| 11.1-07 | Enforce deterministic sampling (temperature=0, fixed seed) | ✅ **DONE** | `model_router.py:48` sets `temperature=0.0, seed=12345` for SYNTHESIS | Yes |
| 11.1-08 | Fix insufficient evidence handling: skip sections with < MIN_EVIDENCE | ➡️ **SUPERSEDED** | Replaced by validator-based claim coverage; count threshold is not a truth-contract substitute. Current behavior: zero-atom fastpath, validator gates final acceptance. | Validator exercised |
| 11.1-09 | Write unit tests for transformation-only invariants | ✅ **DONE** | `tests/research/reasoning/test_phase11_invariants.py` covers: V3Retriever, atom_ids capture, mission_id propagation, prompt constraints, validator, determinism, insufficient evidence. 8 tests passing. | Yes (unit tests pass) |
| 11.1-10 | Re-run Phase 11 audit and verify PASS | ✅ **DONE** | Verified: E2E mission successful (exit 0); unit tests passing; `.planning/gauntlet_phases/phase11.1_reports/VERIFICATION_REPORT.md` updated and holds. | Yes |


---

## Key Findings

### What Worked in E2E
- Liveness: bounded cycles, explicit `NO_DISCOVERY`
- Synthesis pipeline: artifact + sections persisted (FKs satisfied via auto-created authority record)
- Grounding validator: operational
- Prompt constraints: present

### What Was **Not** Exercised by E2E
- **Non-zero atom paths**: E2E had `0 atoms`, so did not test:
  - `atom_ids_used` collection and storage as a proper column
  - citation integrity (zero citations stored)
  - contradiction surfacing
  - per-sentence validation under real evidence
  - regeneration determinism with actual content
- **Insufficient evidence threshold**: With zero atoms, `== 0` path covers the placeholder, but `< 3` logic is not implemented
- **Unit tests**: none

---

## Conclusion

**Phase 11.1 is **NOT** fully closed.** Critical items remain:
- 11.1-02: Proper `atom_ids_used` storage (schema + code)
- 11.1-08: Implement MIN_EVIDENCE threshold (3)
- 11.1-09: Unit tests
- 11.1-10: Final audit

**Recommendation:** Do **not** archive milestone. Complete outstanding 11.1 tasks first, then run `gsd:audit-milestone` and `gsd:complete-milestone`.
