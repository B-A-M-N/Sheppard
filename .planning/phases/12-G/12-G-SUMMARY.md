# Phase 12-G Summary — Chroma Concurrency Hardening (GLOBAL LOCK)

**Status:** ❌ **REOPENED — PRIOR CLOSURE INVALIDATED BY LIVE APPLICATION CRASH**
**Date:** 2026-04-01 (Reopened)
**Milestone:** v1.2 — Derived Insight & Report Excellence Layer

---

## IMPORTANT NOTICE: PHASE REOPENED

**12-G is hereby REOPENED** due to compelling evidence from a live application crash during mission execution.

**Prior Closure Invalidated:** The phase was originally marked "FULL PASS" on 2026-04-01. However, a subsequent live mission ("Psychology") experienced a native segmentation fault in `chromadb/api/rust.py:_upsert`, proving that the invariant "All Chroma native-touching operations are serialized process-wide" was **false** in the running system.

**Current Status:** Forensic analysis completed. Root cause identified. Remediation in progress.

---

## Original Problem Statement (from initial 12-G)

The system experienced intermittent segmentation faults during embedding generation and ChromaDB operations under concurrent async load. Root cause: ONNX runtime thread-safety violations when multiple threads simultaneously accessed native embedding components through unsynchronized ChromaDB calls.

**Initial attempt:** Added per-instance `asyncio.Lock()` to three classes.
**Failure:** Live mission (`test_searx_psychology`) still segfaulted in `chromadb/api/rust.py:_upsert` from a threadpool worker.

**Root cause:** `asyncio.Lock()` only serializes within the event loop thread. When work is dispatched to `ThreadPoolExecutor` (via `run_in_executor` or `asyncio.to_thread`), multiple threads could concurrently enter Chroma's Rust layer, causing native memory corruption.

---

## Solution Implemented (Original Fix): Process-Wide Chroma Guard

**Invariant:** *All ChromaDB collection operations (add, upsert, query, delete, get) must execute under a single global threading lock.*

Implemented:

- `src/memory/chroma_process_lock.py`: Global `threading.RLock()` with async context manager `with_chroma_lock()`
- Updated **all** Chroma access points to use the global guard:
  - `src/memory/adapters/chroma.py` (new adapter, now sole entry point for V3)
  - `src/memory/manager.py` (MemoryManager)
  - `src/core/memory/embeddings.py` (EmbeddingManager)
  - `src/memory/stores/chroma.py` (ChromaMemoryStore — V2 legacy store)

Removed per-instance `asyncio.Lock()` members that were insufficient.

---

## Evidence That Original Fix Was Incomplete

### Live Crash Evidence

- **When:** During live mission execution ("Psychology")
- **Stack trace location:** `chromadb/api/rust.py` → `_upsert`
- **Call context:** `Collection.upsert` from thread pool workers
- **Interpretation:** ONNX Rust code encountered concurrent access or state corruption

### Root Cause of Bypass

**There are at least two independently-locked access points to ChromaDB in the same process:**

1. **ChromaSemanticStoreImpl** (used by V3 system) → uses `with_chroma_lock()` ✓
2. **VectorStoreManager** (used by CleanupManager/MemoryOperations) → uses per-layer `asyncio.Lock()` ⚠️

Both hold their own `PersistentClient` objects pointing at the same persistence directory. If both are active concurrently (e.g., V3 system running, and a background cleanup task instantiates StorageManager), they can perform Chroma operations concurrently **and** the VectorStoreManager's per-layer locks do not serialize across layers or with the global lock.

This is a **lock fragmentation** + **multiple client** problem.

### Why the Original Test Suite Passed

The concurrency test `tests/memory/test_chroma_concurrency.py` specifically tests **MemoryManager**, which uses the global lock. It does **not** exercise `VectorStoreManager`.

The test proved: *"If all code paths used MemoryManager's locking strategy, concurrent access would be safe."*

The test did **not** prove: *"No alternate code paths exist that bypass the lock."*

---

## Current Invariant Violation

**Claimed Invariant (Original 12-G):** All active Chroma access paths are serialized by `with_chroma_lock()`.

