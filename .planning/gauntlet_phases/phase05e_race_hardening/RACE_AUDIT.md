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

**Pattern:** Multiple vampire coroutines (`_VAMPIRE_COUNT` workers, default >= 2) pull jobs from `queue:scraping` via `BLPOP`. Two vampires can dequeue different job objects that represent the same URL (duplicate enqueue by frontier) and both reach `get_source_by_url_hash` before either has finished scraping and inserting.

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
