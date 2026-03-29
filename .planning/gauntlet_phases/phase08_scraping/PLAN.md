# PHASE 08 — SCRAPING / CONTENT NORMALIZATION AUDIT

## Phase Goal

Verify that fetched content is transformed into **trustworthy, structured, deterministic, metadata-preserving, chunk-valid inputs** suitable for downstream distillation.

## Phase Identity

Phase 08 is an **as-implemented audit** (not a rebuild). This phase uses code inspection **plus** targeted runtime probes to validate behavior.

## Scope

### In Scope

* Fetch adapters
* Content extraction
* Normalization / transformation
* Metadata capture and preservation
* Chunk output validity
* Determinism of normalized output
* Failure behavior quality
* Downstream interface validity

### Out of Scope

* Frontier logic
* Budget / enforcement
* Distillation / atom extraction
* Indexing / search
* Query layer
* Deep Redis/Postgres persistence internals
* Deduplication correctness as its own phase

### Special Boundary Rules

* **Chunking**: in scope only as interface validator (no empty chunks, no catastrophic splits, output must be consumable downstream)
* **Deduplication**: out of scope, but note if normalization produces unstable/ambiguous content representations that would undermine dedupe assumptions

---

## Success Criteria

Phase 08 is `PASS` only if **all** criteria are satisfied:

1. Supported content types enumerated from code (no assumptions) and accurately documented.
2. Normalized outputs structurally consistent across tested content types.
3. Metadata required for lineage preserved through normalization.
4. Chunk outputs valid, non-empty, suitable for downstream distillation.
5. Same input yields materially identical normalized output across repeated runs.
6. Failure cases do not silently corrupt downstream inputs.

**Verdict Options:**
- `PASS` — All criteria met
- `PARTIAL` — 4–5 criteria met, remaining gaps are non-blocking and documented
- `FAIL` — ≤3 criteria met, OR critical defects found requiring immediate fix

---

## Normalization Output Contract

Every normalized unit must contain:

* `content` — non-empty normalized text
* `source_url` — non-null (or explicitly documented exception)
* `content_type` — html / pdf / other actual implemented type
* `captured_at` or equivalent timestamp (or explicit null with documented reason)
* `extraction_method` or equivalent
* attribution fields actually used downstream

### Chunk Contract

Each chunk must:

* Be non-empty
* Be deterministic for same input
* Not exceed configured max size
* Preserve meaningful text boundaries reasonably
* Contain no obvious corruption or null-content fragments

---

## Failure Classification

### Acceptable Hard Failure
Explicit exception / crash that is properly surfaced and logged.

### Acceptable Soft Failure
Empty / low-signal content rejected with explicit flag/marker.

### Unacceptable Failure (Critical Defect)
* Malformed normalized content accepted as valid
* Metadata silently dropped
* Chunk output produced but structurally invalid
* Inconsistent output for same input without documented cause
* Failure cases produce garbage that flows downstream

**Critical defects require immediate escalation to Phase 08.1 (repair), not merely documentation.**

---

## Probe Strategy

### Minimum Probe Set (All Required)

1. Clean HTML page
2. Messy HTML page (tables, code blocks, nested structure)
3. PDF document
4. Failure case (malformed content or unreachable fetch target)

### Determinism Probe

Run same successful input **twice** and compare:

* Normalized content (hash or diff)
* Metadata values
* Chunk count and boundaries

Material mismatch without explanation = finding → likely FAIL.

---

## Tasks

### Task 08-01 — Enumerate Implemented Surfaces

**Objective:** Map actual acquisition/normalization code; do not assume format support.

**Actions:**
- Inspect `src/research/acquisition/` and related content processors
- List all fetch adapters actually implemented
- List all normalization transforms applied
- Identify chunk generation entrypoint

**Deliverable:** Enumerate in `CONTENT_INGEST_AUDIT.md`:
- Implemented content types (from code, not guesses)
- Fetch paths
- Normalization pipeline stages
- Chunk interface location

