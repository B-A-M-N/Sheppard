# Sheppard V3 Hardening Gauntlet — GSD Command Pack

**Usage:** Copy each phase's command and execute with `/gsd:do` or equivalent GSD orchestrator.

**Prerequisites:**
- GSD workflow installed and configured
- Sheppard V3 repository initialized with `.planning/` directory
- Claude Code / GSD agent available

---

## PHASE 01 — GROUND-TRUTH SYSTEM INVENTORY

### Command

```
/gsd:do
```

### Prompt

```
You are executing Phase 01 for Sheppard V3: Ground-Truth System Inventory.

Mission:
Create a complete, evidence-bound inventory of the real system as implemented, not as described aspirationally.

Objectives:
1. Enumerate all entrypoints (main.py, workers, CLI)
2. Enumerate all worker processes
3. Enumerate all storage systems and their usage
4. Enumerate all queues, schemas, collections, tables, indexes
5. Enumerate all CLI commands, slash commands, API routes, background jobs
6. Identify all declared architecture claims in README/docs and verify whether each exists in code

Required method:
- Inspect repository structure
- Inspect startup scripts
- Inspect main application entrypoints
- Inspect worker/orchestration code
- Inspect memory/storage code
- Inspect configuration/env loading code
- Inspect docs/README for architecture claims
- Build traceability from claim → file → symbol/function/class

Deliverables (write to .planning/phase01_inventory/):
- SYSTEM_MAP.md
- ENTRYPOINT_INVENTORY.md
- ARCHITECTURE_TRACEABILITY.md
- PHASE-01-VERIFICATION.md

Mandatory sections in SYSTEM_MAP.md:
- Runtime topology
- Execution entrypoints
- Storage surfaces
- Queues and background processing
- Distillation pipeline stages
- Retrieval/query path
- Reporting path
- External dependencies
- Unknowns / dead ends / missing links

Mandatory outputs:
- A table of every architecture claim with status:
  - VERIFIED (code exists and matches claim)
  - PARTIAL (code exists but incomplete)
  - NOT FOUND (no code found)
  - CONTRADICTED (code contradicts claim)

Hard fail conditions:
- Any major README claim is accepted without code verification
- Any entrypoint is omitted
- Any storage layer is described vaguely without exact files/symbols
- Any "distributed" or "async" claim is left unproven

Completion bar:
Do not mark PASS unless the repo can be explained end-to-end with explicit file-level evidence.
```

### Expected Deliverables

```
.planning/phase01_inventory/
  SYSTEM_MAP.md
  ENTRYPOINT_INVENTORY.md
  ARCHITECTURE_TRACEABILITY.md
  PHASE-01-VERIFICATION.md
```

### Verification Criteria

- All entrypoints listed with exact file paths and invocation commands
- All storage systems mapped with read/write responsibilities
- All queues named with producers/consumers identified
- All README claims cross-referenced with code evidence
- Missing or contradicted items explicitly called out

---

## PHASE 02 — RUNTIME & BOOT PATH VALIDATION

### Command

```
/gsd:do
```

### Prompt

```
You are executing Phase 02 for Sheppard V3: Runtime & Boot Path Validation.

Mission:
Verify the real startup path, initialization sequence, dependency requirements, and boot-time failure modes.

Objectives:
1. Validate all documented startup commands
2. Validate environment loading and required configuration
3. Validate service dependency assumptions
4. Identify all boot blockers, silent failures, and hidden prerequisites
5. Prove whether the system can start cleanly from a fresh environment

Required method:
- Inspect startup scripts and shell wrappers
- Inspect config loading
- Inspect env var usage
- Inspect DB initialization and migrations
- Inspect service connection logic
- Run or simulate startup paths where possible
- Document all required services, ports, and sequencing assumptions

Deliverables (write to .planning/phase02_boot/):
- BOOT_SEQUENCE.md
- CONFIG_REQUIREMENTS.md
- STARTUP_FAILURE_MATRIX.md
- PHASE-02-VERIFICATION.md

Mandatory checks:
- What starts first?
- What fails if Postgres is absent?
- What fails if Redis is absent?
- What fails if Chroma is absent?
- What fails if Ollama is absent?
- What fails if Firecrawl/SearXNG are absent?
- Are errors explicit or hidden?
- Are defaults sane or dangerous?

Hard fail conditions:
- Startup docs do not match actual runtime behavior
- Required env vars are undocumented
- Services fail silently
- Initialization order is implicit rather than enforced

Completion bar:
PASS only if a new operator could start the system from the documented path without guesswork.
```

