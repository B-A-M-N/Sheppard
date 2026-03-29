# Phase 06 — Discovery Ambiguities (Audit Scope)

**Purpose**: Define the precise set of ambiguities that Phase 06 (Discovery Engine Audit) is authorized to observe, classify, and evidence. This is the *working set* for the audit. No other items from the master ambiguity register are in scope.

**Scope boundary**: Only aspects of the discovery layer (AdaptiveFrontier, Crawler, URL selection, depth behavior, state persistence). Do NOT expand into orchestration, condensation, budget, indexing, CLI, or performance concerns.

---

## 1. Taxonomy Hierarchy Not Enforced

**Issue**: `parent_node_id` is declared in `MissionNode` schema but never populated at runtime.

**What the code does**:
- `_frame_research_policy()` prompts for structured topic decomposition (15 nodes)
- `_save_node()` and `_respawn_nodes()` construct `MissionNode` without setting `parent_node_id`
- Result: every node in the database has `parent_node_id = None`

**Correct classification**:
```
STATUS: PARTIAL (STRUCTURE PRESENT, BEHAVIOR ABSENT)
```

**Audit question**:
> Does the system actually produce a navigable research tree, or just a flat list?

**Required evidence**:
- `domain_schema.py` line ~107 — `parent_node_id: Optional[str] = None`
- `frontier.py` lines 157-171 — `_save_node` construction (no parent_node_id)
- `frontier.py` lines 329-352 — `_respawn_nodes` calls `_save_node` without parent_node_id

---

## 2. Deep Mining / Pagination Mischaracterized

**Issue**: The code supports `range(1, 6)` pages but uses break-on-first-success logic, so pages 2–5 are only fetched if earlier pages yield zero new URLs.

**What the code does**:
```python
# crawler.py lines 294-330
for page in range(1, 6):
    # fetch page
    if page_new_count > 0:
        break  # stop as soon as any new URL found
```

**Behavior**:
- Fresh mission (empty `visited_urls`): page 1 yields many new URLs → loop breaks immediately → pages 2–5 never fetched
- Near-saturation (many known URLs): pages 1..N all duplicates → loop continues to page N+1 where new URL found
- Fully saturated: no new URLs anywhere → inner break fires on line 300 (empty result)

**Correct classification**:
```
STATUS: PARTIAL / MISCHARACTERIZED (FALLBACK PAGINATION, NOT DEPTH EXPLORATION)
```

**Audit question**:
> Does discovery intentionally explore deeper result space, or only fallback when dedupe exhausts earlier pages?

**Required evidence**:
- `crawler.py` lines 294-330 — `discover_and_enqueue` page loop
- `crawler.py` lines 322-326 — break condition `if page_new_count > 0: break`
- Behavior table from SEARCH_BEHAVIOR_REPORT.md (fresh vs. near-saturation vs. saturated)

---

## 3. URL Quality Controls Not Enforced

**Issue**: `ACADEMIC_WHITELIST_DOMAINS` exists and `_is_academic()` classifies URLs, but no filtering occurs in the enqueue path. `academic_only` mode is implemented but never activated.

**What the code does**:
- `ACADEMIC_WHITELIST_DOMAINS` list (crawler.py lines 25-30)
- `_is_academic(url)` returns True/False based on domain substring match (lines 385-387)
- `_route_url()` assigns "fast"/"slow" lanes (processing priority, not filtering)
- `discover_and_enqueue()` has **no call to `_is_academic`** — every URL not in `visited_urls` is enqueued unconditionally
- `academic_only` flag on `Crawler` defaults to `False` (line 71)
- `FirecrawlLocalClient` construction in `system.py` lines 125-128 does **not set** `academic_only=True`

**Correct classification**:
```
STATUS: PARTIAL (CLASSIFICATION INFRASTRUCTURE PRESENT, NO ENFORCEMENT)
```

**Audit question**:
> Does the system actually control input quality, or just label URLs?

**Required evidence**:
- `crawler.py` lines 25-30 — whitelist definition
- `crawler.py` lines 112-132 — `_route_url` (lane assignment, not rejection)
- `crawler.py` lines 185 — `academic_only` parameter (default False)
- `crawler.py` lines 294-330 — `discover_and_enqueue` (no `_is_academic` call)
- `system.py` lines 125-128 — `FirecrawlLocalClient` construction (no `academic_only=True`)
- The code path where `academic_only` would be checked is `crawler.py` line ~185 (likely an `if` block)

---

## 4. Epistemic Mode Persistence Lost on Restart

