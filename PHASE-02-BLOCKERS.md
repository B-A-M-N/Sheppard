# Phase 02 V3 Activation — Blockers

**Status**: RESOLVED ✅
**Date**: 2026-03-27
**Audit**: `.planning/gauntlet_phases/phase02_v3_activation/VERIFICATION.md`

---

## Blocker Summary

All four architectural blockers have been **resolved**. V3 activation is complete and verified.

---

### ✅ Blocker 1: Chunking Stage Missing — RESOLVED

**Fix**: `src/memory/storage_adapter.py:804-828`
- `ingest_source()` now calls `chunk_text()` and `create_chunks()`
- Chunks are created with proper lineage (`source_id`, `mission_id`, `topic_id`)
- Chunks indexed in Chroma `corpus_chunks` collection

**Verification**: `corpus.chunks` contains rows; each references valid `source_id`

---

### ✅ Blocker 2: Query reads from V2, not V3 — RESOLVED

**Fix**: `src/core/system.py:131`; New file: `src/research/reasoning/v3_retriever.py`
- Created `V3Retriever` that queries `knowledge_atoms` via adapter.chroma
- Wired into `SystemManager` as `self.retriever = V3Retriever(adapter=self.adapter)`
- `HybridRetriever` no longer used in V3 path

**Verification**: `/query` returns atoms from V3 `knowledge_atoms` collection

---

### ✅ Blocker 3: Atom + Evidence Persistence Not Atomic — RESOLVED

**Fix**: `src/memory/storage_adapter.py:604-673`
- Implemented `store_atom_with_evidence(atom, evidence_rows)` method
- Uses single DB transaction (`async with conn.transaction()`)
- Validates evidence non-empty; commits both atom and evidence together
- Index and cache happen after commit

**Verification**: `DistillationPipeline` uses this method (line 111);

---

### ✅ Blocker 4: Database Targeting Inconsistency — RESOLVED

**Fix**: `src/config/database.py:55`; `src/core/system.py:82`
- V3 adapter DSN set to `DB_URLS["sheppard_v3"]` (`10.9.66.198/sheppard_v3`)
- All V3 writes/reads use this pool
- V2 `MemoryManager` not referenced by V3-critical paths

**Verification**: No V3 data in `semantic_memory`; all V3 ops target `sheppard_v3`

---

## Resolution Order Applied

1. Chunking ✓
2. Query V3 path ✓
3. Atomic evidence ✓
4. DB targeting ✓

---

## Current Status

**Phase 02**: COMPLETED
**Verification**: See `VERIFICATION.md` — all criteria PASS

Proceed to Phase 03 (Triad Enforcement) with confidence.
