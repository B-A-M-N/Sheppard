---
phase: 05e-race-hardening
plan: 01
subsystem: acquisition-pipeline
tags: [race-conditions, redis-lock, toctou, audit, gap-closure]
dependency_graph:
  requires: [phase05a-dedup]
  provides: [A13-gap-closed, race-audit]
  affects: [src/core/system.py, acquisition-pipeline]
tech_stack:
  added: []
  patterns: [redis-nx-lock, tdd-ttl-only-release, defense-in-depth]
key_files:
  created:
    - .planning/gauntlet_phases/phase05e_race_hardening/RACE_AUDIT.md
  modified:
    - src/core/system.py
decisions:
  - "TTL-only lock release (no explicit unlock) to keep TOCTOU window fully closed during scrape duration"
  - "300s TTL chosen to cover worst-case scrape + ingestion time while allowing recovery if vampire crashes mid-scrape"
  - "Lock not released on scrape failure — DB status check catches the re-queued URL after TTL expiry"
metrics:
  completed: 2026-03-27
  tasks: 2
  files: 2
---

# Phase 05E Plan 01: Race Hardening Summary

**One-liner:** Redis SET NX distributed lock on `lock:scraping:{url_hash}` prevents TOCTOU duplicate scraping by concurrent vampire workers, closing gap A13.

---

## What Changed

### Task 1 — src/core/system.py

Added a Redis NX lock acquisition block in `_vampire_loop` between the budget check and the `_scrape_with_retry` call (lines 365–374):

```python
lock_key = f"lock:scraping:{job.get('url_hash', '')}"
acquired = await self.adapter.acquire_lock(lock_key, ttl_s=300)
if not acquired:
    logger.debug(f"[Vampire-{vampire_id}] Skipping already-processing URL: {url}")
    continue
```

The lock uses `StorageAdapter.acquire_lock` which calls `redis.set(key, token, ex=300, nx=True)` internally. The lock is intentionally never explicitly released — the 300s TTL is the sole release mechanism.

### Task 2 — RACE_AUDIT.md

Created a formal race condition audit enumerating all 7 concurrent hot paths in the acquisition and ingestion pipeline. Each path has a named protection mechanism and an explicit VERDICT. No path is marked safe without identifying what makes it safe.

---

## Why (Gap A13)

Multiple vampire coroutines (`_VAMPIRE_COUNT` workers) pull from a shared Redis queue. Two vampires can dequeue different job objects for the same URL (duplicate enqueue by frontier) and both pass the `get_source_by_url_hash` check simultaneously — this is the TOCTOU window. Without a lock, both proceed to `_scrape_with_retry`, making two redundant HTTP calls to firecrawl-local and racing to insert into `corpus.sources`. The DB unique constraint on `url_hash` prevents data corruption but does not prevent the wasted network I/O.

The NX lock ensures only one vampire proceeds past the lock acquisition point per URL at any given time. The second vampire logs at DEBUG and continues to the next job immediately.

---

## Evidence

Verification commands and expected results:

```
grep -n "lock:scraping:" src/core/system.py
# Expected: exactly one match inside _vampire_loop (line ~370)

grep -n "acquire_lock" src/core/system.py
# Expected: exactly one match inside _vampire_loop

grep -n "Skipping already-processing URL" src/core/system.py
# Expected: exactly one match

grep -c "VERDICT" .planning/gauntlet_phases/phase05e_race_hardening/RACE_AUDIT.md
# Expected: 8 or more (7 table rows + column header)

python -c "import ast; ast.parse(open('src/core/system.py').read()); print('syntax OK')"
# Expected: syntax OK
```

---

## Deviations from Plan

None — plan executed exactly as written.

---

## Verification Decision: PASS

All acceptance criteria met:
- `lock:scraping:` appears exactly once in `_vampire_loop`, after the budget check, before `_scrape_with_retry`
- `acquire_lock` appears exactly once in `system.py`
- `_scrape_with_retry` call is intact (not removed)
- `get_source_by_url_hash` check is intact (defense-in-depth layer preserved)
- RACE_AUDIT.md exists with 7 enumerated paths, each with VERDICT column populated
- RACE_AUDIT.md explicitly closes gap A13 in the "Gaps Closed" section
- No existing `_vampire_loop` logic removed

## Self-Check

- [x] src/core/system.py modified with NX lock block (verified by grep: line 370)
- [x] RACE_AUDIT.md created with 7 VERDICT rows
- [x] All _vampire_loop original logic preserved (get_source_by_url_hash at line 354, budget check at line 360, _scrape_with_retry at line 377 all present in final read)
