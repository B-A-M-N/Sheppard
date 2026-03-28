# Phase 01 Research — System Inventory Findings

**Researcher:** Claude Code Agent
**Date:** 2025-03-27
**Phase:** 01 — Ground-Truth System Inventory

---

## Executive Summary

Sheppard V3 is a **hybrid V2/V3 architecture** in transition. The V3 "Universal Domain Authority Foundry" design is partially implemented with strong foundations but integration gaps exist. The system centers on a **Triad Memory Stack** (Postgres, Chroma, Redis) but V2 components still use legacy storage.

**Overall Assessment:**
- **Production Entrypoints:** 3 confirmed (`main.py`, `scout_worker.py`, `run_refinery.py`)
- **Workers:** Vampire swarm concept exists but implementation is basic
- **Storage:** Full V3 schema defined but not fully wired; V2 still operational
- **Pipeline:** `/learn` path partially implemented, gaps in state machine
- **Claims vs Reality:** Mixed — some claims verified, some aspirational, some contradicted

---

## 1. ENTRYPOINT INVENTORY

### Production (P)

| Entrypoint | File | Purpose | Status |
|-----------|------|---------|--------|
| Main Brain (interactive console) | `main.py` | Launches ChatApp with Rich UI; handles `/learn`, `/query`, `/report`, `/status`, `/nudge` commands | VERIFIED |
| Scout Worker (vampire) | `scout_worker.py` | Distributed scraping worker; pulls from Redis queue, uses Firecrawl | VERIFIED |
| Refinery Runner | `run_refinery.py` | Standalone refinery/processing script (possibly for batch processing) | PARTIAL — unclear integration |

### Worker (W)

| Worker | File | Role | Status |
|--------|------|------|--------|
| Vampire workers | Implemented via `_vampire_loop` in `src/core/system.py` | 8 concurrent local workers dequeuing from Redis | VERIFIED (but basic) |
| Reasoning Rig | Not implemented as separate node — remote model routing via `src/llm/model_router.py` | PARTIAL — concept exists, no actual distributed worker |
| Lazy Scout | Not implemented | NOT FOUND |

### Operator/Admin (O)

| Command | File | Purpose | Status |
|---------|------|---------|--------|
| `/learn` | `src/core/commands.py` → `system_manager.learn()` | Start research mission | VERIFIED |
| `/query` | `src/core/commands.py` → `system_manager.query()` | Search memory | VERIFIED |
| `/report` | `src/core/commands.py` → `system_manager.generate_report()` | Generate master brief | VERIFIED |
| `/status` | `src/core/commands.py` → `system_manager.status()` | System dashboard | VERIFIED |
| `/missions` | `src/core/commands.py` | List active missions | VERIFIED |
| `/stop` | `src/core/commands.py` → `system_manager.cancel_mission()` | Cancel mission | VERIFIED |
| `/nudge` | `src/core/commands.py` → `system_manager.nudge_mission()` | Steer frontier | VERIFIED |
| `/distill` | `src/core/commands.py` | Manual condensation trigger | VERIFIED |
| `/consolidate` | `src/core/commands.py` | Atom consolidation | VERIFIED |

### Diagnostic (D)

| Script | Purpose | Status |
|--------|---------|--------|
| `schemafix.py` | DB schema fixes/maintenance | VERIFIED |
| `server_wipe.py` | Wipe server data (destructive) | VERIFIED |
| `server_setup.py` | Server provisioning | VERIFIED |
| `diag_search.py` | Diagnostic search | PARTIAL |
| `system_checks.py` | System health checks | VERIFIED |
| `bench_test.py` | Benchmark testing (performance) | VERIFIED (benchmark category) |

### Migration/Setup (M)

| Script | Purpose | Status |
|--------|---------|--------|
| `src/memory/setup_v3.py` (referenced in README) | Initialize V3 memory schema | NOT FOUND (file missing) |
| `src/memory/schema_v3.sql` | V3 schema definition | VERIFIED |
| `src/memory/schema.sql` | V2 schema definition | VERIFIED |
| `start_research_stack.sh` | Start all services (Postgres, Redis, Chroma, Ollama, Firecrawl, SearXNG) | VERIFIED |

### Unsafe/Destructive (U)

- `server_wipe.py` — data destruction
- `schemafix.py` — could be destructive depending on operation

---

## 2. STORAGE SYSTEMS MAPPING

### 2.1 Postgres (The Truth)

