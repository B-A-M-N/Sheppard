---
phase: 12-02
plan: 01
subsystem: research
tags: [python, asyncio, timing, instrumentation, retrieval, testing]

# Dependency graph
requires:
  - phase: 12-01
    provides: baseline benchmark suite and metrics establishing performance targets
provides:
  - RETRIEVAL_CONCURRENCY_LIMIT constant (=8) in assembler.py for Wave 2 concurrency
  - Per-section retrieval timing instrumentation in build_evidence_packet using time.perf_counter
  - DEPRECATED marker on src/retrieval/retriever.py dead code module
  - test_concurrent_assembly.py scaffolding file with 5 test stubs for Wave 2 implementation
affects:
  - 12-02-02 (implements assemble_all_sections using RETRIEVAL_CONCURRENCY_LIMIT)
  - 12-02-03 (validation plan depends on test stubs becoming real tests)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Per-section timing: wrap retriever.retrieve() with time.perf_counter() start/stop, log at DEBUG"
    - "Concurrency limit as module-level constant: RETRIEVAL_CONCURRENCY_LIMIT = 8 in assembler.py"
    - "Dead code deprecation: module-level DEPRECATED docstring with pointer to active replacement"
    - "Test scaffolding: pytest.skip() stubs with descriptive await messages for Wave 2"

key-files:
  created:
    - tests/research/reasoning/test_concurrent_assembly.py
  modified:
    - src/research/reasoning/assembler.py
    - src/retrieval/retriever.py

key-decisions:
  - "RETRIEVAL_CONCURRENCY_LIMIT = 8 set as the default concurrency ceiling for asyncio.Semaphore in Wave 2"
  - "Timing uses time.perf_counter() (monotonic, high-resolution) not datetime.utcnow()"
  - "Retrieved item count logged alongside ms to aid diagnostics (len(retrieved_context.all_items))"
  - "src/retrieval/retriever.py retained with DEPRECATED marker rather than deleted -- tests/retrieval/test_retriever.py imports from it"

patterns-established:
  - "Instrumentation pattern: _t0 = time.perf_counter() before async call, _ms = (perf_counter() - _t0) * 1000 after"
  - "Dead code annotation: module-level DEPRECATED docstring with pointers to active replacements"

requirements-completed: [PERF-01]

# Metrics
duration: 10min
completed: 2026-03-30
---

# Phase 12-02 Plan 01: Retrieval Instrumentation & Test Scaffolding Summary

**Per-section retrieval timing added to EvidenceAssembler, RETRIEVAL_CONCURRENCY_LIMIT=8 constant defined, dead src/retrieval/retriever.py deprecated, and concurrent assembly test file scaffolded for Wave 2**

## Performance

- **Duration:** ~10 min
- **Started:** 2026-03-30T00:00:00Z
- **Completed:** 2026-03-30T00:10:00Z
- **Tasks:** 2
- **Files modified:** 3 (assembler.py modified, retriever.py modified, test file created)

## Accomplishments
- Added `import asyncio`, `import time`, and `RETRIEVAL_CONCURRENCY_LIMIT = 8` to assembler.py with zero behavior change
- Wrapped `retriever.retrieve()` call in `build_evidence_packet` with `time.perf_counter()` timing that logs section title, duration in ms, and item count at DEBUG level
- Added DEPRECATED module docstring to `src/retrieval/retriever.py` directing readers to `src/research/reasoning/v3_retriever.py`
- Created `tests/research/reasoning/test_concurrent_assembly.py` with 5 test methods: 4 skipping stubs for Wave 2 + `test_concurrency_limit_constant_defined` passing immediately
- All 95 existing tests pass unchanged (9 reasoning + 86 others)

## Task Commits

Each task was committed atomically:

1. **Task 1: Per-section timing and RETRIEVAL_CONCURRENCY_LIMIT** - `bb3e6f2` (feat)
2. **Task 2: Deprecate dead retriever and create test scaffolding** - `f8d1b33` (feat)

**Plan metadata:** TBD (docs: complete plan)

## Files Created/Modified
- `src/research/reasoning/assembler.py` - Added asyncio/time imports, RETRIEVAL_CONCURRENCY_LIMIT=8 constant, per-section timing instrumentation around retriever.retrieve()
- `src/retrieval/retriever.py` - Added DEPRECATED module docstring at top of file
- `tests/research/reasoning/test_concurrent_assembly.py` - Created with TestConcurrentAssembly and TestTimingInstrumentation classes, 5 test stubs

## Decisions Made
- RETRIEVAL_CONCURRENCY_LIMIT set to 8 as the Wave 2 asyncio.Semaphore ceiling (matches plan spec, tunable)
- Timing uses `time.perf_counter()` (monotonic, high-resolution) for sub-millisecond accuracy
- `src/retrieval/retriever.py` retained with DEPRECATED marker (not deleted) because `tests/retrieval/test_retriever.py` imports from it
- `test_concurrent_produces_identical_atom_ids_as_sequential` stub includes full docstring explaining the global re-sort invariant interpretation per RESEARCH.md Open Question #1

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None - all changes were straightforward additive-only modifications with no behavior changes.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Plan 02 (Wave 2) can now use `RETRIEVAL_CONCURRENCY_LIMIT` as the semaphore limit in `assemble_all_sections`
- Test scaffolding at `tests/research/reasoning/test_concurrent_assembly.py` is ready for Plan 02 to fill in implementations
- The 4 skipped stubs will become real tests once `assemble_all_sections` is implemented
- Timing logs will be visible in production at DEBUG level immediately

---
*Phase: 12-02*
*Completed: 2026-03-30*
