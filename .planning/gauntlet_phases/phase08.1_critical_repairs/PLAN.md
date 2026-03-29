# PHASE 08.1 — CRITICAL REPAIRS: Chunking + Validation Enforcement

## Phase Goal

Repair the normalization pipeline so that content is validated, chunked in the live path, and rejected early if invalid. Fix exactly the defects found in Phase 08: (1) chunking not implemented, (2) Memory validation bypassed, (3) early rejection missing.

## Phase Identity

Phase 08.1 is a **critical repair phase** with narrow scope. It is not a redesign. It corrects specific architectural violations that allowed invalid data to flow downstream.

## Scope

### In Scope

* Implement live-path chunking using configured `chunk_size` and `chunk_overlap`
* Enforce `Memory` object validation so empty content cannot be created
* Add early rejection of empty/invalid normalized content before storage
* Add regression tests proving the fixes
* Re-run all Phase 08 probes to verify repairs

### Out of Scope

* Changing chunking strategy (use simple deterministic splitter)
* Optimizing chunk boundaries or overlap logic
* Redesigning Memory model or its schema
* Modifying upstream fetch/normalization logic beyond the integration points
* Adding new content types or format support
* Deduplication, frontier, budget, distillation, indexing

---

## Success Criteria

Phase 08.1 achieves `PASS` only if **all** are satisfied:

1. `chunk_size` and `chunk_overlap` are actively used in the live pipeline
2. Content exceeding `chunk_size` produces **multiple** chunks (N > 1)
3. Overlap between adjacent chunks is correctly preserved
4. `Memory(content="")` or equivalent raises exception immediately
5. Empty normalized content is rejected **before** chunking/storage with explicit error
6. Live pipeline stores **chunks**, not monolithic Memory objects, for large content
7. All Phase 08 probes re-run and now pass (or acceptable failures unchanged)
8. Regression tests exist and prove criteria 1–6

---

## Critical Defect Rule

This phase exists **only** to repair the two Phase 08 critical defects:

1. Chunking not implemented in execution path
2. Validation bypass allowing invalid data

Any other defects discovered during repair are **out of scope** and must be deferred to a later phase.

---

## Hard Fail Conditions

Phase 08.1 automatically fails if:

- `chunk_size`/`chunk_overlap` still not used in actual storage path
- Large content still stored as single Memory object
- Empty content can still be instantiated or stored
- Empty normalized content can reach storage without rejection
- Phase 08 probes still fail due to original defects
- Fixes are test-only and not present in live path
- Chunking helper exists but integration point still stores monolithic object

---

## Tasks

### Task 08.1-01 — Implement Live Chunking

**Objective:** Ensure the live pipeline actually chunks normalized text before storage.

**Actions:**
- Locate the code path where normalized content is converted to `Memory` objects for storage
- Insert chunking step: `chunks = chunk_text(normalized_content, chunk_size, chunk_overlap)`
- For each chunk, create separate `Memory` (or equivalent chunk object) with metadata:
  - `chunk_index` (0-based)
  - `chunk_count` (total chunks for this source)
  - `source_url` / parent document reference preserved
- Replace single-object storage with loop storing each chunk

**Implementation:**
- If no chunking helper exists, add minimal `chunk_text()` function (deterministic, no empty chunks)
- If helper exists but unused, hook it into the pipeline
- Ensure sequential chunk indices and correct overlap logic

**Deliverable:** Modified file(s) showing integration; `chunk_text` helper if new

**Acceptance:**
- [ ] Code review shows chunking invoked before storage
- [ ] For content `len() > chunk_size`, storage contains `>1` chunk objects
- [ ] Chunk objects contain correct `chunk_index` and `chunk_count`
- [ ] Overlap between chunks verified (chunk[i] ends overlap chars before chunk[i+1] starts)

---

### Task 08.1-02 — Enforce Memory/Content Validation

**Objective:** Ensure `Memory` objects (or chunk objects) cannot be created with empty content.

**Actions:**
- Inspect `Memory` class: locate custom `__init__` and `__post_init__`
- Fix validation bypass by choosing **one**:
  - **Option A:** Move validation logic into `__init__` (preferred if custom `__init__` exists)
  - **Option B:** Call `self.__post_init__()` at end of custom `__init__`
- Ensure validation checks:
  - `content` is not `None`
  - `content` is not empty after `str().strip()`
  - Raises `ValueError` (or appropriate) for invalid input

**Deliverable:** Modified `Memory` class file

**Acceptance:**
- [ ] `Memory(content="")` raises exception immediately
- [ ] `Memory(content="   ")` raises exception immediately
- [ ] `Memory(content=None)` raises exception
- [ ] Valid non-empty content still instantiates successfully

---

### Task 08.1-03 — Add Early Rejection Before Storage

**Objective:** Prevent empty normalized content from reaching chunking/storage layers.

**Actions:**
- Locate integration point: after normalization, before chunking
- Add explicit guard:
  ```python
  if normalized_content is None or not normalized_content.strip():
      raise ValueError("Normalized content is empty; refusing to store")
  ```
