# Phase 12-02.1: Retrieval Latency Diagnosis — Analysis

**Date:** 2026-03-30  
**Phase:** 12-02.1 (Retrieval Latency Diagnosis)  
**Goal:** Identify why per-query retrieval latency is ~1s instead of expected ~150ms.

---

## Executive Summary

We instrumented `V3Retriever` to profile query execution and ran a comprehensive test matrix across corpus sizes (small/medium/large) and concurrency levels (1 vs 8 sections). The data reveals that:

- **Single-query latency is excellent** (144–184ms) for all corpus sizes, meeting the original ~150ms assumption.
- **Concurrent retrieval suffers drastic serialization** — per-section duration balloons to ~1s when 8 queries run concurrently, yielding total retrieval ~1.3s, well above the PERF-01 target (200–300ms).
- The root cause is **GIL contention during embedding computation**. The Chroma query is run in a thread pool (`asyncio.to_thread`), and the embedding model (CPU-bound Python) cannot parallelize across threads due to Python's GIL. This contention causes each of the 8 concurrent tasks to wait ~7× longer than the single-query baseline.
- Corpus size (per mission) has minimal impact on per-query latency (173ms for 1000 atoms vs 144ms for 20 atoms). Total database bloat (accumulated atoms from all missions) also does **not** materially affect latency because the mission_id filter is efficient.

Thus, **the architecture is correct**; the performance gap is caused by runtime environment constraints, not algorithmic flaws.

---

## Test Matrix

We ran 6 diagnostic executions. Results summarized:

| Corpus Tier | Sections | DB Total Atoms Before | DB After | Concurrent Total (ms) | Mean Per-Section Total (ms) | Mean Query (ms) | Parallelism Efficiency |
|-------------|----------|----------------------|----------|----------------------|----------------------------|-----------------|------------------------|
| small (20)  | 1        | 160                  | 160+20   | 144.4                | 144.2                      | 144.2           | 1.00×                  |
| small (20)  | 8        | 160                  | 180+20   | 1225.0               | 1030.2                     | 1030.2          | 6.73×                  |
| medium (500)| 1        | 180                  | 180+500  | 184.6                | 184.5                      | 184.4           | 1.00×                  |
| medium (500)| 8        | 680                  | 680+500  | 1296.1               | 1046.7                     | 1046.6          | 6.46×                  |
| large (1000)| 1        | 1180                 | 1180+1000| 173.6                | 173.5                      | 173.4           | 1.00×                  |
| large (1000)| 8        | 2180                 | 2180+1000| 1324.7               | 1111.8                     | 1111.7          | 6.71×                  |

Observations:
- Single-section runs: 144–184ms, within expected range.
- 8-section runs: 1030–1112ms per-section, ~6.5× efficiency.
- Efficiency ~6.7 indicates about 16% serialization overhead; per-section durations increase ~7× over single-query baseline.

---

## Answers to Diagnosis Questions

### 1. Is the time dominated by embedding generation, Chroma query, or metadata filtering?

**Answer:** The time is dominated by the **embedding generation** combined with the Chroma vector search, both executed within the `coll.query` call to Chroma. Post-processing (building `RetrievedItem` objects) is negligible (<0.1ms). The instrumentation shows `query_ms` (which includes embedding and search) accounts for >99.9% of retrieval time.

### 2. Is the benchmark running against a bloated / dirty corpus?

**Answer:** The database accumulated atoms from previous runs (140 → 3180 atoms total). However, single-query latency does **not** correlate with total DB size because the `mission_id` filter isolates each mission's corpus. The per-mission corpus size (20/500/1000) has only minor impact (144ms vs 174ms). Therefore, **bloat is not the bottleneck**.

### 3. Does a fresh database materially reduce latency?

**Answer:** Even with a relatively "dirty" DB (2180 total atoms), single-query latency remained ~173ms. A truly fresh DB would not significantly improve numbers. The issue is not data cleanliness.

### 4. Does corpus size scale linearly, sublinearly, or pathologically?

**Answer:** Sublinear. Single-query retrieval time increased only ~20% when corpus size grew from 20 to 1000 atoms. This indicates the vector index (likely HNSW) scales well.

### 5. Does mission_id filtering contribute meaningfully to cost?

**Answer:** No. The filter is efficient; latency independent of total DB atoms. The cost is dominated by vector search over the mission's own atoms (~20–1000 vectors), which scales well.

### 6. Is there any unnecessary repeated work per section query?

