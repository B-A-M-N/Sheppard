# ChromaDB Thread Safety Specification

## 1. Assumptions

- ChromaDB's Python API is **thread-safe** at the client level **only when embedding generation is not invoked**
- The ONNX Runtime used for embedding generation **is NOT thread-safe** and will cause memory corruption if called concurrently
- ChromaDB operations that may trigger embedding generation:
  - `collection.add()` without pre-computed embeddings (if embedding_function is set)
  - `collection.query()` with `query_texts` parameter (not pre-computed embeddings)
  - Any operation where the collection has an embedding function configured

## 2. Contract

> **All code that directly calls ChromaDB collection methods must serialize those calls with an `asyncio.Lock` to ensure only one embedding-triggering operation executes at a time within a process.**

## 3. Required Guard Primitive

```python
import asyncio

class ChromaClientWrapper:
    def __init__(self, client):
        self.client = client
        self._lock = asyncio.Lock()  # Global per-process lock

    async def safe_add(self, collection_name, **kwargs):
        async with self._lock:
            coll = self.client.get_collection(collection_name)
            coll.add(**kwargs)

    # Similarly for query, upsert, update, etc.
```

## 4. Approved Access Surfaces

The following classes are **approved** to directly access ChromaDB collections:

| Class | Location | Lock Attribute | Lock Scope |
|-------|----------|----------------|------------|
| `ChromaSemanticStoreImpl` | `src/memory/adapters/chroma.py` | `self._lock` | all methods |
| `ChromaMemoryStore` | `src/memory/stores/chroma.py` | `self._lock` | all methods |
| `MemoryManager` | `src/memory/manager.py` | `self._chroma_lock` | `chroma_query`, `store_chunk` |
| `EmbeddingManager` | `src/core/memory/embeddings.py` | `self._chroma_lock` | `_process_single_embedding`, `_check_similar_embeddings`, `query_similar_embeddings` |
| `VectorStoreManager` | `src/core/memory/storage/vector_store.py` | `self.operation_locks[layer]` | per-layer lock on all ops |

## 5. Prohibited Patterns

❌ **DO NOT:**
- Call `collection.add()` or `collection.query()` directly without holding a lock
- Instantiate `PersistentClient` in application code (only in store/adapter constructors)
- Use `asyncio.to_thread()` without also serializing with a lock
- Assume that because a method is async, it is automatically safe (the lock is still needed)

✅ **DO:**
- Route all Chroma access through one of the approved surfaces above
- Add a new lock to any new class that directly uses ChromaDB
- Document the lock with an inline comment: `# Serialize all ChromaDB operations to prevent ONNX thread-safety crashes`

## 6. Verification

To prove the invariant:

1. **Static check:** All methods that call collection methods contain `async with self._lock` or equivalent
2. **Dynamic check:** Stress test with 20+ concurrent tasks; assert no crashes and that the lock serializes (count in-critical-section ≤ 1)
3. **Regression check:** Unit test that fails if lock attribute is removed from required classes

## 7. Change History

- **2026-04-01:** Initial spec created (Phase 12-G)
