---
phase: 05e-race-hardening
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - src/core/system.py
  - .planning/gauntlet_phases/phase05e_race_hardening/RACE_AUDIT.md
autonomous: true
requirements: [A13]
gap_closure: true

must_haves:
  truths:
    - "Two vampire workers dequeuing the same URL simultaneously cannot both proceed to scrape it"
    - "The first vampire to acquire a Redis NX lock on a URL scrapes it; the second logs a skip and continues"
    - "Lock keys expire in 300 seconds, preventing permanent starvation if a vampire crashes mid-scrape"
    - "All known concurrent hot paths are enumerated with a risk level and verdict (safe / accepted / needs-guard)"
    - "No path is marked 'safe' without identifying the mechanism that makes it safe"
  artifacts:
    - path: "src/core/system.py"
      provides: "Redis NX lock guard in _vampire_loop before _scrape_with_retry call"
      contains: "lock:scraping:"
    - path: ".planning/gauntlet_phases/phase05e_race_hardening/RACE_AUDIT.md"
      provides: "Enumeration of all concurrent hot paths with verdict table"
      contains: "TOCTOU"
  key_links:
    - from: "src/core/system.py:_vampire_loop"
      to: "self.adapter.acquire_lock(lock_key, ttl_s=300)"
      via: "StorageAdapter.acquire_lock before _scrape_with_retry"
      pattern: "lock:scraping:"
    - from: "RACE_AUDIT.md"
      to: "src/core/system.py, src/research/acquisition/frontier.py, src/memory/storage_adapter.py"
      via: "cross-reference to actual code locations"
      pattern: "VERDICT"
---

<objective>
Close gap A13: duplicate processing is still possible when multiple vampire workers dequeue different jobs for the same URL at the same time. The DB unique constraint on url_hash prevents data corruption but does not prevent redundant network I/O and scraping work.

Purpose: Add a Redis SET NX distributed lock per URL that short-circuits the second vampire before it calls _scrape_with_retry. Pair this with a written race audit that justifies which paths need guards and which are already safe by construction.

Output: Modified _vampire_loop in system.py with NX lock, and RACE_AUDIT.md as the formal analysis artifact required by the phase spec.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/gauntlet_phases/phase05e_race_hardening/PHASE-05E-PLAN.md
@.planning/gauntlet_phases/phase05a_dedup/PLAN.md

<interfaces>
<!-- From src/core/system.py _vampire_loop (lines 304–356) -->
<!-- self.adapter is a StorageAdapter instance -->
<!-- job dict has keys: url, url_hash, mission_id -->
<!-- _scrape_with_retry is called at line 332 -->
<!-- The TOCTOU window is between line 320 (get_source_by_url_hash) and line 332 (_scrape_with_retry) -->

Relevant _vampire_loop skeleton:
```python
async def _vampire_loop(self, vampire_id: int):
    while True:
        job = await self.adapter.dequeue_job("queue:scraping", timeout_s=10)
        if not job: continue
        url = job.get("url")
        mission_id = job.get("mission_id")
        # ... mission_id guard ...

        # TOCTOU window starts here:
        existing = await self.adapter.get_source_by_url_hash(job.get("url_hash", ""))
        if existing and existing.get("status") == "fetched":
            continue

        # ... budget check ...

        result = await self.crawler._scrape_with_retry(url)   # line 332
        # ... ingest ...
```

Lock acquisition via StorageAdapter (src/memory/storage_adapter.py line 872):
```python
# acquire_lock(key, ttl_s) returns LockHandle | None
# Truthy (LockHandle) if the lock was acquired, None if already held by another caller
acquired = await self.adapter.acquire_lock(lock_key, ttl_s=300)
if not acquired:
    continue  # another vampire is already processing this URL
```

<!-- From src/research/acquisition/frontier.py _save_node (lines 156–170) -->
<!-- node_id = uuid.uuid5(NAMESPACE_URL, f"{mission_id}:{node.concept}") -->
<!-- uses upsert_mission_node — idempotent by node_id -->

<!-- From src/memory/storage_adapter.py store_atom_with_evidence (lines 604–660) -->
<!-- Wrapped in conn.transaction() -->
<!-- ON CONFLICT (atom_id) DO UPDATE — idempotent after 05A fix -->
<!-- ON CONFLICT (atom_id, source_id, chunk_id) DO UPDATE on evidence rows -->
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Add Redis NX scraping lock to _vampire_loop in system.py</name>
  <files>src/core/system.py</files>
  <read_first>
    - src/core/system.py lines 304–356 — read the full _vampire_loop to confirm exact indentation, the location of the existing TOCTOU check (line 320), and the call to _scrape_with_retry (line 332). Identify how self.adapter is used elsewhere in the file to confirm the correct method path.
  </read_first>
  <action>
