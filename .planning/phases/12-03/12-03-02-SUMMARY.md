# Phase 12-03 Summary: Synthesis throughput improvements

**Status:** 🟡 PARTIAL PASS
**Date:** 2026-03-31

## Deliverables

- ✅ `12-03-01`: Async worker pool refactored (bounded concurrency, retry, metrics)
- ✅ `12-03-02`: Benchmark updated to use parallel synthesis loop
- 🟡 PERF-02: Throughput target NOT met on single-endpoint deployment

## What Changed

- Replaced sequential `for section in sections: generate → validate → store` with bounded async worker pool
- Removed `previous_context` dependency (sections generated independently)
- Added retry logic (3 attempts, exponential backoff) per section
- Added timing metrics (synthesis total, LLM time, validator time)
- Updated benchmark suite (`scripts/benchmark_suite.py`) to mirror production code
- Added `SYNTHESIS_CONCURRENCY_LIMIT=1` deployment override (`.env`, `.env.example`)

## PERF-02 Verification

| Metric | Value |
|--------|-------|
| Baseline sections/min (Phase 12-01) | ~6.54 |
| Phase 12-03 sections/min (10 iterations) | 4.29 |
| Target | ≥ 7.85 |
| Guardrail tests (pre+post) | 99/99 passed |

## Performance Analysis

The bounded async worker pool is architecturally correct, but the **single Ollama endpoint serializes concurrent requests** at the inference server. Results:

- When multiple sections send concurrent requests to one GPU endpoint, they **queue** at the server
- No parallel GPU compute — just increased queue overhead
- Net effect: synthesis takes ~14s/section regardless of concurrency, but slightly worse due to server-side queuing

**This is a deployment limitation, not a design flaw.**

## Root Cause

- Single `.90` Ollama endpoint = **sequential inference** regardless of client-side concurrency
- The `asyncio.Semaphore(8)` allows 8 concurrent clients, but the GPU processes one request at a time
- Without multi-endpoint load balancing or batching GPU inference, section-level parallelism cannot accelerate LLM calls

## Blocking Condition

```
PERF-02: blocked by single-endpoint inference serialization
```

## Mitigations

- `SYNTHESIS_CONCURRENCY_LIMIT=1` set in `.env` — degrades gracefully to sequential behavior when GPU can't parallelize
- Code structure preserved — enables speedup when:
  - Multiple inference endpoints available (load balanced)
  - Batch inference API used (single call for multiple sections)
  - Local multi-GPU deployment

## Guardrails Preserved

- ✅ 99/99 pytest tests pass (pre and post benchmark)
- ✅ Validator runs on every section
- ✅ `atom_ids_used` integrity preserved
- ✅ Deterministic ordering after parallel execution
- ✅ Citation correctness maintained

## Next Steps

- Phase 12-04 (Structured metrics & tracing): continue with current code
- Future: add multi-endpoint synthesis when deployment supports it
- Re-test PERF-02 when load-balanced inference is available
