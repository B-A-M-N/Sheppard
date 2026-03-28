# Phase 03 — Gap Closure Plan

**Based on**: `PHASE-03-VERIFICATION.md` — FAIL
**Objective**: Remediate triad contract violations to achieve PASS
**Date**: 2026-03-27

---

## Identified Gaps

1. **Archivist Direct Chroma Write** (Hard Fail)
   - `src/research/archivist/index.py` writes to `archivist_research` Chroma collection without canonical Postgres record and bypassing StorageAdapter.
2. **Redis Queue Mismatch** (Process Bug)
   - `crawler.py` enqueues to `queue:acquisition`; `system.py` dequeues from `queue:scraping`.

---

## Remediation Tasks

### Task G1: Refactor Archivist to Triad-Compliant Access (Preserve Function)

**Goal**: Eliminate direct Chroma access while preserving Archivist's search/compilation behavior.

**Decision**: Archivist provides meaningful research capability, so we keep it. The violation is the bypass of StorageAdapter, not Archivist's existence.

**Actions**:

1. **Extend ChromaSemanticStore interface** (`src/memory/storage_adapter.py` and `src/memory/adapters/chroma.py`):
   - Add `async def clear_collection(self, name: str) -> None`
   - Add optional `embeddings` parameter to `index_document` and `index_documents` to support precomputed embeddings.
   - Implement in `ChromaSemanticStoreImpl`.

2. **Refactor Archivist to use injected ChromaSemanticStore**:
   - Remove `chromadb.PersistentClient` creation from `src/research/archivist/index.py`.
   - Add `init(chroma_store)` and store globally.
   - Change `clear_index` and `add_chunks` to be async and use `chroma_store` methods.
   - Change `src/research/archivist/retriever.py` to use `chroma_store.query()` directly; make `search` async.
   - Update `src/research/archivist/loop.py`:
     - Make `run_research`, `execute_section_cycle`, `fill_data_gaps` async.
     - Pass `chroma_store` through to index/retriever calls.
     - Replace all `index.*` and `retriever.search` calls with async versions.

3. **Update call site** in `src/research/system.py`:
   - Modify `ResearchSystem` to accept `chroma_store` (or adapter) in constructor.
   - In `generate_findings`, replace `await loop.run_in_executor(None, run_research, ...)` with `await run_research(..., chroma_store=self.chroma_store, ...)`.

4. **Wire dependencies** in `src/core/system.py`:
   - When initializing `ResearchSystem` (if used), pass `self.adapter.chroma` as the chroma_store.

**Acceptance**:
- No file in `src/research/archivist/` contains `chromadb.Client` or `PersistentClient` instantiation.
- All Chroma operations in Archivist use `ChromaSemanticStore` methods (`index_documents`, `query`, `clear_collection`).
- The Archivist collection `archivist_research` remains and continues to store research data using precomputed embeddings.
- Existing Archivist functionality tests (if any) pass; research reports generate as before.
- Grep for `chromadb.Client(` in `src/research/archivist/` returns empty.

---

### Task G2: Align Redis Queue Names

**Goal**: Ensure enqueued jobs are consumed.

**Actions**:

- Option A (preferred): Change enqueue in `src/research/acquisition/crawler.py:240` from:
  ```python
  await system_manager.adapter.enqueue_job("queue:acquisition", payload)
  ```
  to:
  ```python
  await system_manager.adapter.enqueue_job("queue:scraping", payload)
  ```

- Option B: Add a second vampire worker loop that listens on `queue:acquisition` and processes same as scraping queue.

**Acceptance**:
- All enqueued URLs for slow-lane are eventually dequeued and processed.
- No jobs are lost due to queue name mismatch.

---

### Task G3: Verify Gap Closure

**Goal**: Re-run triad audit to confirm violations resolved.

**Actions**:
1. After implementing G1 and G2, re-execute Phase 03 audit:
   - Run `gsd:validate-phase 3` or manually produce new `MEMORY_CONTRACT_AUDIT.md`
2. Confirm:
   - No direct Chroma writes
   - No Redis queue issues
   - All writes classified correctly
3. Update `PHASE-03-VERIFICATION.md` with PASS verdict.

---

## Implementation Status

✅ **G1 completed**: Archivist refactored to use injected ChromaSemanticStore; all direct Chroma access removed.
✅ **G2 completed**: Redis queue names aligned; `crawler.py` enqueues to `queue:scraping`.
⏳ **G3 pending**: Re-run triad audit to verify.

---

## Success Criteria for Gap Closure

- [x] `src/research/archivist/index.py` no longer writes directly to Chroma
- [x] All enqueue operations target a queue that has consumers
- [ ] Re-audit shows zero hard violations
- [ ] PHASE-03-VERIFICATION.md updated to PASS

---

**Next: Run Phase 03 verification audit.**
