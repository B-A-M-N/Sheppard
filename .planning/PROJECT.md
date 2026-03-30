# Sheppard V3 — Project Definition

**Current Milestone:** v1.1 — Performance & Observability
**Previous Milestone:** v1.0 — Truth Contract Implementation (✅ Archived 2026-03-30)

---

## Current State (v1.1 — In Planning)

The system is **provably truth-bound** (v1.0 guarantees). Now we optimize and add observability while preserving those invariants.

**v1.0 Baseline:**
- Retrieval: V3Retriever, strict grounding, sequential citations, refusal for unsupported queries
- Synthesis: pure transformation, complete provenance (`atom_ids_used`), mission isolation, determinism, binary refusal
- Validator: per-sentence citation + lexical overlap; cannot be bypassed

**Status:** All v1.0 tests passing; audit PASS; tagged and archived.

---

## v1.1 Goals: Performance & Observability

### 1. Performance Optimization
- Benchmark suite to establish baselines (P95 latency, throughput)
- Retrieval latency reduction (caching, async tuning)
- Synthesis throughput improvements (batching, early termination)
- Chunk/atom storage efficiency (deduplication)

### 2. Observability & Debugging
- Structured metrics (retrieval hit rates, synthesis validator rejections, DB latencies)
- Distributed tracing (mission → step spans)
- Debug APIs: mission timeline, retrieval details, metrics endpoint
- Dashboard prototypes (Grafana or simple HTML)

### 3. High-Evidence E2E Coverage
- Full-path integration test: mission → frontier → ingestion → extraction → retrieval → synthesis → persistence
- Validates citations match `atom_ids_used`, report passes validator, all evidence real atoms

### 4. Contradiction System Upgrade
- Remove legacy `memory.get_unresolved_contradictions` dependency
- V3-native contradiction queries (DB or V3Retriever)
- Contradictions properly attributed to atoms
- Synthesis includes contradictions when relevant

### 5. Ranking Improvements (Constraint-Safe)
- Relevance scoring within retrieval limit (cosine similarity, recency, authority)
- Deterministic ordering preserved (seed-controlled)
- No hard filtering (all retrieved atoms still returned)

**Guardrails:**
- ❌ No changes to truth contract invariants
- ❌ No weakening of validator semantics
- ❌ No modifications to `atom_ids_used` or `mission_id` storage
- ✅ All existing tests must pass unchanged

---

## Known Limitations (from v1.0)

- Contradiction retrieval still uses legacy path (to be fixed in v1.1)
- High-evidence synthesis E2E not yet exercised (to be added in v1.1)

---

## Modification History

| Version | Date | Notes |
|---------|------|-------|
| v1.0 | 2026-03-30 | Truth contract enforced end-to-end; milestone archived |
| v1.1 | (in progress) | Performance + Observability |


---

## Current State (v1.0 — Shipped 2026-03-30)

Sheppard V3 now enforces **end-to-end truth guarantees**:

### Retrieval (Phase 10)
- All answers derived solely from retrieved knowledge atoms
- Mandatory sequential citations `[A001]`, `[A002]`
- Explicit refusal when evidence insufficient
- Contradictions preserved, not hidden
- Validator prevents uncited or unsupported claims

### Synthesis (Phases 11–11.1)
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

---

## Next Milestone Goals (v1.1 — Performance & Observability)

**Objective:** Optimize retrieval latency, add metrics/tracing, and upgrade contradiction handling without breaking truth contract.

### Focus Areas

1. **Performance**
   - Reduce retrieval query latency (caching strategies, embedding precomputation)
   - Pipeline throughput improvements (parallelization, async bounds)
   - Synthesis generation time optimization (streaming, early termination)

2. **Observability**
   - Structured metrics: retrieval hit rates, synthesis success/failure counts, validator rejection reasons
   - Tracing: mission lifecycle spans, per-section timing, DB query latency
   - Dashboards: real-time view of active missions, error rates

3. **Contradiction System Upgrade**
   - Replace legacy `memory.get_unresolved_contradictions` with V3-native query
   - Ensure contradictions properly attributed to atoms and included in synthesis when relevant
   - Add validator checks for contradiction awareness (optional flag)

4. **High-Evidence E2E Coverage**
   - Create integration test that exercises full path: retrieval → synthesis with real atoms → successful report
   - Validate citations and `atom_ids_used` match in final output

5. **Ranking Improvements (Constraint-Safe)**
   - Better atom ordering (beyond simple lexical sort) while preserving determinism (seed-controlled)
   - Relevance scoring adjustments within retrieval limit (still no hard filtering)

---

## Deferred Work (Future)

- Phase 06-XX: Validation / Integration (remaining gap closures)
- Phase 08: Scraping / Content Normalization (post-08.1 hardening)
- Phase 12+: async governance, final verifications

---

## Known Limitations (v1.0)

- Contradiction retrieval currently depends on legacy `memory.get_unresolved_contradictions`; not yet V3-native
- High-evidence synthesis path not covered by E2E script (unit + integration tests provide coverage)

---

## Modification History

| Version | Date | Notes |
|---------|------|-------|
| v1.0 | 2026-03-30 | Truth contract enforced end-to-end; milestone archived |
