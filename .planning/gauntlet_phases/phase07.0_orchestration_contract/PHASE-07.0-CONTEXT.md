# Phase 07.0 — Orchestration Contract Definition

**Purpose**: Lock down the execution semantics, trigger points, and consistency model for the unified research orchestrator before any implementation or validation work begins.

**Scope**: Pure specification. No code, no tests, no validation framework. This is the "contract" that Phase 07 (validation) will later verify against.

**Out-of-scope**:
- Implementation details (algorithms, data structures)
- Configuration options (ceiling values, thresholds)
- CLI/API design
- Performance targets (latency, throughput)
- Documentation structure
- Demo scenarios

---

## 1. Mission Lifecycle State Machine

```
                      ┌──────────────┐
                      │   created    │ ← initial
                      ───────┬───────┘
                             │ orchestrator.run_mission()
                             ▼
                      ┌──────────────┐
                      │   active     │ ← frontier+crawler running
                      ───────┬───────┘
                             │
                ┌───────────┼───────────┐
                │           │           │
                ▼           ▼           ▼
          ┌─────────┐ ┌─────────┐ ┌─────────┐
          │complete │ │ stopped │ │ failed  │ ← terminal
          └─────────┘ └─────────┘ └─────────┘
                │           │           │
                │           │           │ (retryable?)
                │           │           ▼
                │           │     ┌─────────┐
                │           └────►│  retry  │
                │                 └────┬────┘
                │                      │
                └──────────────────────┘ (conditional)
```

**State definitions**:

| State | Invariant | Transitions |
|-------|-----------|-------------|
| `created` | Mission record exists, no tasks started | → `active` on `run_mission()` |
| `active` | Frontier running, budget monitoring, condensation may be queued/running | → `complete` (exhaustion or ceiling) <br> → `stopped` (user cancel) <br> → `failed` (uncaught exception, budget overflow without recovery) |
| `complete` | Mission finished normally; final report generated | Terminal |
| `stopped` | User cancelled; partial state preserved for resume | Could → `active` on resume (optional) |
| `failed` | Unrecoverable error; requires manual intervention | Could → `retry` (if safe) or terminal |
| `retry` | System performing automatic retry (e.g., after transient network) | → `active` or `failed` |

**Required state fields**:
- `mission_id` (UUID)
- `status` (enum above)
- `created_at`, `updated_at`
- `error` (str, null if OK)
- `final_report` (text, nullable)

---

## 2. Execution Loop (Happy Path)

```
orchestrator.run_mission(topic_id, ceiling_bytes):
  1. Initialize components:
     - frontier = AdaptiveFrontier(topic_id)
     - crawler = Crawler()
     - budget = BudgetMonitor(topic_id, ceiling_bytes)
     - condensation = DistillationPipeline(ollama, memory, budget, adapter)
     - index = ArchivistIndex(mission_id)  ← scoped
     - Set status = active

  2. Start background tasks (async):
     - budget_monitor_task = monitor loop (poll every 10s)
     - condensation_task = wait for high threshold, then run

  3. Main discovery loop (frontier.run()):
     while frontier not exhausted:
       concept = frontier.next_concept()
       urls = crawler.discover(concept)
       for url in urls:
         if not visited(url):
           success = enqueue_job(url)  ← may trigger backpressure
           if success:
             mark_visited(url)
             frontier.record_fetch()
           else:
             backpressure_triggered = True
             break loops
       frontier.checkpoint()

     if backpressure_triggered:
       pause frontier (wait for queue to drain)
       resume after threshold drops

  4. Exit conditions (checked after each frontier iteration):
     - Exhaustion: frontier.is_exhausted → set status=complete, break
     - Ceiling: budget.raw_bytes >= ceiling_bytes → set status=complete, break
     - Failure: budget cannot free space after condensation attempt → set status=failed, break

  5. Shutdown:
     - Cancel background tasks gracefully
     - If status == active due to exhaust/ceiling:
         → Run final condensation pass (if needed)
         → Generate final report (via synthesis)
         → Save report to DB
         → Set status=complete

  6. Return mission_id
```

**Critical invariants**:
- Frontier, crawler, budget all share the same `topic_id` (scoping)
- `visited_urls` must be persisted or shared to avoid re-fetch across restarts
- Condensation runs in its own task; may overlap with discovery while budget high
- Backpressure causes frontier to pause, not exit

---

## 3. Trigger Points

### 3.1 Condensation Trigger

**When**: `BudgetMonitor` polls every 10s (configurable). If `raw_bytes / ceiling >= threshold`:

| Threshold level | Action |
|-----------------|--------|
| `LOW` (70%) | Log warning only |
| `HIGH` (85%) | Queue condensation (if not already running/queued) |
| `CRITICAL` (95%) | Block enqueue (backpressure) AND urgent condensation |

**Semantics**:
- Condensation is **idempotent**: running multiple times on same sources is safe (atoms deduplicated)
- If condensation already running/queued at HIGH+, skip new trigger (avoid pile-up)
- Condensation may prune raw sources (mark as condensed); budget must adjust `raw_bytes` accordingly
- Condensation failures: log error, continue; do **not** fail mission unless repeatedly failing

