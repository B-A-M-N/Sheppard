# Phase 01 Execution Plan — Ground-Truth System Inventory

**Phase:** 01
**Status:** Ready for execution
**Date:** 2025-03-27

---

## Phase Summary

Comprehensive audit of Sheppard V3's actual implementation surfaces, storage systems, and pipeline paths. Map every executable entrypoint, storage table/collection, and verify architecture claims against code evidence.

**Primary deliverable:**
- `SYSTEM_MAP.md` — complete topology
- `ENTRYPOINT_INVENTORY.md` — catalog with classification
- `ARCHITECTURE_TRACEABILITY.md` — claim → evidence table

**Success criteria:**
- All production surfaces enumerated and classified
- All storage systems mapped (Postgres, Chroma, Redis)
- All architecture claims traced to code with verification level
- Critical gaps flagged (Tier 1 findings)
- No dead code misrepresented as active

---

## Task Breakdown

### Task 1: Entrypoint Enumeration & Classification

**Objective:** Identify all executable surfaces and classify by role.

**Actions:**
1. Search repository for Python entrypoints:
   ```bash
   find . -name "*.py" -type f | grep -E "(main|worker|scout|refinery|setup|wipe|bench|diag|check)" | grep -v __pycache__ | sort
   ```
2. For each candidate, inspect:
   - `if __name__ == "__main__"` blocks
   - CLI argument parsing (argparse/click/typer)
   - Invocation patterns in docs/README
3. Classify into: `production`, `worker`, `operator/admin`, `diagnostic`, `benchmark`, `migration/setup`, `unsafe/destructive`
4. Determine call graph: is it referenced elsewhere? Or standalone?

**Output:** List of entrypoints with file path, classification, invocation command, and reachability status (`VERIFIED` if called in normal operation, `NOT_FOUND` if dead code).

**Tools:** Bash find, Grep, Read

**Acceptance:**
- [ ] All top-level `*_worker.py`, `*_setup.py`, `main.py`, etc. found
- [ ] Classification applied to each
- [ ] Dead code identified and marked

---

### Task 2: Storage Systems Deep Dive

**Objective:** Map Postgres, Chroma, Redis usage in detail.

#### 2.1 Postgres Schema & Access

**Actions:**
1. Locate all SQL schema files:
   - `src/memory/schema_v3.sql`
   - `src/memory/schema.sql`
2. For each, list all tables, indexes, constraints, foreign keys
3. Identify which schema (config, mission, corpus, knowledge, authority, application) each table belongs to
4. Search codebase for table access:
   ```bash
   grep -r "INSERT INTO\|SELECT FROM\|UPDATE.*knowledge\|corpus\|mission" src/ --include="*.py"
   ```
5. Categorize read/write paths by component:
   - Frontier writes to `mission.*`?
   - Crawler writes to `corpus.sources`?
   - Distiller writes to `knowledge.knowledge_atoms`?
   - Retriever reads from which tables?

**Output:**
- Table of all Postgres tables with: purpose, write component, read components, key fields
- Highlight missing tables (e.g., `visibility` on knowledge_atoms if absent)

**Acceptance:**
- [ ] All tables from both schemas enumerated
- [ ] Write ownership assigned
- [ ] Read patterns documented

#### 2.2 Chroma Collections

**Actions:**
1. Find Chroma client initialization: `chromadb.PersistentClient` or `chromadb.HttpClient`
2. Locate collection names:
   - Search `.get_collection(`, `.create_collection(`, collection name strings
3. List all collections referenced
4. For each collection:
   - Which component writes to it?
   - Which component reads from it?
   - What metadata is stored?
   - Is it V2 or V3?

**Output:**
- Table: collection name, purpose, writer, reader, V2/V3 alignment

**Acceptance:**
- [ ] All collections identified
- [ ] Write/read mapping complete

#### 2.3 Redis Keys & Queues

**Actions:**
1. Find Redis configuration: `src/config/database.py` for connection
2. Search for `redis.` method calls in code:
   - `.zadd(`, `.zpopmax(`, `.blpop(`, `.set(`, `.get(`, `.delete(`
3. Extract key patterns and their purposes
4. Document queue semantics (list? sorted set? pub/sub?)
5. Note any lock patterns

**Output:**
- Redis key inventory with pattern, producer, consumer, TTL, data type

**Acceptance:**
- [ ] All Redis operations found
- [ ] Queue contracts documented

---

### Task 3: Pipeline & Command Path Tracing

**Objective:** Verify that key commands actually execute end-to-end.

**Focus commands:** `/learn`, `/query`, `/report`, `/status`

**Actions:**
1. For `/learn`:
   - Start at `commands.py` → `system_manager.learn()`
   - Trace mission creation: where stored? (V2 memory or V3 Postgres?)
   - Trace frontier → discovery → queue enqueue
   - Trace worker dequeue → crawl → ingest
   - Trace condensation trigger → atom extraction → storage
   - Document each handoff point
2. For `/query`:
   - Trace retrieval path: which tables/collections queried?
   - Does it hit V3 atoms or only V2?
   - How is context assembled?
