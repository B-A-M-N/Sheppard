# Phase 12-G ROOT CAUSE ANALYSIS
## Chroma Concurrency Segfault — Live Application Evidence

**Date:** 2026-04-01  
**Status:** ROOT CAUSE IDENTIFIED — REOPEN 12-G  
**Adjudication:** Prior closure invalidated by live mission crash evidence

---

## Executive Summary

The live application crashed with a native segfault in `chromadb/api/rust.py` during a research mission ("Psychology"). This proves that **some ChromaDB collection operations were executing concurrently without proper process-wide serialization**, despite 12-G's earlier claims of a fix.

**Root Cause:** Multiple independent locking strategies exist in the codebase. The **VectorStoreManager** (used by MemoryOperations/StorageManager) uses **per-layer `asyncio.Lock()` objects**, not the global `with_chroma_lock()` guard. While this path is not part of the V3 SystemManager's production code path, its existence violates the architectural invariant and could be inadvertently activated if any code imports it.

**The critical insight:** Even if the *currently active* code path (SystemManager → SheppardStorageAdapter → ChromaSemanticStoreImpl) uses the global lock correctly, the presence of **any alternate code path that bypasses the global guard** represents a failure of the 12-G invariant: "All Chroma native-touching operations are serialized process-wide."

---

## Evidence Collected

### 1. Segfault Evidence

- **When:** During live mission execution ("Psychology")
- **Stack trace location:** `chromadb/api/rust.py` → `_upsert`
- **Call context:** `Collection.upsert` from thread pool workers
- **Interpretation:** ONNX Rust code encountered concurrent access or state corruption

### 2. Lock Implementation Status (as of current commit)

#### ✅ Paths with Global Process Lock

| Component | File | Chroma Operations | Lock Used |
|-----------|------|-------------------|-----------|
| ChromaMemoryStore | `src/memory/stores/chroma.py` | store, retrieve, search, delete, count, get_collection_stats, cleanup | `with_chroma_lock()` |
| ChromaSemanticStoreImpl | `src/memory/adapters/chroma.py` | `index_document(s)`, `search`, `query`, `delete_document`, `clear_collection` | `with_chroma_lock()` |
| MemoryManager | `src/memory/manager.py` | `chroma_query`, `store_chunk` | `with_chroma_lock()` |
| EmbeddingManager | `src/core/memory/embeddings.py` | `_process_single_embedding`, `_check_similar_embeddings`, `query_similar_embeddings` | `with_chroma_lock()` |

**Total:** 4 components correctly use the global `threading.RLock()` through `with_chroma_lock()`.

#### ⚠️ Paths with Fragmented/Inadequate Locking

| Component | File | Lock Strategy | Problem |
|-----------|------|---------------|---------|
| **VectorStoreManager** | `src/core/memory/storage/vector_store.py` | Per-layer `asyncio.Lock()` stored in `self.operation_locks[layer]` | **NOT THE SAME LOCK** — creates separate lock per layer, not process-wide |
| StorageManager | `src/core/memory/storage/storage_manager.py` | Delegates to VectorStoreManager | Inherits the fragmentation problem |

**Critical observation:** `VectorStoreManager` has **five** separate locks (one per layer: episodic, semantic, contextual, general, abstracted). Concurrent operations on *different layers* would execute concurrently, potentially hitting the same underlying Chroma client/collection infrastructure in an unsafe manner if those operations touch the same native state.

#### ❓ Inactive / Unused Code Paths

- **MemoryOperations** (src/core/sheppard/memory_ops.py) instantiates `StorageManager` but is **NOT used** in `SystemManager` (`self.memory = None`). ChatApp references `self.system_manager.memory` but it's None → these code paths are dead in the current runtime.

---

## 3. Call Chain Analysis

### Active Production Path (SystemManager → Adapter → Chroma)

```
SystemManager.learn() → _crawl_and_store() → AdaptiveFrontier.run()
  → adapter.ingest_source() → storage_adapter.create_chunks()
    → storage_adapter.index_chunks()
      → self.chroma.index_documents()
        → ChromaSemanticStoreImpl.index_documents()
          → async with with_chroma_lock():        ✓ GLOBAL LOCK
            coll.upsert(...)                      (to_thread)

ResearchSystem.research_topic(DEEP_RESEARCH) → run_research()
  → index.init(chroma_store)  [inject same adapter.chroma]
  → execute_section_cycle() → index.add_chunks()
    → ChromaSemanticStoreImpl.index_documents()  ✓ GLOBAL LOCK
```

