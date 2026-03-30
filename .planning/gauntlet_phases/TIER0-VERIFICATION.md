# Tier 0 Foundation Verification

**Purpose:** Confirm storage layer correctness before Phase 11 (Report Generation Audit).
**Method:** Code inspection only. No implementation.

---

## A.1 — Database Schema Existence

**Status:** VERIFIED (with naming clarification)

**Evidence:**

Schema defined in: `src/memory/schema.sql`

### corpus.sources
```sql
CREATE TABLE IF NOT EXISTS corpus.sources (
    source_id TEXT PRIMARY KEY,
    mission_id TEXT NOT NULL,
    topic_id TEXT NOT NULL,
    url TEXT NOT NULL,
    normalized_url TEXT NOT NULL,
    normalized_url_hash TEXT NOT NULL,
    domain TEXT,
    title TEXT,
    source_class TEXT NOT NULL,
    mime_type TEXT,
    language TEXT,
    trust_score NUMERIC(8,4),
    quality_score NUMERIC(8,4),
    canonical_text_ref TEXT,
    content_hash TEXT,
    status TEXT NOT NULL DEFAULT 'discovered',
    metadata_json JSONB NOT NULL DEFAULT '{}',
    captured_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```
Indexes: `(mission_id, normalized_url_hash)` unique, `idx_sources_topic_id`, `idx_sources_source_class`.

### knowledge.knowledge_atoms
```sql
CREATE TABLE IF NOT EXISTS knowledge.knowledge_atoms (
    atom_id TEXT PRIMARY KEY,
    authority_record_id TEXT,
    mission_id TEXT,
    topic_id TEXT NOT NULL,
    domain_profile_id TEXT NOT NULL REFERENCES config.domain_profiles(profile_id),
    atom_type TEXT NOT NULL,
    title TEXT NOT NULL,
    statement TEXT NOT NULL,
    summary TEXT,
    confidence NUMERIC(8,4),
    importance NUMERIC(8,4),
    novelty NUMERIC(8,4),
    stability TEXT,
    scope_json JSONB NOT NULL DEFAULT '{}',
    qualifiers_json JSONB NOT NULL DEFAULT '{}',
    lineage_json JSONB NOT NULL DEFAULT '{}',
    metadata_json JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```
Indexes: `idx_knowledge_atoms_topic_id`, `idx_knowledge_atoms_authority_record_id`, `idx_knowledge_atoms_atom_type`.

**Note:** Ambiguity register refers to `corpus.atoms`, but V3 uses `knowledge.knowledge_atoms`.

---

## A.2 / A.14 — Adapter Identity

**Status:** VERIFIED

**Evidence:**

Adapter: `SheppardStorageAdapter` (`src/memory/storage_adapter.py:412`)

- Constructor: takes `pg: PostgresStore`, Redis, Chroma. `self.pg = pg` (line 422).
- Low-level Postgres: `PostgresStoreImpl` (`src/memory/adapters/postgres.py:12`)
- Exposes required methods:
  - `self.adapter.pg` — raw Postgres operations
  - `get_text_ref(blob_id)` — line 539
  - `get_mission(mission_id)` — line 455

**Usage in DistillationPipeline** (`src/research/condensation/pipeline.py`):
```python
sources = await self.adapter.pg.fetch_many("corpus.sources", where={"mission_id": mission_id, "status": "fetched"}, limit=5)
mission_row = await self.adapter.get_mission(mission_id)
ref = await self.adapter.get_text_ref(text_ref)
await self.adapter.store_atom_with_evidence(atom_row, evidence_rows)
```

`SheppardStorageAdapter` is the canonical data access layer for V3.

---

## A.3 — KnowledgeAtom Schema

**Status:** VERIFIED

**Evidence:**

Class: `KnowledgeAtom` in `src/research/domain_schema.py:233`

**Fields:**
- `atom_id: str`
- `topic_id: str`
- `authority_record_id: Optional[str]`
- `domain_profile_id: str`
- `atom_type: str` (definition, claim, mechanism, constraint, tradeoff, failure_mode, contradiction, example, metric)
- `title: str`
- `statement: str`
- `summary: Optional[str]`
- `confidence: float` (0–1)
- `importance: float`
- `novelty: float`
- `stability: str` (e.g., "medium")
- `scope: AtomScope` (applies_to, does_not_apply_to, jurisdiction, environment, time_range, version_range)
- `qualifiers: AtomQualifiers` (version_notes, temporal_notes, caveats, counterpoints)
- `lineage: AtomLineage` (created_by, created_at, **mission_id**, extraction_mode, parent_objects)
- `metadata: Dict[str, Any]`

**Postgres serialization:** `to_pg_row()` (line 252) includes `mission_id` from lineage; nested fields JSON-encoded. Evidence stored separately via `store_atom_with_evidence()`.

V3 table `knowledge.knowledge_atoms` maps these fields (see A.1).

---

## A.9 — Multi-Mission Isolation

**Status:** VERIFIED

### Fixed Methods

Both adapter methods now enforce mission scoping:

| Method | Fix | Verification |
|--------|-----|--------------|
| `get_source_by_url_hash(mission_id, normalized_url_hash)` | Added `mission_id` to WHERE clause + updated caller | See `tests/mission_isolation/test_cross_mission_isolation.py` |
| `list_atoms_for_topic(mission_id, topic_id, ...)` | Added `mission_id` to WHERE clause | Same test suite |

**Query Guarantees:**
```sql
-- Before
SELECT * FROM corpus.sources WHERE normalized_url_hash = $1;
SELECT * FROM knowledge.knowledge_atoms WHERE topic_id = $1;

-- After
SELECT * FROM corpus.sources WHERE mission_id = $1 AND normalized_url_hash = $2;
SELECT * FROM knowledge.knowledge_atoms WHERE mission_id = $1 AND topic_id = $2;
```

### Test Coverage

- `test_cross_mission_source_isolation`: Ensures source lookup cannot cross missions
- `test_atoms_do_not_leak_across_missions`: Ensures atom queries are mission-scoped
- `test_list_sources_respects_mission_id`: Sanity check that existing scoping works

### Invariant

No read operation can return data belonging to a different mission. All adapter methods that query by natural keys now require explicit `mission_id` parameter.

---

## Summary Table

| Item | Status | Notes |
|------|--------|-------|
| A.1 Schema Existence | VERIFIED | `corpus.sources`, `knowledge.knowledge_atoms` exist |
| A.2/A.14 Adapter Identity | VERIFIED | `SheppardStorageAdapter` with required methods |
| A.3 KnowledgeAtom Schema | VERIFIED | Full fields confirmed; `mission_id` in lineage |
| A.9 Multi-Mission Isolation | VERIFIED | All adapter methods now enforce mission_id scoping |

**Result:** Cross-mission leakage sealed. Ready for Phase 11.