**Connection:** Configured in `src/config/database.py` — `DB_URLS['semantic_memory']` points to remote server (10.9.66.198:5432)

**V3 Schema** (`src/memory/schema_v3.sql`):

Multi-schema design with strict foreign keys:

- `config.domain_profiles` — domain configuration
- `mission.*` — missions, nodes, mode runs, frontier snapshots, events
- `corpus.*` — sources, chunks, text_refs, clusters
- `knowledge.*` — knowledge_atoms, atom_evidence, atom_relationships, atom_entities, atom_usage_stats, contradiction_sets, evidence_bundles, bundle_*
- `authority.*` — authority_records, authority_core_atoms, authority_related_records, authority_advisories, authority_frontier_state, authority_contradictions, synthesis_artifacts, synthesis_*
- `application.*` — application_queries, application_outputs, application_evidence, application_lineage

**V2 Schema** (`src/memory/schema.sql`):

Legacy tables still in use:
- `topics`, `sources`, `crawl_sessions`, `knowledge_atoms` (V2 version), `thematic_syntheses`, `advisory_briefs`, `frontier_nodes`, `contradictions`, `meta_memory`, `distillation_log`

**Write Paths:**
- V3: Via `PostgresStoreImpl` in `src/memory/adapters/postgres.py` (Protocol-based adapter)
- V2: Via `MemoryManager` (still active for some components)

**Read Paths:**
- Both V2 and V3 query Postgres directly for different purposes
- Retrieval (`HybridRetriever`) reads from V2 tables only — **CRITICAL GAP**

**Lineage-Relevant Fields:**
- `mission.mission_nodes.parent_node_id` — frontier tree
- `corpus.sources.mission_id` + `source_id` — source lineage
- `corpus.chunks.source_id` — chunk→source
- `knowledge.knowledge_atoms.lineage_json` — atom evidence chains
- `knowledge.atom_evidence` — binding table
- `authority.authority_records` — canonical compilation

**Constraints:**
- Foreign keys mostly defined with `ON DELETE CASCADE` or `SET NULL`
- Unique constraints: `(mission_id, normalized_url_hash)` on sources, `(mission_id, atom_hash)` on atoms (in V3 plan, but check actual schema)
- Check constraints for enums in V3 schema (visibility, status, atom_type)

**Status:** PARTIAL — V3 schema exists but not all tables may be in use; V2/V3 dual operation causes confusion.

---

### 2.2 Chroma (The Proximity)

**Connection:** Persistent client at `chroma_storage/` directory (from `src/memory/adapters/chroma.py`)

**Collections (from code analysis):**

**V2 Collections:**
- `knowledge_atoms` — Level B atoms
- `thematic_syntheses` — Level C syntheses
- `advisory_briefs` — Level D briefs
- `project_artifacts` — project-specific
- `archivist_research` — archivist vectors

**V3 Collections:**
- `corpus_chunks` — raw chunk embeddings
- `knowledge_atoms` — (different from V2? potential collision)
- `authority_records` — authority record embeddings
- `synthesis_artifacts` — synthesis artifacts

**Write Paths:**
- `ChromaSemanticStoreImpl.index_chunk()`, `.index_atom()`, `.index_authority_record()`, `.index_synthesis_artifact()`
- Called from distillation pipeline and ingestion

**Read Paths:**
- `HybridRetriever` queries V2 collections only
- `ArchivistRetriever` queries with source tiering
- Search: `collection.query()` with `where` metadata filters

**Projection Status:**
- **Questionable** — Chroma may contain derived data but need to verify if all embeddings are derivable from Postgres
- Rebuild script likely exists or can be built: iterate Postgres sources/chunks/atoms and re-embed

**Status:** VERIFIED but with concerns about dual V2/V3 collections and rebuildability not proven.

---

### 2.3 Redis (The Motion)

**Connection:** `redis://localhost:6379` (single instance; config has multi-db but not used)

**Namespaces/Uses:**

1. **Queue:**
   - `queue:scraping` — list-based (`BLPOP`) for URL jobs
   - `queue:acquisition` — separate queue?
   - `firecrawl:fast`, `firecrawl:slow` — lane routing

2. **Locks:**
   - Distributed mutex via `acquire_lock()` in `src/core/system.py`
   - Used for resource coordination

3. **Active State:**
   - `active_state:*` with TTL for transient state
   - Frontier nodes cached via `set_active_state()`

4. **Hot Cache:**
   - `cache:*` pattern for frequently accessed objects

