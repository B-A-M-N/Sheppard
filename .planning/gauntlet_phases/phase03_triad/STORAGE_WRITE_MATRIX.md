# Phase 03 — Storage Write Matrix

**Scope**: V3 runtime (post-authority-lock)

---

## Legend

- **Store**: Postgres (P), Chroma (C), Redis (R)
- **Canonical**: Truth stored only in Postgres
- **Projection**: Derived from Postgres
- **Ephemeral**: Motion/queue, cache
- **Violation**: Misplaced or ambiguous storage

---

## Write Operations

### SystemManager

| Method | Store | Table/Key | Canonical? | Notes |
|--------|-------|-----------|------------|-------|
| `adapter.upsert_domain_profile` | P | `config.domain_profiles` | ✅ Canonical | Profile created per mission |
| `adapter.create_mission` | P | `mission.research_missions` | ✅ Canonical | Mission record |
| `adapter.upsert_mission_node` | P | `mission.mission_nodes` | ✅ Canonical | Frontier nodes |
| `adapter.checkpoint_frontier` | P | `mission.frontier_checkpoints` | ✅ Canonical | Frontier state |
| `adapter.update_mission_status` | P | `mission.research_missions` | ✅ Canonical | Status updates |
| `adapter.ingest_source` | P | `corpus.text_refs`, `corpus.sources` | ✅ Canonical | Source ingestion |
| `adapter.create_chunks` (called within ingest) | P | `corpus.chunks` | ✅ Canonical | Chunk layer |
| `adapter.store_atom_with_evidence` | P | `knowledge.knowledge_atoms`, `knowledge.atom_evidence` | ✅ Canonical | Atom+evidence atomic |
| `adapter.index_atom` (via store_atom) | C | `knowledge_atoms` collection | ✅ Projection | Derived from atom |
| `adapter.index_chunks` (via create_chunks) | C | `corpus_chunks` collection | ✅ Projection | Derived from chunks |
| `adapter.cache_hot_object` | R | various hot keys | ✅ Ephemeral | Cache, TTL 1h |
| `adapter.set_active_state` | R | `*:active:*` | ✅ Ephemeral | In-mission active flags |
| `adapter.enqueue_job` (crawler) | R | `queue:scraping` | ✅ Ephemeral | Work queue, recoverable from sources |

### AdaptiveFrontier (acquisition/frontier.py)

| Method | Store | Table/Key | Canonical? | Notes |
|--------|-------|-----------|------------|-------|
| `adapter.upsert_mission_node` | P | `mission.mission_nodes` | ✅ Canonical | Frontier node state |
| `adapter.checkpoint_frontier` | P | `mission.frontier_checkpoints` | ✅ Canonical | Snapshots |
| `adapter.get_latest_frontier_checkpoint` | R | `frontier:ckpt:{mission_id}` | ✅ Ephemeral | Hot cache |

### DistillationPipeline (condensation/pipeline.py)

| Method | Store | Table/Key | Canonical? | Notes |
|--------|-------|-----------|------------|-------|
| `adapter.pg.fetch_many` (read) | P | `corpus.sources` | — | Read only |
| `store_atom_with_evidence` | P | `knowledge.knowledge_atoms`, `atom_evidence` | ✅ Canonical | Atomic |
| `adapter.index_atom` | C | `knowledge_atoms` | ✅ Projection | |
| `adapter.pg.update_row` | P | `corpus.sources.status` | ✅ Canonical | Mark condensed |

### V3Retriever (reasoning/v3_retriever.py)

| Method | Store | Collection | Canonical? | Notes |
|--------|-------|------------|------------|-------|
| `adapter.chroma.search` | C | `knowledge_atoms` | ✅ Projection | Semantic search |

### Archivist (research/archivist/index.py) — **VIOLATION**

| Method | Store | Collection | Canonical? | Notes |
|--------|-------|------------|------------|-------|
| `chroma_client.get_or_create_collection` | C | `archivist_research` | ❌ Violation | Direct Chroma access, bypasses adapter; not derived from Postgres |
| `collection.add` | C | `archivist_research` | ❌ Violation | Independent writes |

---

## Summary

- **Canonical writes**: All target Postgres via adapter
- **Projections**: Chroma indexing is always adapter-mediated (except archivist violation)
- **Ephemeral**: Redis used for queue, cache, locks, active state
- **Direct bypass**: Archivist writes directly to Chroma → violates triad discipline
- **V2 writes**: None (locked)

---

## Violations

1. **Archivist direct Chroma access**:
   - File: `src/research/archivist/index.py`
   - Issue: Creates own Chroma client and indexes research documents without going through adapter
   - Impact: Chroma contains data not derived from Postgres; may be unrecoverable if Postgres is the only truth source
   - Recommendation: Refactor archivist to use `adapter.index_*` methods or store results via adapter

---

## Notes

- All adapter methods follow the Postgres → Chroma → Redis projection pattern.
- `index_*` methods are called *after* Postgres commit, making them eventually consistent (not atomic). This is acceptable since Chroma is a projection.
- No V2 stores are written during V3 operation (Phase 03.0 lock).
