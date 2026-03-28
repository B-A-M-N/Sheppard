# PHASE 02 — V3 ACTIVATION IMPLEMENTATION PLAN

**Phase:** 02 (Activation)
**Type:** Implementation (not audit)
**Duration:** 1-2 weeks (intensive)
**Status:** Ready to start

---

## Mission

Transform Sheppard from V2 operational core to V3-activated foundation by implementing the missing core pieces:

1. Postgres canonical truth integration
2. V3 command surface (`/learn`, `/query`, `/report`, `/nudge`)
3. Decomposed pipeline (frontier → discovery → queue → crawl → smelt → index)
4. Atom + lineage enforcement

This is **build work**, not verification. The outcome must be a system where the V3 architecture claims are **actually present and reachable**.

---

## Success Criteria (Gate to Resume Gauntlet)

Phase 02 is complete when **all** of these are **demonstrably true**:

- [ ] **Postgres is live:** V3 schema applied, data is written and read from Postgres tables (`mission.*`, `corpus.*`, `knowledge.*`)
- [ ] **`/learn` command exists:** Can invoke `/learn <topic>` and it creates a mission record in Postgres, runs the pipeline, produces atoms with evidence
- [ ] **`/query` command exists:** Can query accumulated knowledge and get answers grounded in stored atoms (with citations)
- [ ] **`/report` command exists:** Can generate report from stored atoms and lineage
- [ ] **`/nudge` command exists:** Can steer frontier during active mission
- [ ] **Pipeline stages separable:** Can observe/disentangle frontier, discovery, crawl, smelt, index as distinct stages (even if in one process)
- [ ] **Atoms + evidence stored:** Atoms exist in `knowledge.knowledge_atoms` with at least one `atom_evidence` link per atom
- [ ] **Lineage traceable:** Can query: mission → sources → chunks → atoms → report sections and prove each link

**These are binary gates.** No partial credit. The system must demonstrably exhibit V3 behavior.

---

## Scope & Boundaries

### In Scope (Must Build)

1. **Postgres Integration**
   - Apply `src/memory/schema_v3.sql` to create all V3 tables
   - Wire `PostgresStoreImpl` (from `src/memory/adapters/postgres.py`) into the system as canonical write/read
   - Ensure all mission/source/atom writes go to Postgres
   - Ensure all queries read from Postgres (or from Chroma that can be rebuilt from Postgres)

2. **Command Surface**
   - Add V3 commands to `src/core/commands.py`:
     - `/learn` → calls `SystemManager.start_mission()` or equivalent
     - `/query` → calls retrieval over V3 atoms
     - `/report` → generates synthesis artifacts
     - `/nudge` → modifies frontier parameters
   - Ensure these are the **primary** interface (old `/research`, `/memory` can remain as aliases or be removed)

3. **Pipeline Decomposition**
   - Split `ResearchSystem.research_topic()` into separate, observable stages:
     - `Frontier.run(mission_id)` → yields `ConceptTask` objects
     - `Discovery.search_concept(concept)` → returns URLs
     - `Queue.enqueue(urls)` → pushes to Redis
     - `Crawler.fetch(url)` → returns raw content
     - `Smelter.distill(content)` → returns atoms
     - `Indexer.store(atoms)` → writes to Postgres + Chroma
   - Each stage should be a distinct function/class with clear inputs/outputs
   - Ensure async/background execution where appropriate

4. **Atom + Lineage**
   - Ensure atom extraction produces structured atoms with `atom_type`, `statement`, `confidence`, etc.
   - Enforce evidence binding: every atom must have at least one source + chunk reference
   - Write to `knowledge.knowledge_atoms` AND `knowledge.atom_evidence`
   - Ensure atomic transactions (use `ON CONFLICT` idempotency)
   - Add validation: reject atoms without evidence

5. **Mission State**
   - Create `mission.research_missions` record on `/learn`
   - Update status as pipeline progresses
   - Store `mission_id` on all derived entities (sources, atoms, reports)

### Out of Scope (Defer to Later Gauntlet Phases)