**Actual Invariant (Post-Crash Analysis):** ❌ **FALSE**

**Verified Bypass Paths:**

| Component | File | Lock Strategy | PersistentClient? | Status |
|-----------|------|---------------|-------------------|---------|
| ChromaSemanticStoreImpl | adapters/chroma.py | `with_chroma_lock()` | Injected (single) | ✓ Active V3 path |
| MemoryManager | manager.py | `with_chroma_lock()` | Own instance (deprecated) | ✓ Locked but unused |
| EmbeddingManager | embeddings.py | `with_chroma_lock()` | Injected | ✓ |
| ChromaMemoryStore | stores/chroma.py | `with_chroma_lock()` | Own instance (V2) | ✓ |
| **VectorStoreManager** | storage/vector_store.py | **Per-layer `asyncio.Lock()`** | **Own instance** | **❌ BYPASS** |
| StorageManager | storage/storage_manager.py | Delegates to VSM | N/A (delegates) | **❌ Inherits bypass** |

**Critical Bypass:** `VectorStoreManager` creates its **own** `PersistentClient` and uses **five separate** `asyncio.Lock()` objects (one per layer). Concurrent operations on different layers can proceed in parallel, violating process-wide serialization.

**Activation Path:** `CleanupManager.perform_full_cleanup()` instantiates `StorageManager` directly, which instantiates `VectorStoreManager`. If cleanup runs during active system operation, two independent PersistentClient instances access the same Chroma database concurrently → segfault.

---

## Remediation Plan (12-G Reclosure Requirements)

### Step 1: Audit and Remove Duplicate PersistentClient Instances

**Action:** Ensure only ONE `PersistentClient` exists per process.

- [ ] **SystemManager** is the canonical creator (already true for V3)
- [ ] **VectorStoreManager** must NOT create its own client
- [ ] **MemoryManager** (deprecated) should either accept injected client or be removed
- [ ] **ChromaMemoryStore** (V2 legacy) should accept injected client or be removed

### Step 2: Unify Locking Surface

**Invariant Upgrade:**
> **No Chroma client, collection, or native-touching operation may exist outside the single canonical Chroma runtime surface guarded by `with_chroma_lock()`.**

All code that directly calls `collection.add()`, `collection.upsert()`, `collection.query()`, `collection.get()`, `collection.delete()`, or `client.get_or_create_collection()` must:
1. Use the injected client from SystemManager, OR
2. If creating own client (legacy), still wrap ALL operations in `with_chroma_lock()` — but prefer client injection

**Required Modifications:**

- [ ] `VectorStoreManager`:
  - Remove `self.client = chromadb.PersistentClient(...)`
  - Add `client` parameter to `__init__(self, client: Optional[chromadb.PersistentClient] = None)`
  - If client provided, use it; if not, fallback to creating own (but log warning)
  - Replace **ALL** `async with self.operation_locks[layer]` with `async with with_chroma_lock()`
  - Remove `self.operation_locks` dict entirely

- [ ] `StorageManager`:
  - Pass injected client to VectorStoreManager if used
  - Consider deprecating entire class if V2 code paths are dead

- [ ] `CleanupManager`:
  - Accept `chroma_store: ChromaSemanticStoreImpl` parameter instead of creating StorageManager
  - Use `chroma_store.cleanup_collection()` or similar V3 method
  - **Do NOT instantiate StorageManager** bypassing the global lock

- [ ] `MemoryManager` (if still used anywhere):
  - Remove own client creation
  - Accept injected client
  - Ensure all Chroma ops use `with_chroma_lock()` (seems already done, but verify)

### Step 3: Repo-Wide Audit for Direct Chroma Access

Run grep for direct collection operations to ensure none bypass the lock:

```bash
grep -rn "collection\.\(add\|upsert\|query\|get\|delete\|update\|get_or_create_collection\)" src/ --include="*.py"
```

Verify each hit:
- [ ] Is inside `with_chroma_lock()` context?
- [ ] Uses the canonical client?
- [ ] If not, fix or remove