### Expected Deliverables

```
.planning/phase02_boot/
  BOOT_SEQUENCE.md
  CONFIG_REQUIREMENTS.md
  STARTUP_FAILURE_MATRIX.md
  PHASE-02-VERIFICATION.md
```

---

## PHASE 03 — TRIAD MEMORY CONTRACT AUDIT

### Command

```
/gsd:do
```

### Prompt

```
You are executing Phase 03 for Sheppard V3: Triad Memory Contract Audit.

Mission:
Audit the full memory architecture and verify that each store has a clear, enforced responsibility with no truth leakage.

Objectives:
1. Map all reads and writes to Postgres
2. Map all reads and writes to Chroma
3. Map all reads and writes to Redis
4. Identify overlap, duplication, leakage, or contract violations
5. Determine whether Chroma can be fully rebuilt from Postgres
6. Determine whether Redis can be lost without losing truth

Required method:
- Inspect all storage client usage
- Trace write paths from ingestion through retrieval
- Identify where canonical data is first written
- Identify whether embeddings or atom truth bypass Postgres
- Identify whether queues carry unrecoverable state

Deliverables (write to .planning/phase03_triad_audit/):
- MEMORY_CONTRACT_AUDIT.md
- STORAGE_WRITE_MATRIX.md
- STORAGE_READ_MATRIX.md
- REBUILDABILITY_ASSESSMENT.md
- PHASE-03-VERIFICATION.md

Mandatory classification:
Every stored artifact must be classified as one of:
- Canonical truth (only in Postgres)
- Derived projection (in Chroma, derivable from Postgres)
- Ephemeral motion (in Redis, replacable)
- Misplaced / ambiguous (violates triad)

Hard fail conditions:
- Chroma contains truth not reconstructable from Postgres
- Redis holds unrecoverable mission state
- Postgres lineage is incomplete
- Storage responsibilities are fuzzy or mixed

Completion bar:
PASS only if storage contracts are explicit, enforceable, and evidenced in code.
```

---

## PHASE 04 — DATA MODEL & LINEAGE INTEGRITY

### Command

```
/gsd:do
```

### Prompt

```
You are executing Phase 04 for Sheppard V3: Data Model & Lineage Integrity.

Mission:
Verify that lineage is real, complete, and queryable.

Objectives:
1. Identify the mission model
2. Identify the source/document model
3. Identify the atom model
4. Identify the report/output model
5. Verify all relationships and foreign-key-like bindings
6. Verify whether lineage can be reconstructed without guessing

Required method:
- Inspect schemas, ORM models, migrations, SQL files
- Trace lineage creation during ingestion/distillation
- Trace lineage consumption during retrieval/reporting
- Identify orphan risks and broken joins
- Identify where lineage is optional and whether that is acceptable

Deliverables (write to .planning/phase04_lineage/):
- LINEAGE_MAP.md
- ENTITY_RELATIONSHIP_AUDIT.md
- ORPHAN_RISK_REPORT.md
- PHASE-04-VERIFICATION.md

Mandatory questions:
- Can every atom be tied to a source?
- Can every source be tied to a mission?
- Can every report be tied to atoms?
- Can lineage survive retries/reprocessing?
- Is lineage immutable or overwritten?

Hard fail conditions:
- Atoms can exist without valid source lineage
- Reports can be generated without recoverable provenance
- Mission/source/atom relations are implied instead of enforced

Completion bar:
PASS only if lineage is structurally present and operationally used.
```

---

## PHASE 05 — `/learn` PIPELINE PATH AUDIT

### Command

```
/gsd:do
```

### Prompt