**Acceptance:**
- [ ] All content types explicitly sourced from code evidence
- [ ] No format listed without code reference
- [ ] Unknown/unsupported types explicitly documented as such

---

### Task 08-02 — Map End-to-End Path: Fetch → Normalize → Chunk

**Objective:** Trace real flow for each supported type.

**Actions:**
- For each content type, trace: adapter → raw → normalized → chunks
- Document data transformations at each step
- Capture metadata flow

**Deliverable:** `CONTENT_INGEST_AUDIT.md` (expanded)
- Diagram or sequential description per content type
- Data structure schemas at each transition
- Metadata preservation points

**Acceptance:**
- [ ] End-to-end path complete from fetch to chunk-ready output
- [ ] No "black box" steps unverified
- [ ] Chunk output format/structure clearly defined

---

### Task 08-03 — Define Spec-as-Implemented

**Objective:** Produce definitive documentation of current behavior.

**Deliverable:** `NORMALIZATION_SPEC_AS_IMPLEMENTED.md`

**Must include:**
- Supported content types (sourced from Task 08-01)
- Normalization transformations (actual code logic, not desired behavior)
- Metadata fields preserved (with source code references)
- Chunk assumptions and constraints
- Known exclusions / unsupported inputs
- Error handling behavior per stage

**Acceptance:**
- [ ] Spec reflects implementation exactly, not aspiration
- [ ] All statements traceable to code paths
- [ ] Gaps and limitations explicitly called out

---

### Task 08-04 — Runtime Probe: HTML

**Objective:** Validate normalization on real HTML content.

**Probes:**
- Clean HTML page (well-formed, minimal noise)
- Messy HTML page (tables, code blocks, complex DOM)

**Capture:**
- Normalized output (sample)
- Metadata completeness
- Chunk count and sample
- Any data loss, corruption, or unexpected transformations

**Deliverable:** `CONTENT_INGEST_AUDIT.md` (probe results section)

**Acceptance:**
- [ ] Both probes complete
- [ ] Normalized text coherent and readable
- [ ] Source URL and timestamps preserved
- [ ] Chunks non-empty and reasonably sized

**Critical Defect Escalation:**
- [ ] If HTML produces malformed normalized output → document and escalate

---

### Task 08-05 — Runtime Probe: PDF

**Objective:** Validate PDF extraction quality and robustness.

**Probe:** Single representative PDF (text-based, not scanned image).

**Capture:**
- Extracted text quality (retention of formatting, tables, lists)
- Metadata (title, author, dates if available)
- Chunking results
- Parse failures or warnings

**Deliverable:** `SOURCE_METADATA_AUDIT.md` or `CONTENT_INGEST_AUDIT.md`

**Acceptance:**
- [ ] PDF either succeeds cleanly or fails explicitly with clear error
- [ ] No silently accepted garbage output
- [ ] Text extraction maintains reasonable structure

**Critical Defect Escalation:**
- [ ] If PDF yields malformed/nonsensical text accepted as valid → escalate

---

### Task 08-06 — Runtime Probe: Failure Case

**Objective:** Verify failure modes are explicit, not silent corruption.

**Probe:** Malformed content or unreachable fetch target.

**Capture:**
- System response (exception, error code, log output)
- Whether downstream receives any output
- Classification: hard fail, soft fail, or silent corruption

**Deliverable:** `FETCH_FAILURE_REPORT.md`

**Acceptance:**
- [ ] Probe executes and terminates
- [ ] Failure is explicit (exception/error, not silent acceptance)
- [ ] No partial/invalid output passed downstream

**Critical Defect Escalation:**
- [ ] If failure produces garbage output marked valid → escalate

---

### Task 08-07 — Determinism Check

**Objective:** Verify same input yields same output.

**Probe:** Repeat one successful input **twice** (same URL/content).

**Compare:**
- Normalized content (exact match or explainable differences only)
- Metadata values
- Chunk count and boundaries

**Deliverable:** `NORMALIZATION_SPEC_AS_IMPLEMENTED.md` (determinism section)

