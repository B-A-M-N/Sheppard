# Phase 12-02: Retrieval Latency Optimization — Context

**Gathered:** 2026-03-30
**Status:** Ready for planning
**Source:** Inline assumptions review + user refinements

<domain>
## Phase Boundary

Optimize total retrieval latency from ~1200ms to ≤200–300ms by parallelizing section retrieval in EvidenceAssembler. The bottleneck is N sequential ChromaDB queries (one per section), not the query itself. Fix is orchestration-level concurrency.

</domain>

<decisions>
## Implementation Decisions

### Target Definition
- **PERF-01 target = TOTAL retrieval across all sections**, not per-query
- Current: ~1200ms total (8 sections × ~150ms/query)
- First goal: ≤200–300ms total
- Realistic via concurrency (parallelizing 8 queries)

### Where Optimization Lives
- **Primary: `EvidenceAssembler`** — controls section loop, concurrency, ordering
- **Secondary: `V3Retriever`** — only if needed after concurrency wins are measured
- Keep V3Retriever simple and deterministic; do NOT move logic there

### Concurrency Pattern (MANDATORY)
Must use index-preserving gather, NOT naive gather:
```python
tasks = [
    (section.index, asyncio.create_task(retrieve_for_section(section)))
    for section in sections
]
results = [(index, await task) for index, task in tasks]
results.sort(key=lambda x: x[0])  # restore section order
```

### Global Re-sort Before Citation Assignment (NON-NEGOTIABLE)
After merging all atoms from concurrent results:
```python
all_atoms = sorted(all_atoms, key=lambda x: x.global_id)
```
Citation keys ([A001], [A002]...) must be stable and reproducible.

### `atom_ids_used` Ordering
Must remain deterministic post-concurrency. Current per-section sort by `global_id` is correct; must be preserved.

### Prefetch Cache — DEFERRED
Good idea but do it only AFTER concurrency change is confirmed to hit target.
- Avoids over-complexity
- Avoids memory risk
- Concurrency alone likely sufficient

### Corpus Tiers for Benchmarking (MANDATORY before 12-03)
Three tiers required:
- **SMALL**: ~20 atoms (current synthetic baseline)
- **MEDIUM**: ~200–500 atoms
- **LARGE**: ~1000+ atoms
Current 20-atom baseline is insufficient to expose scaling behavior.

### Dead Code
- `src/retrieval/retriever.py` = likely dead/legacy
- Confirm via import grep, mark deprecated, do NOT optimize

### Instrumentation Expansion
Add to benchmark output:
```json
{
  "retrieval_queries": 8,
  "concurrency_level": 8,
  "retrieval_parallelism_efficiency": "<actual_ms vs sequential_estimate>"
}
```
If possible, also separate: `embedding_ms` vs `query_ms` (embedding usually dominates).

### Execution Order
1. Add per-section timing instrumentation
2. Implement concurrent section retrieval (assembler layer)
3. Re-run benchmark (small + medium corpus)
4. Validate determinism + citation stability
5. Only then consider prefetch cache
6. Evaluate thread pool / embedding bottleneck

### Claude's Discretion
- Thread pool executor size tuning (if parallelism reveals thread contention)
- Whether to add an explicit asyncio.Semaphore to bound concurrency
- How to seed MEDIUM/LARGE corpus (synthetic injection extension of benchmark script)
- Whether to consolidate or just deprecate `src/retrieval/retriever.py`

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Retrieval Stack (Active Path)
- `src/research/reasoning/v3_retriever.py` — V3Retriever: the active retriever used by assembler
- `src/research/reasoning/assembler.py` — EvidenceAssembler: PRIMARY optimization target
- `src/research/reasoning/synthesis_service.py` — SynthesisService: calls assembler per section
- `src/memory/adapters/chroma.py` — ChromaSemanticStoreImpl: async Chroma wrapper (uses asyncio.to_thread)

### Dead Code
- `src/retrieval/retriever.py` — LIKELY DEAD; do not optimize, only confirm and deprecate

### Benchmarking
- `scripts/benchmark_suite.py` — existing benchmark to extend for before/after comparison
- `BASELINE_METRICS.md` — Phase 12-01 baseline (retrieval_ms mean=1209ms, P95=1379ms, 8 sections, 20 atoms)

### Truth Contract (DO NOT WEAKEN)
- `src/research/reasoning/retriever.py` — RetrievalQuery, RoleBasedContext, RetrievedItem models
- `src/research/reasoning/synthesis_service.py` — validator and citation enforcement

### Project Guidelines
- `.planning/REQUIREMENTS.md` — PERF-01 requirement definition

</canonical_refs>

<specifics>
## Specific Ideas

- Section retrieval concurrency: `asyncio.gather` with index preservation
- Re-sort: `sorted(all_atoms, key=lambda x: x.global_id)` before citation assignment
- Benchmark parallelism efficiency metric: `sequential_estimate_ms / actual_parallel_ms`
- Seed MEDIUM corpus: extend benchmark_suite.py's atom injection to 200-500 atoms
- Timing granularity: per-section timing (not just total) to expose which sections are outliers

</specifics>

<deferred>
## Deferred Ideas

- Prefetch cache (fetch all mission atoms once, filter in-memory per section) — deferred until concurrency confirmed insufficient
- External Redis cache layer — out of scope for this phase
- ChromaDB index configuration changes — out of scope
- Re-ranking / scoring changes — Phase 12-07
- Persistent metrics backend (Prometheus/Grafana) — Phase 12-04

</deferred>

---

*Phase: 12-02-retrieval-latency-optimization*
*Context gathered: 2026-03-30 via assumptions review*
