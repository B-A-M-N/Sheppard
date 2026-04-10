# Phase 12-G PLAN — Chroma Concurrency Hardening

## Objective

Enforce the invariant: **All ChromaDB operations that can trigger embedding generation are serialized via asyncio.Lock.**

## Scope

- **In-Scope:** All code that directly calls ChromaDB client methods (`add`, `query`, `upsert`, `update`, `delete`, `get`, `count`)
- **Out-of-Scope:** Indirect calls through already-locked adapters or stores (assume they are correct)
- **Critical Path:** `MemoryManager`, `EmbeddingManager`, `ChromaMemoryStore`

---

## Implementation Tasks

### Task 1 — Patch Active Bypasses (Already Completed)

- [x] Add `self._lock = asyncio.Lock()` to `ChromaMemoryStore`
- [x] Wrap all public methods (`store`, `retrieve`, `search`, `delete`, `get_collection_stats`, `cleanup`) with `async with self._lock`
- [x] Add `self._chroma_lock = asyncio.Lock()` to `MemoryManager`
- [x] Wrap `chroma_query()` and `store_chunk()` with lock
- [x] Add `self._chroma_lock = asyncio.Lock()` to `EmbeddingManager`
- [x] Wrap `_process_single_embedding`, `_check_similar_embeddings`, `query_similar_embeddings` with lock

**Verification:** Code review confirms lock present on all risky methods.

---

### Task 2 — Audit & Consolidate Access Surface

- [ ] Scan repository for any remaining direct ChromaDB client usage
- [ ] Identify any code that bypasses `ChromaSemanticStore` or `ChromaMemoryStore`
- [ ] Document which surface is canonical
- [ ] Add module-level comment at top of each file that directly uses ChromaDB: "All ChromaDB operations must be serialized with a lock"
- [ ] Ensure no code directly instantiates `PersistentClient` except in initialization of stores/adapters

**Deliverable:** `CHROMA_ACCESS_SURFACE_AUDIT.md` with findings and remediation plan for any remaining bypasses.

---

### Task 3 — Create Concurrency Stress Test

- [ ] Write test `tests/memory/test_chroma_concurrency.py`
- [ ] Spawn 20-50 concurrent async tasks performing ChromaDB operations (indexing + search)
- [ ] Run long enough to ensure no segfaults (minimum 100 total operations across tasks)
- [ ] Add instrumentation to prove serialized execution (e.g., count concurrent critical section entries, assert <=1 at any time)
- [ ] Run under pytest with `-n auto` if possible, or pure asyncio

**Deliverable:** `tests/memory/test_chroma_concurrency.py` + test passes reliably.

---

### Task 4 — Write Regression Test for Lock Presence

- [ ] Test that `ChromaMemoryStore` has `_lock` attribute
- [ ] Test that `MemoryManager` has `_chroma_lock` attribute
- [ ] Test that `EmbeddingManager` has `_chroma_lock` attribute
- [ ] This prevents accidental lock removal in refactors

**Deliverable:** Existing or new test file.

---

### Task 5 — Document Canonical Pattern

Create `CHROMA_THREAD_SAFETY_SPEC.md`:

- State the thread-safety assumption (ONNX not thread-safe)
- Declare the required guard primitive (`asyncio.Lock`)
- Show code pattern for correct implementation
- List all approved access surfaces (adapter, store, manager with lock)
- Prohibit raw `collection.*` calls outside approved surfaces

---

### Task 6 — Verification Checklist

Create `PHASE-12-G-VERIFICATION.md`:

- [ ] All Chroma operations in `MemoryManager` are locked
- [ ] All Chroma operations in `EmbeddingManager` are locked
- [ ] All Chroma operations in `ChromaMemoryStore` are locked
- [ ] No code directly instantiates `PersistentClient` except in store/adapter constructors
- [ ] Concurrency stress test passes (no crashes, serialized execution)
- [ ] All existing tests continue to pass (no regressions)
- [ ] Lock attributes exist in all required classes

---

## Acceptance Criteria

1. **Invariant holds:** No segfaults under concurrent load in staging environment
2. **Concurrency test passes** with 50 tasks, 200 operations, zero crashes
3. **No unprotected Chroma call sites** remain outside the three locked classes
4. **Artifacts created:** `CHROMA_THREAD_SAFETY_SPEC.md`, `CHROMA_ACCESS_SURFACE_AUDIT.md`, `PHASE-12-G-VERIFICATION.md`
5. **Documentation updated:** Any developer doc that describes Chroma usage includes the lock requirement

---

## Rollback Plan

If issues arise:
- The lock additions are non-breaking API changes
- Revert the lock code ONLY if a better guard primitive is designed
- Keep the concurrency stress test to validate any alternative

---

## Notes

- This is a **stability-critical** phase; it blocks further synthesis work until resolved
- The patch is already applied; this phase formalizes and verifies
- The goal is not just a quick fix but establishing an **enforceable architectural contract**
