# Phase 05 — `/learn` Pipeline Ambiguities

**Status**: UNBLOCKED (proceed to audit)
**Date**: 2026-03-27 (updated)
**Auditor**: Claude Code

---

## Resolution Summary

Phase 05 was initially blocked by upstream Phase 03.0 and Phase 03 violations. Those have been **resolved**.

**Resolved upstream blockers**:
- ✅ A1: V2 Memory Still Used — removed
- ✅ A2: Frontier Dual Persistence — removed
- ✅ A3: Vampire Dual Writes — removed
- ✅ A4: Topic vs Mission ID Identity — locked to `mission_id`

**Upstream verification updates**:
- Phase 03.0: Canonical Authority Lock — **PASS** (verification updated)
- Phase 03: Triad Enforcement — **PASS** with frontier dual-persistence fix incorporated

**Remaining gaps** (non-blocking, for Phase 03 to finalize):
- A5: Budget Monitor V2 Dependency
- A6: Condensation Parameter Mismatch
- A7: Distillation Trigger Undefined
- A14: Chunk → Atom Trigger Gap

These do not prevent Phase 05 audit; they represent pipeline correctness details to be validated during audit.

---

## Ambiguity Summary (Current)

| # | Ambiguity | Severity | Maps To | Status |
|---|-----------|----------|---------|--------|
| 1 | V2 Memory Still Used | HARD FAIL | Phase 03.0 | ✅ RESOLVED |
| 2 | Frontier Dual Persistence | HARD FAIL | Phase 03 | ✅ RESOLVED |
| 3 | Vampire Dual Writes | HARD FAIL | Phase 03 | ✅ RESOLVED |
| 4 | Topic vs Mission ID Identity | HARD FAIL | Phase 03.0 | ✅ RESOLVED |
| 5 | Budget Monitor V2 Dependency | HIGH | Phase 03 | OPEN (Phase 03 scope) |
| 6 | Condensation Parameter Mismatch | HIGH | Phase 02/03 | OPEN |
| 7 | Distillation Trigger Undefined | HIGH | Phase 02/03 | OPEN |
| 8 | ResearchSystem Unused | MEDIUM | Phase 02 | OPEN |
| 9 | State Machine Implicit | HIGH | Phase 05 scope | OPEN |
| 10 | URL Deduplication Incomplete | MEDIUM | Phase 05 quality | OPEN |
| 11 | Atom Deduplication Unknown | MEDIUM | Phase 05 quality | OPEN |
| 12 | Retry Policies Undefined | MEDIUM | Phase 05 quality | OPEN |
| 13 | Race Conditions Unchecked | LOW | Phase 05 quality | OPEN |
| 14 | Chunk → Atom Trigger Gap | HIGH | Phase 02/03 | OPEN |
| 15 | Indexing Completeness | MEDIUM | Phase 03 | ✅ VERIFIED OK |

---

## Critical Blockers (Must Fix Before Phase 05)

### A1. V2 Memory Still Used

**Evidence**:
- `src/core/system.py:174` — `await self.memory.create_topic()`
- `src/core/system.py:175` — `await self.memory.update_topic_status(topic_id, "active")`
- `src/core/system.py:385` — `await self.memory.update_topic_status(topic_id, "done")`
- `src/core/system.py:391` — `await self.memory.update_topic_status(topic_id, "failed")`
- `src/core/system.py:419` — `await self.memory.update_topic_status(topic_id, "stopped")`
- `src/research/acquisition/frontier.py:142` — `self.sm.memory.get_visited_urls()`
- `src/research/acquisition/frontier.py:158` — `self.sm.memory.get_frontier_nodes()`
- `src/research/acquisition/frontier.py:187` — `await self.sm.memory.upsert_frontier_node()`

**Why blocking**: Phase 03.0 set `self.memory = None`. These calls will **crash at runtime**.

**Required**: Replace all `self.memory.*` with V3 adapter methods or remove if redundant.

**Owner**: Phase 03.0 (Canonical Authority Lock)

---

### A2. Frontier State Persistence Split

**Evidence** (`src/research/acquisition/frontier.py:137-187`):

