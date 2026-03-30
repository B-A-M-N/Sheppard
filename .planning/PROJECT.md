# Sheppard V3 — Project Definition

**Current Version:** v1.0 (Truth Contract Implementation)
**Next Milestone:** Performance & Observability (tentative v1.1)

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