**Acceptance:**
- [ ] Two runs produce materially identical outputs
- [ ] Any variance documented and justified (e.g., timestamps, nonce fields)
- [ ] Chunk boundaries consistent unless size-based splitting with same parameters

**Critical Defect Escalation:**
- [ ] Material nondeterminism in core content or chunking → escalate

---

### Task 08-08 — Chunk Interface Validation

**Objective:** Audit chunk outputs for downstream fitness.

**Actions:**
- Inspect chunk output schema/structure
- Review chunk generation code for edge cases
- Analyze sample chunks for empty/size violations/broken splits

**Deliverable:** `SOURCE_METADATA_AUDIT.md` (chunk section)

**Acceptance:**
- [ ] No empty chunks in valid output
- [ ] No chunks exceeding max size
- [ ] Text boundaries respect段落/语义 reasonably (no mid-sentence breaks unless necessary)
- [ ] Schema/structure matches downstream consumer expectations

**Critical Defect Escalation:**
- [ ] Empty or corrupt chunks accepted → escalate

---

### Task 08-09 — Metadata Lineage Integrity

**Objective:** Verify lineage-critical metadata survives normalization.

**Focus:**
- `source_url` (must not be null for retrievable content)
- `captured_at` / fetch timestamp
- `content_type` accuracy
- `extraction_method` provenance
- Any attribution fields used downstream

**Deliverable:** `SOURCE_METADATA_AUDIT.md`

**Acceptance:**
- [ ] All lineage-critical fields present in normalized output
- [ ] No silent dropping or nulling of metadata
- [ ] Exceptions explicitly documented with justification

**Critical Defect Escalation:**
- [ ] Metadata required for downstream provenance lost → escalate

---

### Task 08-10 — Final Classification and Verdict

**Objective:** Synthesize findings, produce final report, declare verdict.

**Deliverables:**
- `FETCH_FAILURE_REPORT.md` (consolidated failure analysis)
- `PHASE-08-SUMMARY.md` (executive summary)
- `PHASE-08-VERIFICATION.md` (verdict template filled)

**Verdict Logic:**
- Count satisfied Success Criteria (1–6)
- Check for any critical defects escalated

**Final Status:**
- `PASS` — All 6 criteria met, zero critical defects
- `PARTIAL` — 4–5 criteria met, zero critical defects; gaps documented
- `FAIL` — ≤3 criteria met OR any critical defect present

**Acceptance:**
- [ ] All required deliverables present
- [ ] Verdict justified with evidence references
- [ ] Critical defects (if any) explicitly listed for Phase 08.1

---

## Critical Defect Rule (Embedded)

This is an audit **except**:

If during execution any task uncovers a defect that causes:
- Pipeline crash on normal supported input
- Metadata loss breaking lineage
- Invalid downstream input accepted as valid

Then the phase **must not** merely document. Instead:
1. Note the defect as **Phase 08.1 critical repair**
2. Halt further audit (or mark as awaiting repair)
3. Recommend immediate fix before proceeding

---

## Hard Fail Conditions

Phase 08 automatically fails (verdict `FAIL`) if **any** of:

- Supported input produces malformed normalized output without detection
- Metadata required for lineage silently lost
- Chunk output empty/corrupt while marked valid
- Same input yields materially inconsistent output without documented cause
- Failure cases produce garbage accepted downstream
- Actual implementation contradicts documented normalization behavior
- Critical defect present and not deferred to Phase 08.1

---

## Notes for Executor

- **Do not** redesign the normalizer.
- **Do not** optimize chunking strategy.
- **Do not** broaden support claims beyond code evidence.
- **Do not** treat deduplication as a core audit target.
- **Do** use runtime probes to validate behavior; code reading alone insufficient.
- **Do** adhere to scope boundary rules (chunker as validator only, dedupe out-of-scope).
- **Do** record concrete evidence (samples, hashes, diffs) in deliverables.

Proceed methodically through Tasks 08-01 → 08-10. Capture findings objectively.
