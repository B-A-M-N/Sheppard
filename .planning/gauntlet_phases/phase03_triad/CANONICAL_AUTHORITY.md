# Canonical Authority Lock — Phase 03.0

**Date**: 2026-03-27
**Status**: DECISION — LOCKED
**Phase**: 03.0 (precedes Triad Enforcement)

---

## Mission

Establish a single source of truth for the V3 system and eliminate runtime ambiguity between V2 and V3 data stores.

---

## Decisions (Non-Negotiable)

### 1. V2 MemoryManager Removal

**Decision**: `MemoryManager` is **removed** from the V3 runtime.

- `SystemManager.initialize()` will **no longer instantiate** `self.memory`
- All V3 code paths **must not** import or call `MemoryManager` methods
- `HybridRetriever` (which depends on `MemoryManager`) is **deleted** from the V3 codebase

**Enforcement**:
- No `from src.memory.manager import MemoryManager` in any V3 component
- No `self.memory` usage in `SystemManager` or downstream V3 classes

---

### 2. V2 Data Fate

**Decision**: V2 database (`semantic_memory`) is **archived**.

- May contain valuable historical research
- **Not** part of runtime dependency
- Optional one-way migration script may copy data into V3 schema, but:
  - Migration is manual, off-line
  - System does not read V2 during normal operation

**Enforcement**:
- Connection string `POSTGRES_DSN` for V2 remains in `.env` for archive access only
- V3 adapter uses **only** `DB_URLS["sheppard_v3"]`

---

### 3. Fallback Policy

**Decision**: **NO FALLBACKS** — V3 operations fail loudly if canonical data is missing.

- If mission/source/atom not found in V3 → error, not V2
- No silent degradation
- No “best effort” mixed-read strategies

**Enforcement**:
- No conditional `if not v3_result: fallback_to_v2(...)`
- Missing data raises explicit `CanonicalDataMissingError`

---

### 4. HybridRetriever Disposition

**Decision**: **REMOVE** `HybridRetriever` from V3 codebase.

Rationale:
- Encodes V2 assumptions (queries `memory.lexical_search_atoms`, `memory.chroma_query`, etc.)
- Adapting it risks leaking V2 semantics
- V3 uses `V3Retriever` with clean adapter-based queries

**Action**:
- Delete or move to legacy directory (outside `src/research/reasoning/`)
- Ensure no imports remain

---

### 5. Existing V2 Data

**Decision**: **ARCHIVE + OPTIONAL MIGRATION**.

- V2 data left as is; not imported automatically
- If migration is desired:
  - Write standalone script: `scripts/migrate_v2_to_v3.py`
  - Run once, manually
  - Validate against V3 schema constraints
  - Do **not** run concurrently with live system

---

### 6. Compatibility Shim

**Decision**: **NONE** in core system.

If external tools need V2-compatible interface:
- Build separate read-only service that queries V3
- Expose V2-like API endpoints
- Keep it out of the V3 triad codebase

---

## Enforcement Rules (Code-Level)

All V3 components **must**:

1. **Initialize only V3 adapter**:
   ```python
   # SystemManager
   self.adapter = SheppardStorageAdapter(...)  # V3 only
   # NO: self.memory = MemoryManager()
   ```

2. **Query only V3 knowledge**:
   - Use `V3Retriever` (not `HybridRetriever`)
   - All read methods go through `self.adapter` (Postgres/Chroma)

3. **Write only to V3 canonical**:
   - `adapter.upsert_*`, `adapter.create_*` methods
   - No direct SQL against V2 DB

4. **Handle missing data explicitly**:
   - Raise `CanonicalDataMissingError` or similar
   - Do not attempt fallback

---

## Verification Checklist

- [ ] `SystemManager.initialize` does not create `MemoryManager` instance
- [ ] No imports of `src.memory.manager` in V3 components
- [ ] `HybridRetriever` removed or placed outside active code paths
- [ ] All queries use `V3Retriever` or adapter methods
- [ ] No conditional fallback to V2 in any code path
- [ ] System boots and runs with only V3 adapter connected
- [ ] Tests pass with V3-only storage

---

## Rationale

> *“You are not upgrading V2. You are replacing the authority layer.”*

Any residual V2 coupling:
- Creates undefined behavior
- Makes triad enforcement impossible to verify
- Invites silent data divergence
- Dooms future correctness

Lock authority now or never.

---

## Next Steps

1. Implement code changes listed above
2. Run integration tests to confirm V3-only operation
3. **Then** proceed to Phase 03 (Triad Contract Audit) with clean surface

---

**Lock effective immediately. All subsequent work must conform.**
