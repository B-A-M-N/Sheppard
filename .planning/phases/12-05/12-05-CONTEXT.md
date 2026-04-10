# Phase 12-05: Contradiction system V3 upgrade — Context

**Gathered:** 2026-03-31
**Status:** Ready for planning
**Source:** Direct user decisions (authoritative input)

---

<domain>

## Phase Boundary

**Goal:** Replace legacy `memory.get_unresolved_contradictions` dependency with V3 adapter-level contradiction queries. Wire contradictions into synthesis flow. Verify FK attribution. No schema changes. Read-path only.

**Requirements Addressed:** CONTR-01, CONTR-02, CONTR-03, CONTR-04

---

</domain>

<decisions>

## Implementation Decisions (LOCKED)

### CONTR-01 — Retrieval Path

- **Replace** `memory.get_unresolved_contradictions(mission_id, limit=5)` call
- **Use** V3 adapter-level direct DB query (PG) against `knowledge.contradictions` table
- **Do NOT** route through `V3Retriever` (contradictions are relational pairs, not semantic targets)
- **Do NOT** create a new contradiction retriever class
- **Scope:** Read path only — write path owner stays as `memory/manager.py` for now

### CONTR-02 — Schema Status

- **Already satisfied** — `contradictions` table has `atom_a_id` and `atom_b_id` FK columns pointing to `knowledge.knowledge_atoms`
- **No migration needed**
- **Action:** Verify FK constraints exist in DB; document in verification

### CONTR-03 — Synthesis Integration

- **YES — Must update Archivist prompt** to surface contradictions
- Contradictions appear as **separate context block** in the prompt (not merged into atoms)
- Archivist should **acknowledge conflicts** but **NOT resolve them**
- `write_section` currently ignores `packet.contradictions` — must be fixed

### CONTR-04 — Validator

- **No validator logic change required**
- **Contradiction citations must reference underlying atom IDs** (not contradiction record IDs)
- Contradictions reference `a.id` and `b.id` (atom IDs), so `[A001]` or `[A002]` in prose will validate fine
- Validator unchanged: checks citations → atoms, lexical overlap → unchanged

### Data Structure

- **Keep contradictions separate** in `packet.contradictions` (NOT merged into `packet.atoms`)
- Contradictions are relationships between atoms, not standalone knowledge units
- `EvidencePacket.contradictions` field exists already (List[Dict])

### Write Path Ownership

- **memory/manager.py** continues to write contradictions (inserts into `contradictions` table during extraction)
- **12-05 scope is READ PATH ONLY** — no write path migration

### Table Population

- Verify at runtime; phase proceeds regardless of data presence
- If empty: contradiction code path is dormant but correctly wired
- If populated: full feature works

---

## Execution Flow (Post-12-05)

```python
# assemble_all_sections
→ fetch atoms (V3Retriever - batch/semantic)
→ fetch contradictions (adapter-level PG query)
→ attach to EvidencePacket (atoms + contradictions separate)
→ pass to Archivist (both used in prompt)
```

## Archivist Prompt Update

Contradictions should appear as a new block in the prompt:

```
### IDENTIFIED CONTRADICTIONS IN THE EVIDENCE:
- CONFLICT: [description]
  CLAIM A: [atom_a_content] [A001]
  CLAIM B: [atom_b_content] [A002]
```

The archivist must **acknowledge** but not **resolve** contradictions.

---

## Code Changes Required

### Files to modify:

1. **`src/research/reasoning/assembler.py`** (lines 158-169)
   - Replace `self.memory.get_unresolved_contradictions(mission_id, limit=5)`
   - Use `self.adapter.pg_pool.acquire().fetch(...)` or equivalent V3 adapter query
   - Query: `SELECT * FROM contradictions WHERE topic_id = $1 AND resolved = FALSE LIMIT 5`

2. **`src/research/archivist/synth_adapter.py`** (prompt construction)
   - Add contradictions block to prompt if `packet.contradictions` is non-empty
   - Format with atom ID references `[A001]`, `[A002]` for FK-correct citations

3. **`src/memory/manager.py`** (verify only)
   - Confirm FK constraints on `contradictions.atom_a_id` and `contradictions.atom_b_id`

### Files NOT to modify:

- `src/research/reasoning/v3_retriever.py` (contradictions NOT semantic retrieval)
- `src/research/reasoning/synthesis_service.py` (validator untouched)
- `src/memory/manager.py` (write path — scope is read-only for 12-05)

---

## Success Criteria

- **CONTR-01:** No calls to `memory.get_unresolved_contradictions` in codebase
- **CONTR-02:** FK relationships verified in DB schema
- **CONTR-03:** Synthesis surfaces contradictions when present (archivist prompt includes contradiction block)
- **CONTR-04:** Validator passes unchanged — contradiction citations reference atom IDs directly

---

## FORBIDDEN

- **DO NOT** merge contradictions into atoms
- **DO NOT** bypass adapter layer for DB access
- **DO NOT** modify validator rules or behavior
- **DO NOT** resolve contradictions — only surface them
- **DO NOT** introduce semantic retrieval for contradictions
- **DO NOT** change truth contract invariants (Phase 10/11)
- **DO NOT** add external dependencies

---

## Out of Scope

- Contradiction write path migration
- Smelter/extraction contradiction generation
- Contradiction resolution logic (courtroom)
- Dashboard/API for contradictions

---

</decisions>

<canonical_refs>

## Canonical References

**Downstream agents MUST read these before planning or implementing:**

### Phase scope & requirements
- `.planning/REQUIREMENTS.md` — CONTR-01 through CONTR-04 definitions
- `.planning/ROADMAP.md` — Phase 12-05 entry in milestone v1.1

### Prior work (must not break)
- `.planning/phases/10-11/` — Truth contract phases (validator unchanged)
- `.planning/phases/12-04/` — Structured logging (preserve existing span instrumentation)

### Source code (instrumentation targets)
- `src/research/reasoning/assembler.py:158-169` — Current contradiction retrieval code to replace
- `src/research/archivist/synth_adapter.py` — Archivist prompt (add contradictions block)
- `src/memory/manager.py:244-284` — Contradictions write path (verify only)
- `src/research/reasoning/synthesis_service.py:169-220` — Validator (verify unchanged)
- `src/core/system.py` — System orchestration (not modified, but spans instrumented)

---

</canonical_refs>

<deferred>

## Deferred Ideas

- CONTR write path migration from memory/manager.py to V3-native extraction
- Contradiction resolution (courtroom) logic
- Contradiction dashboard/API
- Smelter-generated contradiction improvements
- Semantic contradiction retrieval

---

</deferred>

---

*Phase: 12-05 — Contradiction system V3 upgrade*
*Context gathered: 2026-03-31 via direct user decisions*
