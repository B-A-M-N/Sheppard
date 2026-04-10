# Phase 12-G Verification Report (REOPENED FOR REMEDIATION)

**Status:** ❌ **REOPENED — LIVE CRASH VALIDATES ROOT CAUSE**
**Date:** 2026-04-01 (Reopened)
**Verifier:** Claude Code (with human oversight)

---

## Executive Summary

Phase 12-G addresses the ONNX thread-safety crash by enforcing serialization of all ChromaDB operations that may trigger embedding generation. The invariant is **mechanically proven at the unit level**, but full forensic closure of the original native crash class requires elimination of all bypass paths, most critically the `VectorStoreManager` which creates a second PersistentClient and uses per-layer locks.

**This phase is REOPENED** because the prior closure assumed all active code paths were identified and patched. A live mission crash proved the existence of an alternate, independently-locked access path that violated the core invariant.

---

## Reopening Evidence

### Live Crash (2026-04-01)

- **Scenario:** Mission "Psychology" execution
- **Failure:** Segmentation fault in `chromadb/api/rust.py:_upsert`
- **Root Cause:** Concurrent Chroma access from two independent clients with fragmented locking:
  - V3 system: `ChromaSemanticStoreImpl` with global lock (safe)
  - Cleanup path: `VectorStoreManager` via `StorageManager` with per-layer locks (unsafe)
- **Conclusion:** The invariant "All Chroma operations are serialized process-wide" was false at runtime

---

## Current State Assessment

### ✅ Correctly Guarded Paths

All these use `with_chroma_lock()` and (ideally) the canonical client:

| Component | File | Lock Used | Client Status |
|-----------|------|-----------|---------------|
| ChromaSemanticStoreImpl | `src/memory/adapters/chroma.py` | `with_chroma_lock()` | Should be injected |
| ChromaMemoryStore | `src/memory/stores/chroma.py` | `with_chroma_lock()` | Creates own (V2 legacy) |
| MemoryManager | `src/memory/manager.py` | `with_chroma_lock()` | Creates own (deprecated) |
| EmbeddingManager | `src/core/memory/embeddings.py` | `with_chroma_lock()` | Injected |

### ❌ Bypass Paths (Must Fix)

| Component | File | Lock Strategy | Problem |
|-----------|------|---------------|---------|
| **VectorStoreManager** | `src/core/memory/storage/vector_store.py` | Per-layer `asyncio.Lock()` | **NOT global**; creates own `PersistentClient` |
| **StorageManager** | `src/core/memory/storage/storage_manager.py` | Delegates to VSM | Inherits fragmentation |
| **CleanupManager** | `src/core/memory/cleanup.py` | Instantiates `StorageManager` | **Activates the bypass** |

**Activation:** `CleanupManager.perform_full_cleanup()` creates a `StorageManager` → `VectorStoreManager` → second `PersistentClient` → concurrent with V3 client → segfault.

---

## Verification Checklist for 12-G Reclosure

### Static Analysis

- [x] Global lock implementation exists (`src/memory/chroma_process_lock.py`)
- [x] All V3 paths identified and use global lock
- [ ] **No file creates its own PersistentClient except SystemManager** (AUDIT REQUIRED)
- [ ] **Every collection operation wrapped in `with_chroma_lock()`** (AUDIT REQUIRED)

### Dynamic Testing (Pre-Fix)

- [ ] **Kill test 1:** `test_vector_store_bypasses_global_lock` — Prove max_concurrent > 1 when using VectorStoreManager alongside V3 adapter (EXPECTED TO FAIL initially)
- [ ] **Kill test 2:** `test_cleanup_creates_second_client` — Prove CleanupManager instantiates a second PersistentClient (EXPECTED TO FAIL initially)
- [ ] **Kill test 3:** `test_cross_client_concurrency` — Concurrent ops from two clients can execute simultaneously (EXPECTED TO FAIL initially)

### Dynamic Testing (Post-Fix)