Insert a Redis NX lock acquisition block between the budget check and the _scrape_with_retry call. The insertion point is after the `if not self.budget.can_crawl(mission_id):` block (lines 326–329) and before `result = await self.crawler._scrape_with_retry(url)` (line 332).

Add the following block at that location (match the surrounding 16-space indentation):

```python
                # Distributed lock: prevent redundant concurrent scraping of the same URL.
                # Two vampires can both pass get_source_by_url_hash simultaneously (TOCTOU).
                # acquire_lock uses Redis SET NX internally; only one caller proceeds.
                # The other skips without data loss — the DB unique constraint on url_hash
                # would reject the duplicate anyway.
                lock_key = f"lock:scraping:{job.get('url_hash', '')}"
                acquired = await self.adapter.acquire_lock(lock_key, ttl_s=300)
                if not acquired:
                    logger.debug(f"[Vampire-{vampire_id}] Skipping already-processing URL: {url}")
                    continue
```

No other lines in the method change. The lock is intentionally not released after scraping completes: the 300-second TTL acts as the release mechanism, which also covers the case where a vampire crashes mid-scrape. By the time the TTL expires, the scraped source will have status "fetched" in the DB, so the existing `get_source_by_url_hash` check at line 320 will catch any re-queue of the same URL after the lock expires.

Do NOT add a `finally:` block to release the lock. Explicit release would re-open the TOCTOU window for any vampire that re-dequeues the same URL within the scrape duration. TTL-only release is the correct pattern here.
  </action>
  <verify>
    <automated>grep -n "acquire_lock" /home/bamn/Sheppard/src/core/system.py</automated>
  </verify>
  <acceptance_criteria>
    - `grep -n "lock:scraping:" src/core/system.py` returns exactly one match inside _vampire_loop
    - `grep -n "acquire_lock" src/core/system.py` returns exactly one match
    - `grep -n "Skipping already-processing URL" src/core/system.py` returns exactly one match
    - `grep -n "_scrape_with_retry" src/core/system.py` still returns a match (the call was not removed)
    - The lock block appears between the budget check and the _scrape_with_retry call (verify line order with grep -n)
  </acceptance_criteria>
  <done>
    src/core/system.py contains the acquire_lock block. The lock key pattern is `lock:scraping:{url_hash}`, TTL is 300s, and a vampire that fails to acquire the lock logs at DEBUG and continues to the next job without calling _scrape_with_retry.
  </done>
</task>

<task type="auto">
  <name>Task 2: Write RACE_AUDIT.md enumerating all concurrent hot paths</name>
  <files>.planning/gauntlet_phases/phase05e_race_hardening/RACE_AUDIT.md</files>
  <read_first>
    - src/core/system.py lines 304–356 — confirm final state of _vampire_loop after Task 1
    - src/research/acquisition/frontier.py lines 156–170 (_save_node) — confirm upsert_mission_node usage
    - src/memory/storage_adapter.py lines 604–660 (store_atom_with_evidence) — confirm transaction + ON CONFLICT
    - src/research/acquisition/crawler.py lines 280–331 (discover_and_enqueue) — confirm visited_urls is in-memory only
    - src/research/acquisition/budget.py — find the BudgetMonitor/BudgetManager class and confirm asyncio.Lock usage
  </read_first>
  <action>
Create the file at `.planning/gauntlet_phases/phase05e_race_hardening/RACE_AUDIT.md` with the following exact content:

