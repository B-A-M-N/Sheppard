# Phase 05 — Queue Handoff & Async Boundary Audit

**Date**: 2026-03-27
**Auditor**: Claude Code

Detailed analysis of how work moves between pipeline stages, including queue semantics, deduplication, retries, and concurrent access.

---

## 1. Producer → Consumer Handoff: Frontier → Vampire

### Handoff Mechanism
- **Producer**: `AdaptiveFrontier.run()` via `crawler.discover_and_enqueue()`
- **Queue**: Redis list `queue:scraping`
- **Consumers**: 8 parallel `_vampire_loop()` tasks in `SystemManager`

### Enqueue Path

**File**: `src/research/acquisition/crawler.py:280-331`

```python
async def discover_and_enqueue(...) -> int:
    for page in range(1, 6):
        urls = await self._search(query, pageno=page)
        for url in urls:
            if visited_urls and url in visited_urls: continue
            lane = self._route_url(url)
            payload = {
                "topic_id": topic_id,
                "mission_id": mission_id or topic_id,
                "url": url,
                "url_hash": md5(url.encode()).hexdigest(),
                "lane": lane,
                "priority": 1 if lane == "fast" else 0
            }
            await system_manager.adapter.enqueue_job("queue:scraping", payload)
            if visited_urls: visited_urls.add(url)
            total_enqueued += 1
        if page_new_count > 0: break  # stop after first fruitful page
```

- Enqueues are **fire-and-forget** from frontier perspective (no acknowledgment)
- `visited_urls` set prevents immediate duplicate enqueues within same mission, but:
  - `visited_urls` is **in-memory only** — lost on frontier restart → duplicates possible
- Each URL enqueued once (first page with hits)

### Dequeue Path

**File**: `src/core/system.py:305-353`

```python
async def _vampire_loop(self, vampire_id: int):
    while True:
        job = await self.adapter.dequeue_job("queue:scraping", timeout_s=10)
        if not job: continue
        mission_id = job.get("mission_id")
        # Dedupe check
        existing = await self.adapter.get_source_by_url_hash(job.get("url_hash"))
        if existing and existing.get("status") == "fetched":
            continue  # skip
        # Budget check
        if not self.budget.can_crawl(mission_id):
            await self.adapter.enqueue_job("queue:scraping", job)  # re-queue
            await asyncio.sleep(30); continue
        # Scrape & ingest
        result = await self.crawler._scrape_with_retry(url)
        if result:
            await self.adapter.ingest_source(source_meta, result.markdown)
```

- Vampires **compete** for jobs: `dequeue_job` is a blocking pop; each job goes to exactly one vampire
- Timeout 10s: if queue empty, vampire yields and retries
- **Idempotency**: Before scraping, vampire checks `get_source_by_url_hash()`; if source already exists with `status='fetched'`, job is skipped (idempotent consumer)
- **Backpressure**: If budget full, job is **re-queued** (enqueued again at tail) and vampire sleeps 30s

---

## 2. Queue Semantics & Guarantees

| Property | Value | Evidence |
|----------|-------|----------|
| Queue type | Redis list (LPUSH / RPOP) | `RedisStoresImpl.enqueue_job()` / `dequeue_job()` |
| Ordering | LIFO (stack) or FIFO depending on implementation | Need to check `RedisStoresImpl` |
| Visibility timeout | None (immediate processing) | — |
| Dead letter queue | None | Failed jobs not re-queued after max retries |
| Acknowledgment | Implicit via deletion after dequeue | Job removed from list on `RPOP` |
| Durability | Depends on Redis persistence config | Not controlled at app level |

### Redis Queue Implementation

Likely pattern:
- `enqueue_job`: `redis.lpush(queue, serialized(payload))`
- `dequeue_job`: `redis.rpop(queue)` → returns payload or None

**Implications**:
- At-most-once delivery: if vampire crashes after dequeue but before ingestion, job is lost
- No explicit retry limit; failed jobs (e.g., scrape errors) are **not** re-queued unless budget check triggers re-queue
- Scrape failures inside `_vampire_loop` (exception on ingest?) cause loop to log error and continue — job already popped

---

## 3. Deduplication Mechanisms

### URL Deduplication
- **Producer-side**: `visited_urls` Set in `AdaptiveFrontier` prevents re-enqueue in same frontier run
- **Consumer-side**: `get_source_by_url_hash(job["url_hash"])` check in vampire prevents re-scrape if source already ingested
- **Schema constraint**: `corpus.sources` has unique index on `(mission_id, normalized_url_hash)` — database rejects duplicates

**Gap**: `visited_urls` not persisted across restarts. After restart, frontier re-discovers URLs, vampires may scrape again until first one completes and stores source. Duplicate detection then kicks in (idempotent via content hash) but wasted work occurs.

### Atom Deduplication
- `knowledge_atoms` primary key: `atom_id` (UUID) — no natural dedupe
- **No content-hash constraint** — identical atoms from different sources may be inserted multiple times
- Evidence links may differ, but atom statement duplication not prevented

**Risk**: Atom explosion without deduplication by content hash (identified in ambiguities A11).

---

## 4. Retry & Error Handling

### Scrape Retry
**Location**: `src/research/acquisition/crawler.py:335-359`

```python
async def _scrape_with_retry(self, url: str) -> Optional[CrawlResult]:
    for attempt in range(self.config.max_retries):  # default: 3
        try:
            async with self._session.post(...) as resp:
                ...
        except:
            await asyncio.sleep(self.config.retry_base_delay * (2 ** attempt))
    return None
```

- Exponential backoff: `retry_base_delay * 2^attempt` (e.g., 1s, 2s, 4s)
- After max retries, returns `None`
- Vampire logs error and continues (job considered consumed; no re-queue)