**Issue**: The `exhausted_modes` set tracks which epistemic modes have been tried per node, but it is re-initialized to `set()` on every restart.

**What the code does**:
- `AdaptiveFrontier` maintains `self.exhausted_modes` (per node) to avoid repeating modes
- `_load_checkpoint()` (frontier.py lines 143-148) loads checkpoint state but **does not restore** `exhausted_modes` from storage
- Instead, line 147: `exhausted_modes=set()` — resets to empty set on every startup
- Result: after a restart, the frontier re-generates nodes and **re-attempts all 4 modes** for each node, duplicating work

**Correct classification**:
```
STATUS: PARTIAL (IN-MEMORY PROGRESSION, NO PERSISTENCE)
```

**Audit question**:
> Does epistemic progression survive mission lifecycle events (restart, resume), or does it reset each run?

**Required evidence**:
- `frontier.py` lines 143-148 — `_load_checkpoint` resetting `exhausted_modes=set()`
- `frontier.py` lines 286-310 — mode selection and injection logic (uses `exhausted_modes`)
- Note: Checkpoint file contents (if any) to confirm `exhausted_modes` not saved

---

## 5. Queue / Backpressure Unbounded

**Issue**: `enqueue_job()` in `redis.py` performs an unbounded `rpush` with no queue depth check, no llen guard, no circuit breaker. Discovery can outpace the 8 vampire workers indefinitely.

**What the code does**:
```python
# redis.py lines 83-84
async def enqueue_job(self, job):
    await self.redis.rpush(self.queue_key, serialize(job))
```
- No `llen` check before push
- No max-depth configuration
- No feedback from worker pool to frontier
- No backpressure mechanism (rate limiting, pause signal, rejection)

**Risk**: Under sustained high yield, queue grows unboundedly → memory pressure → Redis OOM → system instability.

**Correct classification**:
```
STATUS: OPEN (ARCHITECTURAL GAP — NO THROTTLE)
```

**Audit question**:
> Does discovery respect system capacity, or can it overproduce work indefinitely?

**Required evidence**:
- `redis.py` lines 83-84 — `enqueue_job` implementation (unbounded rpush)
- Count of vampire workers (likely 8 from `config` or constant) — to show producer-consumer ratio
- Absence of any: `llen` check, `ltrim`, circuit breaker, pause/resume signaling

---

## 6. Optional Slot

**Guideline**: Only include this if a clear, well-evidenced discovery bug emerges that doesn't fit the above 5. Do NOT invent a sixth item to fill the slot. If nothing compelling, leave blank.

**Potential candidates** (only if strongly supported by code):
- Discovery deduplication timing (URL check before/after fetch)
- Multi-mission discovery interference (shared Redis keys, visited_urls leakage)
- Search result ranking / relevance ordering (if claimed but absent)
- Node generation determinism (temperature, seed)

**Default**: Empty.

---

## Phase 06 Deliverables (from this ambiguity set)

### Documents to produce:

1. **DISCOVERY_AUDIT.md** — classification table (7 areas including the 5 above, plus 2 more from claims), overall verdict
2. **TAXONOMY_GENERATION_AUDIT.md** — deep dive on `parent_node_id` gap (A.1 above)
3. **SEARCH_BEHAVIOR_REPORT.md** — deep dive on break-on-first-success inversion (A.2 above)
4. **URL_SELECTION_HEURISTICS.md** — deep dive on `academic_only` inactivity (A.3 above)
5. **PHASE-06-VERIFICATION.md** — checklist, runtime-only items, missing/inflated claims, verdict

### Expected outcomes:

- Each ambiguity is **observed** (code inspection confirms behavior)
- Each ambiguity is **classified** (PASS / PARTIAL / FAIL / OPEN)
- Each ambiguity has **line-number evidence**
- The overall verdict: `PASS` with multiple `PARTIAL` findings is **the correct outcome** (structures exist, enforcement missing)

### What Phase 06 is NOT:

- NOT a redesign phase
- NOT a gap-closure implementation phase
- NOT a source of new features
- NOT a forum for debating "what should have been"

It is a **brutal, evidence-grounded inventory** of discovery layer reality versus claims.

---

**Reference**:
- Full master ambiguity register: `.planning/AMBIGUITY_REGISTER_MASTER.md`
- Phase 06 plan template: `.planning/gauntlet_phases/phase06_discovery/PLAN.md`
- Completed audit (expected location): `.planning/gauntlet_phases/phase06_discovery/DISCOVERY_AUDIT.md`
