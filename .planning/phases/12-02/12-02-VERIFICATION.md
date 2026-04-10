---
phase: 12-02
verified: 2026-03-31T03:40:00Z
status: gaps_found
score: 15/16
re_verification:
  previous_status: none
  gaps_closed: []
  regressions: []
gaps:
  - truth: "Before/after comparison shows retrieval_ms improvement from concurrent gather (and meets PERF-01 target ≤200-300ms)"
    status: failed
    reason: "Benchmark run on current environment shows total retrieval_ms = 1066ms (P95=1066ms, n=1) which is above the ≤200-300ms target. The per-section mean retrieval time is ~980ms, indicating high per-query latency. Concurrency provides ~6.4x parallelism efficiency but absolute latency remains ~1s. The expected per-query latency (~150ms) assumed in the target is not observed, likely due to corpus bloat or indexing changes. No demonstration that the target is met."
    artifacts:
      - path: "scripts/benchmark_suite.py"
        issue: "Benchmark infrastructure is correct and measures concurrency, but actual numbers do not meet target."
      - path: "src/research/reasoning/assembler.py"
        issue: "Concurrent retrieval implementation is correct, but underlying query latency is too high."
    missing:
      - "Investigate and reduce per-query retrieval latency (e.g., caching, index optimization, corpus cleanup)."
      - "Run controlled benchmark on a fresh corpus to measure true concurrency benefit vs baseline."
      - "If per-query latency cannot be reduced, re-evaluate target feasibility."
---

# Phase 12-02: Retrieval Latency Optimization — Verification Report

**Phase Goal:** PERF-01 — reduce total retrieval latency from ~1200ms to ≤200–300ms via concurrent assembly.

**Verified:** 2026-03-31T03:40:00Z
**Status:** gaps_found
**Re-verification:** No (initial)

**Overall Score:** 15/16 must-have truths verified (93.75%)

---

## Goal Achievement Summary

The concurrent retrieval implementation is complete and verified. EvidenceAssembler.assemble_all_sections uses index-preserving asyncio.gather, integrates into SynthesisService, and all tests pass (99 guardrail tests, 5 concurrent assembly tests). Truth contract invariants preserved.

However, the primary performance target — total retrieval ≤200–300ms — is **not achieved**. A live benchmark run on the current database shows total retrieval time of **1066ms** with per-section mean ~980ms. Concurrency yields a parallelism efficiency of 6.43×, but the absolute latency remains ~1s due to high per-query latency. The target requires per-query latency to be ~150ms; current per-query latency is ~1s.

The gap blocks full goal achievement.

---

## Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | build_evidence_packet logs per-section retrieval timing in milliseconds | ✓ VERIFIED | `assembler.py` lines 113-119 contain `time.perf_counter()` and debug log |
| 2 | RETRIEVAL_CONCURRENCY_LIMIT constant exists and is configurable | ✓ VERIFIED | `assembler.py` line 25: `RETRIEVAL_CONCURRENCY_LIMIT = 8` |
| 3 | src/retrieval/retriever.py has deprecation docstring | ✓ VERIFIED | `retriever.py` top contains DEPRECATED notice |
| 4 | New test file exists with stubs for concurrent assembly tests | ✓ VERIFIED | `tests/research/reasoning/test_concurrent_assembly.py` created |
| 5 | test_concurrent_produces_identical_atom_ids_as_sequential stub exists (later filled) | ✓ VERIFIED | Test method implemented and passes |
| 6 | EvidenceAssembler.assemble_all_sections retrieves all sections concurrently via asyncio.gather | ✓ VERIFIED | `assembler.py` lines 161-207 implement `assemble_all_sections` with `asyncio.gather` |
| 7 | Section order is preserved after concurrent gather using index-preserving pattern | ✓ VERIFIED | `indexed_tasks` tuples and dict mapping by `section.order` (lines 178-206) |
| 8 | A single section failure returns an empty EvidencePacket without crashing other sections | ✓ VERIFIED | Exception handling in `assemble_all_sections` returns empty `EvidencePacket` (lines 194-205) |
| 9 | SynthesisService.generate_master_brief uses assemble_all_sections for retrieval but keeps LLM synthesis sequential | ✓ VERIFIED | `synthesis_service.py` line 86 calls `assemble_all_sections`; synthesis loop lines 90-146 sequential |
| 10 | atom_ids_used ordering is identical between concurrent and sequential execution | ✓ VERIFIED | test_concurrent_produces_identical_atom_ids_as_sequential passes (5/5 tests passed) |
| 11 | The synthesis_service.py section loop body is unchanged after refactor (only evidence retrieval call changes) | ✓ VERIFIED | Grep counts unchanged: `_validate_grounding`=2, `write_section`=1, `citation`=15; `build_evidence_packet` removed from synthesis_service |
| 12 | Benchmark supports --corpus-tier argument with small/medium/large options | ✓ VERIFIED | `benchmark_suite.py` lines 31-35 and argparse add argument (line ~110) |
| 13 | MEDIUM tier seeds 500 atoms, LARGE tier seeds 1000 atoms | ✓ VERIFIED | `CORPUS_TIERS` dict: `"medium": 500, "large": 1000` (lines 32-35) |
| 14 | Benchmark output JSON includes retrieval_queries, concurrency_level, retrieval_parallelism_efficiency | ✓ VERIFIED | `benchmark_suite.py` adds these keys to `run_result` (lines 417-419) and they appear in `verification_benchmark.json` |
| 15 | Before/after comparison shows retrieval_ms improvement from concurrent gather | ✗ FAILED | Benchmark run shows total retrieval_ms = 1066ms (vs baseline sequential total ≈1200ms). No clear improvement to ≤200-300ms. Per-query latency ~980ms prevents target achievement. |
| 16 | benchmark_suite.py imports and instantiates EvidenceAssembler to call assemble_all_sections through production code path | ✓ VERIFIED | `benchmark_suite.py` line 26 imports; line 270 calls `assemble_all_sections` |

**Score:** 15 verified / 16 total = 0.9375

---

## Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/research/reasoning/assembler.py` | Per-section timing, RETRIEVAL_CONCURRENCY_LIMIT, `assemble_all_sections` implementation | ✓ VERIFIED | Exists, substantive (~200 lines), imported by synthesis_service and benchmark, wired into system |
| `src/research/reasoning/synthesis_service.py` | Integration of concurrent retrieval | ✓ VERIFIED | Exists, substantive, calls `assemble_all_sections`, no direct `build_evidence_packet` calls |
| `tests/research/reasoning/test_concurrent_assembly.py` | Concurrent assembly tests | ✓ VERIFIED | Exists, 5 tests, all passing |
| `scripts/benchmark_suite.py` | Extended with corpus tiers and concurrency metrics | ✓ VERIFIED | Exists, includes `CORPUS_TIERS`, `retrieval_parallelism_efficiency`, and uses `assemble_all_sections` |

---

## Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `assembler.py` | `time.perf_counter` | timing instrumentation in `build_evidence_packet` | ✓ WIRED | Lines 113-119 |
| `assembler.py` | `asyncio.gather` | `assemble_all_sections` | ✓ WIRED | Line 186 |
| `synthesis_service.py` | `assembler.py` | `assemble_all_sections` call | ✓ WIRED | Line 86 |
| `benchmark_suite.py` | `seed_high_evidence_atoms` | `--corpus-tier` → count parameter | ✓ WIRED | Lines 117-121 |
| `benchmark_suite.py` | `assembler.py` | import and use of `assemble_all_sections` | ✓ WIRED | Line 26 import, line 270 call |

---

## Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| `assembler.py:assemble_all_sections` | `packets: Dict[int, EvidencePacket]` | `build_evidence_packet` per section | Yes — pulls from Chroma via `retriever.retrieve` | ✓ FLOWING |
| `synthesis_service.py:generate_master_brief` | `all_packets` | `assembler.assemble_all_sections` | Yes — each packet contains `atoms` and `atom_ids_used` | ✓ FLOWING |
| `synthesis_service.py` | `prose` | `archivist.write_section(packet, previous_context)` | Yes — LLM-generated text | ✓ FLOWING |

---

## Behavioral Spot-Checks

We executed a live benchmark to verify key behaviors:

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Benchmark runs and produces JSON with concurrency metrics | `python scripts/benchmark_suite.py --scenario high_evidence --corpus-tier small --iterations 1` | Completed successfully; output `verification_benchmark.json` includes `retrieval_parallelism_efficiency=6.43`, `concurrency_level=8`, `retrieval_ms=1066ms` | ✓ PASS |
| Concurrent retrieval actually overlaps queries (demonstrated by >1× parallelism) | Same benchmark | Efficiency 6.43× indicates strong overlap; sequential estimate sum ≈6860ms, actual concurrent ≈1066ms | ✓ PASS |
| Guardrail tests pass | `pytest tests/research/reasoning/test_concurrent_assembly.py` and full suite | 5/5 concurrent tests passed; 99 total guardrail tests passed | ✓ PASS |

The benchmark confirms concurrency works and delivers ~6.4× speedup relative to sequential sum, but absolute retrieval time (1066ms) does **not** meet the ≤200–300ms target.

---

## Requirements Coverage

| Requirement | Description | Status | Evidence |
|-------------|-------------|--------|----------|
| PERF-01 | Retrieval query latency P95 < 200ms (baseline unknown, must measure) | ⚠️ PARTIAL | Implementation achieves concurrency, but measured retrieval_ms = 1066ms (P95 not available from n=1) exceeds 200ms. Baseline total sequential ≈1200ms; concurrency reduced estimated sequential sum (≈6860ms) to ≈1066ms, but absolute per-query latency (~1s) remains too high. Target not met. |
| Truth Contract (byte counts) | `_validate_grounding`=2, `write_section`=1, `citation`=15 | ✓ SATISFIED | Grep counts in `synthesis_service.py` match exactly; no refactor regression. |
| Guardrail tests | No regression in v1.0 test suite | ✓ SATISFIED | 99 tests passed (excluding known broken tests). |

---

## Anti-Patterns Found

No anti-patterns detected in modified files:
- No TODO/FIXME/placeholder comments
- No empty implementations or hardcoded stubs
- No console.log-only handlers

---

## Human Verification Required

No additional human testing needed; all automated checks completed and benchmark executed.

---

## Gaps Summary

**Critical Gap:** The phase goal — reduce total retrieval latency to ≤200–300ms — is not achieved. Current measurement shows retrieval_ms ≈1066ms. Concurrency is correctly implemented and provides substantial speedup relative to sequential sum, but high per-query latency (~1s) prevents meeting the absolute target.

**Root cause hypothesis:** The per-query latency is higher than the baseline (~150ms) possibly due to database bloat (many atoms accumulated from previous runs) or changes in indexing. However, even with a fresh corpus, the implementation cannot achieve the target unless individual queries become faster. The target was based on an assumption that each section query would be around 150ms; current queries are ~1s.

**Recommendations:**
- Investigate ChromaDB query performance: index health, embedding dimension, distance computation cost.
- Consider per-query caching of frequent embeddings or precomputing section query results.
- Evaluate if the number of sections can be reduced (some topics may need fewer sections).
- Re-run benchmark on a clean database to isolate corpus size effect; if queries are faster when corpus is small, the issue is scaling rather than concurrency.
- If per-query latency cannot be reduced to ~150ms, relax the target to a more realistic value (e.g., ≤500ms) or revisit the optimization strategy (e.g., batching queries, moving to a faster vector store).

---

_Verified: 2026-03-31T03:40:00Z_
_Verifier: Claude (gsd-verifier)_
