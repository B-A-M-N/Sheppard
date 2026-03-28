# Phase 03 — Triad Enforcement — Execution Plan

**Phase**: 03
**Type**: Audit
**Status**: Ready
**Date**: 2026-03-27

---

## Mission

Audit the V3 memory architecture to verify that each store (Postgres, Chroma, Redis) has a clear, enforced responsibility with no truth leakage, now that canonical authority is locked to V3.

---

## Success Criteria

Phase 03 complete when deliverables are produced and show:

- ✅ Postgres is sole source of truth for atoms, sources, missions
- ✅ Chroma contains ONLY derivable projections (indexed from Postgres)
- ✅ Redis contains NO unrecoverable state (can be lost and rebuilt)
- ✅ All writes to canonical data go through Postgres first
- ✅ Rebuild script would work (theoretical)
- ✅ No V2 runtime reads (ensured by Phase 03.0)

---

## Task Breakdown

### Task 1: Inventory Adapter Usage

**Objective**: Identify all calls to `SheppardStorageAdapter` methods across V3 components.

**Actions**:
1. Search codebase for `adapter.` method calls:
   - `adapter.upsert_*`, `adapter.create_*`, `adapter.get_*`, `adapter.index_*`
2. For each component (`system.py`, `frontier.py`, `crawler.py`, `pipeline.py`, `v3_retriever.py`), list:
   - Which adapter methods are called
   - Which store do they target (pg, chroma, redis)?
3. Build a preliminary write/read map by component

**Deliverable**: Raw inventory (can be incorporated into write/read matrices)

**Acceptance**:
- [ ] All adapter uses found
- [ ] No stray direct store usage (e.g., direct `chromadb.Client` calls) outside adapter

---

### Task 2: Build Storage Write Matrix

**Objective**: Document what data is written to each store and when.

**Actions**:
1. For each write operation identified in Task 1:
   - Target table/collection
   - Data fields written
   - Invariant: is this canonical (Postgres) or projection (Chroma/Redis)?
2. Tabulate:

| Component | Method | Target Store | Table/Collection | Canonical? | Notes |
|-----------|--------|--------------|------------------|------------|-------|

3. Verify that every canonical write goes to Postgres first, then projections

**Deliverable**: `STORAGE_WRITE_MATRIX.md`

**Acceptance**:
- [ ] All writes classified
- [ ] No canonical writes to Chroma/Redis alone
- [ ] Projection writes follow canonical commit (eventual consistency OK)

---

### Task 3: Build Storage Read Matrix

**Objective**: Document where each store is read during normal V3 operations.

**Actions**:
1. Trace read paths for `/query` and `/learn`:
   - `V3Retriever.retrieve` → reads from Chroma `knowledge_atoms`
   - `DistillationPipeline.run` → reads from Postgres `corpus.sources`
   - `SystemManager` other methods (e.g., `generate_report`) → reads from Postgres/Chroma as needed
2. For each read:
   - Source store (Postgres/Chroma/Redis)
   - Purpose
   - Is the data canonical or projection?

**Deliverable**: `STORAGE_READ_MATRIX.md`

**Acceptance**:
- [ ] All read access points enumerated
- [ ] No reads from V2 (`semantic_memory`) — already locked
- [ ] No read from Chroma that would return non-projection data

---

### Task 4: Verify Chroma Rebuildability

**Objective**: Confirm Chroma is a pure projection of Postgres.

**Actions**:
1. Check that all Chroma indexing goes through adapter's `index_*` methods, which are called after Postgres writes
2. Ensure no code writes directly to Chroma (search for `chroma_client` or `chromadb` outside adapter)
3. Theoretically, can we wipe Chroma and rebuild by re-scanning Postgres? The `index_*` methods should be idempotent.
4. Document any gaps (e.g., missing reindex script)

**Deliverable**: `REBUILDABILITY_ASSESSMENT.md`

**Acceptance**:
- [ ] No direct Chroma writes outside adapter
- [ ] All Chroma rows can be traced to a Postgres source row
- [ ] Rebuild plan documented (even if manual)

---

### Task 5: Verify Redis Ephemerality

**Objective**: Ensure Redis holds only ephemeral motion state, not truth.

**Actions**:
1. Identify all Redis usage:
   - `RedisStoresImpl` methods: `enqueue_job`, `dequeue_job`, `set_active_state`, `cache_hot_object`, `acquire_lock`
2. Determine if any Redis-stored data is unrecoverable if Redis is lost:
   - Queues: can be rebuilt from Postgres? (pending jobs may be in `corpus.sources` with status='fetched' not yet processed; if Redis queue lost, those may be orphaned. Need assessment.)
   - Active state: can be rebuilt from Postgres (e.g., active missions still in `research_missions` with status 'active')
   - Hot cache: definitely rebuildable from Postgres
3. Decide if any Redis data qualifies as "truth" — should not.

**Deliverable**: Included in `REBUILDABILITY_ASSESSMENT.md`

**Acceptance**:
- [ ] No persistent truth stored only in Redis
- [ ] Data loss in Redis is non-fatal (can be regenerated or is transient)

---

### Task 6: Identify Contract Violations

**Objective**: Compile any violations of triad discipline found during Tasks 1-5.

**Actions**:
1. Review inventory and matrices
2. Flag cases where:
   - Chroma holds non-projection data
   - Redis holds unrecoverable state
   - Writes bypass Postgres
   - V2 reads appear (should be none)
3. Document each violation with:
   - File/line
   - Description
   - Severity (hard fail vs warning)

**Deliverable**: Section in `MEMORY_CONTRACT_AUDIT.md`

---

### Task 7: Produce Final Audit Report

**Objective**: Synthesize findings into the final Phase verification.

**Actions**:
1. Write `MEMORY_CONTRACT_AUDIT.md` summarizing the overall triad health
2. Include the four deliverables (write matrix, read matrix, rebuildability, audit)
3. Provide a **VERDICT**: PASS / PARTIAL / FAIL
4. If PARTIAL/FAIL, list required remediations

**Deliverable**: `PHASE-03-VERIFICATION.md`

---

## Out of Scope

- Refactoring or fixing violations during this audit phase
- Implementation of rebuild scripts (but concept must be feasible)
- Performance tuning

---

## Execution Notes

- This is an audit, not a refactor. Document facts, do not change code.
- If issues are found, note them; do not fix inline.
- The authority lock from Phase 03.0 is assumed; any V2 read is a hard fail.

---

**Proceed with systematic code inspection and produce deliverables.**