```
You are executing Phase 05 for Sheppard V3: /learn Pipeline Path Audit.

Mission:
Trace the complete lifecycle of a /learn request from input receipt to final atom storage.

Objectives:
1. Identify how /learn is parsed
2. Identify how missions are created
3. Identify how topic decomposition happens
4. Identify how discovery/search happens
5. Identify how URLs are queued
6. Identify how scraping is triggered
7. Identify how smelting/distillation is triggered
8. Identify how atoms are stored and indexed

Required method:
- Trace function calls end-to-end
- Produce a state transition map
- Identify async boundaries
- Identify retries, locks, dedupe, and queue semantics
- Identify all points where work can be lost, duplicated, or stall

Deliverables (write to .planning/phase05_learn_audit/):
- LEARN_EXECUTION_TRACE.md
- PIPELINE_STATE_MACHINE.md
- QUEUE_HANDOFF_AUDIT.md
- PHASE-05-VERIFICATION.md

Mandatory state chain:
At minimum document:
INPUT_RECEIVED
→ MISSION_CREATED
→ TOPIC_DECOMPOSED
→ URL_DISCOVERED
→ URL_QUEUED
→ URL_FETCHED
→ CONTENT_NORMALIZED
→ ATOMS_EXTRACTED
→ ATOMS_STORED
→ INDEX_UPDATED

Hard fail conditions:
- A state transition exists only implicitly
- Work can disappear silently
- Deduplication is undefined
- Retry behavior is undefined
- A major step depends on wishcasting

Completion bar:
PASS only if /learn can be described as a concrete state machine with evidence.
```

---

## PHASE 06 — DISCOVERY ENGINE VERIFICATION

### Command

```
/gsd:do
```

### Prompt

```
You are executing Phase 06 for Sheppard V3: Discovery Engine Verification.

Mission:
Audit the discovery layer to verify that topic expansion, search, and URL harvesting behave as claimed.

Objectives:
1. Verify taxonomic decomposition exists
2. Verify epistemic mode selection exists
3. Verify multi-page search/deep mine behavior exists
4. Verify discovery dedupe and prioritization
5. Verify that discovered URLs are relevant and non-trivial

Required method:
- Inspect decomposition code and prompts
- Inspect search integrations
- Inspect discovery scheduling and fanout
- Inspect relevance filtering and dedupe logic
- Run or inspect example outputs where possible

Deliverables (write to .planning/phase06_discovery/):
- DISCOVERY_AUDIT.md
- TAXONOMY_GENERATION_AUDIT.md
- SEARCH_BEHAVIOR_REPORT.md
- URL_SELECTION_HEURISTICS.md
- PHASE-06-VERIFICATION.md

Mandatory ambiguity extraction:
Explicitly surface:
- decomposition depth defaults
- search page depth defaults
- result scoring rules
- rejection criteria
- obscure-source discovery proof vs. aspiration

Hard fail conditions:
- Discovery is just thin search wrapping with inflated claims
- Taxonomy generation is claimed but not enforced
- Search depth is claimed but not implemented
- URL quality controls are absent

Completion bar:
PASS only if discovery behavior is concretely evidenced and operationally meaningful.
```

---

## PHASE 07 — DISTRIBUTED QUEUE & WORKER AUDIT

### Command

```
/gsd:do
```

### Prompt

```
You are executing Phase 07 for Sheppard V3: Distributed Queue & Worker Audit.

Mission:
Audit the distributed worker model, shared queue behavior, concurrency controls, and failure handling.

Objectives:
1. Verify the Redis queue contract
2. Verify multiple workers can consume safely
3. Verify duplicate consumption protection
4. Verify retry and poison-job handling
5. Verify worker heartbeats, liveness, or equivalent observability
6. Verify remote node/offloader behavior is real

Required method:
- Inspect worker code
- Inspect queue semantics
- Inspect lock usage
- Inspect job lifecycle
- Inspect any heartbeat/worker registry mechanisms
- Identify concurrency hazards and race conditions

Deliverables (write to .planning/phase07_workers/):
- WORKER_MODEL_AUDIT.md
- QUEUE_SEMANTICS_REPORT.md
- DUPLICATION_AND_LOCKING_AUDIT.md
- DISTRIBUTED_FAILURE_MODES.md
- PHASE-07-VERIFICATION.md

Mandatory questions:
- At-least-once or exactly-once?
- How are stuck jobs detected?
- What happens if a worker dies after claiming work?
- Can two workers process the same URL?
- Is node identity meaningful or cosmetic?

Hard fail conditions:
- Duplicate processing is uncontrolled
- Queue claims are optimistic but unenforced
- Dead worker recovery is undefined
- "distributed" is only conceptual

Completion bar:
PASS only if distributed processing semantics are explicit and defended.
```