**Trigger flow**:
```python
# budget_monitor_task loop
if raw_bytes / ceiling >= HIGH and not condensation_running:
    condensation_queue.put(mission_id)
elif raw_bytes / ceiling >= CRITICAL:
    enqueue_blocked = True  # backpressure engages
```

### 3.2 Exhaustion Detection

**Frontier-driven**:
- `AdaptiveFrontier.is_exhausted` property returns `True` when:
  - All nodes in `self.nodes` have `all(mode in exhausted_modes for mode in EPISTEMIC_MODES)`, AND
  - No new nodes generated in last N iterations (stagnation)
- Frontier calls `self.checkpoint()` after each node saturation to persist state

**Orchestrator check**:
```python
if frontier.is_exhausted:
    status = complete
```

### 3.3 Ceiling Enforcement

**Budget-driven**:
- `BudgetMonitor.raw_bytes` tracks total raw content size (DB query sum, not just in-memory)
- When `raw_bytes >= ceiling_bytes`:
  - Set `ceiling_reached = True`
  - Orchestrator exits discovery loop after current frontier iteration
  - Final condensation runs to free space if needed
  - Status = complete

**Note**: Temporary overage allowed up to small buffer (1%) due to polling lag.

### 3.4 Backpressure Engagement

**Redis adapter**:
- `enqueue_job()` checks `llen(queue)` before `rpush`
- If `depth >= MAX_QUEUE_DEPTH` (config, default 10000):
  - Log warning
  - Return `False` (reject)
- **Crawler** on rejection:
  - Set `backpressure_triggered = True`
  - Break inner URL loop
  - Break outer page loop
- **Orchestrator**:
  - Detects flag; pauses frontier (stop calling `next_concept()`)
  - Waits for queue depth to drop below threshold (poll every 1s)
  - Resumes frontier when drained

**Purpose**: Prevent Redis OOM by matching producer rate to consumer capacity.

---

## 4. Control Authority

### 4.1 BudgetMonitor Role

The BudgetMonitor is the **gatekeeper** for resource limits:

- **Tracks**: `raw_bytes` (sum of `sources.size`), `condensed_bytes` (sum of `atoms.size`)
- **Polls**: Every 10s to recalculate from DB (not in-memory counters)
- **Triggers**:
  - HIGH → enqueue condensation job
  - CRITICAL → signal backpressure to frontier
- **Does NOT**:
  - Stop the world immediately at ceiling (allows buffer)
  - Kill the mission (that's orchestrator's job)
  - Manage condensation execution (just signals)

### 4.2 Orchestrator Role

Orchestrator is the **state machine owner**:

- Holds `mission.status`
- Starts/stops components
- Checks exit conditions after each frontier iteration
- Performs final condensation and report generation
- Handles errors and user stop requests

### 4.3 CondensationPipeline Role

Condensation is a **batch worker**:

- Input: `SELECT sources WHERE mission_id=? AND status='fetched' AND condensed=False`
- Output: `KnowledgeAtom` rows, `sources.condensed=True`
- Reports: number of atoms extracted, sources condensed
- Idempotent: running twice on same source yields no duplicate atoms (dedup by content hash)
- Should run in separate async task, not block discovery loop

### 4.4 Stop Conditions

Mission ends when:

1. `frontier.is_exhausted == True` → `complete`
2. `budget.raw_bytes >= ceiling_bytes` → `complete` (possibly early)
3. `User initiates stop` → `stopped` (graceful: finish current work, checkpoint, shutdown)
4. `Uncaught exception in critical component` → `failed`

**Note**: Backpressure alone does **not** stop mission; only pauses frontier until queue drains.

---

## 5. Consistency Model

### 5.1 Atomic Guarantees

These operations **must** be atomic:

- `visited_urls` insertion: "check-then-set" for a URL must be atomic to prevent duplicate fetches across concurrent crawlers.
- `enqueue_job` + `visited_urls` update: should be atomic (both commit or neither) to avoid losing work if backpressure rejects.
- `condensation` atom insertion: each atom must be created exactly once per source (dedup by content hash).
- `mission.status` transitions: status changes (active → complete/stopped/failed) must be durable.

### 5.2 Eventual Consistency

- `raw_bytes` in BudgetMonitor may lag DB by up to poll interval (10s). This is acceptable.
- `frontier.exhausted_modes` may not reflect condensation progress (no coupling needed).
- Index updates (chunks + atoms) may be slightly behind ingestion; query-time freshness is "good enough".

### 5.3 Allowed Races

- Multiple crawler workers can fetch different URLs concurrently (no coordination needed beyond `visited_urls` atomic check).
- Frontier may generate new nodes while condensation runs (no locking; eventually consistent).
- Multiple condensation jobs overlapping are safe due to idempotency, but we prevent concurrent runs via flag.

### 5.4 Critical Sections