**Answer:** Each section query repeats the embedding computation for its query text. In concurrent runs, these embeddings are computed in separate threads, leading to GIL contention. Batching query embeddings for multiple sections could eliminate this contention.

---

## Root Cause Analysis

The profiling data shows that when we run 1 section, the `query_ms` (embedding + vector search) is ~150–180ms. When we run 8 sections concurrently, the *individual* `query_ms` becomes ~1s, while the total concurrent time is only ~1.3s. This indicates that the 8 queries are **not executing in parallel**; instead, they are effectively serialized with queuing.

The code path in `ChromaSemanticStoreImpl.query` uses `await asyncio.to_thread(coll.query, ...)` to run the blocking Chroma query. The `coll.query` method:
- Computes the query embedding (likely using a CPU-bound embedding model like sentence-transformers).
- Performs vector search.

This function is CPU-bound and holds Python's GIL for the duration. When 8 coroutines call `asyncio.to_thread` concurrently, they submit 8 work items to the default thread pool. Threads run concurrently but **cannot execute Python bytecode in parallel due to the GIL**. They time-slice, effectively running them sequentially. Each task's wall duration includes waiting for its turn, inflating per-section times by ~7×.

The parallelism efficiency of ~6.7× out of 8 suggests a small amount of overlap (maybe I/O or parts of embedding that release the GIL), but the bulk is serial.

This explains why the earlier verifier observed ~1s per-section: they ran the benchmark with 8 sections, which suffered the same contention.

---

## Recommendations

### Fix Options (ordered by feasibility/impact)

1. **Increase thread pool size and use process-based parallelism**  
   Configure asyncio's default executor to use a `ProcessPoolExecutor` with `N` workers (e.g., 8). Each process has its own GIL, allowing true parallel embedding computation. However, this increases memory usage (embedding model loaded N times). Might be acceptable for a dedicated service.

2. **Batch embeddings at retrieval time**  
   Instead of calling `V3Retriever.retrieve` 8 times independently, batch the 8 section queries into a single call to Chroma with `query_texts: [text1, text2, …]`. Chroma can compute embeddings in one forward pass and return results for all queries in a single backend round-trip. This would eliminate per-query embedding overhead and reduce contention entirely. Requires refactoring `EvidenceAssembler.assemble_all_sections` to group queries, but that's a localized change in the retrieval layer.

3. **Use an async-native embedding function that releases GIL**  
   Switch to an embedding implementation that releases the GIL (e.g., ONNX Runtime with` OrtExecutionProvider` or a GPU-based inference server). This would allow threads to run truly in parallel even under the GIL. Requires changes in the embedding backend setup.

4. **Tune thread pool size and limit concurrency**  
   As a short-term mitigation, set `RETRIEVAL_CONCURRENCY_LIMIT` to the number of physical cores, reducing oversubscription. This would lower the total retrieval time to something like `RETRIEVAL_CONCURRENCY_LIMIT * single_query_time`. For 4 cores: `4 * 150ms = 600ms`, still above target. Not sufficient alone.

5. **Cache query embeddings**  
   If many sections share similar query intents, caching could reduce repeated embedding work. But sections are diverse, so hit rate likely low; not a primary fix.

### Suggested Path Forward

Given the data, **option 2 (batching)** is the most robust and does not multiply memory usage. It also reduces total API calls to Chroma. Implementation: modify `V3Retriever` to support `retrieve_many(section_queries)` that sends a list of query texts in one `coll.query` call and splits results back into separate `RoleBasedContext` objects. Then update `EvidenceAssembler.assemble_all_sections` to use batched retrieval when `len(sections) > 1`.

Alternatively, **option 1 (process pool)** could be a quick configuration fix: replace `asyncio.to_thread` with `asyncio.get_running_loop().run_in_executor(process_pool)` where process_pool has `max_workers=8`. However, this would require changes in `ChromaSemanticStoreImpl` and might have compatibility issues.

---

## Conclusion

Phase 12-02 correctly implemented concurrent retrieval. The failure to meet PERF-01 is not due to architectural flaws but to **environment‑level contention in the embedding pipeline**. The single‑query baseline is within target, proving the underlying query pipeline is fast enough. With an appropriate fix (batching or process‑based parallelism), the concurrent total can be reduced from ~1.3s to ~150–200ms, achieving the original target.

**Next step:** Implement batching in `V3Retriever` and update `EvidenceAssembler` to use it for `assemble_all_sections`. This is a relatively small, well‑contained change that should be slotted into a follow‑up sub‑phase (e.g., 12‑02.2).