---

## PHASE 08 — SCRAPING / CONTENT NORMALIZATION AUDIT

### Command

```
/gsd:do
```

### Prompt

```
You are executing Phase 08 for Sheppard V3: Scraping / Content Normalization Audit.

Mission:
Audit the content acquisition and normalization path to verify that fetched content is usable for downstream distillation.

Objectives:
1. Verify fetch path(s) and source adapters
2. Verify PDF/static/web handling
3. Verify normalization format
4. Verify metadata capture
5. Verify source attribution preservation
6. Verify fallback/error handling for malformed content

Required method:
- Inspect scraper/fetcher code
- Inspect normalization/transformation code
- Inspect metadata extraction
- Inspect how failures and low-quality fetches are handled

Deliverables (write to .planning/phase08_scraping/):
- CONTENT_INGEST_AUDIT.md
- NORMALIZATION_SPEC_AS_IMPLEMENTED.md
- SOURCE_METADATA_AUDIT.md
- FETCH_FAILURE_REPORT.md
- PHASE-08-VERIFICATION.md

Mandatory checks:
- Is content chunked before or after normalization?
- Is raw source preserved?
- Are citations/URLs retained?
- How are PDFs treated?
- How are empty or low-signal pages rejected?

Hard fail conditions:
- Content is scraped but not normalized consistently
- Source metadata is lost
- Distillation inputs are malformed or underspecified
- The system cannot distinguish empty vs. useful content

Completion bar:
PASS only if the refinery input contract is explicit and stable.
```

---

## PHASE 09 — SMELTER / ATOM EXTRACTION AUDIT

### Command

```
/gsd:do
```

### Prompt

```
You are executing Phase 09 for Sheppard V3: Smelter / Atom Extraction Audit.

Mission:
Audit the atom extraction path to verify schema correctness, parsing robustness, and evidence integrity.

Objectives:
1. Identify the atom schema
2. Verify extraction prompts and parsers
3. Verify malformed JSON repair logic
4. Verify dedupe logic
5. Verify atom typing and evidence binding
6. Verify invalid extraction rejection criteria

Required method:
- Inspect distillation prompts
- Inspect parser and repair code
- Inspect validation rules
- Inspect storage write path for atoms
- Review sample atoms if available

Deliverables (write to .planning/phase09_smelter/):
- ATOM_SCHEMA_AUDIT.md
- EXTRACTION_PIPELINE_REPORT.md
- JSON_REPAIR_AUDIT.md
- ATOM_VALIDATION_AND_REJECTION_RULES.md
- PHASE-09-VERIFICATION.md

Mandatory checks:
- Are atoms standalone?
- Are atoms typed consistently?
- Is evidence attached or just implied?
- Can malformed model output poison the system?
- Are duplicates suppressed deterministically?

Hard fail conditions:
- Atom schema is soft or inconsistent
- Repair logic mutates meaning unsafely
- Atoms can be stored without validation
- Evidence linkage is weak or missing

Completion bar:
PASS only if atom extraction is bounded, typed, and evidence-preserving.
```

---

## PHASE 10 — RETRIEVAL & INTERACTIVE AGENT INTEGRATION

### Command

```
/gsd:do
```

### Prompt

