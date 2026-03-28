# Phase 03 — Triad Enforcement — Context

**Purpose**: Guide the audit of memory architecture to enforce strict triad discipline after canonical authority lock.

---

## Architectural State (Post-03.0)

- **Canonical Truth**: PostgreSQL (`sheppard_v3`) exclusively via `SheppardStorageAdapter`
- **V2 Deprecated**: `MemoryManager` removed from runtime; no instantiation
- **Retrieval**: `V3Retriever` only; no fallback to V2
- **HybridRetriever**: Deleted from `retriever.py`; no longer available
- **SystemManager**: V3-only initialization; `self.memory = None`

---

## Audit Objectives

1. Map all reads and writes to Postgres
2. Map all reads and writes to Chroma
3. Map all reads and writes to Redis
4. Identify overlap, duplication, leakage, or contract violations
5. Determine whether Chroma can be fully rebuilt from Postgres
6. Determine whether Redis can be lost without losing truth

---

## Known Artifacts (Pre-Compliance)

- V3 adapter implements Triad Discipline: write Postgres → index Chroma → cache Redis
- StorageAdapter methods enforce the invariant for each store type
- `corpus.chunks` now created during ingestion (fixed in Phase 02)
- Atomic `store_atom_with_evidence` ensures atom+evidence consistency
- V3Retriever reads from `knowledge_atoms` collection only

---

## Scope of Audit

**In Scope**:
- All code in `src/core/` and `src/research/` that uses storage via `SheppardStorageAdapter` or direct stores
- Focus on V3 data flow: ingestion → distillation → retrieval
- Verify that no V2 storage is touched by V3 paths (already locked)
- Confirm that Chroma is a pure projection (derivable from Postgres)
- Confirm that Redis holds only ephemeral/motion state

**Out of Scope**:
- V2 archival database (`semantic_memory`) — not accessed
- Legacy modules that are not imported by V3 runtime
- External tools that may query V2 (outside scope)

---

## Expected Deliverables

- `MEMORY_CONTRACT_AUDIT.md` — overall assessment
- `STORAGE_WRITE_MATRIX.md` — table of what writes where
- `STORAGE_READ_MATRIX.md` — table of what reads from where
- `REBUILDABILITY_ASSESSMENT.md` — can Chroma be rebuilt? can Redis be lost?
- `PHASE-03-VERIFICATION.md` — pass/fail with evidence

---

## Hard Constraints

- **FAIL** if Chroma contains data not derivable from Postgres
- **FAIL** if Redis holds unrecoverable mission state
- **FAIL** if any V3 code reads from V2 during normal operation
- **FAIL** if Postgres lineage is incomplete or inconsistent

---

## Notes

The earlier Gray Area report (30 items) provides preliminary findings. The audit now must verify that, given the authority lock, the triad contracts hold in the current codebase. Some items from that list are already resolved by the lock (e.g., Dual V2/V3, HybridRetriever fallback). Others require inspection (e.g., Chroma bypass in archivist, queue mismatch). These should be classified as violations if present.

---

**Proceed to planning and execution.**
