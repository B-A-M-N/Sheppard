# Phase 12-G — Chroma Concurrency Hardening

## Context & Problem Statement

### The Incident

Recurrent segfaults occurred during concurrent operations due to ONNX Runtime thread-safety violations. The root cause:

- ChromaDB's embedding generation (via ONNX) is **not thread-safe**
- Multiple async tasks were calling ChromaDB operations simultaneously from thread pool workers
- Memory corruption and process crashes resulted

### Architecture Audit Findings

Two distinct ChromaDB access surfaces exist in the codebase:

1. **Adapter layer** (`src/memory/adapters/chroma.py` — `ChromaSemanticStoreImpl`)
   - Already has `asyncio.Lock()` and serializes all operations ✅

2. **Store layer** (`src/memory/stores/chroma.py` — `ChromaMemoryStore`)
   - No lock — vulnerable (but appears unused in current runtime)

3. **MemoryManager** (`src/memory/manager.py`)
   - Directly instantiates `PersistentClient` and uses raw collections
   - Methods `chroma_query()` and `store_chunk()` had **no lock** ❌
   - This is the **active bypass** causing production crashes

4. **EmbeddingManager** (`src/core/memory/embeddings.py`)
   - Batch processing spawns concurrent tasks that call `collection.add()` and `collection.query()` directly
   - No lock — vulnerable ❌

5. **VectorStoreManager** (`src/core/memory/storage/vector_store.py`)
   - Already has per-layer `asyncio.Lock()` in `self.operation_locks` ✅

### Conclusion

The concurrency bug was not a single-point failure but an **architectural drift** where multiple code paths reached ChromaDB with inconsistent synchronization policies.

---

## Nyquist Validation Gap

| Contract Aspect | Status |
|----------------|--------|
| Thread-safety requirement stated explicitly in spec | ❌ Missing |
| Implementation enforces serialization at all access points | ❌ Incomplete |
| Concurrency stress test exists | ❌ Missing |
| Regression test preventing lock removal | ❌ Missing |
| Single canonical access surface defined | ❌ Ambiguous |

---

## Invariant (To-Be)

**All ChromaDB operations that can trigger embedding generation must be serialized per process.**

This includes:
- `collection.add()` (with auto-generated embeddings)
- `collection.query()` (with `query_texts` that trigger embedding generation)
- `collection.upsert()` / `update()` / `delete()` (safe but should be serialized for consistency)
- Any operation that may transitively invoke ONNX Runtime

Enforcement mechanism: `asyncio.Lock()` guarding all such calls at the **outermost** access surface (store/adapter boundary).

---

## Phase Goal

- Patch all unprotected ChromaDB call sites (already done in hotfix)
- Create formal specification and test suite
- Unify access surface to prevent future drift
- Verify under concurrent load
