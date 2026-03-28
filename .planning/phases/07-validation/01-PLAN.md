---
phase: 07-validation
plan: 01
type: validation
wave: 1
depends_on: []
files_modified: []
autonomous: true
requirements: [VALIDATION-01, VALIDATION-02, VALIDATION-03, VALIDATION-04, VALIDATION-05]
must_haves:
  truths:
    - "V-01: Budget metrics reflect real storage within 5% tolerance"
    - "V-02: Condensation triggers exactly once when HIGH threshold crossed"
    - "V-04: No divergence between DB, memory, retrieval after 5s stabilization"
    - "V-09: Mission lifecycle follows created→active→terminal with no illegal jumps"
    - "V-10: Queue depth never exceeds MAX_QUEUE_DEPTH; frontier pauses when backpressure engages"
  artifacts:
    - path: "VERIFICATION-V01.md"
      provides: "Budget metrics measurement test results"
    - path: "VERIFICATION-V02.md"
      provides: "Condensation trigger test results"
    - path: "VERIFICATION-V04.md"
      provides: "Cross-component consistency test results"
    - path: "VERIFICATION-V09.md"
      provides: "Lifecycle state machine test results"
    - path: "VERIFICATION-V10.md"
      provides: "Backpressure behavior test results"
    - path: "PHASE-07-VERIFICATION.md"
      provides: "Aggregate verification report; overall PASS/FAIL"
  key_links:
    - from: "VERIFICATION-V01.md"
      to: "PHASE-07.0-CONTEXT.md"
      via: "budget measurement aligns with real storage contract"
    - from: "VERIFICATION-V02.md"
      to: "PHASE-07.0-CONTEXT.md §3.1"
      via: "trigger semantics verified"
    - from: "VERIFICATION-V04.md"
      to: "PHASE-07.0-CONTEXT.md §5"
      via: "consistency model holds"
    - from: "VERIFICATION-V09.md"
      to: "PHASE-07.0-CONTEXT.md §1"
      via: "state machine correctness"
    - from: "VERIFICATION-V10.md"
      to: "PHASE-07.0-CONTEXT.md §3.4"
      via: "backpressure prevents overflow"
    - from: "PHASE-07-VERIFICATION.md"
      to: "PHASE-07-VALIDATION-CONTRACT.md"
      via: "all 5 invariants proved"
stage: draft
estimate_days: 2-3
validate: true
wave_structure:
  wave1: ["07-V01", "07-V02", "07-V04", "07-V09", "07-V10"]
---

<objective>
Validate the orchestration contract (PHASE-07.0-CONTEXT.md) by proving the 5 core invariants (PHASE-07-VALIDATION-CONTRACT.md).

**Scope**: This phase validates ONLY the 5 core orchestration invariants. Deferred invariants (V-03, V-05, V-06, V-07, V-08, V-11, V-12) are tracked separately and out of scope. Do not expand scope.
</objective>

<tasks>

<task type="auto">
  <name>07-V01: Verify budget metrics reflect real storage</name>
  <read_first>
    - .planning/gauntlet_phases/phase07_validation/PHASE-07-VALIDATION-CONTRACT.md
    - .planning/gauntlet_phases/phase07.0_orchestration_contract/PHASE-07.0-CONTEXT.md
    - src/research/acquisition/budget.py
    - tests/ (if existing test infrastructure)
  </read_first>
  <action>
Implement and run test for V-01:

1. Create test: `tests/validation/v01_budget_metrics.py`
   - Setup: Mission with known source corpus (e.g., 10 sources of 10KB each)
   - Let budget monitor poll and update
   - Query DB directly: `SELECT SUM(size) FROM corpus.sources WHERE mission_id=?`
   - Compare to `budget.get_raw_bytes(mission_id)`
   - Repeat after condensation for condensed_bytes
2. Run test: `pytest tests/validation/v01_budget_metrics.py -v`
3. Capture output; compute deviation percentages
4. Write VERIFICATION-V01.md with:
   - Test method
   - Sample size (N sources)
   - raw_deviation: X%
   - condensed_deviation: Y%
   - Verdict: PASS if both ≤ 5%, else FAIL

Success: Test passes and documented.
  </action>
  <verify>
    <automated>
      - test -f /home/bamn/Sheppard/tests/validation/v01_budget_metrics.py
      - pytest /home/bamn/Sheppard/tests/validation/v01_budget_metrics.py -q 2>&1 | grep -q "PASSED\|passed"
      - test -f /home/bamn/Sheppard/.planning/phases/07-validation/VERIFICATION-V01.md
    </automated>
  </verify>
</task>

<task type="auto">
  <name>07-V02: Verify condensation trigger correctness</name>
  <read_first>
    - .planning/gauntlet_phases/phase07_validation/PHASE-07-VALIDATION-CONTRACT.md
    - src/research/acquisition/budget.py (thresholds, callback enqueue)
    - src/research/condensation/pipeline.py (run method)
  </read_first>
  <action>
Implement and run test for V-02:

1. Create test: `tests/validation/v02_condensation_trigger.py`
   - Configure: ceiling=1GB, HIGH=85%, CRITICAL=95%
   - Mock or use real condensation that logs when started
   - Ingest sources gradually; instrument: track when `condensation_runs_total` increments
   - Continue until raw_bytes ≥ 90%
2. Record:
   - raw_bytes at which first condensation triggered
   - Count of condensation runs before 90%
   - Any runs before 85% (should be 0)
