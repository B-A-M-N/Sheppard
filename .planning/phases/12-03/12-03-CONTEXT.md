# Phase 12-03: Synthesis throughput improvements — Context

**Gathered:** 2026-03-31  
**Status:** Ready for planning  
**Source:** Direct user decisions (authoritative input)

---

<domain>

## Phase Boundary

**Goal:** Optimize synthesis throughput by parallelizing independent section generation while preserving all truth contract invariants (Phase 10/11).

**Objective:** Achieve ≥20% improvement in `validated_sections_per_minute` through safe async worker pool concurrency at the section level.

**Requirements Addressed:** PERF-02

**Out of Scope:**
- Retrieval (Phase 12-02 complete)
- Ranking (Phase 12-07)
- Prompt semantics (Phase 11 locked)
- Database schema changes

---

</domain>

<decisions>

## Implementation Decisions (LOCKED)

### Bottleneck & Strategy

- **Primary bottleneck:** Sequential LLM section generation loop
- **Secondary:** Validator cost per section (unchanged, just parallelized)
- **Strategy:** Replace `for section in sections: generate → validate → store` with async worker pool
- **Mechanism:** Concurrent independent section processing, NOT LLM batch API (no multi-prompt single-call batching assumed)

### Parallelism Boundaries

- **Safe parallelism:** Section-level ONLY (each section is isolated unit of work)
- **Forbidden:**
  - Parallelizing inside a single section (LLM call stays single prompt per section)
  - Sharing mutable state across sections
  - Modifying citation assignment logic to be concurrent
  - Changing validator semantics
  - Skipping validator for performance

### Safety Rules (Non-negotiable)

- Each section: generate → validate → store (same pipeline, just concurrent)
- Validation runs per-section independently (no shared validator state assumed)
- Final report assembly is **deterministic + strictly ordered** by section index
- Citation keys assigned **AFTER** all sections complete (no concurrent numbering)
- `atom_ids_used` must remain correct; no data loss or duplication
- Truth contract invariants preserved exactly (Phase 10/11)

### Success Criteria (PERF-02)

- ≥20% increase in `sections_per_minute` measured from start of synthesis batch to final validated+stored sections
- No change in:
  - Citation correctness (same atoms cited)
  - `atom_ids_used` integrity
  - Determinism (same seed/temperature → same outputs)
  - Validator rejection rates/behavior

### Forbidden Optimizations

- **DO NOT:** Skip validator
- **DO NOT:** Batch prompts into one LLM call (unless it's transparent to pipeline)
- **DO NOT:** Modify citation logic or numbering scheme
- **DO NOT:** Relax grounding rules or truth contract checks
- **DO NOT:** Introduce shared mutable state across section tasks

### Execution Model

```python
# Pseudocode for target implementation
tasks = [
    (section.index, asyncio.create_task(process_section(section)))
    for section in sections
]
results = [
    (idx, await task)  # gathers all
    for idx, task in tasks
]
results.sort(key=lambda x: x[0])  # restore deterministic order
# THEN: assign citation keys based on sorted results
```

- Out-of-order execution: ✅ allowed
- Out-of-order final output: ❌ forbidden (must restore index order)

### Resource Constraints

- Worker pool size: bounded (configurable, default 4–8 concurrent tasks)
- Acceptable: 2–4× memory increase due to concurrent LLM responses buffering
- Unacceptable: unbounded concurrency, OOM risk, runaway async tasks

---

### Claude's Discretion

- Exact worker pool size tuning (likely 4–8 based on CPU/IO profile)
- Whether to use `asyncio.Semaphore` pool or `concurrent.futures.ThreadPoolExecutor`
- How to handle individual section failures (retry policy, partial completion semantics)
- Baseline measurement methodology details (benchmark harness reuse from 12-01)

---

</decisions>

<canonical_refs>

## Canonical References

**Downstream agents MUST read these before planning or implementing:**

### Phase scope & requirements
- `.planning/REQUIREMENTS.md` — Milestone v1.1 requirements, PERF-02 definition
- `.planning/ROADMAP.md` — Phase 12-03 entry, overall Phase 12 context

### Prior work (must not break)
- `.planning/phases/12-01/BASELINE_METRICS.md` — Benchmark methodology, baseline measurement approach
- `.planning/phases/10-11/*` (Truth Contract phases) — Invariants that must be preserved
  - Search for `SynthesisService`, `validator`, `atom_ids_used` definitions
- `.planning/phases/12-02/12-02-PLAN.md` and `12-02-SUMMARY.md` — Retrieval optimizations (to ensure synthesis can leverage ready data)

### Source code (synthesis pipeline)
- `src/core/chat.py` or `src/core/synthesis.py` (likely locations for SynthesisService)
- `src/research/models.py` (atom, citation models)
- `src/config/logging.py` (metrics/tracing if present)

**Action:** The planner should search the codebase to locate the actual synthesis implementation files and include them in `read_first` for tasks.

---

</canonical_refs>

<specifics>

## Specific Ideas

### Existing harness reuse
- Adapt `scripts/benchmark_suite.py` from Phase 12-01 to measure synthesis throughput
- Instrument `SynthesisService` to emit timing metrics: `synthesis_llm_ms`, `validator_ms`, `sections_count`, `total_synthesis_s`
- Compute `sections_per_minute = sections_count / (total_synthesis_s / 60)`

### Expected architecture changes
- Introduce async worker pool (bounded concurrency) around section loop
- Keep per-section pipeline intact (LLM → validate → store)
- Add `asyncio.gather()` or thread pool for concurrent section workers
- Ensure deterministic ordering: preserve original section order in final assembly
- Defer citation key assignment until after all sections complete

### Validation
- Reuse existing guardrail tests (Phase 10/11 validation must still pass)
- Add throughput measurement to benchmark suite
- Verify `atom_ids_used` correctness equals baseline
- Check validator rejection rate unchanged

---

</specifics>

<deferred>

## Deferred Ideas

None — PRD covers phase scope completely.

---

</deferred>

---

*Phase: 12-03 — Synthesis throughput improvements*  
*Context gathered: 2026-03-31 via direct user decisions*