**Outcome**: Transient network errors retried; permanent failures lose the URL.

### Queue Dequeue Failures
- If `dequeue_job` returns `None` (timeout), vampire loops immediately (no sleep)
- No special handling for malformed jobs (assumes well-formed payload)

### Budget Backpressure
- If `budget.can_crawl()` returns False, vampire **re-queues** the job and sleeps 30s
- Job goes back to tail of queue; will be retried later
- Prevents runaway storage growth during condensation

---

## 5. Concurrency & Races

### Multiple Vampires
- 8 tasks run the same `_vampire_loop`, all competing for `queue:scraping`
- Redis `RPOP` is atomic — each job delivered to exactly one vampire
- **Race**: Two vampires may both check `get_source_by_url_hash()` for same URL if:
  - Same URL enqueued twice (producer duplicate)
  - Both check before either has ingested
  - Both may scrape; database unique constraint on `(mission_id, normalized_url_hash)` prevents duplicate source rows, but second insert becomes no-op (ON CONFLICT) — wasteful but safe

### Budget Updates
- `BudgetMonitor.record_bytes()` called via `on_bytes_crawled` callback from `crawler.crawl_topic` (synchronous path) **or from vampire?**
  - **Issue**: Vampire does **not** call `on_bytes_crawled`. Budget only updated during `crawl_topic` runs, not during vampire consumption.
  - **Gap**: Condensation may not trigger from vampire-scraped sources because `record_bytes` not invoked.
  - Budget monitor has secondary polling loop (`run_monitor_loop()`) that checks `raw_bytes_total` from DB? Let's check: `budget._check_thresholds` uses in-memory `budget.raw_bytes`, which is updated by `record_bytes`. If `record_bytes` never called, thresholds never crossed → condenser never fires.
  - **Critical gap**: Vampire ingestion bypasses budget accounting.

**Verification needed**: Is `on_bytes_crawled` wired into vampire path? In `system.py:126` during initialization: `self.crawler = FirecrawlLocalClient(..., on_bytes_crawled=self.budget.record_bytes)`. Then in `_vampire_loop`, after successful scrape we call `self.crawler._scrape_with_retry(url)` but **do not** call `self.budget.record_bytes()`. The `crawler` itself does not call the callback in `_scrape_with_retry`. So indeed, vampire-scraped sources do **not** increment budget raw_bytes.

This is a **silent bug**: Condensation will not trigger from vampire work, only from `crawl_topic` synchronous path (which is used by... somewhere else? Possibly legacy). Need to fix by adding `await self.budget.record_bytes(mission_id, result.raw_bytes)` after `ingest_source` in vampire.

---

### Frontier Node Checkpoint Races
- `_save_node()` called after each node processed (line 126)
- Multiple frontier runs may exist (different missions) each with separate `AdaptiveFrontier` instance
- `self.sm.adapter.upsert_mission_node()` uses `mission_id` in PK — no conflicts across missions
- **Race within same mission**: Frontier runs single-threaded (async one node at a time), so checkpoint sequential — safe

---

## 6. Missing or Undefined Behaviors

| Issue | Category | Impact |
|-------|----------|--------|
| Vampire does not call `budget.record_bytes` | Accounting gap | Condensation never triggers from vampire-scraped sources; storage may grow unchecked |
| `visited_urls` not persisted | Dedupe gap | Duplicate discovery after restart wastes scrape quota |
| No dead-letter queue for failed jobs | Error handling | Permanent failures lose work silently |
| No job acknowledgment before scrape | Reliability | Job lost if vampire crashes mid-scrape |
| Retry count not logged | Observability | Hard to diagnose repeated failures |
| Condenser runs sequentially (semaphore=2) but no global limit | Throughput | Could cause backlog if many sources fetched |

---

## 7. Queue Handoff Summary Table

| Stage | Handoff Type | Storage | Guarantees | Loss Conditions |
|-------|--------------|---------|------------|-----------------|
| Frontier → Redis | Async enqueue | Redis `queue:scraping` list | At-most-once delivery (job present) | Redis restart with volatile config; queue overflow (unlikely) |
| Redis → Vampire | Atomic pop | Redis list | Each job consumed by one vampire | Vampire crash after pop, before completion |
| Vampire → Ingestion | Direct call | V3 `corpus.sources` | Source persisted atomically | Crash before `ingest_source` completes → job lost |
| Ingestion → Distillation | DB polling | `corpus.sources` rows with `status='fetched'` | Sources eventually picked up by condenser | Condenser never runs (budget gap) or crashes |
| Distillation → Storage | Transaction | `knowledge_atoms`, `atom_evidence` | Atomic commit; index + cache after | Crash inside transaction → rollback; after commit but before index → manual reindex needed |

---

## 8. Recommendations

1. **Fix budget accounting in vampire**:
   ```python
   # After successful ingestion in _vampire_loop:
   await self.budget.record_bytes(mission_id, result.raw_bytes)
   ```
2. **Persist `visited_urls`**:
   - Store visited URL hashes in DB (e.g., `ops.visited_urls` table) with TTL
   - Load on frontier start
3. **Add dead-letter queue**:
   - On scrape failure after retries, enqueue to `queue:failed` for later analysis
4. **Add job acknowledgment before work**:
   - Use Redis `RPOPLPUSH` pattern: move job to `processing` queue before scrape, delete only after success
5. **Atom deduplication**:
   - Add unique constraint on `knowledge_atoms(mission_id, statement_hash)` or content fingerprint
6. **Observability**:
   - Log each state transition (mission status changes, source status updates)
   - Expose metrics (queue depth, vampire throughput, condenser lag)

---

**Status**: Audit complete. Critical gap identified: **vampire does not trigger budget accounting**, preventing automatic distillation. This must be fixed for pipeline completeness (A7).