```markdown
# Race Condition Audit — Phase 05E

**Date:** 2026-03-27
**Scope:** All concurrent hot paths in the acquisition and ingestion pipeline.
**Prerequisite:** Phase 05A (deterministic uuid5 atom_id) is applied.

---

## Summary Table

| Path | Concurrency Type | Risk | Protection Mechanism | VERDICT |
|------|-----------------|------|---------------------|---------|
| Vampire TOCTOU (same URL, multiple workers) | Multi-coroutine, shared Redis queue | Medium — redundant scraping | Redis SET NX lock (`lock:scraping:{url_hash}`, TTL 300s) added in Phase 05E | ACCEPTED WITH GUARD |
| corpus.sources unique constraint (url_hash) | Multi-coroutine | Low — data corruption | DB unique constraint on url_hash; second INSERT is rejected/upserted | SAFE BY DB |
| frontier._save_node concurrent writes | Multi-coroutine (frontier loop + respawn) | Low | node_id = uuid5(mission_id:concept); upsert_mission_node is idempotent | SAFE BY DESIGN |
| BudgetMonitor.record_bytes + _check_thresholds | Multi-coroutine | Low — torn read/write on counters | asyncio.Lock() wraps all state mutations | SAFE BY DESIGN |
| store_atom_with_evidence concurrent atom insert | Multi-coroutine (distillation workers) | Low — duplicate atom rows | asyncio conn.transaction() + ON CONFLICT (atom_id) DO UPDATE; uuid5 atom_id from Phase 05A ensures same atom_id for same content | SAFE AFTER 05A |
| discover_and_enqueue visited_urls dedup | Multi-coroutine (frontier round per query) | Low — redundant enqueue of same URL | visited_urls is a shared Set[str] passed by reference into each discover_and_enqueue call; no lock needed (single frontier coroutine owns the set) | SAFE BY ARCHITECTURE |
| _scrape_with_retry concurrent HTTP calls | Multi-coroutine (multiple vampires) | None — stateless | Each call is an independent aiohttp POST; no shared mutable state | NOT A RACE |

---

## Detailed Analysis

### 1. Vampire TOCTOU — ACCEPTED WITH GUARD

**Location:** `src/core/system.py` `_vampire_loop` lines 304–356

**Pattern:** Multiple vampire coroutines (`_VAMPIRE_COUNT` workers, default ≥ 2) pull jobs from `queue:scraping` via `BLPOP`. Two vampires can dequeue different job objects that represent the same URL (duplicate enqueue by frontier) and both reach `get_source_by_url_hash` before either has finished scraping and inserting.

**Window:** Between `get_source_by_url_hash` (read) and `ingest_source` (write). If both vampires read "not yet fetched" simultaneously, both call `_scrape_with_retry` and attempt ingestion. The DB `ON CONFLICT (url_hash)` on `corpus.sources` prevents double insertion, but both network requests complete wastefully.

**Guard added (Phase 05E):**
```python
lock_key = f"lock:scraping:{job.get('url_hash', '')}"
acquired = await self.adapter.acquire_lock(lock_key, ttl_s=300)
if not acquired:
    logger.debug(f"[Vampire-{vampire_id}] Skipping already-processing URL: {url}")
    continue
```
`acquire_lock` (storage_adapter.py line 872) calls `client.set(key, token, ex=ttl_s, nx=True)` internally and returns a `LockHandle` (truthy) if acquired, `None` if already held.

Lock is NOT explicitly released. The 300s TTL is the release mechanism. This is intentional: explicit release re-opens the window during the scrape duration. After TTL expiry the DB `get_source_by_url_hash` check catches re-queued duplicates with status "fetched".

**Residual risk:** If a vampire crashes after acquiring the lock but before completing ingestion, the URL is blocked for 300s. After TTL expiry, the next vampire will find status != "fetched" and will re-scrape. This is correct behavior (no data loss, one retry cycle).

---

### 2. corpus.sources Unique Constraint — SAFE BY DB

**Location:** `src/memory/storage_adapter.py` `ingest_source`

**Pattern:** Even without the NX lock, a second vampire reaching `ingest_source` for the same URL would hit the `ON CONFLICT (url_hash)` clause on `corpus.sources`. The row is upserted (not duplicated). No data corruption is possible.

**Verdict:** Safe by DB constraint. The NX lock in path 1 above makes this a defense-in-depth layer, not the primary guard.

---

### 3. frontier._save_node — SAFE BY DESIGN

**Location:** `src/research/acquisition/frontier.py` lines 156–170

**Pattern:** `_save_node` is called from within the single `AdaptiveFrontier.run()` coroutine loop and from `asyncio.create_task(self._save_node(node))` in `_select_next_action`. Concurrent calls for the same node can occur during rapid status transitions.

**Protection:** `node_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{self.mission_id}:{node.concept}"))` — deterministic. `upsert_mission_node` uses `ON CONFLICT (node_id) DO UPDATE`. Two concurrent upserts for the same node_id are serialized by the DB; the last writer wins on status/yield fields, which is acceptable (monotonic saturation progression).

**Verdict:** Safe by design. No guard needed.

---

### 4. BudgetMonitor Counters — SAFE BY DESIGN

**Location:** `src/research/acquisition/budget.py`

**Pattern:** `record_bytes` and `_check_thresholds` mutate in-process counters. Multiple vampire coroutines call `record_bytes` concurrently after each successful scrape.

**Protection:** `asyncio.Lock()` wraps all counter mutations. Within a single asyncio event loop, only one coroutine holds the lock at a time.

**Verdict:** Safe by design. Lock is already in place.

---

### 5. store_atom_with_evidence Concurrent Atom Insert — SAFE AFTER 05A

**Location:** `src/memory/storage_adapter.py` lines 604–660

**Pattern:** Distillation workers running concurrently for different sources can produce the same atom (same concept, same content). Before Phase 05A these had different uuid4 atom_ids so both inserted successfully, creating duplicates. After Phase 05A the atom_id is `uuid5(mission_id:source_id:content[:200])`, so two concurrent distillation passes for the same source produce identical atom_ids.