```
You are executing Phase 10 for Sheppard V3: Retrieval & Interactive Agent Integration.

Mission:
Audit the interactive query path and verify that the agent can answer from accumulated knowledge while background research continues.

Objectives:
1. Identify the interactive chat/query entrypoint
2. Identify retrieval logic over atoms
3. Identify ranking/relevance logic
4. Identify how retrieved context is injected into responses
5. Verify whether live crawl knowledge becomes queryable incrementally
6. Verify fallback behavior when memory lacks coverage

Required method:
- Inspect chat/query code path
- Inspect retrieval adapters to Chroma/Postgres
- Inspect context-building logic
- Inspect whether response synthesis is grounded in stored atoms
- Inspect whether the system leaks back to generic model priors without warning

Deliverables (write to .planning/phase10_retrieval/):
- QUERY_PATH_AUDIT.md
- RETRIEVAL_GROUNDING_REPORT.md
- CONTEXT_ASSEMBLY_AUDIT.md
- LIVE_RESEARCH_INTERACTION_REPORT.md
- PHASE-10-VERIFICATION.md

Mandatory checks:
- Can the user ask a question during an active mission?
- Does the answer use atoms or just the base model?
- Is provenance available in responses?
- Is partial knowledge surfaced honestly?
- Is there a distinction between memory-grounded vs. model-native answer content?

Hard fail conditions:
- Interactive answers are not grounded
- Crawl results are not actually available to chat
- Retrieval exists but is not wired into response generation
- The system pretends certainty when memory is incomplete

Completion bar:
PASS only if interactive answering is truly memory-backed and compatible with async research.
```

---

## PHASE 11 — REPORT GENERATION AUDIT

### Command

```
/gsd:do
```

### Prompt

```
You are executing Phase 11 for Sheppard V3: Report Generation Audit.

Mission:
Audit report generation to verify that reports are built from stored atoms and lineage rather than ad hoc re-reasoning over thin context.

Objectives:
1. Identify the report command path
2. Identify report input sources
3. Verify whether reports consume atoms, sources, and lineage
4. Verify output structure
5. Verify evidence carry-through into the report

Required method:
- Inspect report generation logic
- Inspect input retrieval path
- Inspect citation or provenance handling
- Identify whether reports query live web or stored memory
- Inspect output templates or synthesis rules

Deliverables (write to .planning/phase11_reports/):
- REPORT_PIPELINE_AUDIT.md
- REPORT_INPUT_PROVENANCE.md
- REPORT_EVIDENCE_CARRYTHROUGH.md
- PHASE-11-VERIFICATION.md

Mandatory checks:
- Does /report use stored atoms only?
- Can it regenerate after Chroma rebuild?
- Are citations/source pointers retained?
- Is report identity tied to mission identity?

Hard fail conditions:
- Reports are detached from lineage
- Reports depend on fresh browsing when they should not
- Reports are synthesized from vague summaries rather than atoms

Completion bar:
PASS only if reports are memory-derived, reproducible, and provenance-bound.
```

---

## PHASE 12 — ASYNC / NON-BLOCKING EXECUTION AUDIT

### Command

```
/gsd:do
```

### Prompt

```
You are executing Phase 12 for Sheppard V3: Async / Non-Blocking Execution Audit.

Mission:
Audit the execution model to verify that crawling, distillation, retrieval, and interaction can coexist without blocking or corrupting each other.

Objectives:
1. Identify all async boundaries
2. Identify blocking operations in the main path
3. Identify lock contention risks
4. Identify shared resource bottlenecks
5. Verify whether user interaction remains responsive during heavy work

Required method:
- Inspect event loop/thread/process model
- Inspect worker boundaries
- Inspect main process responsiveness assumptions
- Identify synchronous network/model calls in hot paths
- Document backpressure and queueing behavior

Deliverables (write to .planning/phase12_async/):
- ASYNC_EXECUTION_MODEL.md
- BLOCKING_RISK_REPORT.md
- RESOURCE_CONTENTION_AUDIT.md
- OPERATOR_RESPONSIVENESS_REPORT.md
- PHASE-12-VERIFICATION.md

Mandatory checks:
- What blocks the main process?
- What blocks chat?
- What blocks atom storage?
- What blocks report generation?
- Where does backpressure accumulate?

Hard fail conditions:
- "async" is mostly marketing language
- Critical paths are synchronous and serial
- User interaction degrades catastrophically under load
- Locks/queues can starve important work

Completion bar:
PASS only if non-blocking behavior is real, measurable, and architecturally clear.
```

