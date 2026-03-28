# Phase 05 Verification — `/learn` Pipeline Audit

**Date**: 2026-03-27
**Auditor**: Claude Code
**Verdict**: ⚠️ **PARTIAL** — State machine traceable, but critical gaps present

---

## State Machine

All transitions verified **in principle**, with notes:

- [x] `INPUT_RECEIVED` → `MISSION_CREATED`
- [ ] `MISSION_CREATED` → `TOPIC_DECOMPOSED` — *implicit (not persisted)*
- [x] `TOPIC_DECOMPOSED` → `URL_DISCOVERED`
- [x] `URL_DISCOVERED` → `URL_QUEUED`
- [x] `URL_QUEUED` → `URL_FETCHED` — *at-most-once delivery (no ack before work)*
- [x] `URL_FETCHED` → `CONTENT_NORMALIZED`
- [ ] `CONTENT_NORMALIZED` → `ATOMS_EXTRACTED` — *trigger may not fire (A7)*
- [x] `ATOMS_EXTRACTED` → `ATOMS_STORED`
- [x] `ATOMS_STORED` → `INDEX_UPDATED`

**Critical Gap**: Distillation trigger depends on `budget.record_bytes()` being called after ingestion. **Vampire does NOT call this**. Condensation only fires if `crawl_topic` path used (unused in V3). Therefore `ATOMS_EXTRACTED` transition **may never happen** for majority of sources.

---

## Deduplication Verified

- [x] **URL dedupe** mechanism exists (frontier `visited_urls` + vampire `url_hash` check + DB constraint)
  - *Gap*: `visited_urls` not persisted; duplicates possible after restart
- [ ] **Atom dedupe** mechanism exists — **NONE** (atoms use UUID `atom_id`, no content-hash constraint)

---

## Retry Behavior Documented

- [x] **Fetch retry** defined: `_scrape_with_retry` — 3 attempts, exponential backoff
- [x] **Distillation retry** defined: per-source try/except; failures mark source `error`
- [x] **Failure states** handled: source status updated; batch continues
- [ ] **Job retry** undefined: failed jobs (after max retries) are dropped; no dead-letter queue

---

## Evidence

- **Execution trace**: `LEARN_EXECUTION_TRACE.md` — complete file:line mapping
- **State machine**: `PIPELINE_STATE_MACHINE.md` — transition table and diagram
- **Queue audit**: `QUEUE_HANDOFF_AUDIT.md` — async boundaries and gap analysis
- **Code references**: See index in trace document

---

## Verdict

**Status**: ⚠️ **PARTIAL**

### Why Not PASS?

Hard fail condition triggered:

> **A major step depends on wishcasting**

Specifically: **Distillation does not automatically trigger from vampire-scraped sources** (A7). The condenser relies on `budget.record_bytes()` to cross storage thresholds, but `_vampire_loop` never calls this method after successful ingestion. As a result:

- Sources ingested by vampires accumulate in `corpus.sources` with `status='fetched'`
- Budget in-memory `raw_bytes` never increases (only updated by `crawl_topic` callback)
- Condensation never fires unless manual `/distill` invoked
- Pipeline stalls at `CONTENT_NORMALIZED` → `ATOMS_EXTRACTED` never happens

### Additional Gaps

- **Atom deduplication missing** (A11) — duplicate atoms will proliferate
- **Work loss on vampire crash** — job popped but not acked; mid-scrape failure loses URL permanently
- **Visited URLs not persisted** — duplicate discovery after restart

---

## Required Fixes (Before PASS)

### 1. Fix Budget Accounting in Vampire (A7)

**File**: `src/core/system.py:355-353`

Add after `ingest_source`:

```python
await self.adapter.ingest_source(source_meta, result.markdown)
# Trigger budget accounting to potentially fire condensation
await self.budget.record_bytes(mission_id, result.raw_bytes)
```

**Impact**: Condensation will now trigger based on actual ingested bytes from vampire path.

---

### 2. Atom Deduplication (A11)

**Option A (preferred)**: Add unique constraint on `knowledge_atoms(mission_id, content_hash)` and compute hash from `statement`.

**Option B (defensive)**: Before `store_atom_with_evidence()`, check if atom with same content_hash exists and reuse existing atom_id.

---

### 3. Acknowledged Job Handoff (Reliability)

Implement reliable queue pattern:
- Use `RPOPLPUSH` to move job from `queue:scraping` to `queue:processing`
- After successful ingestion, remove from `queue:processing`
- On startup, requeue any orphaned jobs from `queue:processing` back to main queue

---

## Residual Non-Blocking Gaps

| ID | Description | Severity | Why Not Blocking |
|-----|-------------|----------|------------------|
| A5 | BudgetMonitor uses `topic_id` (bridge in place) | Medium | Works with `topic_id=mission_id` bridge |
| A6 | Condensation param mismatch (bridge) | Medium | `topic_id = mission_id` bridge works |
| A14 | Chunk → atom trigger depends on A7 fix | High | Once A7 fixed, condenser will process chunks |
| A10 | URL dedupe in-memory only | Medium | Django dedupe protects; some waste acceptable |
| A12 | Retry policies defined but could be more robust | Low | Current retry sufficient |
| A13 | Race conditions possible (duplicate scrapes) | Low | DB constraints prevent data corruption |
| A8 | ResearchSystem unused | Low | V3 uses frontier pipeline; ResearchSystem can be deprecated |

---

## Conclusion

The `/learn` pipeline **is traceable and deterministic in its core transitions**. The state machine, while implicit, is well-defined and implementable.

However, **distillation trigger broken** prevents the pipeline from reaching completion. Fix A7 (+14) is **required** before Phase 05 can PASS.

**Next**:
1. Apply fix to `_vampire_loop` to call `budget.record_bytes()`
2. Re-verify distillation fires automatically
3. Address atom deduplication (A11) for long-term hygiene
4. Consider implementing acknowledged queue pattern for production safety

Upon A7 fix: **PASS** likely achievable (remaining gaps are quality/optimization, not blockers).
