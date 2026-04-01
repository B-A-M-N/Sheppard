# Project Roadmap

**Current Milestone:** v1.1 — Performance & Observability
**Scope:** Phase 12 (optimize retrieval/synthesis, add metrics/tracing, upgrade contradictions)
**Previous Milestone:** v1.0 — Truth Contract Implementation (✅ COMPLETE, archived)

---

## Phase 12 — Performance & Observability (v1.1)

**Objective:** Optimize latency/throughput and add full observability without weakening truth invariants.

| Plan | Name | Status | Tasks (C/T) |
| ---- | ---- | ------ | ----------- |
| 12-01 | Benchmark suite & baseline metrics | ✅ Completed | 3/0 |
| 12-02 | Retrieval Latency Optimization | ✅ Completed | 5/5 |
| 12-02.1 | Retrieval Latency Diagnosis | ✅ Completed | 4/4 |
| 12-02.2 | Batch Multi-Query Retrieval | ✅ Completed | 4/4 |
| 12-03 | Synthesis throughput improvements | ✅ Partial PASS | 2/2 |
| 12-04 | Structured metrics & tracing | ✅ Completed | 1/1 |
| 12-05 | Contradiction system V3 upgrade | ✅ Completed | 1/1 |
| 12-06 | High-evidence E2E integration test | ⏳ Pending | 0/0 |
| 12-07 | Ranking improvements (constraint-safe) | ⏳ Pending | 0/0 |

### Phase 12-02: Retrieval Latency Optimization

**Goal:** Reduce total retrieval latency from ~1200ms to ≤200-300ms by parallelizing section retrieval in EvidenceAssembler.
**Requirements:** [PERF-01]
**Plans:** 3/3 plans complete

Plans:
- [x] 12-02-01-PLAN.md — Instrumentation, dead code deprecation, test scaffolding
- [x] 12-02-02-PLAN.md — Concurrent assembly implementation + tests
- [x] 12-02-03-PLAN.md — Benchmark extension with corpus tiers + before/after comparison

**Guardrails:**
- No weakening of Phase 10/11 truth contract invariants
- All existing tests must pass unchanged
- Determinism preserved (seed/temperature untouched)

### Phase 12-02.1: Retrieval Latency Diagnosis

**Goal:** Identify root cause of high per-query latency observed after 12-02 implementation.
**Status:** ✅ Completed (Diagnostic)
**Artifacts:** ANALYSIS.md with full findings and recommendations

The investigation revealed that single-query latency is within target (~150–180ms), but concurrent retrieval (8 sections) suffers severe serialization due to GIL contention during embedding computation. The recommended fix is to batch section queries into a single Chroma call.

### Phase 12-02.2: Batch Multi-Query Retrieval

**Goal:** Implement batch retrieval to eliminate GIL contention and achieve PERF-01.
**Status:** ✅ Completed
**Artifacts:** 12-02.2-SUMMARY.md

Implemented `V3Retriever.retrieve_many` and modified `EvidenceAssembler.assemble_all_sections` to use it. Also extended Chroma adapter for `query_texts`. Results:
- Small corpus: 227ms
- Medium corpus: 266ms
- Large corpus: 260ms
All within ≤300ms target. Guardrails passed. PERF-01 achieved.

### Phase 12-03: Synthesis throughput improvements

**Goal:** Achieve ≥20% increase in validated_sections_per_minute by parallelizing section generation with bounded async worker pool while preserving truth invariants.
**Requirements:** [PERF-02]
**Plans:** 0/2 plans complete

Plans:
- [ ] 12-03-01-PLAN.md — Core parallel synthesis refactoring (config, worker pool, metrics, retry)
- [ ] 12-03-02-PLAN.md — Benchmark update and throughput verification

**Guardrails:**
- No weakening of Phase 10/11 truth contract invariants.
- All existing tests must pass unchanged.
- Determinism preserved (seed/temperature untouched).
- Validator runs on every section; no skipping.
- Citations assigned after all sections complete.
- Forbidden: skip validator, batch prompts, modify citation logic, shared mutable state.

### Phase 12-07: Ranking Improvements (Constraint-Safe)

**Goal:** Activate post-retrieval composite scoring to reorder atoms before synthesis, opt-in via enable_ranking, deterministic, no atoms dropped.
**Requirements:** [RANK-01, RANK-02, RANK-03, RANK-04]
**Plans:** 2 plans

Plans:
- [ ] 12-07-01-PLAN.md — Create ranking.py, extend RetrievalQuery, wire _build_from_context
- [ ] 12-07-02-PLAN.md — Test suite: unit + assembler integration tests (TDD)

**Guardrails:**
- No weakening of Phase 10/11 truth contract invariants.
- All existing tests must pass unchanged.
- No atoms dropped in any retrieval path.
- Default behavior (enable_ranking=False) must be byte-for-byte identical to current behavior.
- No new third-party dependencies.

---

## Phase 06 — Discovery Engine

| Plan | Name | Status | Tasks (C/T) |
| ---- | ---- | ------ | ----------- |
| 06-01 | Audit | ✅ Completed | 1/1 |
| 06-02 | parent_node_id fix | ✅ Completed | 1/1 |
| 06-03 | Deep mining fix | ✅ Completed | 1/1 |
| 06-04 | Academic filtering | ✅ Completed | 1/1 |
| 06-05 | exhausted_modes persistence | ✅ Completed | 1/1 |
| 06-06 | Queue backpressure | ✅ Completed | 1/1 |
| 06-XX | Validation / Integration | ⬜ Pending | 0/0 |

## Phase 07 — Orchestration Validation

| Plan | Name | Status | Tasks (C/T) |
| ---- | ---- | ------ | ----------- |
| 07-01 | Core invariants | ✅ Completed | 5/5 |

## Phase 08 — Scraping / Content Normalization Audit

| Plan | Name | Status | Tasks (C/T) |
| ---- | ---- | ------ | ----------- |

## Phase 09 — Smelter / Atom Extraction Audit

| Plan | Name | Status | Tasks (C/T) |
| ---- | ---- | ------ | ----------- |
| 09-01 | Atom schema and extraction pipeline | ✅ Completed | 0/0 |
| 09-XX | Gap Closure (soft acceptance) | ✅ Completed | 0/0 |

## Phase 10–11.1 — Truth Contract Implementation (v1.0)

**Status:** ✅ COMPLETE (archived 2026-03-30)

*All phases consolidated under milestone v1.0. See `.planning/milestones/v1.0-ROADMAP.md` for full details.*


**Legend**: ✅ Completed, ⬜ Pending, 🔄 In Progress

## Notes

- All gaps from Phase 06-01 audit have been closed.
- Database migration pending for `exhausted_modes_json` column.