```python
# Load: V3 first, V2 fallback
db_nodes = await self.sm.adapter.list_mission_nodes(self.mission_id)
if not db_nodes:
    legacy_nodes = await self.sm.memory.get_frontier_nodes(self.topic_id)

# Save: Writes to BOTH
await self.sm.adapter.upsert_mission_node(v3_node.to_pg_row())
await self.sm.memory.upsert_frontier_node(self.topic_id, **node.to_dict())  # <-- V2
```

**Why blocking**: Two sources of truth violate triad (Postgres sole canonical). V2 fallback contradicts V3-only guarantee.

**Required**: Remove V2 fallback and V2 writes. Use V3 exclusively.

**Owner**: Phase 03 (Triad Enforcement)

---

### A3. Vampire Dual Writes

**Evidence** (`src/core/system.py:349-360`):

```python
# V3 write (correct)
await self.adapter.ingest_source(source_meta, result.markdown)

# V2 write (violation)
await self.memory.store_source(
    topic_id=topic_id,
    url=url,
    content=result.markdown,
    ...
)
```

**Why blocking**: Writes to both V3 (`corpus.sources`) and V2 legacy store. Attempts to use `self.memory` fail in V3.

**Required**: Remove V2 `memory.store_source()` call entirely.

**Owner**: Phase 03 (Triad Enforcement)

---

### A4. Topic vs Mission ID Identity Crisis

**Evidence**:
- `learn()` creates both `topic_id` (via V2) and `mission_id` (V3)
- Frontier uses both: `self.topic_id` and `self.mission_id`
- `_crawl_and_store` line 377: `mission_id = topic_id` fallback
- V3 adapter methods take `mission_id`; V2 methods take `topic_id`

**Ambiguity**: What is canonical identifier in V3?

**Required decision**: **`mission_id` is the ONLY canonical identifier in V3**. `topic_id` is deprecated and must not exist in runtime paths.

**Owner**: Phase 03.0 (Identity Model Lock)

---

## High-Priority Gaps (Pipeline Correctness)

### A5. BudgetMonitor V2 Dependency

- `system.py:203` — `self.budget.register_topic(topic_id=topic_id, ...)`
- `frontier.py:86` — `self.sm.budget.get_status(self.topic_id)`
- `system.py:329` — `if not self.budget.can_crawl(topic_id)`

**Gap**: BudgetMonitor tracks by `topic_id` (V2). Must migrate to `mission_id` or be replaced.

**Owner**: Phase 03 (Triad alignment)

---

### A6. Condensation Parameter Mismatch

- `pipeline.py:43` — `run(self, mission_id: str, priority)`
- `system.py:430` — `_condensation_callback(self, topic_id: str, priority)`
- `pipeline.py:45` — `topic_id = mission_id  # Bridge for budget hooks`

**Gap**: Fragile identity bridging. Standardize on `mission_id` throughout.

**Owner**: Phase 02/03 boundary

---

### A7. Distillation Trigger Undefined

**Evidence**:
- `_vampire_loop` calls `ingest_source` but does **not** trigger distillation
- `DistillationPipeline.run()` must be called explicitly
- `_condensation_callback` defined but not registered with budget monitor
- Manual `/distill` works but auto-trigger unknown

**Gap**: How does distillation start automatically when storage thresholds crossed?

**Required**: BudgetMonitor should call `_condensation_callback` when thresholds crossed.

**Owner**: Phase 02/03 (Pipeline orchestration)

---

### A14. Chunk → Atom Trigger Gap

**Evidence**:
- `ingest_source` (storage_adapter.py:767) creates chunks but does **not** trigger atom extraction
- `DistillationPipeline.run()` processes sources with `status="fetched"`
- Who decides when to run distillation after chunks exist?

**Gap**: Missing orchestrator that connects "chunks created" → "start distilling".

**Owner**: Phase 02/03 (Pipeline completeness)

---

## Medium Priority (Defer but Track)