3. For `/report`:
   - Trace report generation: inputs, processing, output storage
4. For `/status`:
   - What data is shown? Where does it come from?

**Output:**
- For each command: flow diagram in text or markdown table showing functions called and storage accessed

**Acceptance:**
- [ ] `/learn` path traced from start to atom storage
- [ ] `/query` path traced with data sources identified
- [ ] Gaps and dead ends noted

---

### Task 4: Architecture Claims Verification

**Objective:** Cross-check README claims against code evidence.

**Claims to verify (from README):**
1. Triad Memory Stack enforced
2. Distributed Vampire Metabolism (8-12 workers, Redis queue, scout offloaders)
3. Atomic Distillation with JSON recovery
4. Lineage First guarantee
5. Non-blocking async research
6. Real-time steering (`/nudge`)
7. Continuous mission execution
8. Commands: `/learn`, `/status`, `/nudge`, `/report`

**Actions:**
1. For each claim, locate code evidence:
   - File path + function/class names
   - If NOT FOUND or PARTIAL, specify what's missing
2. Assign verification level:
   - `NOT FOUND` — no implementation
   - `PARTIAL` — exists but incomplete or disconnected
   - `VERIFIED` — implemented and reachable
   - `DEMONSTRATED` — verified plus runtime/test evidence (if we have logs/tests)
3. Flag contradictions (e.g., claim says X but code does Y)

**Output:**
- `ARCHITECTURE_TRACEABILITY.md` — table with columns: Claim, Evidence (file:symbol), Verification Level, Notes, Critical?

**Acceptance:**
- [ ] All major claims evaluated
- [ ] Contradictions called out
- [ ] Critical gaps flagged

---

### Task 5: Critical Findings Synthesis

**Objective:** Compile Tier 1 gaps for escalation.

**Actions:**
1. From Task 4, extract claims marked PARTIAL/NOT_FOUND that are foundational
2. Write concise finding statements:
   - What's missing or contradicted
   - Why it matters (risk)
   - Suggested category (e.g., "Storage Contract Violation", "Pipeline Gap")
3. Prioritize: Critical (blocks V3) vs. Important vs. Nice-to-have

**Output:**
- Section in `SYSTEM_MAP.md` listing critical findings with rationale

**Acceptance:**
- [ ] At least 3 critical findings documented (expected: triad discipline, retrieval grounding, lineage enforcement)
- [ ] Each finding has clear evidence reference

---

### Task 6: Deliverables Compilation

**Objective:** Produce final deliverable files.

**Files to create:**

1. **SYSTEM_MAP.md** — comprehensive system overview
   - Runtime topology (describe how components connect)
   - Execution entrypoints table
   - Storage surfaces (Postgres tables, Chroma collections, Redis keys)
   - Pipeline stages (discovery → crawl → distill → index)
   - Retrieval/query path
   - Reporting path
   - External dependencies (Postgres, Redis, Chroma, Ollama, Firecrawl)
   - Unknowns and dead ends
   - Critical findings section

2. **ENTRYPOINT_INVENTORY.md** — detailed catalog
   - Table: Entrypoint, File, Classification, Invocation, Reachability, Notes

3. **ARCHITECTURE_TRACEABILITY.md** — claim verification matrix
   - Table: Claim, Evidence (with file:line), Verification Level, Critical?, Notes

4. **PHASE-01-VERIFICATION.md** — verdict

**Acceptance:**
- [ ] All 4 files exist with substantial content
- [ ] Evidence explicitly cited (file paths, function names)
- [ ] No vague statements without code reference

---

## Verification Checklist (Pre-Sign-off)

Before marking Phase 01 VERIFIED, ensure:

- [ ] **Completeness:** Every Python file in `src/` is accounted for in some component description
- [ ] **Entrypoints:** All main entrypoints listed with correct classification
- [ ] **Storage:** Postgres tables fully enumerated; Chroma collections identified; Redis key patterns documented
- [ ] **Claims:** Every README claim has a row in traceability table
- [ ] **Critical gaps:** At least top 3 critical findings documented with justification
- [ ] **Evidence:** All assertions backed by file references (no hand-waving)
- [ ] **No dead code misrepresented:** Unreachable functions marked as `PARTIAL` or `NOT_FOUND`

---

## Risk Notes

- **Schema mismatch:** V3 schema file may not match actual database — if possible, connect to DB and run `\dt` to verify real tables. If not possible, note as limitation.
- **Dead code:** Some functions may be imported but never called — rely on grep for call sites, but acknowledge uncertainty
- **Configuration:** Actual runtime config (`.env`) may differ from defaults — note assumptions

---

## Execution Instructions

1. Read this PLAN.md thoroughly
2. Execute tasks in order (they build on each other)
3. Write findings incrementally to the deliverable files
4. At end, fill `PHASE-01-VERIFICATION.md` with verdict PASS/PARTIAL/FAIL
5. Update `.planning/gauntlet_phases/STATUS.md` with completion status

---

**Remember:** This is an inventory, not a fix. Document honestly. If the system is broken, say so. If claims are aspirational, mark them NOT_FOUND. The goal is truth, not propaganda.
