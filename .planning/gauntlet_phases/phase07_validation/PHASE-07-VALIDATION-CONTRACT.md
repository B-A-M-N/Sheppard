# Phase 07 — Validation Contract (Core Orchestration)

**Purpose**: Define the invariants, measurement methods, and pass/fail criteria for validating the **orchestration contract** defined in PHASE-07.0-CONTEXT.md. This is a focused validation of the control spine, not a comprehensive system quality audit.

**Scope**: Only the 5 core orchestration invariants. All other concerns are deferred to later phases.

---

## Core Invariant Set (Phase 07 PASS requires ALL)

| ID | Invariant | Description |
|-----|-----------|-------------|
| V-01 | `budget_metrics_reflect_real_storage` | BudgetMonitor reports actual DB size within 5% |
| V-02 | `condensation_trigger_correctness` | Condensation triggers exactly once at HIGH threshold |
| V-04 | `cross_component_consistency` | No divergence between DB, memory, retrieval after 5s |
| V-09 | `mission_lifecycle_transitions_correct` | State machine follows `created→active→terminal` |
| V-10 | `backpressure_prevents_queue_overflow` | Queue depth never exceeds MAX_QUEUE_DEPTH |

---

## V-01: BudgetMetricsReflectRealStorage

**Measurement**:
- Compare `budget.get_raw_bytes(mission_id)` vs `SELECT SUM(size) FROM corpus.sources WHERE mission_id=?`
- Compare `budget.get_condensed_bytes(mission_id)` vs `SELECT SUM(size) FROM corpus.atoms WHERE mission_id=?`

**Pass criteria**: ≤ 5% deviation for both.

**Failure**: In-memory counters diverge → ceiling unreliable.

---

## V-02: CondensationTriggerCorrectness

**Measurement**:
1. Set thresholds: LOW=70%, HIGH=85%, CRITICAL=95%
2. Ingest sources; monitor condensation runs and log events
3. Stop when `raw_bytes` reaches 90%

**Pass criteria**:
- At least one condensation run between 85–90%
- Zero runs before 85%
- Runs non-overlapping (next starts only after previous finishes)

**Failure**: Premature/missing/duplicate triggers.

---

## V-04: CrossComponentConsistency

**Measurement**:
1. Ingest source + atoms
2. Wait 5s for sync
3. Query ArchivistIndex for that source/atom by ID
4. Compare returned object to DB row (fields match)
5. Repeat for 100 random items

**Pass criteria**:
- 100% match on all fields (timestamps ±1s)
- Zero missing items

**Failure**: Stale cache, lost writes, partial sync.

---

## V-09: MissionLifecycleTransitionsCorrect

**Measurement**:
1. Start mission; record `status` from DB
2. Let run to completion (or stop)
3. Query audit log/history for `statusChange` events
4. Verify sequence validity and durability

**Pass criteria**:
- Sequence: `created → active → (complete|stopped|failed)`
- No illegal jumps (e.g., `created → complete`)
- Terminal state persists across DB restart

**Failure**: State machine corruption, non-durable terminal.

---

## V-10: BackpressurePreventsQueueOverflow

**Measurement**:
1. Set `MAX_QUEUE_DEPTH = 100` (test value)
2. Pre-enqueue 100 jobs
3. Attempt additional enqueue → must reject
4. Drain queue
5. Verify frontier resumes

**Pass criteria**:
- Queue depth ≤ 101 (≤ 100 + 1 race)
- Frontier pauses when backpressure engaged
- Frontier resumes when depth < 90 (hysteresis)

**Failure**: Queue overflow → Redis OOM; frontier continues producing.

---

## Verification Process

For each invariant:
1. Implement test (unit/integration/E2E)
2. Run against current codebase
3. Record `PASS` or `FAIL` with evidence
4. Aggregate: ALL must `PASS` for Phase 07 success
5. Any `FAIL` → gap → Phase 07 re-work or new gap-closure phase

**Artifacts**:
- `tests/validation/v01_budget_metrics.py`
- `tests/validation/v02_condensation_trigger.py`
- `tests/validation/v04_consistency.py`
- `tests/validation/v09_lifecycle.py`
- `tests/validation/v10_backpressure.py`
- `PHASE-07-VERIFICATION.md` summarizing results

---

## Contract Enforcement

- No adding invariants mid-stream
- No loosening criteria after seeing results
- No skipping because "hard"

If an invariant cannot be tested → that itself is a design gap → mark `FAIL` and open new ambiguity.

---

**Locked items**: These 5 invariants are the **definition of done** for Phase 07.

**Deferred** (not part of this contract, will be planned later):
- V-03 Report quality evaluable
- V-05 Firecrawl test strategy defined
- V-06 ResearchSystem/orchestrator integration
- V-07 Config exposes required metrics
- V-08 LLM errors handled gracefully
- V-11 Exhausted modes survive restart (Phase 06 gap already fixed; this verifies the fix, could be included if desired but not core)
- V-12 Academic filtering enforced (Phase 06 gap; same note)

**Rationale**: Phase 07 validates the orchestration spine. The deferred items are either already verified by earlier phases or belong to product/quality hardening.