- Ensure error is logged with sufficient context (source URL, content type)
- Ensure pipeline aborts for that source (does not create partial chunks)

**Deliverable:** Modified integration file

**Acceptance:**
- [ ] Empty normalized content triggers exception
- [ ] Exception message clearly indicates empty content rejection
- [ ] No chunk objects or Memory objects created for empty input
- [ ] Error propagates to caller/logs with source context

---

### Task 08.1-04 — Add Regression Tests

**Objective:** Prove fixes work and prevent regression.

**Test Cases (add to existing test suite):**

1. `test_chunk_text_splits_large_input()`: len(text) > chunk_size → ≥3 chunks, all non-empty
2. `test_chunk_text_preserves_overlap()`: adjacent chunks share exactly `chunk_overlap` chars
3. `test_chunk_text_small_input_single_chunk()`: len(text) <= chunk_size → 1 chunk
4. `test_empty_normalized_content_rejected()`: integration function raises `ValueError` for empty string
5. `test_memory_empty_content_raises()`: `Memory(content="")` raises
6. `test_pipeline_stores_multiple_chunks_for_large_content()`: integration test shows chunk_count > 1
7. `test_failure_case_rejects_garbage()`: malformed input does not store any chunk
8. `test_determinism_after_fix()`: same input twice yields identical chunk counts and boundaries

**Deliverable:** New or updated test file(s) in test suite

**Acceptance:**
- [ ] All 8 tests present and passing
- [ ] Tests target actual live code paths (not mocks unless necessary)
- [ ] Tests prove criteria 1–6 from Success Criteria

---

### Task 08.1-05 — Re-run All Phase 08 Probes

**Objective:** Verify original audit findings are now resolved.

**Probes to re-run (same inputs as Phase 08 if available):**
1. Clean HTML page
2. Messy HTML page
3. PDF (if supported; if not, note limitation)
4. Failure case (malformed/unreachable)
5. Determinism probe (same input twice)
6. Large content probe (> chunk_size) to confirm chunking

**Capture Changes:**
- Chunk count now > 1 for large content
- No empty chunks produced
- Empty content probe now raises instead of storing
- All other probes maintain prior passing behavior

**Deliverable:** Updated `PHASE-08.1-SUMMARY.md` with probe re-run results

**Acceptance:**
- [ ] All probes executed
- [ ] Original failures from Phase 08 now pass
- [ ] No new regressions introduced in previously passing probes
- [ ] Evidence recorded (chunk counts, error messages, sample outputs)

---

### Task 08.1-06 — Produce Summary + Verification

**Objective:** Document changes and declare final verdict.

**Deliverables:**

1. `PHASE-08.1-SUMMARY.md`
   - What failed in Phase 08
   - What was changed (file-level, function-level)
   - What remained untouched (scope discipline)
   - Probe re-run results summary

2. `PHASE-08.1-VERIFICATION.md`
   - File change list
   - Test list (8 regression tests)
   - Chunk evidence (sample output from large input)
   - Validation enforcement proof (exception demonstration)
   - Integration proof (pipeline trace)
   - Verdict: `PASS` or `FAIL` (per Hard Fail Conditions)

**Acceptance:**
- [ ] Both deliverables present
- [ ] Verdict justified with concrete evidence references
- [ ] If `PASS`, all Hard Fail Conditions shown to be false
- [ ] If `FAIL`, remaining gaps clearly documented

---

## Verification Template

```markdown
# Phase 08.1 Verification

## Changes Applied

- [ ] Chunking integrated into live storage path
- [ ] Memory validation enforced
- [ ] Early rejection added
- [ ] Regression tests added (8 tests)

## Evidence

### Chunking
- (file, function, sample output showing N>1 chunks)

### Validation Enforcement
- (Memory(content="") raises; test proof)

### Early Rejection
- (empty normalized content raises before storage)

### Integration
- (pipeline trace: fetch → normalize → validate → chunk → store)

### Probe Re-run
- (Phase 08 probes: all previous failures now pass)

## Verdict

**Status:** PASS / FAIL

## Remaining Gaps

- (none, or list if any)
```

---

## Completion Criteria

`PASS` only if:
- All 6 Success Criteria met
- All 8 regression tests passing
- All Phase 08 probes re-run and original defects resolved
- No hard fail condition remains true

`FAIL` if any hard fail condition persists.

---

## Notes for Executor

- **Do not** redesign chunking strategy; use simple deterministic splitter
- **Do not** broaden scope; fix only the two critical defects
- **Do not** allow fixes to exist only in tests; live path must be corrected
- **Do** ensure validation is in production code, not just test assertions
- **Do** preserve existing behavior for non-empty valid content
- **Do** add explicit error messages for empty content rejection
- **Do** keep changes minimal and focused

Proceed sequentially through Tasks 08.1-01 → 08.1-06. Write deliverables to `.planning/gauntlet_phases/phase08.1_critical_repairs/`.
