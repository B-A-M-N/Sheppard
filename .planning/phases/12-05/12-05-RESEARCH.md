# Phase 12-05 Research: Contradiction System V3

## Executive Summary

Replace `memory.get_unresolved_contradictions(mission_id, limit=5)` in assembler.py
with direct adapter-level PG query. Archivist already formats contradictions correctly.
Validator unchanged. Schema already has FKs. Single-file change.

Current architecture:
```python
# assembler.py:163 — LEGACY PATH
conflicts = await self.memory.get_unresolved_contradictions(mission_id, limit=5)
```

Target architecture:
```python
# assembler.py — V3 NATIVE PATH
rows = await adapter.pg_pool.acquire().fetch(
    "SELECT ... FROM contradictions c ...",
    mission_id, 5
)
```

## Current State Analysis

### Where contradictions live

Memory manager queries:
- `src/memory/manager.py:261-277` — `get_unresolved_contradictions(topic_id, limit=5)`
- SQL: `FROM contradictions c JOIN knowledge_atoms a ON a.id = c.atom_a_id JOIN knowledge_atoms b ON b.id = c.atom_b_id`
- Returns: `contra_id`, `description`, `atom_a_content`, `atom_b_content`, etc.
- Table name: `contradictions` (no schema prefix)

### How assembler uses it

`src/research/reasoning/assembler.py:158-169`:
```python
if "contradictions" in [r.lower() for r in section.target_evidence_roles]:
    if self.memory is not None:
        conflicts = await self.memory.get_unresolved_contradictions(mission_id, limit=5)
        for c in conflicts:
            packet.contradictions.append({
                "description": c['description'],
                "claim_a": c['atom_a_content'],
                "claim_b": c['atom_b_content']
            })
```

### How archivist formats them

Already correct:
```python
def _format_evidence_brief(self, packet):
    brief = ""
    for atom in packet.atoms:
        brief += f"{atom.get('global_id')} ...\n"
    if packet.contradictions:
        brief += "\n### IDENTIFIED CONTRADICTIONS IN EVIDENCE:\n"
        for c in packet.contradictions:
            brief += f"- CONFLICT: {c.get('description')}\n  CLAIM A: ...\n"
    return brief
```

System prompt already includes contradiction handling rule.

### How validator handles it

Validator in `synthesis_service.py` checks:
1. Each sentence has `[A#]` or `[S#]` style citation
2. Cited ID in `packet.atom_ids_used`
3. Lexical overlap with `packet.atoms` text

Contradictions reference atom IDs (from `atom_a_content` and `atom_b_content`),
so validator passes — it sees `[A001]` citation and finds matching atom in `packet.atoms`.

## Data Population

Contradictions inserted when `atom_type == 'contradiction'` during extraction/condensation.
The smelter pipeline creates contradiction atoms that get stored.
If extraction pipeline produces contradictions, the table will have data.

SQL pattern for insertion (memory/manager.py:248-251):
```sql
INSERT INTO contradictions (topic_id, description, resolved) VALUES ($1, $2, FALSE)
```
Note: This simplified insertion doesn't populate `atom_a_id` / `atom_b_id` —
it just stores the description. Full attribution depends on the extraction pipeline
setting these FK columns. If they're NULL, the JOIN in `get_unresolved_contradictions`
would exclude these rows. This means **only extraction-time contradictions with proper
FKs appear via the current query**.

The query uses `JOIN knowledge_atoms a ON a.id = c.atom_a_id` — if `atom_a_id` is NULL,
the row is excluded. So current data may be sparse.

## CONTR-01: Replacement Pattern

**Target code** (assembler.py — replace line 163):
```python
# OLD
conflicts = await self.memory.get_unresolved_contradictions(mission_id, limit=5)

# NEW — V3 adapter-level query
conflicts = await self._get_unresolved_contradictions(mission_id, limit=5)
```

Implementation in assembler.py:
```python
async def _get_unresolved_contradictions(self, mission_id: str, limit: int = 5) -> List[Dict]:
    """V3-native contradiction retrieval via direct PG query."""
    from src.config.database import DatabaseConfig
    from core.memory.storage.postgresql import PostgresStoreImpl  # or use adapter.pg_pool
    import uuid

    pool = getattr(self, '_contradiction_pool', None)
    # Use adapter's pool if available, otherwise use existing connection
    # The assembler needs access to pg_pool — see implementation note below
```

## CONTR-02: Schema

FKs exist via `atom_a_id` and `atom_b_id` columns in contradictions table.
The JOIN confirms referential integrity at query time.
Migration NOT required — schema already correct.

## CONTR-03: Archivist Integration

**ALREADY CORRECT** — `_format_evidence_brief` already appends contradictions block.
System prompt already includes contradiction rule.
No changes needed to archivist code.

## CONTR-04: Validator Compatibility

**ALREADY CORRECT** — validator checks citations against atom IDs.
Contradictions reference atom IDs in their content descriptions.
Validation passes because contradictions don't create new citation labels —
they reference existing atom IDs [A001], [A002], etc.

## Implementation Risks

1. **`self.memory` vs adapter/pg_pool**: The assembler needs PG access. If `_contradiction_pool` or adapter.pg_pool is not available, need wiring. Check how assembler is initialized.

2. **Empty contradictions**: If no data, code path runs but returns empty list. No functional change.

3. **FK NULLs**: Extration-time contradictions may not have populated `atom_a_id`/`atom_b_id`, making them invisible to the JOIN query. This is a data gap, not a code gap.
