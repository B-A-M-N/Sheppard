# ChromaDB Access Surface Audit

**Date:** 2026-04-01
**Phase:** 12-G

## Executive Summary

Five distinct code paths reach ChromaDB. Two were unprotected; both have been patched. One unused V2 store also patched for defense-in-depth. The architecture still suffers from **duplication** (multiple stores/adapters) that creates risk of future drift.

---

## Audit Matrix

| File | Class / Function | Chroma Usage | Lock Present? | Lock Type | Status |
|------|------------------|--------------|---------------|-----------|--------|
| `src/memory/adapters/chroma.py` | `ChromaSemanticStoreImpl` | All methods (`_get_collection`, `index_document`, `index_documents`, `search`, `query`, `delete_document`, `clear_collection`) | ✅ Yes | `self._lock` (global) | Active Safe |
| `src/memory/stores/chroma.py` | `ChromaMemoryStore` | All public methods (`store`, `retrieve`, `search`, `delete`, `get_collection_stats`, `cleanup`) | ✅ Yes (hotfixed) | `self._lock` (global) | Unused but Safe |
| `src/memory/manager.py` | `MemoryManager` | `chroma_query()`, `store_chunk()` | ✅ Yes (hotfixed) | `self._chroma_lock` (global) | **Active Safe** |
| `src/core/memory/embeddings.py` | `EmbeddingManager` | `_process_single_embedding`, `_check_similar_embeddings`, `query_similar_embeddings` | ✅ Yes (hotfixed) | `self._chroma_lock` (global) | **Active Safe** |
| `src/core/memory/storage/vector_store.py` | `VectorStoreManager` | `store_memory`, `retrieve_memories`, `validate_connection`, `cleanup_old_memories` | ✅ Yes | `self.operation_locks[layer]` (per-layer) | Active Safe |

---

## Canonical Access Surface Recommendation

Currently, **three independent surfaces** provide access to ChromaDB:

1. **Adapter:** `ChromaSemanticStoreImpl` (used by `system.py` via `SheppardStorageAdapter`)
2. **Store:** `ChromaMemoryStore` (apparently unused in current runtime)
3. **Manager:** `MemoryManager` (used directly by `research/content_processor.py`)

**Risk:** Architectural drift; future developers may choose incorrectly and reintroduce unlocked access.

**Recommended consolidation:**
- Keep **adapter** as the canonical surface for V3 storage
- Deprecate `ChromaMemoryStore` (remove from codebase after verifying no internal usage)
- Refactor `MemoryManager` to use the adapter instead of raw client, then remove its direct Chroma calls
- Continue using `VectorStoreManager` for core memory system (it is already safely locked)

Alternatively, document all three as approved with explicit guidance on when to use each.

---

## Remaining Work

- [ ] Search for any **direct** `collection.query(..., query_texts=...)` calls that bypass these surfaces (outside of test code)
- [ ] Add module-level comments to each file warning about thread-safety requirement
- [ ] Create concurrency stress test that exercises all three surfaces under load

---

## Evidence

- Patch diffs applied on 2026-04-01 to `stores/chroma.py`, `manager.py`, `embeddings.py`
- All modifications add `asyncio.Lock()` and wrap critical sections
- No unprotected collection method calls remain in these files