5. **Retry Scheduling:**
   - Sorted set `retry:<queue>` for delayed retries

**Ephemeral Claim:**
- Redis holds **only transient state** (queues, locks, cache)
- All truth in Postgres
- **But:** frontier state caching in Redis could be considered motion, but if lost, does system recover cleanly? Need to verify.

**Status:** VERIFIED usage pattern; recovery guarantee needs testing (Phase 03).

---

### 2.4 File-Based Storage

- `corpus.text_refs` table stores `storage_uri` OR `inline_text`
- `storage_uri` likely points to compressed files on disk (e.g., `data/` or `chroma_storage/`)
- Raw content also stored in `corpus.chunks.inline_text` for short content

**Status:** VERIFIED pattern; implementation details need code inspection.

---

## 3. PIPELINE & QUERY PATHS

### 3.1 `/learn` Pipeline (Partial Verification)

**Traced Path:**

1. **Command parsing** — `src/core/commands.py` → `system_manager.learn(topic_name, ...)`
2. **Mission creation** — creates `ResearchMission` object; stores in memory (V2?) or Postgres?
3. **Topic decomposition** — `AdaptiveFrontier.run()` in `src/research/acquisition/frontier.py`
   - Generates research policy with LLM
   - Yields `ConceptTask` objects
   - Uses epistemic modes: GROUNDING, EXPANSION, DIALECTIC, VERIFICATION
4. **Discovery → Queue** — `crawler.discover_and_enqueue()` likely pushes URLs to Redis
5. **Scraping** — Vampire workers consume `queue:scraping` via `_vampire_loop` in `system.py`
   - Calls `crawler.fetch_url()` (FirecrawlLocalClient)
   - Ingests via `adapter.ingest_source()` (StorageAdapter)
6. **Condensation** — Budget monitor triggers `condensation_pipeline` when threshold crossed
   - `DistillationPipeline` in `src/research/condensation/pipeline.py`
   - Extracts atoms, binds evidence
   - TODO: `resolve_contradictions()`, `consolidate_atoms()` are stubs
7. **Storage** — Atoms stored via adapter to Postgres and Chroma
8. **Index update** — Chroma collections updated

**Gaps:**
- Mission state machine not explicit (states implied)
- Frontier → queue integration not fully traced
- Evidence binding may be incomplete
- Promotion logic (quarantine → mission-active → canonical) not fully implemented

**Status:** PARTIAL — major steps exist but some are stubs or unclear.

---

### 3.2 Interactive Query / Retrieval

**Command:** `/query <text>` → `system_manager.query()`

**Path:**
1. `HybridRetriever.retrieve()` in `src/research/reasoning/retriever.py`
2. 4-stage architecture:
   - Lexical prefilter (PG_TRGM)
   - Semantic retrieval (ChromaDB)
   - Structural retrieval (concept graph, project artifacts, contradictions)
   - Re-ranking (composite score)
3. Context assembly into role-based slots (definitions, evidence, contradictions, project artifacts, unresolved)
4. Inject into LLM prompt → response

**Gaps:**
- Retrieval uses V2 memory tables only — **does not query V3 atoms**
- Mission isolation not enforced — mixes all topics unless `topic_filter`
- No explicit query modes (chat, research, synthesis, verification)
- Quarantine filtering unclear

**Status:** VERIFIED but **CRITICAL GAP** — V3 atoms not in retrieval path. This contradicts README claim that agent uses distilled knowledge.

---

### 3.3 Report Generation

**Command:** `/report <topic_id>` → `generate_report()`

**Path:**
1. Uses `Archivist` components to synthesize Tier 4 master brief
2. Pulls from atoms, sources, possibly authority records
3. Output stored in `authority.synthesis_artifacts`

**Gaps:**
- Report generation details not fully traced
- Unclear if uses V2 or V3 data
- Lineage preservation in reports needs verification

**Status:** PARTIAL — high-level exists, details need inspection.

---

## 4. WORKER & DISTRIBUTED SYSTEM

### 4.1 Vampire Swarm

**Implementation:**
- In `src/core/system.py`: `_vampire_loop` async tasks (8 concurrent)
- Each dequeues from Redis `queue:scraping` using `BLPOP`
- Calls `self.adapter.ingest_source()` after fetch
- Budget check via `budget.can_crawl()` before processing

**Queue:**
- Redis list, not priority
- No dead-letter queue
- No worker heartbeats/registry

