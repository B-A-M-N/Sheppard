# Sheppard V3 Activation - Phase 02 Audit Report

**Audit Date**: 2026-03-27
**Auditor**: Claude Code
**Scope**: Verification of V3 activation criteria

---

## Executive Summary

The Sheppard V3 implementation shows **significant architectural gaps**. While the V3 schema is well-defined and the adapter pattern is implemented, several critical components still rely on V2 infrastructure. The pipeline is partially separable but the chunking stage is missing in the V3 path. Evidence enforcement lacks atomic transaction guarantees. Most critically, the query system does not read from V3 knowledge tables.

**Overall Assessment**: ⚠️ PARTIAL FAILURE — Major components still on V2.

---

## Detailed Findings

### A. SystemManager Methods Use V3 Adapter

#### ✅ PASS: `learn()` uses V3 adapter
- **File**: `src/core/system.py:181-192`
- Creates domain profile via `adapter.upsert_domain_profile()`
- Creates mission via `adapter.create_mission()`
- Ingestion in `_vampire_loop:340` calls `adapter.ingest_source()`

#### ❌ FAIL: `query()` uses V2 HybridRetriever, not V3 knowledge
- **File**: `src/core/system.py:131,224`
- Retriever initialized: `self.retriever = HybridRetriever(memory_manager=self.memory)`
- `self.memory` is V2 `MemoryManager`, not V3 adapter
- `HybridRetriever` (`src/research/reasoning/retriever.py:136-227`) calls:
  - `self.memory.lexical_search_atoms()` → queries V2 `knowledge_atoms` table (not V3)
  - `self.memory.chroma_query()` → queries V2 Chroma collections (knowledge_atoms, thematic_syntheses, advisory_briefs)
  - `self.memory.find_concepts_by_text()`, `self.memory.traverse_concept_graph()` → V2 concept graph
- **Conclusion**: All retrieval reads from V2 infrastructure. V3 knowledge.knowledge_atoms table is never queried.

#### ⚠️ PARTIAL: `generate_report()` writes to V3 but reads from V2
- **File**: `src/core/system.py:134,419`; `src/research/reasoning/synthesis_service.py:27-96`
- Uses adapter to store synthesis artifacts (line 70-93)
- BUT: `EvidenceAssembler.build_evidence_packet()` (line 92-100+) uses `self.retriever` (V2) to gather atoms
- Mock authority_record_id used (line 48): `auth_id = f"dar_{topic_id[:8]}"`
- Does not read from V3 `authority.authority_records` or `authority.synthesis_artifacts` as source
- **Conclusion**: Reports are stored in V3 but content is assembled from V2 atoms.

#### ✅ PASS: `nudge_mission()` uses V3 adapter via AdaptiveFrontier
- **File**: `src/core/system.py:393`; `src/research/acquisition/frontier.py:370-371`
- Frontier uses V3 adapter for node persistence (line 147, 184, 196, 199)

---

### B. Pipeline Decomposition

#### Pipeline Stages Analysis

**Intended**: frontier → discovery → queue → crawl → smelt → index

**Actual Flow**:

1. **Frontier** (`AdaptiveFrontier.run()` in `src/research/acquisition/frontier.py:76-135`)
   - ✅ Distinct stage
   - Generates queries and calls `crawler.discover_and_enqueue()`

2. **Discovery/Queue** (`discover_and_enqueue()` in `src/research/acquisition/crawler.py:280-330`)
   - ✅ Distinct stage
   - Enqueues jobs to Redis queue `"queue:scraping"`

3. **Crawl** (`_vampire_loop()` in `src/core/system.py:299-359`)
   - ✅ Dequeues from Redis (line 305)
   - ✅ Calls Firecrawl to scrape (line 326)
   - ✅ Calls V3 `adapter.ingest_source()` (line 340)

4. **Chunking Stage** ❌ **MISSING**
   - `adapter.ingest_source()` (`src/memory/storage_adapter.py:705-746`) stores:
     - `corpus.text_refs` (line 712-716)
     - `corpus.sources` (line 741)
   - **Does NOT create `corpus.chunks`** from the text
   - The V2 legacy path calls `self.memory.store_source()` (line 343-351) which also doesn't create chunks directly
   - **Gap**: No code calls `adapter.create_chunks()` to populate `corpus.chunks` table
   - Impact: The chunk layer is completely bypassed, breaking the V3 lineage (chunks are referenced by `atom_evidence.chunk_id`)

5. **Smelt** (`DistillationPipeline.run()` in `src/research/condensation/pipeline.py:44-144`)
   - ✅ Distinct stage
   - ✅ Fetches sources from `corpus.sources` (line 50-54)
   - ✅ Extracts atoms and binds evidence (line 111-118)
   - ⚠️ Evidence binding not atomic (see section C)

6. **Index**
   - ⚠️ Atoms are indexed in Chroma via `adapter.upsert_atom()` → `index_atom()` (storage_adapter.py:577-580, 827-830)
   - ⚠️ Chunks would be indexed via `index_chunks()` but chunks don't exist
   - ✅ Indexing is separate from storage

**Pipeline Separation Verdict**: ⚠️ **PARTIAL**
- Stages are conceptually distinct
- **But chunking stage is absent** in V3 ingestion path
- V3 corpus.chunks table remains empty

---

### C. Evidence Enforcement

#### ❌ FAIL: Atoms can be created without evidence in separate transactions

- **Atom creation**: `storage_adapter.py:577-580`
  ```python
  async def upsert_atom(self, atom: JsonDict) -> None:
      await self.pg.upsert_row("knowledge.knowledge_atoms", "atom_id", atom)
      await self.index_atom(atom)
      ...
  ```

