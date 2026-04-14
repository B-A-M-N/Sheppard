# Codebase Concerns

**Analysis Date:** 2026-04-14

## CONFIRMED BUG: Missing "fetched" → "extracted" State Transition

**Severity:** HIGH — Causes duplicate atom extraction and stuck sources

**Issue:** The distillation pipeline extracts atoms from sources in `"fetched"` status, but then tries to transition from `"extracted"` → `"condensed"`. There is **no intermediate step** that transitions `"fetched"` → `"extracted"` after successful atom extraction.

**State machine** (`src/research/state_machine.py`):
```
"fetched" → {"extracted", "error", "filtered_out"}
"extracted" → {"condensed", "filtered_out", "rejected"}
```

**Pipeline code** (`src/research/condensation/pipeline.py`):
- Line 117: `WHERE status='fetched'` — fetches sources in "fetched" state ✅
- Line 321: `transition_source_status(..., "filtered_out", current_status="fetched")` — Gate 0a reject ✅
- Line 306, 311, 343: `transition_source_status(..., "error", current_status="fetched")` — early errors ✅
- Line 447: `transition_source_status(..., "condensed", current_status="extracted")` — **BUG** ❌
- Line 454: `transition_source_status(..., "filtered_out", current_status="extracted")` — **BUG** ❌
- Line 472: `transition_source_status(..., "rejected", current_status="extracted")` — **BUG** ❌

**Impact:**
1. `transition_source_status` uses `UPDATE ... WHERE status = 'extracted'` — this **silently fails** (returns False, 0 rows updated) because the source is still in `"fetched"` status
2. Sources remain in `"fetched"` status permanently
3. On the next distillation pass, these sources are re-fetched (still `status='fetched'`)
4. Idempotency check at line 158 only skips `"extracted"`, `"condensed"`, `"indexed"` — `"fetched"` passes through
5. Atoms are **re-extracted and re-inserted**, potentially causing duplicate key violations on the deterministic UUID5 `atom_id`
6. Budget accounting fires repeatedly for the same sources
7. Condensation never "completes" — budget thresholds keep firing, condensation keeps running

**Fix approach:** Add `transition_source_status(adapter, source_id, "extracted", current_status="fetched")` immediately after successful atom extraction and before the final status transition. Or, change the final transitions to use `current_status="fetched"` and update the state machine to allow `fetched → condensed` directly.

**Priority:** HIGH — affects all distillation runs

## DLQ Consumer Re-enqueues Without Retry Delay

**Issue:** The DLQ consumer re-enqueues failed jobs back to `queue:scraping` without any delay or retry count increment.

**File:** `src/core/dlq_consumer.py` line 76

**Impact:** If a URL consistently fails (e.g., domain is down), it cycles through: DLQ re-enqueue → vampire picks it up → fails → DLQ again. The vampire loop's own retry logic (3 attempts with exponential backoff) is bypassed.

**Fix approach:** DLQ consumer should increment `retry_count` or use `schedule_retry()` with a future timestamp.

**Priority:** Medium

## Budget Thresholds Are Very Low

**Issue:** Default thresholds trigger condensation at just 1% (50MB), 5% (250MB), and 10% (500MB) of a 5GB ceiling.

**File:** `src/research/acquisition/budget.py` lines 64-66

**Impact:** Condensation runs extremely frequently. The `pending_source_count >= 50` trigger (line 217) is the more practical one for most missions.

**Priority:** Low — works but wasteful

## Retry Mechanism Is Dead Code

**Issue:** `schedule_retry()` and `move_due_retries()` in `src/memory/adapters/redis.py` exist but are never called. The vampire loop handles retries inline with `asyncio.sleep()`.

**Files:**
- `src/memory/adapters/redis.py` lines 109-120
- Not called anywhere in active codebase

**Impact:** The zadd-based delayed retry infrastructure is unused. Inline retry with `asyncio.sleep()` blocks the vampire iteration.

**Priority:** Low — cleanup opportunity

## No Rate Limiting on Firecrawl Calls from Vampires

**Issue:** 8 concurrent vampire workers call Firecrawl `/v1/scrape` with no rate limiting between them.

**Files:**
- `src/research/acquisition/crawler.py` line 392: `_scrape_with_retry()`
- `src/core/system.py` line 194: `NUM_VAMPIRES` default = 8

**Impact:** Local Firecrawl may return errors under load, causing retries and wasted cycles.

**Priority:** Medium

## Test Coverage Gaps

**Untested critical paths:**
- **Distillation status transitions** — the `"fetched"` → `"condensed"` path (which is broken)
- **Budget monitor recurring triggers** — threshold reset after condensation completes
- **Vampire distributed locking** — concurrent URL processing race conditions
- **DLQ consumer** — re-enqueue behavior and interaction with vampire retry loop

**Priority:** Medium

---

*Concerns audit: 2026-04-14*