| # | Ambiguity | Description |
|---|-----------|-------------|
| 10 | URL Dedup Only in Vampire | Frontier enqueues duplicates; vampire dedupes at consume (wasted queue slots). Add dedupe in discovery. |
| 11 | Atom Dedup Unknown | `store_atom_with_evidence` uses `ON CONFLICT (atom_id)` but `atom_id=uuid4()` ensures no conflicts. Should use `content_hash` for idempotency. |
| 12 | Retry Policies Undefined | No visible retry for network failures, LLM errors, DB transactions. Must be documented or implemented. |
| 13 | Race Conditions Unchecked | Potential races in frontier checkpointing, concurrent updates. |
| 15 | ResearchSystem Unused | `ResearchSystem` initialized but never used in V3 path. Decide: wire or remove. |

---

## Structural Clarifications (Not Blockers)

### A9. State Machine Implicit

Phase 05 requires:
```
INPUT_RECEIVED → MISSION_CREATED → TOPIC_DECOMPOSED → URL_DISCOVERED → URL_QUEUED → URL_FETCHED → CONTENT_NORMALIZED → ATOMS_EXTRACTED → ATOMS_STORED → INDEX_UPDATED
```

Current gap: No explicit state tracking. States are implicit in async flows and DB status values (`corpus.sources.status`).

**Required**: Document the **as-is** state machine by analyzing existing code, even if implicit.

**Owner**: Phase 05 (documentary)

---

## Required Resolution Path

### Step 1: Fix Phase 03.0 Blockers (A1, A4)

- Remove all `self.memory.*` calls in V3 runtime
- Lock identity model: `mission_id` only; eliminate `topic_id` from V3 paths
- Verify: `SystemManager.learn()` uses V3 adapter exclusively

### Step 2: Fix Phase 03 Triad Violations (A2, A3, A5)

- Frontier: Remove V2 fallback; persist only via `adapter.upsert_mission_node()`
- Vampire: Remove `memory.store_source()`; rely solely on `adapter.ingest_source()`
- BudgetMonitor: Upgrade to use `mission_id` or mark as V2-only (deprecated)

### Step 3: Complete Phase 02/03 Boundary (A6, A7, A14)

- Standardize condenser on `mission_id` parameter
- Wire budget monitor → `_condensation_callback` registration
- Verify distillation trigger fires automatically when `mission_id` storage thresholds crossed
- Confirm chunk→atom pipeline: `ingest_source` → chunks created → condenser picks up `status="fetched"` sources

### Step 4: Execute Phase 05 Audit

Only after Steps 1-3 complete, trace `/learn` end-to-end and produce:
- `LEARN_EXECUTION_TRACE.md`
- `PIPELINE_STATE_MACHINE.md`
- `QUEUE_HANDOFF_AUDIT.md`
- `PHASE-05-VERIFICATION.md` (PASS only if state machine fully explicit with no missing transitions)

---

## Verdict Prediction

**Current `/learn` implementation**: **FAIL** — V2 dependencies + implicit state machine + missing triggers.

**Minimum for PASS**:
- Zero V2 memory calls in V3 runtime
- Single-source truth (Postgres) for all persistent state
- Explicit state machine traceable in code with all transitions documented
- Distillation trigger operational (automatic or manual with documented policy)
- All deduplication and retry policies defined

---

## Classification Reference

| Ambiguity | Phase | Type |
|-----------|-------|------|
| A1 | 03.0 | Authority violation |
| A2 | 03 | Dual persistence |
| A3 | 03 | Dual persistence |
| A4 | 03.0 | Identity model |
| A5 | 03 | Triad misalignment |
| A6 | 02/03 | API inconsistency |
| A7 | 02/03 | Missing trigger |
| A8 | 02 | Unused component |
| A9 | 05 | Documentation gap |
| A10 | 05 | Incomplete dedupe |
| A11 | 05 | Idempotency gap |
| A12 | 05 | Undefined retries |
| A13 | 05 | Race condition risk |
| A14 | 02/03 | Pipeline gap |
| A15 | 03 | Indexing (OK) |

---

**Action**: Do not proceed with Phase 05 execution until A1–A4 resolved and A2–A3, A5–A7, A14 addressed.