- [ ] **Kill tests pass** after remediation (invariant enforced)
- [ ] **Integration stress test** (`test_chroma_concurrency_memory_manager_integration`) still passes
- [ ] **Unit lock test** (`test_chroma_lock_serialization_unit`) still passes
- [ ] **Live mission replay** of previously crashing scenario succeeds
- [ ] **No regressions**: derivation (18), reasoning (74+), validator derived (9) all pass

### Code Changes Required

- [ ] `src/core/memory/storage/vector_store.py`:
  - [ ] Remove `self.client = chromadb.PersistentClient(...)`
  - [ ] Add `def __init__(self, client: Optional[chromadb.PersistentClient] = None)`
  - [ ] Replace all `async with self.operation_locks[layer]` with `async with with_chroma_lock()`
  - [ ] Remove `self.operation_locks` entirely
- [ ] `src/core/memory/cleanup.py`:
  - [ ] Accept `chroma_store: ChromaSemanticStoreImpl` parameter
  - [ ] Use V3 adapter methods instead of creating StorageManager
- [ ] `src/core/memory/storage/storage_manager.py`:
  - [ ] Propagate injected client to VectorStoreManager, OR
  - [ ] Mark class as deprecated if V2 paths are dead
- [ ] `src/core/memory/manager.py` (if still used):
  - [ ] Remove own client, accept injected
- [ ] `src/memory/stores/chroma.py` (V2 legacy):
  - [ ] Remove own client, accept injected (if kept)

---

## Kill Test Specifications

### Test File: `tests/memory/test_chroma_invariant_kill.py`

#### Test 1: `test_vector_store_bypasses_global_lock`

```python
import asyncio
import pytest
from src.memory.chroma_process_lock import with_chroma_lock, get_chroma_process_lock
from src.memory.adapters.chroma import ChromaSemanticStoreImpl
from src.core.memory.storage.vector_store import VectorStoreManager
import chromadb

@pytest.mark.asyncio
async def test_vector_store_bypasses_global_lock():
    """Prove that VectorStoreManager and V3 adapter can execute concurrently."""

    # Setup: create canonical client and adapter
    client = chromadb.PersistentClient(path="/tmp/test_chroma")
    adapter = ChromaSemanticStoreImpl(client)

    # Setup: create VectorStoreManager with its OWN client (bypass)
    vsm = VectorStoreManager()
    await vsm.initialize()  # This creates its own PersistentClient

    # Instrumentation: track concurrent lock holders
    lock = get_chroma_process_lock()
    concurrent_entries = 0
    max_concurrent = 0
    entry_times = []

    original_acquire = lock.acquire
    original_release = lock.release

    def instrumented_acquire():
        nonlocal concurrent_entries, max_concurrent
        concurrent_entries += 1
        max_concurrent = max(max_concurrent, concurrent_entries)
        entry_times.append(('acquire', asyncio.current_task()))
        return original_acquire()

    def instrumented_release():
        nonlocal concurrent_entries
        concurrent_entries -= 1
        entry_times.append(('release', asyncio.current_task()))
        original_release()

    lock.acquire = instrumented_acquire
    lock.release = instrumented_release

    try:
        # Run concurrent tasks: some use adapter (global lock), some use vsm (bypass)
        async def use_adapter():
            await adapter.index_documents([{"content": "test", "embedding": [0.1]*768}])

        async def use_vsm():
            await vsm.store_memory("key", {"input": "test", "embedding": [0.1]*768}, "episodic", "hash", 0.5)

        tasks = []
        for i in range(10):
            if i % 2 == 0:
                tasks.append(asyncio.create_task(use_adapter()))
            else:
                tasks.append(asyncio.create_task(use_vsm()))

        await asyncio.gather(*tasks)

        # ASSERTION: If both paths used the same global lock, max_concurrent should be 1
        # If bypass exists, max_concurrent could be > 1 (adapter and vsm operations overlap)
        print(f"Max concurrent lock holders: {max_concurrent}")

        # BEFORE FIX: This assertion FAILS because VSM doesn't use global lock
        # AFTER FIX: VSM will use global lock, so max_concurrent == 1
        assert max_concurrent > 1, "Invariant violation not detected — both paths may already be using global lock"

        # Additional check: verify both clients are different objects
        # (Harder to assert cleanly, but we can check by ensuring VSM created its own)
        assert vsm.client is not None
        assert vsm.client != client

    finally:
        lock.acquire = original_acquire
        lock.release = original_release
        await vsm.cleanup()
```