- **Evidence binding**: `storage_adapter.py:595-598`
  ```python
  async def bind_atom_evidence(self, atom_id: str, evidence_rows: Sequence[JsonDict]) -> None:
      if not evidence_rows: return
      rows = [dict(row, atom_id=atom_id) for row in evidence_rows]
      await self.pg.bulk_upsert("knowledge.atom_evidence", ["atom_id", "source_id", "chunk_id"], rows)
  ```

- **Actual usage** (`condensation/pipeline.py:111-118`):
  ```python
  await self.adapter.upsert_atom(atom.to_pg_row())
  await self.adapter.bind_atom_evidence(atom_id, [{...}])
  ```

- **Problem**: Each method acquires its own database connection (PostgresStoreImpl uses `async with self.pool.acquire()` per call). No shared transaction context. If `bind_atom_evidence` fails after `upsert_atom` succeeds, the atom exists with zero evidence rows, violating the invariant.

- **Missing**: Transaction wrapper or combined atomic operation.

---

### D. Database Model Consistency

#### ✅ PASS: V3 schema includes all required tables

**File**: `src/memory/schema_v3.sql`

Required tables exist:

| Table | Lines | Status |
|-------|-------|--------|
| `mission.research_missions` | 56-72 | ✅ |
| `corpus.sources` | 150-170 | ✅ |
| `corpus.chunks` | 203-221 | ✅ |
| `knowledge.knowledge_atoms` | 276-296 | ✅ |
| `knowledge.atom_evidence` | 305-312 | ✅ |
| `authority.synthesis_artifacts` | 466-478 | ✅ |

Additional supporting tables present (mission_events, mission_nodes, corpus.text_refs, etc.)

---

### E. Command Surface

#### ✅ PASS: All four commands present and mapped

**File**: `src/core/commands.py:38-60`

| Command | Handler | Method | Lines |
|---------|---------|--------|-------|
| `/learn` | `_handle_learn()` | `system_manager.learn()` | 72-84 |
| `/query` | `_handle_query()` | `system_manager.query()` | 86-91 |
| `/report` | `_handle_report()` | `system_manager.generate_report()` | 93-126 |
| `/nudge` | `_handle_nudge()` | `system_manager.nudge_mission()` | 222-271 |

All commands exist and call the corresponding SystemManager methods.

---

## Critical Architecture Issues

### 1. Dual Database Inconsistency

**Problem**: Two separate PostgreSQL databases:
- V2 MemoryManager: uses `POSTGRES_DSN` (default: `semantic_memory` on localhost)
- V3 Adapter: uses `sheppard_v3` on `10.9.66.198`

The retriever only queries V2, so V3 knowledge is never read. This defeats the purpose of V3 activation.

**Evidence**:
- `src/memory/manager.py:54`: `dsn = os.getenv("POSTGRES_DSN", "postgresql://sheppard:1234@localhost:5432/semantic_memory")`
- `src/core/system.py:79`: `pg_dsn = DatabaseConfig.DB_URLS.get("sheppard_v3")`
- `src/research/reasoning/retriever.py:133-134`: `def __init__(self, memory_manager): self.memory = memory_manager`

### 2. Chunk Layer Not Populated

**Problem**: `adapter.ingest_source()` stores source and text_ref but never creates `corpus.chunks`. The chunking stage is missing from V3 pipeline.

**Impact**: `knowledge.atom_evidence.chunk_id` references will be NULL (or point to non-existent chunks). The lineage from source → chunk → atom is broken.

**Evidence**:
- `storage_adapter.py:705-746` `ingest_source()` does not call `create_chunks()`
- `condensation/pipeline.py:69-74` retrieves text via `adapter.get_text_ref(text_ref)` and processes inline_text directly, bypassing chunks entirely.

### 3. Non-Atomic Evidence Binding

**Problem**: Upserting atom and binding evidence are separate transactions. No rollback if second step fails.

**Evidence**: `PostgresStoreImpl` methods each acquire independent connections (e.g., line 40, 86, 96). No transaction context propagation.

---

## Summary Matrix

| Criterion | Status | Evidence |
|-----------|--------|----------|
| A. SystemManager uses V3 adapter | ⚠️ PARTIAL | learn/ nudge ✅, query ❌, report ⚠️ |
| B. Pipeline separable | ❌ FAIL | Chunking stage missing entirely |
| C. Evidence enforcement | ❌ FAIL | Non-atomic upsert + bind |
| D. Database model consistency | ✅ PASS | All tables in schema_v3.sql |
| E. Command surface | ✅ PASS | All commands in commands.py |

---

## Recommendations

1. **Query Refactor**: HybridRetriever must query V3 knowledge.knowledge_atoms and corpus.chunks, not V2 memory. Either:
   - Initialize HybridRetriever with V3 adapter, or
   - Create V3-specific retriever that queries `knowledge.knowledge_atoms` and `corpus.chunks` via the adapter

2. **Chunking Stage**: Add chunk creation in `ingest_source()` or as a separate pipeline stage:
   ```python
   chunks = chunk_text(text_content)
   chunk_rows = [{"chunk_id": ..., "source_id": source_id, "inline_text": c, ...} for c in chunks]
   await self.adapter.create_chunks(chunk_rows)
   ```

3. **Atomic Evidence**: Combine atom + evidence insertion into a single transaction, or add compensating delete on failure.

4. **Unified Database**: Ensure all components use the same `sheppard_v3` database. Remove V2 `semantic_memory` dependency for V3 missions.

5. **Evidence Validation**: Add database constraint or trigger to prevent atoms with zero evidence rows (or enforce at application layer with count check).

---

**End of Report**