---

## PHASE 13 — FAILURE MODES & RECOVERY AUDIT

### Command

```
/gsd:do
```

### Prompt

```
You are executing Phase 13 for Sheppard V3: Failure Modes & Recovery Audit.

Mission:
Identify, classify, and verify the system's behavior under failure, interruption, malformed output, and partial state conditions.

Objectives:
1. Enumerate component failure modes
2. Enumerate data corruption risks
3. Enumerate partial-completion states
4. Verify restart/recovery behavior
5. Verify error surfacing quality

Required method:
- Inspect exception handling
- Inspect retries and failure queues
- Inspect recovery/startup reconciliation logic
- Inspect handling of malformed model outputs
- Inspect partial mission/job states

Deliverables (write to .planning/phase13_failures/):
- FAILURE_MODE_CATALOG.md
- RECOVERY_BEHAVIOR_AUDIT.md
- PARTIAL_STATE_HANDLING_REPORT.md
- ERROR_SURFACING_REVIEW.md
- PHASE-13-VERIFICATION.md

Mandatory scenarios:
- Postgres unavailable
- Redis unavailable
- Chroma unavailable
- Ollama unavailable
- Worker dies mid-job
- Model returns malformed JSON
- Source page is empty/garbage
- Mission halts halfway through

Hard fail conditions:
- Failures are hidden
- Recovery depends on operator intuition
- Partial states are unrecoverable
- Error logs are noisy but unhelpful

Completion bar:
PASS only if failure handling is explicit, bounded, and operator-comprehensible.
```

---

## PHASE 14 — BENCHMARK & EVALUATION CONTRACT AUDIT

### Command

```
/gsd:do
```

### Prompt

```
You are executing Phase 14 for Sheppard V3: Benchmark & Evaluation Contract Audit.

Mission:
Audit the benchmark framework and verify that reported scores reflect real system behavior, with clear scope and reproducibility.

Objectives:
1. Identify benchmark entrypoints
2. Identify benchmark datasets/tasks
3. Identify scoring logic
4. Verify what each score actually measures
5. Verify reproducibility and environment assumptions
6. Verify that benchmark claims do not overstate total system capability

Required method:
- Inspect benchmark scripts and scoring code
- Inspect datasets or fixtures
- Inspect result formatting
- Trace score calculation formulas
- Identify any scope mismatch between benchmark and README/claims

Deliverables (write to .planning/phase14_benchmark/):
- BENCHMARK_AUDIT.md
- SCORE_SEMANTICS_REPORT.md
- REPRODUCIBILITY_REVIEW.md
- CLAIM_SCOPE_CORRECTION.md
- PHASE-14-VERIFICATION.md

Mandatory checks:
- Do the scores only reflect research?
- Are memory and integration scores defined precisely?
- Is the environment dependency documented?
- Can the benchmark be rerun consistently?

Hard fail conditions:
- Scores are presented more broadly than they deserve
- Metrics are underdefined
- Benchmark tasks do not map cleanly to system behavior
- Results are irreproducible

Completion bar:
PASS only if benchmark meaning is narrow, explicit, and honest.
```

---

## PHASE 15 — AMBIGUITY EXTRACTION & CORRECTION REGISTER

### Command

```
/gsd:do
```

### Prompt

