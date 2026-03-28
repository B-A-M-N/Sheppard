# Phase 03 — Memory Contract Audit

**Auditor**: Claude Code (static analysis)
**Date**: 2026-03-27
**Scope**: V3 runtime storage access
**Verdict**: ✅ **PASS**

---

## Executive Summary

The V3 memory architecture **fully adheres** to triad discipline:
- Postgres is the canonical source of truth
- Chroma contains only projections (no independent truth)
- Redis holds only ephemeral state (queues, caches, locks)
- All writes to canonical data go through Postgres first via the StorageAdapter

The previously identified violations have been **remediated**:
1. Archivist now uses injected `ChromaSemanticStore`; no direct Chroma client creation
2. Redis queue names aligned (`queue:scraping` used consistently)

The triad contract is fully enforced across the entire V3 codebase.

---

## Compliance Matrix (Post-Remediation)

| Contract Principle | Status | Evidence |
|--------------------|--------|----------|
| Postgres is sole source of truth | ✅ PASS | All canonical writes via adapter → Postgres |
| Chroma contains ONLY derivable projections | ✅ PASS | Archivist uses `ChromaSemanticStore` interface; no direct client; all data projectable from Postgres records |
| Redis contains NO unrecoverable state | ✅ PASS | All Redis keys are queues, caches, or locks; rebuildable from Postgres |
| All canonical writes go through Postgres first | ✅ PASS | Adapter pattern enforced throughout |
| Rebuildability feasible | ✅ PASS | All Chroma collections are projections; rebuild via re-indexing from Postgres |

---

## Key Findings

### ✅ Strengths

- Adapter enforces triad discipline for all V3 core components (system, frontier, condenser, retriever, research)
- Indexing is consistently performed after Postgres commit
- No V2 reads in V3 paths
- Redis usage is appropriate (queues, caches, locks)
- Archivist architecture preserved while gaining triad compliance
- `ResearchSystem` integrated as a V3 component with proper `chroma_store` injection

### ❌ Past Violations (Now Resolved)

#### 1. Archivist Direct Chroma Access — **RESOLVED**

- **File**: `src/research/archivist/index.py` (formerly violated)
- **Original issue**: Created its own `chromadb.PersistentClient` and wrote to `archivist_research` without adapter.
- **Fix applied**:
  - Extended `ChromaSemanticStore` protocol with `clear_collection` and embedding support
  - Refactored Archivist to accept injected `chroma_store`
  - Removed all `chromadb` imports from `archivist/` directory
  - Made indexing and retrieval functions async
- **Verification**:
  ```bash
  grep -rn "chromadb.Client" src/research/archivist/  # empty
  grep -rn "from chromadb" src/research/archivist/  # empty
  ```

#### 2. Redis Queue Mismatch — **RESOLVED**

- **Files**: `src/research/acquisition/crawler.py:240`, `src/core/system.py:314`
- **Original issue**: Enqueue used `queue:acquisition`, dequeue used `queue:scraping`.
- **Fix applied**: Changed enqueue to `"queue:scraping"`
- **Verification**: Both sides now consistently use `queue:scraping`

### ⚠️ Warnings (Non-blocking)

- **Eventual consistency**: Chroma indexing occurs after Postgres commit but not in the same transaction. If indexing fails, data is in Postgres but not discoverable until re-index. Monitoring recommended.
- **V2 MemoryManager**: Still exists but is not used by V3 paths. Consider removal in future cleanup.

---

## Write & Read Matrices

Summaries attached:
- `STORAGE_WRITE_MATRIX.md` — complete catalog of write operations
- `STORAGE_READ_MATRIX.md` — complete catalog of read operations

All writes to canonical stores go through `SheppardStorageAdapter` → Postgres first. Chroma and Redis operations are downstream projections or transient.

---

## Rebuildability

- **Chroma**: All collections (`knowledge_atoms`, `corpus_chunks`, `authority_records`, `synthesis_artifacts`, `archivist_research`) are projections. Can be rebuilt by re-indexing from Postgres (or reprocessing sources). A unified rebuild script is recommended but not required for PASS.
- **Redis**: All data is ephemeral; loss is non-fatal. Pending jobs can be re-enqueued from `corpus.sources` if needed.

---

## Recommendations (Future Work)

1. Produce a **rebuild script** that clears Chroma and re-indexes all projections from Postgres
2. Consider **removing V2 MemoryManager** from the codebase to reduce confusion
3. Add **monitoring/alerting** for Chroma indexing failures to catch projection gaps
4. Document the `ResearchSystem` integration as part of V3 architecture

---

## Conclusion

The V3 memory contract is **fully enforced**. No hard violations remain. Phase 03 PASSES.

**Status**: Phase 03 complete. Proceed to Phase 04 (UAT/Production Readiness) or archive.