- Performance optimization
- Scaling beyond single machine
- Advanced contradiction resolution
- Advanced synthesis/tier 4 briefs
- UI/web interface
- Multi-node deployment
- Full V3 feature parity (some fields in schema can be left NULL initially)

---

## Task Breakdown

### Task 1: Postgres Schema & Connection Validation

**Objective:** Verify Postgres is reachable and apply V3 schema.

**Actions:**

1. Check `.env` for `POSTGRES_DSN` or equivalent
2. Write simple script to connect and apply `src/memory/schema_v3.sql`
3. Verify tables created: `SELECT * FROM information_schema.tables WHERE table_schema IN ('mission','corpus','knowledge','authority')`
4. Test basic CRUD: insert dummy mission, query back

**Deliverable:** Script `scripts/apply_v3_schema.py` + confirmation of table creation

**Acceptance:** All V3 tables exist and are accessible from application code

---

### Task 2: Wire PostgresStoreImpl into System

**Objective:** Make Postgres the canonical write destination for mission/source/atom data.

**Actions:**

1. Review `src/memory/adapters/postgres.py` — ensure all required methods implemented for:
   - `MissionStore`: `create_mission`, `update_mission_status`, `get_mission_state`
   - `CorpusStore`: `ensure_source`, `create_chunk`, `create_text_ref`
   - `KnowledgeStore`: `create_atom`, `create_evidence`, `get_atoms_by_mission`
2. Instantiate `PostgresStoreImpl` in `SystemManager` (or `ResearchSystem`) initialization
3. Replace V2 storage calls (likely to Redis/Chroma directly) with adapter calls
4. For read path: ensure retrieval queries hit Postgres (or Chroma built from Postgres)
5. Test: run a mini-research and verify data lands in Postgres tables

**Deliverable:** Modified `src/core/system.py` (or equivalent) using Postgres adapter

**Acceptance:** After research, `mission.*`, `corpus.*`, `knowledge.*` tables populated

---

### Task 3: Implement `/learn` Command

**Objective:** Add primary entrypoint that starts a V3 mission.

**Actions:**

1. In `src/core/commands.py`, add `cmd_learn(topic: str)`:
   - Calls `SystemManager.start_mission(topic)` (or `ResearchSystem.start_mission()`)
   - `start_mission` should:
     - Generate `mission_id`
     - Insert record into `mission.research_missions` (status='discovering')
     - Kick off pipeline in background task (async)
     - Return mission_id to user immediately
2. Ensure `SystemManager` or `ResearchSystem` has method to start mission asynchronously
3. Test: `/learn "quantum computing"` → prints mission_id, mission record in DB, pipeline starts

**Deliverable:** `/learn` command functional, creates DB-backed mission

**Acceptance:** Can start mission via `/learn` and see it in `mission.research_missions`

---

### Task 4: Decompose Pipeline

**Objective:** Separate monolithic research into distinct stages.

**Actions:**

1. Identify current monolithic method (likely `ResearchSystem.research_topic()`)
2. Refactor into distinct functions/classes:
   - `Frontier` (from `src/research/acquisition/frontier.py`) → `run(mission_id, topic)` yields `ConceptTask`
   - `Discovery` (from `src/research/acquisition/crawler.py` or `discoverer`) → `search(concept)` returns URLs
   - `Queue` (from `src/memory/adapters/redis.py` or new) → `enqueue_urls(mission_id, urls)`
   - `CrawlerWorker` (existing code) → `fetch(url)` returns content
   - `Smelter` (from `src/research/condensation/pipeline.py`) → `distill(content)` returns atoms
   - `Indexer` → uses `PostgresStoreImpl` + `ChromaSemanticStoreImpl` to persist
3. Ensure data flows: frontier → discovery → queue → (worker) → crawl → smelt → index
4. Make stages independently testable (can call frontier alone, etc.)
5. Keep async flow: use `asyncio` or background threads

**Deliverable:** Refactored pipeline with clear separation; each stage has single responsibility

**Acceptance:** Can instrument/log each stage separately; can replace one stage without breaking others

