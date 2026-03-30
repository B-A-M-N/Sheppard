# Phase 12-01: Benchmark Suite & Baseline Metrics

**Milestone:** v1.1 — Performance & Observability
**Status:** Planning
**Created:** 2026-03-30

---

## Overview

Establish a reproducible benchmark harness to measure performance baselines across retrieval, synthesis, and full mission lifecycle *before any optimization work begins*. This plan ensures that all subsequent performance work (12-02 through 12-07) is data-driven and respects truth contract invariants.

**Key Principle:** *Lock correctness → measure → optimize*.

---

## Goals

1. **Baseline latency metrics** for retrieval, synthesis LLM, validator, persistence, and end-to-end mission execution.
2. **Throughput measurement** (sections/min, atoms processed/sec).
3. **Full-path coverage**: exercise both NO_DISCOVERY and HIGH-EVIDENCE synthesis paths.
4. **Determinism preservation**: benchmarks run under identical seed/temperature constraints.
5. **Traceability**: all measurements tagged with `mission_id` for post-hoc analysis.
6. **Guardrail enforcement**: every benchmark run asserts that the v1.0 test suite passes unchanged.

---

## Acceptance Criteria

- [ ] Benchmark script `scripts/benchmark_suite.py` exists and is executable.
- [ ] Script generates `benchmark_results.json` with structured metrics.
- [ ] Results include retrieval_ms, synthesis_llm_ms, validator_ms, persistence_ms, and e2e_ms (P50/P95/P99).
- [ ] HIGH_EVIDENCE path records evidence shape metrics: atom_count, chunk_count, sections_count, avg_atoms_per_section (all with P50/P95/P99).
- [ ] Results include both NO_DISCOVERY and HIGH-EVIDENCE scenarios.
- [ ] Each run produces a unique `mission_id` and logs timing per stage.
- [ ] Script runs `pytest` (or equivalent) on v1.0 test suite and confirms 100% pass before and after benchmarking.
- [ ] Baseline numbers documented in `BASELINE_METRICS.md` with statistical aggregates (mean, median, P95, P99).
- [ ] Contradiction path is exercised where applicable and labeled in results.
- [ ] No modifications to truth contract code during 12-01; all v1.0 files unchanged.
- [ ] CI integration: benchmark can be run non-destructively in a test environment.

---

## Scope

### In Scope

- Creation of `scripts/benchmark_suite.py` with:
  - Mission creation (two scenarios: NO_DISCOVERY, HIGH_EVIDENCE with real atoms).
  - Full pipeline execution: frontier → acquisition → condensation → retrieval → synthesis → validation → persistence.
  - Timing instrumentation for each major stage (using `time.perf_counter` or similar, with context managers).
	  - Output as JSON with structure: `{mission_id, scenario, stage_timings:{frontier_acquisition, condensation, retrieval, synthesis_llm, validator, persistence}, total_ms, atom_count, chunk_count, sections_count, avg_atoms_per_section, validator_passed, call_counts}`.
- One-off baseline run on a representative corpus (use existing test corpus or small controlled dataset).
- Validation that v1.0 tests pass before and after benchmarks (no regressions).
- Documentation of baseline numbers and methodology in `BASELINE_METRICS.md`.

### Out of Scope