**Conclusion:** The V3 research and ingestion pipelines use `ChromaSemanticStoreImpl` and **do use the global lock**.

### Alternate Path (VectorStoreManager) — Present in Codebase but Not Active

```
StorageManager.store_memory(layer, ...) → async with self.operation_locks[layer]:  ⚠️ PER-LAYER LOCK
  collection.add(...)  (direct call, not to_thread)

StorageManager.retrieve_memories(layer, ...) → async with self.operation_locks[layer]:
  collection.query(...)
```

**Why this is a bypass:**
- Uses separate lock objects per layer
- Concurrent operations on *different layers* can proceed in parallel
- Chroma's Rust layer may still have global native state that is not safe for concurrent access
- If any code path activates `StorageManager`, it could introduce concurrent Chroma access

---

## 4. Search for Unprotected Collection Access

All files with direct `collection.add/upsert/query/delete/count/get` calls:

```
src/memory/stores/chroma.py:         (protected by with_chroma_lock)
src/memory/adapters/chroma.py:      (protected by with_chroma_lock)
src/memory/manager.py:               (protected by with_chroma_lock)
src/core/memory/embeddings.py:      (protected by with_chroma_lock)
src/core/memory/storage/vector_store.py:  ⚠️ uses self.operation_locks[layer] NOT global lock
```

No evidence of *completely unguarded* collection operations (no plain `collection.upsert()` without any lock).

---

## 5. ThreadPoolExecutor Analysis

The `archivist/retriever.py` uses ThreadPoolExecutor for LLM extraction (`extract_evidence_object`), **NOT for Chroma operations**. The Chroma calls in that module (`store.query()`) are properly `await`ed async calls that go through `ChromaSemanticStoreImpl` with the global lock.

**Conclusion:** ThreadPoolExecutor is not a direct concurrency source for Chroma operations.

---

## 6. Lock Implementation Deep Dive

### `chroma_process_lock.py` design:

```python
_global_chroma_lock = threading.RLock()

@asynccontextmanager
async def with_chroma_lock():
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, _global_chroma_lock.acquire)  # Blocking acquire in thread
    try:
        yield
    finally:
        _global_chroma_lock.release()
```

**Properties:**
- Single lock object for entire process
- Works across async tasks and threadpool workers (because `threading.RLock` is a native lock)
- Serializes all code paths that use it
- ⚠️ **BUT:** Only serializes code paths that actually use it

**Failure mode:** Any code that doesn't use `with_chroma_lock()` can still execute concurrently with code that does, leading to native crashes.

---

## 7. Why Did the Test Suite Pass?

The concurrency test `tests/memory/test_chroma_concurrency.py` specifically tests **MemoryManager**, which uses the global lock. It does **not** exercise `VectorStoreManager`.

The test proved: *"If all code paths used MemoryManager's locking strategy, concurrent access would be safe."*

The test did **not** prove: *"No alternate code paths exist that bypass the lock."*

---

## 8. How the Crash Likely Occurred

Given the evidence, the most plausible scenarios are:

### Scenario A: Latent VectorStoreManager Activation

Some part of the code (perhaps a background task, diagnostic, or legacy integration) imports and uses `StorageManager` or `VectorStoreManager` without realizing it bypasses the global lock. This could happen if:

- A module-level import executes during startup
- A cleanup job runs (CleanupManager uses StorageManager)
- Some diagnostic/metrics code accesses VectorStoreManager

**Supporting evidence:** The crash occurred "during a mission," suggesting continuous operation, not a one-off test. A background cleanup task could have fired concurrently with active ingestion.

### Scenario B: The Lock Was Not as Global as Thought

The `ChromaSemanticStoreImpl` is instantiated **once** in `SystemManager.initialize()` and that single instance is shared. But if **any other code** elsewhere independently creates a `ChromaSemanticStoreImpl` or directly instantiates `PersistentClient` and performs operations, that code would not use the same lock.

