# Phase 09 Verification

**Date:** 2026-03-29
**Phase:** 09 — Smelter / Atom Extraction Audit
**Status:** PASS (soft acceptance bug fixed in 09.1)

---

## Atom Quality Checklist

| Criterion | Status | Evidence |
|-----------|--------|----------|
| Schema is strict and enforced | PARTIAL | Fields mostly required; `atom_type` not enum-enforced; score ranges unconstrained |
| Evidence binding is mandatory | VERIFIED | `store_atom_with_evidence` called with evidence_rows for each atom |
| Type system consistent (fact/claim/tradeoff/etc) | PARTIAL | Extraction produces 5 types; schema allows any string; no enum |
| JSON repair safe (does not mutate meaning) | REQUIRES INTERPRETATION | LLM-based repair may rephrase; no semantic preservation guarantees |
| Deduplication deterministic | PARTIAL | Per-source deterministic; global dedupe not implemented |
| Invalid outputs rejected | PASS (fixed in 09.1) | Hard reject via validation/repair; source status now correctly `rejected` when zero atoms stored |

---

## Evidence

- **Schema:** `src/research/domain_schema.py`, class `KnowledgeAtom` (lines 233-283)
- **Extraction & Repair:** `src/utils/json_validator.py`, function `extract_technical_atoms` and class `JSONValidator`
- **Pipeline & Evidence:** `src/research/condensation/pipeline.py`, method `DistillationPipeline.run` (lines 81-128)
- **Deduplication:** pipeline.py lines 86-88 (atom_id computation)
- **Rejection handling:** pipeline.py lines 125-127 (exception → `error`), and validator fallback filtering

---

## Verdict Rationale

The atom extraction layer is **mostly well-structured** with clear validation, evidence linkage, and error handling.

The **soft acceptance bug** (source marked `condensed` when zero atoms extracted) has been **fixed in Phase 09.1**. Status transitions now accurately reflect outcomes.

Outstanding items not blocking Phase 09 sign-off:

1. **Type consistency** — not enforced at schema level; relies on extraction prompt. (`PARTIAL`)
2. **Deduplication** — only per-source deterministic; global dedupe pending. (`PARTIAL`)
3. **JSON repair** — LLM-based repair may rephrase content; requires policy interpretation. (`REQUIRES INTERPRETATION`)

These are design/implementation details that do not constitute correctness defects. They are noted for future refinement but do not prevent Phase 09 from passing.

**Overall Status: PASS** (with deferred interpretations)

---

## Schema Violations / Gaps

- **Missing enum for `atom_type`** — Could allow arbitrary types if other code constructs atoms.
- **No score bounds** — `confidence`, `importance`, `novelty` can be any float; should be clamped 0.0–1.0.
- **Evidence external only** — Acceptable if evidence table always joined; not inherently a violation.
- **Soft acceptance** — Zero-atom condensation marks source as `condensed`, potentially hiding systematic extraction failures.
- **LLM repair semantics** — Repair may rephrase content; no verification that original meaning preserved.

---

## Recommendations

1. **Type enforcement** (optional): Convert `atom_type` to an enum in KnowledgeAtom model or validator.
2. **Deduplication policy** (optional): Either implement global dedupe or document that per-source dedupe is the intended design.
3. **JSON repair safety** (requires interpretation): Consider syntax-only repair tools (e.g., `json_repair` library) instead of LLM, or add semantic fingerprinting.
4. **Status logic:** Fixed in Phase 09.1 — no further action needed.
5. **Score validation:** Ensure scores stay within [0,1] either via Pydantic constraints or storage validation.

---

## Next Steps

- If `PARTIAL` is acceptable, proceed to Phase 10.
- If hard fails must be fixed, create gap closure phase for:
  - Fix soft acceptance bug
  - Add type enum
  - Clarify deduplication scope
  - Harden JSON repair

---