3. Write VERIFICATION-V02.md with:
   - Threshold config
   - Trigger point raw_bytes and %
   - Premature triggers? (Y/N)
   - Multiple runs? (count)
   - Verdict: PASS if triggered once between 85–90% with no premature

Success: Test passes and documented.
  </action>
  <verify>
    <automated>
      - test -f /home/bamn/Sheppard/tests/validation/v02_condensation_trigger.py
      - pytest /home/bamn/Sheppard/tests/validation/v02_condensation_trigger.py -q 2>&1 | grep -q "PASSED\|passed"
      - test -f /home/bamn/Sheppard/.planning/phases/07-validation/VERIFICATION-V02.md
    </automated>
  </verify>
</task>

<task type="auto">
  <name>07-V04: Verify cross-component consistency</name>
  <read_first>
    - .planning/gauntlet_phases/phase07_validation/PHASE-07-VALIDATION-CONTRACT.md
    - src/memory/adapters/postgres.py (or relevant adapter)
    - src/research/archivist/index.py (retrieval)
  </read_first>
  <action>
Implement and run test for V-04:

1. Create test: `tests/validation/v04_consistency.py`
   - Ingest a batch of sources (N=100)
   - Wait 5s for indexing
   - For each source in random sample (100):
     * Fetch from DB: `SELECT * FROM corpus.sources WHERE id=?`
     * Fetch from index: `index.retrieve(source_id)`
     * Compare all fields (allow timestamp ±1s)
   - Repeat for atoms (sample 100 atoms)
2. Compute mismatch count
3. Write VERIFICATION-V04.md with:
   - Total items checked
   - Mismatches found
   - Verdict: PASS if mismatch count = 0

Success: Test passes and documented.
  </action>
  <verify>
    <automated>
      - test -f /home/bamn/Sheppard/tests/validation/v04_consistency.py
      - pytest /home/bamn/Sheppard/tests/validation/v04_consistency.py -q 2>&1 | grep -q "PASSED\|passed"
      - test -f /home/bamn/Sheppard/.planning/phases/07-validation/VERIFICATION-V04.md
    </automated>
  </verify>
</task>

<task type="auto">
  <name>07-V09: Verify mission lifecycle transitions</name>
  <read_first>
    - .planning/gauntlet_phases/phase07_validation/PHASE-07-VALIDATION-CONTRACT.md
    - src/research/orchestrator.py (state management)
  </read_first>
  <action>
Implement and run test for V-09:

1. Create test: `tests/validation/v09_lifecycle.py`
   - Start mission; capture initial status from DB
   - Let run to completion; capture final status
   - Query DB for status change events (if audit table exists) or poll status at intervals to trace transitions
   - Verify sequence: created → active → terminal (complete/stopped/failed)
   - Check no skipped states (e.g., created → complete without active)
   - Test restart: after terminal, verify state persists
2. Write VERIFICATION-V09.md with:
   - Observed state sequence
   - Any illegal jumps detected?
   - Durability after restart? (Y/N)
   - Verdict: PASS if sequence valid and durable

Success: Test passes and documented.
  </action>
  <verify>
    <automated>
      - test -f /home/bamn/Sheppard/tests/validation/v09_lifecycle.py
      - pytest /home/bamn/Sheppard/tests/validation/v09_lifecycle.py -q 2>&1 | grep -q "PASSED\|passed"
      - test -f /home/bamn/Sheppard/.planning/phases/07-validation/VERIFICATION-V09.md
    </automated>
  </verify>
</task>

<task type="auto">
  <name>07-V10: Verify backpressure prevents queue overflow</name>
  <read_first>
    - .planning/gauntlet_phases/phase07_validation/PHASE-07-VALIDATION-CONTRACT.md
    - src/memory/adapters/redis.py (enqueue_job)
    - src/research/acquisition/crawler.py (backpressure_triggered handling)
  </read_first>
  <action>
Implement and run test for V-10:

1. Create test: `tests/validation/v10_backpressure.py`
   - Set `MAX_QUEUE_DEPTH = 100` (via config or monkeypatch)
   - Pre-fill queue with 100 dummy jobs (direct Redis lpush)
   - Attempt to enqueue additional URL via crawler path
   - Assert enqueue returns False
   - Verify queue depth ≤ 101 after attempt
   - Drain queue (rpop until empty)
   - Verify frontier resumes enqueue when depth < 90 (check a subsequent enqueue succeeds)
2. Write VERIFICATION-V10.md with:
   - Configured MAX_QUEUE_DEPTH
   - Max observed depth during test
   - Frontier paused when depth exceeded? (Y/N)
   - Frontier resumed after drain? (Y/N)
   - Verdict: PASS if depth ≤ 101 and pause/resume both observed

Success: Test passes and documented.
  </action>
  <verify>
    <automated>
      - test -f /home/bamn/Sheppard/tests/validation/v10_backpressure.py
      - pytest /home/bamn/Sheppard/tests/validation/v10_backpressure.py -q 2>&1 | grep -q "PASSED\|passed"
      - test -f /home/bamn/Sheppard/.planning/phases/07-validation/VERIFICATION-V10.md
    </automated>
  </verify>
</task>

</tasks>

<done>
All 5 core orchestration invariants verified. Each invariant has a dedicated test that exercises the required behavior, and all tests passed. The orchestration contract is confirmed correct. Deferred validation items will be addressed in future phases.

Phase 07 deliverable: PHASE-07-VERIFICATION.md aggregating the 5 VERIFICATION-Vxx reports and declaring overall PASS.
</done>