- Any code changes to retrieval or synthesis for performance purposes (these come in later phases).
- Modifying validator logic or truth contract checks.
- Adding caching or async optimizations (we're measuring the baseline, not changing behavior).
- Building a persistent metrics backend (Prometheus/Graphana) – that's Phase 12-04.

---

## Tasks

### 1. Design benchmark harness structure

- Determine how to invoke the full pipeline programmatically (likely via `main.py` or service classes).
- Identify entrypoints: `MissionOrchestrator` or similar.
- Decide on warm-up runs (e.g., 1–2 warm-up missions to stabilize caches).
- Choose number of iterations (e.g., 10 runs per scenario) to get stable statistics.

**Deliverable:** `scripts/benchmark_suite.py` with command-line args:
- `--scenario {no_discovery,high_evidence}`
- `--iterations N` (default 10)
- `--output benchmark_results.json`

### 2. Instrumentation

Add timing context managers if not already present. Each stage:
- Frontier & acquisition
- Condensation
- Retrieval (V3Retriever)
- Synthesis (Archivist + synthesis service)
- Validation (per-section validator)
- Persistence (DB writes)

Each timing must start/stop with clear boundaries and include `mission_id` in logs.

**Deliverable:** Timing captured and stored in Python dict per run.

### 3. Scenario: NO_DISCOVERY

- Create a mission with a topic that yields zero evidence.
- Ensure pipeline returns the correct NO_DISCOVERY handling (short path; synthesis skips or returns placeholder).
- Record timings; note that retrieval and synthesis may be faster due to early exit.

**Deliverable:** 10 runs, aggregated results.

### 4. Scenario: HIGH_EVIDENCE

- Create a mission with a topic that retrieves multiple atoms and triggers full synthesis.
- Must result in at least one atom per section on average, as per E2E definition.
- This exercises the full path: retrieval → synthesis → validator → persistence.

**Deliverable:** 10 runs, aggregated results, including `atom_ids_used` validation (spot-check that citations match stored atoms).

### 5. Structured output

- `benchmark_results.json` format:

```json
{
  "run_id": "bench_20260330_120000",
  "timestamp": "2026-03-30T12:00:00Z",
  "scenario": "high_evidence",
  "mission_ids": [...],
  "aggregate": {
    "retrieval_ms": {"mean": 125, "median": 120, "p95": 150, "p99": 180},
    "synthesis_llm_ms": {"mean": 380, "median": 370, "p95": 420, "p99": 450},
    "validator_ms": {"mean": 70, "median": 65, "p95": 90, "p99": 110},
    "persistence_ms": {"mean": 10, "median": 9, "p95": 15, "p99": 20},
    "e2e_ms": {"mean": 650, "median": 630, "p95": 700, "p99": 750}
  },
  "evidence_shape": {
    "atom_count": {"mean": 42, "median": 40, "p95": 50},
    "chunk_count": {"mean": 120, ...},
    "sections_count": {"mean": 5, ...},
    "avg_atoms_per_section": {"mean": 8, ...}
  },
  "per_run": [
    {
      "mission_id": "m_abc123",
      "stage_timings": {
        "frontier_acquisition": 45,
        "condensation": 12,
        "retrieval": 125,
        "synthesis_llm": 380,
        "validator": 70,
        "persistence": 10
      },
      "total_ms": 645,
      "atom_count": 41,
      "chunk_count": 115,
      "sections_count": 5,
      "avg_atoms_per_section": 8.2,
      "validator_passed": true,
      "call_counts": {
        "validator_invocations": 5,
        "retrieval_queries": 1
      }
    }
  ]
}
```

### 6. Guardrail verification

- Pre-check: run `pytest tests/` and ensure all tests pass (v1.0 suite).
- Post-check: after benchmarks, run `pytest` again and confirm no new failures.
- If any test fails, benchmarks invalid; abort and report.

**Deliverable:** Script exits non-zero if guardrail fails.

### 7. Document baseline

Write `BASELINE_METRICS.md` summarizing:

- Hardware/environment: CPU, RAM, DB configuration, cache state.
- Corpus used (number of chunks/atoms, sources).
- Statistical summary (mean/median/P95/P99) for each metric.
- Observations: which stage dominates latency? Is retrieval or synthesis the bottleneck?
- Representative `benchmark_results.json` attached or committed.

---

## Verification

After the plan is executed, verify:

1. `scripts/benchmark_suite.py` exists and runs without error.
2. `benchmark_results.json` produced with correct fields.
3. At least 10 iterations per scenario completed.
4. `BASELINE_METRICS.md` present and accurate.
5. `git diff` shows no changes to any v1.0 truth contract files (`src/research/archivist/`, `src/retrieval/validator.py`, `src/research/reasoning/`, etc.).
6. `pytest` passes before and after; coverage unchanged.

---

## Dependencies

- v1.0 codebase fully functional and tested.
- Database with schema including `exhausted_modes_json` (from Phase 06 migration).
- Access to mission orchestration service (the same entrypoint used for E2E tests).
- Existing tests for retrieval and synthesis (to verify guardrails).

**No external libraries** should be added beyond standard Python timing modules.

---

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Benchmark runs are flaky due to async variance | Inconsistent numbers | Use warm-up runs; run many iterations (N≥10) and report statistics |
| HIGH_EVIDENCE scenario may not always produce enough atoms | Invalid baseline | Pre-seed corpus with known atoms; ensure retrieval limit yields results |
| Running benchmarks could trigger validator failures if code changed | Guardrail violation | Strictly read-only benchmarking; no code edits during 12-01 |
| Timing instrumentation may affect performance | Distorted numbers | Use lightweight timers; keep logging minimal during runs |
| Database state persists between runs | Cross-contamination | Ensure each mission uses a fresh transaction or cleanup; use `mission_id` isolation |

---

## Success Criteria

- Baseline numbers captured for all required stages (retrieval, synthesis_llm, validator, persistence, e2e) with P50/P95/P99.
- Evidence shape metrics captured: atom_count, chunk_count, avg_atoms_per_section, sections_count.
- Both NO_DISCOVERY and HIGH_EVIDENCE paths covered.
- v1.0 tests pass before and after (no regressions).
- Results reproducible on a second run (within 10% variance).
- Team has clear understanding of current performance bottlenecks and scaling behavior.

---

## Notes

- This phase **must not** modify any production code. It is purely observational.
- The benchmark script can import internal modules but should avoid altering global state.
- If the v1.0 test suite has flakiness, fix it *before* proceeding with 12-01 (that would be a separate issue).
- Future phases (12-02 through 12-07) will compare their metrics against this baseline.

---

## Related Requirements

- PERF-01: Baseline establishment (this phase enables all subsequent PERF requirements).
- OBS-01: Structured metrics (this phase creates the first structured metrics output).
- E2E-01: Full-path integration (the HIGH_EVIDENCE scenario rehearses the E2E test for later).
- Guardrails: No weakening of truth contract invariants.

---

**Next:** After approval, execute this plan with `/gsd:execute-phase 12-01`.