---

### Task 5: Implement `/query` with Retrieval Over V3 Atoms

**Objective:** Add interactive query that retrieves from stored knowledge atoms.

**Actions:**

1. Ensure `HybridRetriever` or create new `V3Retriever` that:
   - Queries `knowledge.knowledge_atoms` (via Postgres) or Chroma `knowledge_atoms` collection
   - Supports semantic search on atom `statement` embeddings
   - Returns atoms with evidence links
2. Add `cmd_query(question: str)` to `commands.py`:
   - Generates embedding for question
   - Calls retriever
   - Formats context with atom statements + citations
   - Calls LLM to synthesize answer
   - Returns answer with provenance (atom IDs, sources)
3. Test: after some atoms exist, `/query "what is X"` returns answer citing atoms

**Deliverable:** `/query` command that retrieves and synthesizes from stored atoms

**Acceptance:** Query results include references to specific atoms and their sources

---

### Task 6: Implement `/report` Generation

**Objective:** Generate report from accumulated atoms.

**Actions:**

1. Create `ReportGenerator` class:
   - Queries atoms for mission/topic
   - Groups by theme or outline
   - Synthesizes sections using LLM
   - Inserts into `authority.synthesis_artifacts` and related tables
2. Add `cmd_report(topic_or_mission_id: str)` to `commands.py`:
   - Calls `ReportGenerator.generate(mission_id)`
   - Stores artifact, returns artifact_id or path
3. Ensure report generation uses only stored atoms (no fresh crawling)

**Deliverable:** `/report` command produces stored synthesis artifact

**Acceptance:** Report artifact exists in `authority.synthesis_artifacts` with lineage to atoms

---

### Task 7: Implement `/nudge` Frontier Steering

**Objective:** Allow real-time adjustment of frontier behavior.

**Actions:**

1. Ensure `AdaptiveFrontier` has `apply_nudge(instruction: str)` method
   - Parses instruction (could be simple keywords or LLM interpretation)
   - Adjusts parameters: `depth`, `mode_weights`, `search_pages`, etc.
   - Updates frontier state in `ops.mission_state` or similar
2. Add `cmd_nudge(instruction: str)` to `commands.py`:
   - Gets current mission (from context or specified)
   - Calls `frontier.apply_nudge(mission_id, instruction)`
3. Test: during active `/learn`, `/nudge "focus more on implementation details"` modifies frontier behavior

**Deliverable:** `/nudge` command alters frontier parameters

**Acceptance:** Frontier behavior changes after nudge (observable via logs or state)

---

### Task 8: Enforce Atom + Lineage Validation

**Objective:** Ensure no atom can be stored without evidence.

**Actions:**

1. In `Smelter` or `DistillationPipeline`:
   - Before writing atom, check that `atom_evidence` links exist
   - Reject or flag atoms with zero evidence
2. In `PostgresStoreImpl.create_atom()`:
   - Wrap insert in transaction with evidence insert
   - Use `ON CONFLICT` to handle duplicates by `atom_hash`
3. Add database constraint if not present: `ALTER TABLE knowledge.knowledge_atoms ADD CHECK (lineage_json ? 'evidence_links')`
4. Test: attempt to insert atom without evidence → fails

**Deliverable:** Validation prevents lineage-free atoms

**Acceptance:** All atoms in DB have at least one corresponding `atom_evidence` row

---

### Task 9: Verification of V3 Activation Gate

**Objective:** Prove all success criteria are met.

**Actions:**

1. Write script `scripts/verify_v3_activation.py` that checks:
   - Postgres tables populated? (count rows in `mission.research_missions`, etc.)
   - `/learn` command exists and runs? (invoke programmatically or via CLI test)
   - Pipeline stages separable? (log each stage during run)
   - Atoms with evidence? (query `knowledge.atom_evidence` non-empty)
   - `/query` works? (run and check answer includes atom citations)
   - `/report` works? (run and check artifact stored)
   - `/nudge` works? (run and check frontier state changed)