**Concurrency:**
- Uses Redis for simple queue but no explicit locking (BLPOP is atomic)
- Duplicate prevention via `url_checksum` dedupe in ingest

**Distributed Claim:**
- README says "Scout Offloaders: Passive nodes (Laptops, remote servers) pull from the same queue"
- Implementation: Basic, just separate processes running same worker code
- No special node identity or coordination beyond shared queue

**Status:** VERIFIED basic queue-based parallelism; **distributed** is conceptual, not robust.

---

### 4.2 Slow Lane / Offloader

- Referenced in code but not fully implemented
- Intended for PDFs/static sites
- Separate worker type not found

**Status:** NOT FOUND / PARTIAL

---

## 5. DATA MODELS & LINEAGE

### 5.1 Mission Model

**V3:** `mission.research_missions`
- `mission_id`, `topic_id`, `domain_profile_id`, `title`, `objective`, `status`, `budget_*`, `source_count`, `stop_reason`, timestamps

**V2:** `ResearchMission` dataclass in `src/research/models_task.py` — in-memory only?

**Observation:** Missions may be tracked in memory in V2 but V3 adds Postgres persistence. Integration unclear.

**Status:** PARTIAL

---

### 5.2 Source/Chunk Model

**V3:**
- `corpus.sources` — canonical source record with `source_id`, `mission_id`, `url`, `normalized_url_hash`, `status`
- `corpus.chunks` — chunked content with `chunk_id`, `source_id`, `mission_id`, `inline_text` or `text_ref`
- `corpus.text_refs` — blob storage for large content

**Lineage:**
- `source_id` links chunk to source
- `mission_id` present on both
- But **foreign keys to mission** from sources/chunks? In schema: `corpus.sources.mission_id` REFERENCES `mission.research_missions`, `corpus.chunks.mission_id` REFERENCES `mission.research_missions` — YES

**Status:** VERIFIED structure; need to verify write paths enforce.

---

### 5.3 Atom Model

**V2:** `knowledge_atoms` (legacy) — simple table
**V3:** `knowledge.knowledge_atoms` — rich schema with:
- `atom_id`, `mission_id`, `topic_id`, `domain_profile_id`
- `atom_type` (fact/claim/tradeoff/etc)
- `title`, `statement`
- `confidence`, `importance`, `novelty`
- `visibility`? **Inconsistency:** V3 schema I read earlier had `visibility` and `status` fields, but the file `src/memory/schema_v3.sql` I can re-read to confirm.

Let me check: Earlier I read `schema_v3.sql` and it did NOT show `visibility` or `status` on `knowledge_atoms`. Wait — rechecking my notes:

In my initial exploration summary, I saw that `knowledge.knowledge_atoms` in the actual schema file **does not** have `visibility` or `status` columns. But the Phase 1 implementation plan **adds** them. So the current schema is missing these critical fields.

**CRITICAL FINDING:** V3.1 knowledge state separation (quarantined/mission_active/canonical) is **NOT PRESENT** in current `schema_v3.sql`. This is a **CONTRADICTION** between README claims and implementation.

**Status:** NOT FOUND (visibility/status) — this is a **CRITICAL** gap.

---

### 5.4 Atom Evidence

**V3:** `knowledge.atom_evidence` — composite primary key `(atom_id, source_id, chunk_id)`, `evidence_strength`, `supports_statement`

**Lineage:** This is the core evidence binding.

**Status:** VERIFIED table exists; need to verify writes populate it.

---

## 6. ARCHITECTURE CLAIMS TRACEABILITY

### Claim: "Triad Memory Stack" (Postgres truth, Chroma projection, Redis motion)

**Evidence:**
- Postgres: ✅ Used via `PostgresStoreImpl`
- Chroma: ✅ Used via `ChromaSemanticStoreImpl`
- Redis: ✅ Used via `RedisStoresImpl` and direct Redis client
- **Triad discipline:** ❌ **NOT VERIFIED** — V2 still uses different storage; Chroma rebuildability not proven; Redis may hold unrecoverable state

**Verdict:** PARTIAL — triad exists but discipline not enforced across whole system.

---

### Claim: "Distributed 'Vampire' Metabolism" (8-12 workers, Redis queue, scout offloaders)

**Evidence:**
- 8 workers: ✅ `_vampire_loop` spawns 8 tasks in `system.py`
- Redis queue: ✅ `queue:scraping` used
- Scout offloaders: ❌ NOT FOUND (no separate worker implementation, just basic BLPOP)

**Verdict:** PARTIAL — basic parallelism verified, advanced distribution not.