```
You are executing Phase 15 for Sheppard V3: Ambiguity Extraction & Correction Register.

Mission:
Produce a complete ambiguity and contradiction ledger for the system, docs, architecture claims, contracts, defaults, and execution semantics.

Objectives:
1. Extract every implementation ambiguity
2. Extract every README ambiguity
3. Extract every contract mismatch
4. Extract every undefined default or silent assumption
5. Classify each by severity and correction path

Required method:
- Review outputs from all prior phases
- Consolidate all UNKNOWN / PARTIAL / CONTRADICTED findings
- Group them by subsystem
- Recommend exact correction action for each

Deliverables (write to .planning/phase15_ambiguities/):
- AMBIGUITY_REGISTER.md
- CONTRADICTION_LEDGER.md
- CORRECTION_BACKLOG.md
- PHASE-15-VERIFICATION.md

Mandatory classification:
Each item must include:
- ID (unique identifier)
- subsystem (which component)
- ambiguity type (missing, contradictory, underspecified)
- observed evidence (what was found)
- risk (what breaks if unaddressed)
- recommended fix (exact code/doc change)
- affects (code, docs, or both)

Hard fail conditions:
- Ambiguities are handwaved into implementation choices
- Contradictions are buried in prose
- No correction path is proposed

Completion bar:
PASS only if the system's unclear areas are exhaustively surfaced and operationalized.
```

---

## PHASE 16 — CODE CORRECTION PLAN

### Command

```
/gsd:do
```

### Prompt

```
You are executing Phase 16 for Sheppard V3: Code Correction Plan.

Mission:
Turn the audit findings into a concrete engineering correction plan that closes truth gaps, execution gaps, and governance gaps.

Objectives:
1. Translate findings into implementation tasks
2. Group tasks by dependency and risk
3. Separate code fixes from doc fixes
4. Identify enforcement opportunities
5. Define verification requirements for each correction

Required method:
- Use prior phase outputs only (especially Phase 15)
- Do not invent new scope
- Prioritize correctness and enforcement over convenience
- Produce a production-grade remediation roadmap

Deliverables (write to .planning/phase16_correction_plan/):
- REMEDIATION_ROADMAP.md
- FIX_PRIORITY_MATRIX.md
- VERIFICATION_REQUIREMENTS_BY_FIX.md
- PHASE-16-VERIFICATION.md

Mandatory grouping:
- Critical correctness fixes (memory contract violations)
- Data integrity fixes (lineage gaps)
- Async/distribution fixes (concurrency hazards)
- Retrieval grounding fixes (agent not using memory)
- Observability fixes (cannot see what's happening)
- README/spec correction fixes (docs alignment)

Each fix must specify:
- File(s) to modify
- Exact change needed
- Test to verify correctness
- Risk if not fixed

Hard fail conditions:
- Fixes are vague
- Tasks are not dependency-ordered
- No verification is attached to fixes
- Roadmap mixes aspirational features with correctness debt

Completion bar:
PASS only if the remediation plan is executable, testable, and bounded.
```

---

## PHASE 17 — ENFORCEMENT & GOVERNANCE LAYER SPEC

### Command

```
/gsd:do
```

### Prompt

```
You are executing Phase 17 for Sheppard V3: Enforcement & Governance Layer Spec.

Mission:
Define the governance mechanisms required to keep Sheppard honest over time.

Objectives:
1. Define mission lifecycle states
2. Define truth vs. projection contracts
3. Define required verification gates
4. Define operator-visible status surfaces
5. Define event logging / pulse requirements
6. Define anti-silent-failure requirements

Required method:
- Use prior findings to identify where enforcement is needed
- Focus on preventing regressions and false completion claims
- Produce implementable governance contracts, not vague principles

Deliverables (write to .planning/phase17_governance/):
- GOVERNANCE_SPEC.md
- MISSION_STATE_MACHINE.md
- EVIDENCE_AND_VERIFICATION_GATES.md
- STATUS_SURFACE_REQUIREMENTS.md
- PHASE-17-VERIFICATION.md

Mandatory concepts:
- proposed truth vs proven truth (cannot claim completion without evidence)
- mission status transitions (what moves where and when)
- failure visibility (all failures must be observable)
- rebuildability guarantees (system can recover from any store loss)
- completion evidence (what must exist to mark phase done)

Spec must include:
- State machine diagrams or tables
- Gate conditions (boolean predicates)
- Required event types and when they must be emitted
- Status commands (/status must show what?)
- Completion verification checklist

Hard fail conditions:
- Governance is merely descriptive
- No hard gate exists between "ran" and "verified"
- No state model exists for mission lifecycle

Completion bar:
PASS only if the spec can be used to mechanically constrain future development.
```