2. Run end-to-end: `/learn "test topic"` → wait → `/query "question"` → `/report`
3. Document evidence: screenshots, logs, DB queries

**Deliverable:** `V3_ACTIVATION_VERIFICATION.md` with pass/fail for each gate

**Acceptance:** All gates PASS

---

## Validation & Testing

### Unit Tests (if time)

- `tests/unit/test_postgres_adapter.py` — CRUD operations
- `tests/unit/test_pipeline_stages.py` — each stage independently
- `tests/unit/test_lineage_validation.py` — rejection of evidence-free atoms

### Integration Test (must have)

- `tests/integration/test_v3_activation.py`:
  - `/learn` → mission created
  - Wait for pipeline to produce atoms
  - `/query` returns answer with atom citations
  - `/report` generates artifact
  - Verify all DB tables populated

### Manual Smoke Test (required)

Run:

```bash
$ python main.py
> /learn "distributed systems fundamentals"
# Let it run...
> /status  # should show active mission
> /query "what is consensus?"
# Should return answer referencing atoms
> /report <mission_id>
# Should create report artifact
> /nudge "focus more on practical algorithms"
# Should log nudge applied
```

Verify with direct SQL:

```sql
SELECT COUNT(*) FROM mission.research_missions;
SELECT COUNT(*) FROM knowledge.knowledge_atoms;
SELECT COUNT(*) FROM knowledge.atom_evidence;
SELECT * FROM authority.synthesis_artifacts LIMIT 1;
```

---

## Risk & Mitigation

| Risk | Impact | Mitigation |
|------|--------|------------|
| Postgres connection fails | Blocking | Verify `.env` credentials, test connection early |
| V2 code resists decomposition | High | May need to refactor `ResearchSystem` heavily; allocate extra time |
| Chroma rebuild needed | Medium | Write script to clear and rebuild from Postgres after activation |
| Command conflicts (V2/V3) | Medium | Decide: remove V2 commands or alias them |
| Atom extraction fails without V2 legacy | High | Port extraction logic from V2 `extractors.py` to V3 Smelter |
| Performance degrades | Medium | Accept temporary slowdown; optimize later |

---

## File Manifest (What Will Be Created/Modified)

### New Files

- `scripts/apply_v3_schema.py`
- `scripts/verify_v3_activation.py`
- `V3_ACTIVATION_VERIFICATION.md`

### Modified Files

- `src/memory/adapters/postgres.py` (complete implementation if gaps)
- `src/core/system.py` or `src/research/base_system.py` (wire Postgres)
- `src/core/commands.py` (add `/learn`, `/query`, `/report`, `/nudge`)
- `src/research/acquisition/frontier.py` (ensure separable)
- `src/research/condensation/pipeline.py` (ensure separable, evidence enforcement)
- `src/research/archivist/retriever.py` or create new V3 retriever

### Configuration

- `.env` — ensure `POSTGRES_DSN` set correctly

---

## Execution Order (Recommended)

1. Day 1: Tasks 1-2 (Postgres integration)
2. Day 2: Task 3 (`/learn` command)
3. Day 3: Task 4 (pipeline decomposition)
4. Day 4: Task 8 (lineage validation)
5. Day 5: Tasks 5-6 (`/query`, `/report`)
6. Day 6: Task 7 (`/nudge`)
7. Day 7: Task 9 (verification) + polish

---

## Post-Activation

Once V3 activation gates pass:

1. Create `V3_ACTIVATION_COMPLETE.md` with evidence
2. Resume hardening gauntlet at **Phase 03** (renumbered):
   - Phase 03: Triad Memory Contract Audit (now real)
   - Phase 04: Lineage Integrity (now enforced)
   - Phase 05: `/learn` Pipeline Path Audit (now exists)
   - ... continue through 18

The audit phases will now have real code to verify instead of aspirational artifacts.

---

## Non-Negotiable

**Do NOT proceed to next gauntlet phase until V3 activation gates are demonstrably PASS.**

This is the **point of no return**. After this, the system identity is V3 and the remaining phases make sense.

---

**Start execution.**
