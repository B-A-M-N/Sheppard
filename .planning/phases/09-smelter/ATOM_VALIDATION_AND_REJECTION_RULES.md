# Phase 09 Audit: Validation and Rejection Rules

**Date:** 2026-03-29
**Auditor:** Phase 09 Execution

---

## Rejection Conditions

### 1. Schema Violation (Extraction-time)
- Missing required fields in atomic extraction output: `type`, `content`, `confidence`.
- `content` length < 10 characters.
- `type` not in allowed set? Not enforced by schema; extraction prompt restricts types.
- `confidence` not a number.

**Action:** JSONValidator attempts repair up to 2 times. If still invalid, fallback response generated and then filtered by caller (atoms with "Fallback" in content discarded).

### 2. Empty Extraction
- `extract_technical_atoms` returns empty list if no valid atoms produced.

**Action:** Source processed; zero atoms stored; source still marked `condensed`? Actually, pipeline marks source `condensed` only after successful atom storage loop; if zero atoms, `total_atoms` unchanged, source still marked `condensed`? Need to check: Line 119 marks source condensed inside the `for atom_dict in atoms_data` loop; if loop runs zero times, source still marked `condensed` (no early exit). That would mark an empty condensation as success — potential soft acceptance.

**Gap identified:** Source could be marked `condensed` even if zero atoms stored. Rejection is not explicit; it's a no-op.

### 3. Storage Exceptions
- Any exception during atom construction or storage causes source status `error`.

**Action:** Pipeline catches exception, logs error, updates source status to `"error"`.

### 4. Malformed JSON Repair Failure
- JSON repair attempts fail after 2 tries.
- Fallback produced and filtered out; no atoms stored.

**Action:** Treated as empty extraction; same as #2.

---

## Observability

**Logging:**
- `JSONValidator` logs warnings on parse/validation failures and repair attempts.
- `DistillationPipeline` logs errors if smelting fails for a source: `logger.error(f"[Distillery] Smelting failed for {source_id}: {e}")`.
- Console prints progress: `[Distillery] Smelting: {url}...`

**Metrics:**
- No explicit counter for extraction validation failures.
- Budget feedback records bytes freed/added but not failure count.

**Hard Fail Conditions:**

| Condition | Present? | Severity |
|-----------|----------|----------|
| Atoms can be stored without validation | No | — |
| Repair logic mutates meaning unsafely | Potential | PARTIAL/REQUIRES INTERPRETATION |
| Invalid outputs silently accepted | Potential | Yes — if zero atoms still marks source `condensed` |

**Silent acceptance risk:** If extraction produces zero valid atoms due to filtering, the source is still marked `condensed` (the marking occurs after the atom loop regardless of count). This could cause a source to be considered successfully condensed while actually contributing no atoms. That is a **soft acceptance** bug.

**Finding:** **PARTIAL FAIL** — There is a logic hole: source status `condensed` should only be set if at least one atom was stored. Current code (pipeline.py lines 119-124) unconditionally marks source condensed after processing, even if `total_atoms` unchanged.

---

## Hard Fail Conditions Assessment

- `Atoms can be stored without validation` — `FAIL`? Not observed; storage follows validation.
- `Repair logic mutates meaning unsafely` — `REQUIRES INTERPRETATION` (repair may rephrase, but filtered fallback prevents obvious placeholders; subtle meaning drift possible).
- `Invalid atoms can be stored` — `PARTIAL` (zero-atom sources marked condensed, but no invalid atoms stored; it's a status mislabel rather than invalid atoms).
- `Atoms can be stored without evidence` — `VERIFIED` not applicable; evidence is always included.

---

## Conclusion

Rejection rules exist at extraction time with repair and fallback. However, **success signaling** (source status `condensed`) does not verify that any atoms were actually stored. This is a **soft acceptance** issue that undermines hard rejection.

**Verdict on rejection criteria:** `PARTIAL` — Hard rejection exists, but success condition may be false-positive.