---

## PHASE 18 — FINAL RE-VERIFICATION GAUNTLET

### Command

```
/gsd:do
```

### Prompt

```
You are executing Phase 18 for Sheppard V3: Final Re-Verification Gauntlet.

Mission:
Perform a final evidence-bound verification pass over the corrected system and determine whether Sheppard V3 is honest, coherent, and operationally sound.

Objectives:
1. Re-check core architecture claims
2. Re-check startup
3. Re-check memory contracts
4. Re-check /learn path
5. Re-check atom lineage
6. Re-check interactive retrieval
7. Re-check report generation
8. Re-check async behavior
9. Re-check major failure handling

Required method:
- Use the corrected codebase (post Phase 16)
- Re-run prior critical checks
- Validate all critical fixes
- Explicitly call out anything still partial

Deliverables (write to .planning/phase18_final/):
- FINAL_SYSTEM_AUDIT.md
- CRITICAL_FIX_VALIDATION.md
- PRODUCTION_READINESS_DECISION.md
- PHASE-18-VERIFICATION.md

Mandatory final decision:
One of:
- PASS — production-grade within defined scope
- PARTIAL — core works but critical risks remain
- FAIL — architecture claims still exceed implementation

The decision must be justified with explicit references to:
- Which gates passed
- Which gates failed
- What risks remain
- Recommended go/no-go

Hard fail conditions:
- Final decision is softened to avoid discomfort
- Remaining critical issues are not named explicitly
- Verification relies on prior assumptions instead of re-checking

Completion bar:
Only PASS if the implementation now matches the defined scope with evidence.
```

---

## EXECUTION STRATEGY

### Recommended order

Run phases 01-18 sequentially. Each phase builds on the previous.

### Tracking progress

Create a master tracker:

```markdown
# Sheppard V3 Hardening Progress

| Phase | Status | Completion Date | Verdict | Notes |
|-------|--------|------------------|---------|-------|
| 01 | ⏳ | | | |
| 02 | ⏳ | | | |
| ... | | | | |
| 18 | ⏳ | | | |
```

### Phase dependencies

- Phases 01-05: foundational — must complete before deeper audits
- Phases 06-09: pipeline critiques — depend on 05
- Phases 10-12: integration checks — depend on 09
- Phases 13-14: resilience & metrics — depend on 10-12
- Phases 15-16: synthesis — depend on all prior
- Phase 17: governance spec — depends on 16
- Phase 18: final judgment — depends on 17

### When to skip

Never skip. The gauntlet is designed to surface issues that compound if missed.

---

## SAMPLE OUTPUT STRUCTURE

After running Phase 01, you should have:

```
.planning/
├── phase01_inventory/
│   ├── SYSTEM_MAP.md (comprehensive topology)
│   ├── ENTRYPOINT_INVENTORY.md (list of all entrypoints)
│   ├── ARCHITECTURE_TRACEABILITY.md (claim → code mapping)
│   └── PHASE-01-VERIFICATION.md (pass/fail with evidence)
├── phase02_boot/
│   └── ...
```

Each phase directory should contain the required deliverables plus a `PHASE-XX-VERIFICATION.md` that explicitly states:

```
Phase: 01
Verdict: PASS / PARTIAL / FAIL
Evidence:
- File X inspected, line Y shows Z
- Command tested returned expected result
- Missing items: [list]
Critical findings: [list]
Next steps: [recommendations]
```

---

## TROUBLESHOOTING

**If a phase returns PARTIAL:**
- Document the gaps explicitly
- Do not proceed until gaps are understood
- Some partial phases may need rework after later fixes

**If a phase returns FAIL:**
- Stop and assess whether the system is salvageable
- Major architectural issues may require Phase 19 (rearchitecture)

**If claims are contradicted:**
- Update README immediately to match reality
- Do not continue with inflated claims

---

## END OF PACK

Begin with Phase 01 and execute sequentially.

Remember: **No assumptions. No skipping. Evidence only.**
