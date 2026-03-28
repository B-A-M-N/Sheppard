# Phase 04 — Orphan Risk Report

**Definition**: An orphan is a row whose foreign key reference is missing or whose expected lineage chain is broken.

---

## Risk Matrix

| Entity | Orphan Scenario | Severity | Likelihood | Mitigation |
|--------|------------------|----------|------------|------------|
| `knowledge_atoms` | Created without `atom_evidence` rows | High | Current code can produce | **Fix**: Make evidence binding atomic with atom upsert (Phase 02 blocker) |
| `corpus.chunks` | Source ingested but chunking never called | Medium | If chunking stage omitted | **Fix**: Ensure `ingest_source()` creates chunks (Phase 02 blocker) |
| `corpus.chunks` | `source_id` points to deleted source | Low | Impossible (FK CASCADE) | Prevented by DB constraint |
| `atom_evidence` | `chunk_id` points to deleted chunk | Low | Chunk deletion cascades to evidence | Prevented by DB constraint (SET NULL allowed but chunk deletion should cascade) |
| `synthesis_artifacts` | `authority_record_id` points to missing record | Low | Authority record deletion cascades | Prevented by DB constraint |
| `synthesis_citations` | `atom_id` points to deleted atom | Low | Atom deletion cascades | Prevented by DB constraint (SET NULL) |
| `mission.research_missions` | Orphaned `topic_id` (mission deleted) | Low | Mission deletion is intentional | Not an issue |

---

## Detailed Risk: Atoms Without Evidence

**Root cause**: `storage_adapter.upsert_atom()` and `bind_atom_evidence()` are separate transactions. If the second fails, the atom exists with zero evidence rows.

**Code location**:
- `src/research/condensation/pipeline.py:111-118`
- `src/memory/storage_adapter.py:577-580, 595-598`

**Impact**:
- Violates V3 integrity invariant: "every atom must have at least one evidence row"
- Atom appears in retrieval but has no provenance
- Cannot audit where the claim came from

**Current status**: This is a **known blocker** from Phase 02. It must be fixed before V3 activation.

**Recommended fix**:
```python
async def store_atom_with_evidence(self, atom: JsonDict, evidence_rows: Sequence[JsonDict]) -> None:
    async with self.pg.pool.transaction() as conn:
        await self.pg.upsert_row("knowledge.knowledge_atoms", "atom_id", atom, conn=conn)
        if evidence_rows:
            rows = [dict(row, atom_id=atom["atom_id"]) for row in evidence_rows]
            await self.pg.bulk_upsert("knowledge.atom_evidence", ["atom_id", "source_id", "chunk_id"], rows, conn=conn)
```
This ensures atomicity; if evidence binding fails, atom insert rolls back.

---

## Detailed Risk: Sources Without Chunks

**Root cause**: `SheppardStorageAdapter.ingest_source()` stores `corpus.sources` and `corpus.text_refs` but does **not** call `create_chunks()` to populate `corpus.chunks`.

**Code location**: `src/memory/storage_adapter.py:705-746`

**Impact**:
- Chunk layer is bypassed entirely
- `knowledge.atom_evidence.chunk_id` will be NULL (or point to non-existent chunk)
- Lineage `source → chunk → atom` is broken

**Current status**: This is a **known blocker** from Phase 02. Must be fixed.

**Recommended fix**:
Add chunk creation after text ingestion:
```python
# After storing source and text_ref:
chunks = chunk_text(text_content)  # Determine chunking strategy (configurable?)
chunk_rows = [{
    "chunk_id": str(uuid.uuid4()),
    "source_id": source_id,
    "mission_id": mission_id,
    "topic_id": topic_id,
    "chunk_index": idx,
    "inline_text": chunk_text,
    "chunk_hash": hashlib.sha256(chunk_text.encode()).hexdigest(),
    # ... other metadata
} for idx, chunk_text in enumerate(chunks)]
await self.create_chunks(chunk_rows)
```

---

## Detailed Risk: Orphaned Authority Linkage

**Scenario**: `knowledge_atoms.authority_record_id` references a non-existent `authority_records.authority_record_id`.

**Why it's not a risk currently**:
- The field is **not a foreign key** (no DB constraint)
- But in practice, `authority_record_id` is populated only during authority synthesis, which reads atoms and writes linkage
- If an authority record is deleted, atoms remain; their `authority_record_id` becomes a dangling reference

**Severity**: Low — atoms remain valid; authority linkage is advisory

**Mitigation**:
- Either make `authority_record_id` a FK with `SET NULL` on delete
- Or leave as-is, knowing that missing authority records simply mean "no authority claim"

---

## Detailed Risk: Evidence Bundle Orphans

**Scenario**: `knowledge.evidence_bundles.authority_record_id` points to missing authority record, or `topic_id` has no matching topic.

**Why it's acceptable**:
- Bundles are intermediate constructs; they may be created before an authority record exists
- `topic_id` is for organizational queries; absence of FK doesn't break retrieval
- Bundles are cleaned up if authority record is deleted? Not automatically, but they're small

**Severity**: Very Low

---

## Orphan Prevention Mechanisms

1. **Database FKs** with appropriate `ON DELETE`:
   - CASCADE for owned entities (sources→chunks, atoms→evidence, authority→artifacts)
   - SET NULL for optional linkages (chunk_id in evidence, atom/source in citations)
2. **Unique constraints** prevent duplicate source ingestion (normalized_url_hash per mission)
3. **NOT NULL** on required columns (mission_id on sources, atom_id on evidence, etc.)
4. **Composite PKs** ensure evidence rows are uniquely identified

---

## Testability

These risks can be validated with automated checks:

```sql
-- Atoms without evidence
SELECT a.atom_id FROM knowledge.knowledge_atoms a
LEFT JOIN knowledge.atom_evidence e ON a.atom_id = e.atom_id
WHERE e.atom_id IS NULL;

-- Sources without chunks
SELECT s.source_id FROM corpus.sources s
LEFT JOIN corpus.chunks c ON s.source_id = c.source_id
WHERE c.chunk_id IS NULL;

-- Evidence with missing chunk (should only be if chunk was deleted)
SELECT e.atom_id, e.chunk_id FROM knowledge.atom_evidence e
LEFT JOIN corpus.chunks c ON e.chunk_id = c.chunk_id
WHERE e.chunk_id IS NOT NULL AND c.chunk_id IS NULL;

-- Authority atoms pointing to non-existent authority record (if FK not added)
SELECT a.atom_id FROM knowledge.knowledge_atoms a
LEFT JOIN authority.authority_records ar ON a.authority_record_id = ar.authority_record_id
WHERE a.authority_record_id IS NOT NULL AND ar.authority_record_id IS NULL;
```

---

## Conclusion

The **critical** orphan risks are **atoms without evidence** and **sources without chunks** — both are known Phase 02 blockers that must be resolved. The schema provides strong protection against most orphans via cascading FKs, and the remaining soft references are semantically acceptable.

**Action items**:
1. Fix atom evidence atomicity (Phase 02 G3)
2. Fix chunk creation in ingestion (Phase 02 G1/G2 area)
3. Consider adding DB constraint for `knowledge_atoms.authority_record_id` if authority linkage should be validated

Once these are resolved, orphan risks become **low**.
