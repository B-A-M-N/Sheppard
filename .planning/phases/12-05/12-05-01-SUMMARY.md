# Phase 12-05 Summary: Contradiction system V3 upgrade

**Status:** ✅ Completed (CONTR-01 through CONTR-04)
**Date:** 2026-03-31

## Changes

### Files modified:

| File | Change |
|------|--------|
| `src/research/reasoning/assembler.py` | Added `_get_unresolved_contradictions` method with direct PG query; removed `memory.get_unresolved_contradictions` dependency |
| `src/research/archivist/synth_adapter.py` | Enhanced `_format_evidence_brief` to include atom ID citations ([A001], [A002]) for contradiction claims |
| `src/research/reasoning/assembler.py` | Removed `if self.memory is not None:` gate — V3-native path always active |

## CONTR Requirements

| Requirement | Status | Evidence |
|-------------|--------|----------|
| CONTR-01 | ✅ Complete | No `memory.get_unresolved_contradictions` calls in assembler.py |
| CONTR-02 | ✅ Verified | FK via `JOIN knowledge_atoms a ON a.id = c.atom_a_id` in query |
| CONTR-03 | ✅ Complete | Archivist prompt includes `IDENTIFIED CONTRADICTIONS IN EVIDENCE` block with atom ID citations |
| CONTR-04 | ✅ Complete | No validator changes — citations reference atom IDs directly |

## Implementation Details

### CONTR-01: V3-Native Retriever
```python
async def _get_unresolved_contradictions(self, mission_id: str, limit: int = 5):
    pool = getattr(self, "_contradiction_pool", None)
    if pool is None:
        pool = await asyncpg.create_pool(dsn, min_size=1, max_size=2)
        self._contradiction_pool = pool
    # Direct PG query against contradictions table
    # Returns: description, atom_a_global_id, atom_b_global_id, atom_a_content, atom_b_content
```

### CONTR-03: Archivist Prompt Enhancement
```
### IDENTIFIED CONTRADICTIONS IN EVIDENCE:
- CONFLICT: [description]
  CLAIM A: [atom content] [A001]
  CLAIM B: [atom content] [A002]
```

### CONTR-04: Validator Compatibility
Validator unchanged — works because:
- Contradictions reference underlying atom global IDs
- Validator checks `[A#]` citations against `packet.atom_ids_used`
- Contradictions' atom IDs are already in `packet.atom_ids_used` (from atom retrieval)

## Guardrail Results

| Check | Result |
|-------|--------|
| Phase 11 invariants | 8/8 passed |
| Full guardrail suite | 99/99 passed |
| No regression in synthesis | ✅ |
| No memory dependency removed | ✅ (write path preserved) |

## Notes

- Contradictions data dependent on extraction pipeline producing contradiction records
- If `contradictions` table is empty, code path is dormant (correctly returns `[]`)
- Pool initialized lazily on first contradiction retrieval call