**Interpretation:** If `max_concurrent > 1`, the two code paths are NOT sharing the global lock → invariant violation. This test should **FAIL** before fix (assertion fails) and **PASS** after fix (VSM uses global lock, so max stays 1).

#### Test 2: `test_cleanup_creates_second_client`

```python
import pytest
from unittest.mock import patch
from src.core.memory.cleanup import CleanupManager
from src.core.memory.storage.vector_store import VectorStoreManager

def test_cleanup_creates_second_client():
    """Prove that CleanupManager instantiates a second PersistentClient."""
    import chromadb

    with patch('chromadb.PersistentClient') as mock_client_constructor:
        call_count = 0
        original = chromadb.PersistentClient

        def counting_constructor(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return original(*args, **kwargs)

        mock_client_constructor.side_effect = counting_constructor

        cleanup = CleanupManager(importance_threshold=0.5)
        # Run perform_full_cleanup (simplified, may need async)
        # This will create StorageManager -> VectorStoreManager -> PersistentClient

        assert call_count > 1, "Cleanup should trigger creation of a new PersistentClient (second client)"
```

**Interpretation:** If more than one PersistentClient is created during cleanup (one from SystemManager, one from CleanupManager's StorageManager), invariant violated.

---

## Pre-Fix Expected Results

- Kill test 1: **FAIL** (assertion `max_concurrent > 1` fails because VSM doesn't use global lock → max_concurrent stays 1 for adapter only, but we need to detect bypass differently)
- Actually, better: assert that `max_concurrent == 1` when using only adapter, but when mixing VSM it goes > 1. Test as written should detect bypass if VSM operations don't touch global lock at all. Need to refine.

Let me refine the kill test approach:

**Better kill test:** Instrument not just the global lock, but also track whether VSM calls touch it at all. If VSM never calls `with_chroma_lock()`, concurrent adapter + VSM ops will show `max_concurrent == 1` (only adapter operations enter global lock), but that doesn't prove bypass.

**Alternative:** Mock the global lock to count all acquisitions. Then:
- If both use it: total acquisitions = adapter ops + VSM ops
- If only adapter uses it: total acquisitions = adapter ops only

We can also directly check that VSM code does not import/use `with_chroma_lock()`.

**Simplest kill test:** Just grep the source files as a test:

```python
def test_vector_store_uses_global_lock():
    with open('src/core/memory/storage/vector_store.py') as f:
        content = f.read()
    assert 'with_chroma_lock' in content, "VectorStoreManager must use global lock"
```

That's a static check, not dynamic. But it's a clear kill test that fails before fix and passes after.

Let's go with a **mixed approach**:
1. Static test: Verify VSM imports/uses `with_chroma_lock`
2. Dynamic test: Verify that concurrent operations from VSM and adapter together still show `max_concurrent == 1` (meaning both are under the same lock)

The dynamic test will be more convincing.

Actually, the easiest dynamic proof: **Count how many times the global lock is acquired during concurrent operations from both sources**. If both use it, count should equal sum of all operations. If only adapter uses it, count equals adapter ops only.

Let me write a clear kill test that will fail before fix and pass after.

---

## Revised Kill Test Plan (Dynamic Proof)

```python
import asyncio
import pytest
from src.memory.chroma_process_lock import with_chroma_lock, get_chroma_process_lock
from src.memory.adapters.chroma import ChromaSemanticStoreImpl
from src.core.memory.storage.vector_store import VectorStoreManager
import chromadb

@pytest.mark.asyncio
async def test_global_lock_serializes_all_chroma_operations():
    """
    Kill test: Prove that ALL Chroma operations (including from VectorStoreManager)
    are serialized by the single global lock.

    BEFORE FIX: VectorStoreManager uses per-layer locks, not global lock.
                So concurrent adapter + VSM ops will NOT all acquire the global lock.
                Global lock acquisition count will be < total operations.

    AFTER FIX: VectorStoreManager uses global lock.
               All operations acquire global lock → total acquisitions == total ops.
    """

    # Create canonical client and both interfaces
    client = chromadb.PersistentClient(path="/tmp/test_chroma_lock_invariant")
    adapter = ChromaSemanticStoreImpl(client)
    vsm = VectorStoreManager()
    await vsm.initialize()

    # Instrument global lock acquisition counter
    lock = get_chroma_process_lock()
    acquisition_count = 0
    original_acquire = lock.acquire
    original_release = lock.release

    def counting_acquire(*args, **kwargs):
        nonlocal acquisition_count
        acquisition_count += 1
        return original_acquire(*args, **kwargs)

    lock.acquire = counting_acquire
    lock.release = original_release

    try:
        # Perform mixed workload: 5 adapter ops, 5 VSM ops, all concurrent
        adapter_ops = []
        for i in range(5):
            adapter_ops.append(asyncio.create_task(
                adapter.index_documents([{"content": f"doc{i}", "embedding": [0.1]*768}])
            ))

        vsm_ops = []
        for i in range(5):
            vsm_ops.append(asyncio.create_task(
                vsm.store_memory(f"key{i}", {"input": f"doc{i}", "embedding": [0.1]*768}, "episodic", f"hash{i}", 0.5)
            ))

        all_tasks = adapter_ops + vsm_ops
        await asyncio.gather(*all_tasks, return_exceptions=True)

        # Expected total acquisitions: 10 (all ops should go through global lock)
        print(f"Total global lock acquisitions: {acquisition_count} (expected 10)")

        # BEFORE FIX: VSM ops do NOT use global lock, so acquisition_count ~= 5 (only adapter)
        # AFTER FIX: Both use global lock, so acquisition_count == 10
        assert acquisition_count == 10, (
            f"Expected 10 acquisitions (all ops through global lock), got {acquisition_count}. "
            "If < 10, some ops bypassed the lock (invariant violation)."
        )

    finally:
        lock.acquire = original_acquire
        lock.release = original_release
        await vsm.cleanup()
```

**Why This Fails Before Fix:**
- `ChromaSemanticStoreImpl.index_documents()` uses `with_chroma_lock()` → acquires global lock
- `VectorStoreManager.store_memory()` uses `async with self.operation_locks[layer]` → does **NOT** acquire global lock
- Therefore, only 5 adapter ops increment counter; VSM ops don't → `acquisition_count == 5`
- Assertion `acquisition_count == 10` fails

**Why It Passes After Fix:**
- VectorStoreManager replaced per-layer lock with `with with_chroma_lock()`
- All 10 ops acquire global lock → `acquisition_count == 10`
- Assertion passes

This is a **clean, deterministic kill test** that directly measures the invariant.

---

## Additional Static Kill Tests

```python
def test_vector_store_does_not_create_own_client():
    """VSM should not call chromadb.PersistentClient; client should be injected."""
    import ast
    with open('src/core/memory/storage/vector_store.py') as f:
        tree = ast.parse(f.read())

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if (isinstance(node.func, ast.Attribute) and
                isinstance(node.func.value, ast.Name) and
                node.func.value.id == 'chromadb' and
                node.func.attr == 'PersistentClient'):
                pytest.fail("VectorStoreManager must not create its own PersistentClient")

def test_cleanup_manager_uses_adapter_not_storage_manager():
    """CleanupManager must not instantiate StorageManager."""
    with open('src/core/memory/cleanup.py') as f:
        content = f.read()
    assert 'StorageManager()' not in content, "CleanupManager should not create StorageManager"
    assert 'chroma_store' in content, "CleanupManager should accept chroma_store parameter"
```

---

## This Documentation

This verification document supersedes the original `PHASE-12-G-VERIFICATION.md`. It now serves as the **remediation work plan** for closing 12-G properly.

---

## Sign-off (Remediation Phase)

- [ ] **Root cause documented:** ✅
- [ ] **Kill tests written:** ❌
- [ ] **Fix implemented:** ❌
- [ ] **Kill tests pass:** ❌
- [ ] **Regression suite green:** ❌
- [ ] **Live integration verified:** ❌

---

**Next:** Implement kill tests first, then fix, then verify.