**Protection (post-05A):**
- `async with conn.transaction()` — each writer holds a DB transaction.
- `ON CONFLICT (atom_id) DO UPDATE SET ...` on `knowledge_atoms` — second writer updates the same row.
- `ON CONFLICT (atom_id, source_id, chunk_id) DO UPDATE` on `atom_evidence` — evidence rows are upserted.

**Verdict:** Safe after Phase 05A. No additional guard needed.

---

### 6. discover_and_enqueue visited_urls — SAFE BY ARCHITECTURE

**Location:** `src/research/acquisition/crawler.py` lines 280–331

**Pattern:** `visited_urls` is a `Set[str]` owned by `AdaptiveFrontier` and passed by reference to each `discover_and_enqueue` call. The frontier loop is sequential (one `discover_and_enqueue` call per query, not concurrent). The set is mutated inside the call for each enqueued URL.

**Verdict:** No concurrency on this set. The frontier loop is single-coroutine. Safe by architecture.

---

### 7. _scrape_with_retry HTTP Calls — NOT A RACE

**Location:** `src/research/acquisition/crawler.py` lines 335–359

**Pattern:** Stateless aiohttp POST to firecrawl-local. Each call is independent. Return value is a `CrawlResult` dataclass with no shared state.

**Verdict:** Not a race condition. No shared mutable state.

---

## Accepted Races (no guard, documented rationale)

| Race | Rationale |
|------|-----------|
| Vampire lock expires mid-scrape crash → re-scrape after 300s | One extra scrape of a URL is acceptable. DB constraint prevents double insertion. |
| frontier._save_node last-writer-wins on status field | Node status only moves forward (underexplored → saturated). Last-writer-wins is monotonically correct. |

---

## Gaps Closed

- **A13** — TOCTOU window in vampire URL processing is now guarded by Redis SET NX (via `self.adapter.acquire_lock`). Duplicate processing is prevented. Data corruption was already prevented by DB constraints.
```
  </action>
  <verify>
    <automated>grep -c "VERDICT" /home/bamn/Sheppard/.planning/gauntlet_phases/phase05e_race_hardening/RACE_AUDIT.md</automated>
  </verify>
  <acceptance_criteria>
    - File exists at `.planning/gauntlet_phases/phase05e_race_hardening/RACE_AUDIT.md`
    - `grep -c "VERDICT" RACE_AUDIT.md` returns 7 or more (one per table row plus column header)
    - `grep "TOCTOU" RACE_AUDIT.md` returns at least 2 matches (summary table + detailed section)
    - `grep "ACCEPTED WITH GUARD" RACE_AUDIT.md` returns at least 1 match
    - `grep "SAFE BY DESIGN" RACE_AUDIT.md` returns at least 2 matches
    - `grep "SAFE AFTER 05A" RACE_AUDIT.md` returns at least 1 match
    - `grep "A13" RACE_AUDIT.md` returns at least 1 match in the "Gaps Closed" section
  </acceptance_criteria>
  <done>
    RACE_AUDIT.md exists with a 7-row summary table, detailed analysis for each path, and an explicit "Gaps Closed" section naming A13. Every path has a VERDICT. No path is marked safe without naming its protection mechanism.
  </done>
</task>

</tasks>

<verification>
After both tasks complete, run:

    grep -n "lock:scraping:" /home/bamn/Sheppard/src/core/system.py
    grep -n "acquire_lock" /home/bamn/Sheppard/src/core/system.py
    grep -c "VERDICT" /home/bamn/Sheppard/.planning/gauntlet_phases/phase05e_race_hardening/RACE_AUDIT.md

Expected:
- First two commands each return exactly one line inside _vampire_loop
- Third command returns 7 or more

Manual spot-check: open RACE_AUDIT.md and confirm the summary table has 7 rows and no path is missing a verdict.
</verification>

<success_criteria>
- `grep "lock:scraping:" src/core/system.py` matches exactly once inside _vampire_loop
- `grep "acquire_lock" src/core/system.py` matches exactly once
- `grep "Skipping already-processing URL" src/core/system.py` matches exactly once
- RACE_AUDIT.md exists with 7 enumerated paths, each with VERDICT column populated
- RACE_AUDIT.md explicitly closes gap A13 in the "Gaps Closed" section
- No existing _vampire_loop logic is removed (get_source_by_url_hash check, budget check, ingest_source call all remain)
</success_criteria>

<output>
After completion, create `.planning/gauntlet_phases/phase05e_race_hardening/SUMMARY.md` describing:
- What changed (system.py NX lock insertion via acquire_lock, RACE_AUDIT.md created)
- Why (gap A13: TOCTOU window caused redundant concurrent scraping)
- Evidence (grep output confirming lock line, grep count confirming audit completeness)
- Verification decision: PASS or FAIL
</output>