- `visited_urls` set → use Redis SET with NX or PostgreSQL advisory lock to ensure single-writer per URL.
- `condensation_running` flag → atomic compare-and-swap or asyncio.Lock in orchestrator.
- `backpressure_triggered` → atomic bool; crawler tasks read and set.

---

## 6. ArchivistIndex Partitioning (Decision Only)

**Question**: Does `ArchivistIndex` need per-mission partitioning, or do we use separate indexes?

**Required**: Multi-mission support (runs concurrent missions).

**Options**:

| Option | Pros | Cons |
|--------|------|------|
| A. Single index + `mission_id` metadata filter | Memory efficient, single cache | All queries must filter; risk of leakage if filter forgotten |
| B. Separate index per mission (in-memory/file) | Complete isolation, simple | Memory scales with concurrent missions; no cross-mission sharing |

**Decision (待定)**: Option A preferred **if** index backend supports efficient metadata filtering (ChromaDB collections, FAISS with ID mapping). Option B simpler to implement but heavier memory.

**Minimal viable**: Implement Option B first (separate indices), refactor to Option A later if memory becomes issue.

**For contract**: The system **must** support at least 2 concurrent isolated missions. Data from Mission A must never appear in Mission B query results.

---

## 7. Data-Flow Invariants

```
Concept → URLs → Sources → Atoms → Report
```

- **Concept** originates from frontier; labeled with `node_id`
- **URLs** discovered; `node_id` carried as metadata through crawl
- **Source** record includes `mission_id`, `node_id`, `url`, `fetched_at`, `size`
- **Atom** includes `mission_id`, `source_id` chain, `concept` (from node), `claim`, `evidence`
- **Report** aggregates atoms by concept, preserves source citations

**Invariant**: Every atom must be traceable to:
1. The source it came from (`source_id`)
2. The concept that triggered the fetch (`node_id`)
3. The mission it belongs to (`mission_id`)

---

## 8. Error Handling Philosophy

- **Transient errors** (network, rate limits): retry with backoff (3 attempts)
- **Permanent errors** (404, malformed HTML): log and skip; do not retry
- **Condensation failure**: log and continue; condensation may be retried later (idempotent)
- **Budget overflow**: if condensation cannot free space within 5 minutes → `failed`
- **Orchestrator crash**: checkpoint state to DB; on restart, load checkpoint and resume from last known `mission_id` state

---

## 9. Observability Hooks (Minimal Instrumentation)

Even without full metrics, these events **must** be logged:

- `mission.{mission_id}.status_change: {old} → {new}`
- `condensation.triggered: threshold={level} raw_bytes={X} ceiling={Y}`
- `backpressure.triggered: queue_depth={Z}`
- `frontier.exhaustion: nodes={N} modes_exhausted={M}`
- `error.*`: component failures with stacktraces

Log format: structured JSON with `mission_id`, `timestamp`, `component`.

---

## 10. Open Questions (Excluded from Contract — For Later Phases)

These are **not** part of Phase 07.0; they belong to config, product, or performance phases:

- What are exact threshold percentages? (70/85/95 are placeholders)
- What is `MAX_QUEUE_DEPTH`? (10000 is placeholder)
- How long should condensation take per GB?
- What is the final report format (markdown sections, length)?
- How to handle large sources (>1MB)?
- Should condensation batch size be configurable?
- What monitoring dashboard metrics are needed?
- How to expose query interface (REST/WebSocket/CLI)?

---

## 11. Verification Checklist (For Phase 07 Validation)

Later, Phase 07 validation will verify:

- [ ] Mission state machine correctly transitions through all states
- [ ] Condensation triggers exactly at threshold crossings (not repeatedly)
- [ ] Exhaustion detection stops frontier only when truly no new concepts possible
- [ ] Ceiling halts discovery at or slightly above limit (within buffer)
- [ ] Backpressure pauses frontier when queue depth exceeded
- [ ] Two concurrent missions produce no data leakage
- [ ] Atomicity: no duplicate URL fetches under concurrent crawlers
- [ ] Checkpoint/restart: `visited_urls`, `exhausted_modes`, frontier nodes preserved
- [ ] Idempotency: re-running condensation on same sources yields duplicate atoms (deduped)
- [ ] Error handling: transient errors retried, permanent errors skipped

**This checklist derives directly from the contract above.**

---

## 12. Glossary

- **frontier**: `AdaptiveFrontier` — generates research concepts/nodes
- **crawler**: `Crawler` — discovers URLs, fetches content, enqueues sources
- **budget**: `BudgetMonitor` — measures raw/condensed bytes, triggers actions
- **condensation**: `DistillationPipeline` — extracts atoms from sources
- **index**: `ArchivistIndex` — stores chunks and atoms for retrieval
- **queue**: Redis list `queue:scraping`; depth measured by `llen`
- **backpressure**: mechanism that pauses frontier when queue full
- **mission**: single research execution (topic + lifecycle)

---

**Document status**: DRAFT — ready for review before implementation begins.

**Locking rule**: Once approved, **do not change** during implementation. If gaps discovered, they become new ambiguities for a future phase.

---
