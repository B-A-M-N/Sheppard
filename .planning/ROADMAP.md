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
| 12-02 | Retrieval latency optimization | ⏳ Pending | 0/0 |
| 12-03 | Synthesis throughput improvements | ⏳ Pending | 0/0 |
| 12-04 | Structured metrics & tracing | ⏳ Pending | 0/0 |
| 12-05 | Contradiction system V3 upgrade | ⏳ Pending | 0/0 |
| 12-06 | High-evidence E2E integration test | ⏳ Pending | 0/0 |
| 12-07 | Ranking improvements (constraint-safe) | ⏳ Pending | 0/0 |

### Phase 12-02: Retrieval Latency Optimization

**Goal:** Reduce total retrieval latency from ~1200ms to ≤200-300ms by parallelizing section retrieval in EvidenceAssembler.
**Requirements:** [PERF-01]
**Plans:** 3 plans

Plans:
- [ ] 12-02-01-PLAN.md — Instrumentation, dead code deprecation, test scaffolding
- [ ] 12-02-02-PLAN.md — Concurrent assembly implementation + tests
- [ ] 12-02-03-PLAN.md — Benchmark extension with corpus tiers + before/after comparison

**Guardrails:**
- No weakening of Phase 10/11 truth contract invariants
- All existing tests must pass unchanged
- Determinism preserved (seed/temperature untouched)

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

*All phases consolidated into milestone v1.0. See `.planning/milestones/v1.0-ROADMAP.md` for full details.*


**Legend**: ✅ Completed, ⬜ Pending, 🔄 In Progress

## Notes
- All gaps from Phase 06-01 audit have been closed.
- Database migration pending for `exhausted_modes_json` column.
