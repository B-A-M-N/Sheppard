# Sheppard V3 — Project Definition

**Current Milestone:** v1.2 — Deployment Scaling & Throughput Realization (planned)
**Archived Milestones:** v1.0 (Truth Contract), v1.1 (Performance & Observability)

---

## Archived Milestones

### v1.0 — Truth Contract Implementation (Shipped 2026-03-30)

<details>
<summary>Expand to view v1.0 details</summary>

Sheppard V3 now enforces **end-to-end truth guarantees**:

**Retrieval (Phase 10):**
- All answers derived solely from retrieved knowledge atoms
- Mandatory sequential citations `[A001]`, `[A002]`
- Explicit refusal when evidence insufficient
- Contradictions preserved, not hidden
- Validator prevents uncited or unsupported claims

**Synthesis (Phases 11–11.1):**
- Reports built only from atoms via V3Retriever
- Complete provenance: `atom_ids_used` stored per section + `synthesis_citations` links
- Mission isolation: all queries/storage filtered by `mission_id`
- Per-sentence citation enforced; no inference allowed
- Deterministic: temperature=0, fixed seed, sorted atoms
- Binary refusal for insufficient evidence (placeholder sections)

**Verification:**
- Milestone audit: PASS
- Unit tests: 8/8 synthesis invariants passing
- Integration tests: 10/10 retrieval-chat tests passing
- E2E: liveness verified; NO_DISCOVERY path correct; persistence working

**Key Files:**
- `src/research/reasoning/v3_retriever.py`
- `src/retrieval/validator.py`
- `src/research/archivist/synth_adapter.py`
- `src/research/reasoning/synthesis_service.py`
- `tests/research/reasoning/test_phase11_invariants.py`

**Schema:**
- `authority.synthesis_sections` has `atom_ids_used JSONB` (top-level)
- `authority.synthesis_artifacts` and `synthesis_sections` have `mission_id`
- Migrations applied: `schema_patch_phase11.sql`, `schema_patch_phase11_add_atom_ids.sql`

</details>

### v1.1 — Performance & Observability (Shipped 2026-03-31)

<details>
<summary>Expand to view v1.1 details</summary>

**Status:** ✅ PASS (with documented deployment constraint)

**Accomplishments:**
- ✅ Benchmark suite with corpus tiers; baseline established (12-01)
- ✅ Retrieval latency optimized: batch multi-query yields ≤266ms (12-02, 12-02.1, 12-02.2)
- ✅ Structured JSON logging and mission-scoped tracing (12-04)
- ✅ Contradictions upgraded to V3-native with atom attribution (12-05)
- ✅ High-evidence E2E integration test passing (12-06)
- ✅ Constraint-safe ranking fully implemented and tested (12-07)

**Known Limitation (PERF-02):**
Synthesis throughput target (≥20% improvement) not met due to single-endpoint inference serialization. The async worker pool architecture is correct but cannot accelerate GPU-bound LLM calls when only one endpoint is available. Mitigated by `SYNTHESIS_CONCURRENCY_LIMIT=1`. No truth contract violations; system production-ready for current deployment.

**Milestone Archive:** `.planning/milestones/v1.1-ROADMAP.md`  
**Requirements Archive:** `.planning/milestones/v1.1-REQUIREMENTS.md`  
**Reconciliation:** `.planning/phases/v1.1/MILESTONE-RECONCILIATION.md`

</details>

---

## Current State (v1.1 Shipped)

The system is **production-grade, truth-safe, and fully observable**.

### What's Complete

1. **Truth Contract (v1.0)**
   - Strict grounding via V3Retriever
   - Per-sentence citation enforced
   - Complete provenance (`atom_ids_used`)
   - Mission isolation
   - Binary refusal for unsupported queries

2. **Performance Optimizations (v1.1)**
   - Retrieval latency ≤300ms on medium/large corpora (batch queries)
   - Deduplication reduces redundant embedding loads
   - Bounded async synthesis worker pool (architecture ready for multi-endpoint scaling)

3. **Observability (v1.1)**
   - Structured JSON logs with `mission_id` trace correlation
   - Span instrumentation for frontier → retrieval → synthesis
   - Benchmark suite for regression detection
   - Duration metrics captured end-to-end

4. **Contradictions (v1.1)**
   - No legacy `memory` dependency
   - Direct DB query with proper FK attribution
   - Archivist includes contradiction atoms with citations

5. **Verification Coverage (v1.1)**
   - High-evidence E2E test validates full pipeline with real atoms
   - 24 ranking tests (TDD) confirm deterministic reordering
   - 99 guardrail tests ensure no truth contract regressions

**Current Deployment Topology:**
- Single Ollama endpoint (`.90`)
- Single PostgreSQL + Chroma
- Synthesis concurrency limit = 1 (to avoid queue overhead)

---

## Next Milestone Goals (v1.2 — Planned)

**Focus:** Scaling throughput to match multi-core inference capacity.

**Hypothesized Work:**

1. **Multi-endpoint inference routing**
   - Load balance synthesis requests across multiple Ollama instances
   - Remove `SYNTHESIS_CONCURRENCY_LIMIT=1` override
   - Validate that parallel throughput improves as expected

2. **Batch inference API**
   - If provider supports it, send multiple section prompts in single LLM call
   - Reduces per-request overhead and GPU idle time

3. **Queue-aware scheduling**
   - Backpressure to frontier when synthesis queue grows too large
   - Adaptive concurrency based on observed latency

4. **Throughput re-verification**
   - Re-run PERF-02 tests after scaling improvements
   - Document achieved sections/min vs. baseline

5. **Observability enhancements** (if needed)
   - Synthesis queue depth metrics
   - Per-endpoint utilization tracking
   - LLM request batching efficiency

**Success Criteria:**
- Synthesis throughput ≥ baseline +20% (target from PERF-02)
- No degradation in truth contract invariants
- All existing tests continue to pass
- Observable scaling gains (metrics, logs)

---

## Future Work (Unchanged from Existing Roadmap)

These phases were planned in earlier roadmap and remain to be done:

### Phase 06 — Discovery Engine
- 06-XX: Validation / Integration (pending)

### Phase 07 — Orchestration Validation
- 07-01: Core invariants (✅ Completed)

### Phase 08 — Scraping / Content Normalization Audit
- TBD

### Phase 09 — Smelter / Atom Extraction Audit
- 09-01: Atom schema and extraction pipeline ✅
- 09-XX: Gap Closure ✅

---

## Notes

- v1.1 completed with **zero truth contract regressions**.
- v1.2 is expected to be smaller in scope (primarily deployment configuration + validation).
- After v1.2, consider roadmap review to reprioritize remaining phases (08, 09-XX, 06-XX) based on product needs.

---

## Modification History

| Version | Date | Notes |
|---------|------|-------|
| v1.0 | 2026-03-30 | Truth contract enforced end-to-end; milestone archived |
| v1.1 | 2026-03-31 | Performance + Observability shipped; known PERF-02 limitation documented |
| v1.2 | (planned) | Deployment Scaling & Throughput Realization |