### Step 4: Kill Test Writing (Before Fix)

**Purpose:** Prove the invariant violation exists and is detectable via concurrency instrumentation.

**Test Design:**
- [ ] Create `tests/memory/test_chroma_invariant_kill.py`
- [ ] Test: `test_vector_store_bypasses_global_lock`
  - Instantiates a real `ChromaSemanticStoreImpl` (with global lock)
  - Instantiates a real `VectorStoreManager` (with per-layer locks and own client)
  - Launches concurrent tasks that alternately use both interfaces
  - Instruments the global lock's concurrency counter
  - **Asserts:** Both interfaces can access Chroma concurrently (max_inflight > 1), proving lock fragmentation
  - May also check that two separate PersistentClient instances exist

- [ ] Test: `test_cleanup_creates_second_client`
  - Instantiates `CleanupManager` and calls `perform_full_cleanup()`
  - Intercepts `chromadb.PersistentClient` constructor calls
  - **Asserts:** More than one PersistentClient can be created in the same process
  - **Asserts:** CleanupManager uses VectorStoreManager/StorageManager

**Expected Result Before Fix:** Tests FAIL (invariant violation demonstrated)
**Expected Result After Fix:** Tests PASS (only one client, all paths use global lock)

### Step 5: Verification After Fix

- [ ] All existing tests continue to pass (derivation, reasoning, validator, etc.)
- [ ] New kill tests pass
- [ ] Concurrency stress test (`test_chroma_concurrency_memory_manager_integration`) still passes
- [ ] Repo audit shows no unprotected Chroma access
- [ ] Live mission replay of "Psychology" mission succeeds without segfault
- [ ] Runtime instrumentation (if added) shows `max_concurrent == 1` even with cleanup running

---

## Updated Files Changed (Remediation)

| File | Change Required | Status |
|------|-----------------|--------|
| `src/core/memory/storage/vector_store.py` | Remove own client, use injected; replace per-layer locks with `with_chroma_lock()` | ❌ To do |
| `src/core/memory/storage/storage_manager.py` | Propagate injected client, or deprecate | ❌ To do |
| `src/core/memory/cleanup.py` | Accept chroma_store instead of creating StorageManager | ❌ To do |
| `tests/memory/test_chroma_invariant_kill.py` | New kill test | ❌ To do |
| `src/core/memory/manager.py` | Remove own client, accept injected (if still used) | ⚠️ Optional (deprecated) |
| `src/memory/stores/chroma.py` | Remove own client, accept injected (V2 legacy) | ⚠️ Optional (if unused) |

---

## Reclosure Criteria

Phase 12-G will be marked COMPLETE when:

1. ✅ **Kill tests** demonstrate the invariant violation before fix, and pass after fix
2. ✅ **Single-client invariant** enforced: only one PersistentClient per process (SystemManager's)
3. ✅ **Global lock invariant** enforced: all Chroma operations use `with_chroma_lock()`
4. ✅ **Audit complete**: no unprotected collection access remains
5. ✅ **No regressions**: all adjacent test suites pass (derivation 18, reasoning 74+, etc.)
6. ✅ **Live mission verified**: previously crashing mission now completes without segfault

---

## Final Verdict (Pending Remediation)

**Phase 12-G — REOPENED FOR FORENSIC REMEDIATION**

The root cause identified in the original 12-G analysis was correct (need process-wide lock), but the fix application was incomplete due to an alternate code path (`VectorStoreManager` → `CleanupManager`) that created a second PersistentClient and used per-layer locks instead of the global guard.

**Remediation is straightforward** but must be executed with kill-test First to establish before/after proof.

**Estimated effort:** 2-4 hours (assuming VectorStoreManager is truly unused by V3 and can be simply removed or refactored to delegate to the canonical adapter).

---

## Next Steps (Immediate)

1. Write kill test (prove invariant violation)
2. Run kill test (confirm it fails)
3. Implement fix (unify client + lock)
4. Run kill test (confirm it passes)
5. Run full test suite
6. Live mission replay (if feasible)
7. Update this document with FINAL PASS

---