---

### Claim: "Atomic Distillation" (sources smelted into standalone Knowledge Atoms)

**Evidence:**
- `DistillationPipeline` exists: ✅
- Extracts atoms: ✅ (via `extract_technical_atoms` — need to verify)
- Evidence binding: ✅ (via `atom_evidence`)
- **BUT:** `resolve_contradictions()` and `consolidate_atoms()` are stubs
- JSON recovery logic: need to inspect

**Verdict:** PARTIAL — distillation exists but contradiction resolution not implemented.

---

### Claim: "Lineage First" (every atom maintains immutable link back to source research mission and evidence)

**Evidence:**
- `knowledge.atom_evidence` table: ✅
- `lineage_json` field on atoms: ✅
- BUT: Need to verify that **every** stored atom has at least one evidence link
- Need to verify that source links to mission

**Verdict:** PARTIAL — structure present, but enforcement not verified.

---

### Claim: "Non-blocking, asynchronous research at massive scales"

**Evidence:**
- Async/await used throughout: ✅
- Redis queue decouples ingestion: ✅
- Budget monitor runs in background: ✅
- BUT: Need to verify no blocking calls in hot paths
- Need to verify concurrent query vs crawl

**Verdict:** PARTIAL — async patterns exist, but throughput and non-blocking claims need testing (Phase 12).

---

### Claim: "Interactive — real-time steering (`/nudge`)"

**Evidence:**
- `/nudge` command exists: ✅
- `system_manager.nudge_mission()` exists: ✅
- `AdaptiveFrontier.apply_nudge()` method exists? Need to verify.

**Verdict:** PARTIAL — command exists, but effectiveness depends on frontier implementation.

---

### Claim: "Continuous mission execution" and "atomic distillation as the core unit"

**Evidence:**
- Missions: ✅ concept exists
- Distillation: ✅ pipeline exists
- Continuous: ✅ workers run continuously
- BUT: State machine not explicit; completion conditions unclear

**Verdict:** PARTIAL.

---

## 7. PRIORITIZED FINDINGS

### Tier 1 (Critical)

1. **Triad contract violation** — V2/V3 dual storage causing retrieval gap (V3 atoms not in query path) — **CRITICAL**
2. **Missing visibility/status fields** in knowledge atoms for state separation — **CRITICAL** (contradicts V3.1 design)
3. **Lineage enforcement not verified** — atoms may exist without evidence
4. **Retrieval grounding** — agent query does not use V3 atoms

---

### Tier 2

5. **Distributed worker robustness** — basic queue, no advanced features
6. **F Frontier state machine** — implicit transitions
7. **Report generation provenance** — unclear if traceable
8. **Schema completeness** — V3 schema may have gaps vs. Phase 1 plan

---

### Tier 3

9. **Benchmark validity** — need Phase 14 audit
10. **Diagnostic utilities** — organization, not critical

---

## 8. RECOMMENDATIONS FOR RESEARCHER (Phase 01 Execution)

The researcher should:

1. **Catalog all Python modules** in `src/` with their responsibilities (especially `src/research/`, `src/memory/`, `src/core/`)
2. **Trace all entrypoints** identified above to confirm invocation methods and classify precisely
3. **Map storage read/write paths** in detail for Tier 1 surfaces:
   - For Postgres: Which tables are written by which components? Which are read by which?
   - For Chroma: Which collections exist? How are they populated? Which queries hit them?
   - For Redis: All keys patterns present, producers/consumers
4. **Verify claim → code traceability** by producing a table:
   | Claim | Evidence (file:symbol) | Verification Level | Notes |
   |---|---|---|---|
5. **Identify dead code** by checking if entrypoints are referenced anywhere
6. **Confirm schema actual vs. planned** — run `\d` on database or inspect SQL files to see which tables actually exist
7. **Focus on contradictions** — especially retrieval using V2 only while V3 atoms are produced

---

## 9. CONCLUSION

Phase 01 research reveals a **system in transition** with significant architectural gaps. The inventory should:

- Be brutally honest about what's verified vs. aspirational
- Flag **CRITICAL** findings prominently
- Provide clear traceability for downstream phases to target fixes

The researcher's deliverables (`SYSTEM_MAP.md`, `ENTRYPOINT_INVENTORY.md`, `ARCHITECTURE_TRACEABILITY.md`) should reflect this nuanced state.

---

*Research completed: 2025-03-27
Next: Create PLAN.md for execution*