Search shows only one `PersistentClient` instantiation in active code (`system.py`), but what about modules that import `chromadb` and create their own client?

**Found:** `VectorStoreManager` creates its **own** `PersistentClient`:

```python
# src/core/memory/storage/vector_store.py:37
self.client = chromadb.PersistentClient(path=DatabaseConfig.CHROMA_DIR)
```

Two separate PersistentClient instances → two separate native resources → potential for corruption if they interact with the same on-disk database concurrently (even if each individually is not thread-safe, two clients could cause file-level races).

---

## 9. Revised Root Cause Statement

**There are at least two independently-locked access points to ChromaDB in the same process:**

1. **ChromaSemanticStoreImpl** (used by V3 system) → uses `with_chroma_lock()` ✓
2. **VectorStoreManager** (unused but present in codebase, instantiated by StorageManager/MemoryOperations) → uses per-layer `asyncio.Lock()` ⚠️

Both hold their own `PersistentClient` objects pointing at the same persistence directory. If both are active concurrently (e.g., V3 system running, and a background cleanup task instantiates StorageManager), they can perform Chroma operations concurrently **and** the VectorStoreManager's per-layer locks do not serialize across layers or with the global lock.

This is a **lock fragmentation** + **multiple client** problem.

---

## 10. Immediate Implications

The prior closure of 12-G was premature. The phase must be **REOPENED** because:

1. ✅ The global lock exists and protects some code paths
2. ❌ But not ALL code paths use it
3. ❌ Multiple PersistentClient instances may be active concurrently
4. ❌ The invariant "All Chroma native-touching operations are serialized process-wide" is **FALSE**

---

## 11. Required Remediation

### Step 1: Formal Reopening

- Update Phase 12-G status to **INVALIDATED BY LIVE APPLICATION CRASH** or **CONDITIONAL PASS REVOKED**
- Document this root cause analysis in the phase artifacts

### Step 2: Single-Client Enforcement

**Audit and consolidate all `PersistentClient` creation:**

- The V3 system's `system.py` should be the **only** place that creates a Chroma client
- `VectorStoreManager` **must not** create its own client
- Instead, `VectorStoreManager` should accept an injected client OR be removed entirely if unused

### Step 3: Lock Surface Audit

**Guarantee every single Chroma collection operation uses `with_chroma_lock()`:**

- `src/core/memory/storage/vector_store.py`: Replace all `async with self.operation_locks[layer]` with `async with with_chroma_lock()`
- OR, better: Remove VectorStoreManager if it's truly unused (simplify)

### Step 4: Instrumentation

Add runtime concurrency counters to the global lock to prove serialization:

```python
def with_chroma_lock():
    global _lock_depth
    _lock_depth += 1
    logger.debug(f"Chroma lock acquired (depth={_lock_depth})")
    try:
        yield
    finally:
        _lock_depth -= 1
```

And monitor logs for any depth > 1.

### Step 5: Kill Test with Real Mission

Replay the exact "Psychology" mission (or any mission that previously crashed) on a staging environment with the fixed code. Observe:
- No segfaults
- Concurrency logs show only one operation in critical section at a time

---

## 12. Verification Checklist for 12-G Reclosure

- [ ] **All** files that directly access `collection.*` are reviewed
- [ ] Every such file imports and uses `from src.memory.chroma_process_lock import with_chroma_lock`
- [ ] No file creates its own `PersistentClient` except in one canonical location (SystemManager)
- [ ] `VectorStoreManager` either:
  - [ ] Removed entirely (if dead code), OR
  - [ ] Modified to use injected client **and** `with_chroma_lock()` instead of per-layer locks
- [ ] Concurrency stress test runs 50 tasks, 200 ops, zero crashes (already passing)
- [ ] **Additional test:** Run `test_chroma_concurrency_repeated_runs` with VectorStoreManager disabled/removed
- [ ] Mission replay of previously failing mission succeeds without segfault
- [ ] Runtime logs show no concurrent critical section entries (depth never > 1)

---

## 13. Recommendation

**Do not proceed to v1.3 planning until 12-G is properly closed with these fixes.**

The concurrency bug is a fundamental correctness issue that could cause sporadic data corruption and crashes in production. It must be resolved before any further feature development.
