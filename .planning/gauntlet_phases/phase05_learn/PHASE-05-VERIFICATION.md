# Phase 05 Verification — `/learn` Pipeline Audit

**Date**: 2026-03-27 (post-A7 fix)
**Auditor**: Claude Code
**Verdict**: ✅ **PASS**

---

## State Machine

All transitions now verified and functional:

- [x] `INPUT_RECEIVED` → `MISSION_CREATED`
- [x] `MISSION_CREATED` → `TOPIC_DECOMPOSED` (implicit but present)
- [x] `TOPIC_DECOMPOSED` → `URL_DISCOVERED`
- [x] `URL_DISCOVERED` → `URL_QUEUED`
- [x] `URL_QUEUED` → `URL_FETCHED` (at-most-once delivery, idempotent consumer)
- [x] `URL_FETCHED` → `CONTENT_NORMALIZED` (chunks + text_ref)
- [x] `CONTENT_NORMALIZED` → `ATOMS_EXTRACTED` (distillation trigger fixed)
- [x] `ATOMS_EXTRACTED` → `ATOMS_STORED` (atomic transaction)
- [x] `ATOMS_STORED` → `INDEX_UPDATED` (Chroma indexing)

---

## Deduplication Verified

- [x] **URL dedupe** mechanism exists (frontier `visited_urls` + vampire `url_hash` check + DB unique constraint)
  - *Note*: `visited_urls` in-memory only; duplicates possible after restart but DB constraint prevents data corruption
- [ ] **Atom dedupe** mechanism exists — **OPEN** (atoms use UUID `atom_id`, no content-hash constraint) — tracked as A11, non-blocking

---

## Retry Behavior Documented

- [x] **Fetch retry** defined: `_scrape_with_retry` — 3 attempts, exponential backoff
- [x] **Distillation retry** defined: per-source try/except; failures mark source `error`
- [x] **Failure states** handled: source status updated; batch continues
- [ ] **Job retry** undefined: failed jobs dropped; no dead-letter queue — acceptable for current scope

---

## Evidence

- **Execution trace**: `LEARN_EXECUTION_TRACE.md`
- **State machine**: `PIPELINE_STATE_MACHINE.md`
- **Queue audit**: `QUEUE_HANDOFF_AUDIT.md` (pre-A7 fix analysis)
- **Code changes**: Commit `d42398f` — adds `budget.record_bytes()` call in `_vampire_loop` (system.py:348)

---

## Verdict Rationale

### PASS Reason

The `/learn` pipeline now forms a **complete, deterministic state machine**:

1. **Mission created** → DB record with `mission_id`
2. **Frontier** decomposes topic and discovers URLs
3. **URLs queued** → Redis `queue:scraping`
4. **Vampire** consumes, scrapes, and ingests
5. **Ingestion** creates source + chunks (CONTENT_NORMALIZED)
6. **Budget accounting** fires on each ingestion (`record_bytes`)
7. **Threshold crossing** triggers `condensation_callback`
8. **Distillation** extracts atoms from `status='fetched'` sources
9. **Atomic storage** of atoms + evidence
10. **Indexing** updates Chroma for retrieval

**Key fix applied**: `_vampire_loop` now calls `await self.budget.record_bytes(mission_id, result.raw_bytes)` after each successful ingestion. This restores the budget feedback loop, enabling automatic distillation triggering (resolves A7). Without this, raw_bytes never increased and condenser would never fire in the vampire path.

---

## Remaining Non-Blocking Gaps

| ID | Description | Phase | Status |
|-----|-------------|-------|--------|
| A11 | Atom deduplication missing | 03 | OPEN (quality) |
| A10 | `visited_urls` not persisted | 03 | OPEN (acceptable loss) |
| A5 | BudgetMonitor uses `topic_id` (bridge) | 03 | OPEN (migration pending) |
| A6 | Condensation param `topic_id` bridge | 02/03 | OPEN (works via bridge) |
| A14 | Chunk→atom trigger depends on condenser | 03 | RESOLVED (A7 fixed) |
| A12 | Retry policies could be more robust | 05 | OPEN (minor) |
| A13 | Race conditions (duplicate scrapes) | 05 | OPEN (DB constraints protect) |

These will be addressed in subsequent phases (primarily Phase 03 triad cleanup and Phase 06+ refinement). They do **not** prevent Phase 05 PASS.

---

## Conclusion

**Phase 05: PASS**

The `/learn` pipeline is now fully traceable, deterministic, and operational from command to atom storage. No hard fail conditions remain unaddressed.

**Next**: Archive Phase 05 and proceed to Phase 06 (Discovery Optimization) or complete Phase 03 cleanup (A5-A6, A11) as part of triad enforcement.
