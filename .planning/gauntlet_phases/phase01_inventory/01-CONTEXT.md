# Phase 01: Ground-Truth System Inventory — Context

**Gathered:** 2025-03-27
**Status:** Ready for researcher execution

<domain>
## Phase Boundary

Create a complete, evidence-bound inventory of the real system as implemented, not as described aspirationally. This phase is strictly a **truth discovery phase**, not a remediation phase.

Scope includes:
- All execution surfaces (entrypoints, workers, CLI, diagnostics)
- All storage systems (Postgres, Chroma, Redis, file-based)
- All queues, schemas, collections, tables, indexes
- All declared architecture claims in README/docs
- Verification of reachability and wiring (not just existence)

Excludes:
- Performance benchmarking (deferred to Phase 14)
- Fixing identified issues (later phases)
- Architecture redesign (out of scope unless contradictions found)

</domain>

<decisions>
## Implementation Decisions

### 1. Entrypoint Classification

All executable surfaces classified into categories:

- `production` — main application (`main.py`), core workers
- `worker` — distributed processing nodes (`scout_worker.py`, similar)
- `operator/admin` — CLI commands, slash commands, admin utilities
- `diagnostic` — one-off checks, debugging scripts
- `benchmark` — performance testing scripts
- `migration/setup` — DB initialization, schema migrations, setup utilities
- `unsafe/destructive` — wipes, resets, destructive operations

**Nothing excluded** simply because it appears minor or one-off.

---

### 2. Verification Depth Ladder

Components classified by reachability:

- `NOT FOUND` — no meaningful implementation exists
- `PARTIAL` — exists but unclear, incomplete, or disconnected
- `VERIFIED` — implemented and wired into system behavior
- `DEMONSTRATED` — verified plus runtime/log/test evidence

Dead code does not qualify as VERIFIED. Must show call graph or integration.

---

### 3. Storage Mapping Granularity

For each storage surface (Postgres, Chroma, Redis, files):

- tables / collections / namespaces
- purpose of each
- primary write paths (which component writes what)
- primary read paths (which component reads what)
- identity / lineage-relevant fields
- visible constraints or structural assumptions

**NOT full column-level archaeology** unless needed to understand structure.

---

### 4. Claim Traceability Scope

Phase 01 must verify:

**Explicit claims** — stated features in README/docs
**Implied architectural claims** — triad, async, lineage, pipeline completeness
**Deferred claims** — performance, benchmarks, scores → log but mark `DEFERRED — PHASE 14`

---

### 5. Missing/Contradicted Claims Policy

- Explicilty mark: `NOT FOUND`, `PARTIAL`, `CONTRADICTED`
- Do NOT silently reinterpret as "aspirational" unless clearly labeled
- Do NOT downgrade to vague qualifiers

---

### 6. Prioritization Tiers

**Tier 1 (Highest Scrutiny):**
- Triad memory surfaces (Postgres truth, Chroma projection, Redis motion)
- `/learn` pipeline path
- Interactive query/retrieval path
- Lineage-bearing data models

**Tier 2:**
- Worker/distribution system
- Scraping/acquisition pipeline
- Report generation path

**Tier 3:**
- Diagnostics, utilities, benchmarks, maintenance scripts

---

### Claude's Discretion

When exact classification is ambiguous:
- Lean toward inclusion (better to over-inventory than miss a critical surface)
- Use reachability as the VERIFICATION gate, not just naming
- For storage mapping, stop at "sufficient to understand responsibilities" — no need to enumerate every index unless it's functionally significant

</decisions>

<specifics>
## Specific Ideas

- **Evidence standard:** "Can we trace from claim to file to symbol to runtime behavior?"
- **Dead code handling:** If found, mark as NOT_VERIFIED and note in traceability
- **Unwired features:** If code exists but is never called, treat as PARTIAL
- **README vs reality:** Do not sugarcoat mismatches — document explicitly

</specifics>

<canonical_refs>
## Canonical References

**These documents define scope/requirements for this phase:**

### Phase Specification
- `.planning/gauntlet_phases/phase01_inventory/PHASE-01-PLAN.md` — Complete phase mission, objectives, deliverables, hard fail conditions

### Existing Planning Artifacts
- `.planning/phases/phase0_preparation.md`
- `.planning/phases/phase1_implementation_plan.md`
- `.planning/ambiguities_RESOLVED.md`
- `.planning/codebase/ARCHITECTURE.md`
- `.planning/codebase/STRUCTURE.md`
- `.planning/codebase/CONCERNS.md`

### Repository Documents
- `README.md` — Primary architecture claims to verify
- `src/memory/schema_v3.sql` — V3 schema definition (reference for storage)
- `src/config/database.py` — DB/Redis/Chroma configuration

**No external specs exist** — all requirements captured in README and planning docs.

</canonical_refs>

<code_context>
## Existing Code Insights

### High-Level Structure (from ls -la and find)

**Key directories:**
- `src/` — main codebase with submodules: `research/`, `memory/`, `core/`, `config/`, `utils/`, `llm/`, `preferences/`
- `sheppard_v2/` — legacy V2 code (likely still in use for some functionality)
- `data/`, `chroma_storage/` — runtime data
- `logs/` — log output
- `.planning/` — GSD planning artifacts

**Entrypoint candidates:**
- `main.py` — likely main interactive console app
- `scout_worker.py` — distributed worker
- `run_refinery.py` — possibly refinery/processing runner
- Various `*_worker.py` patterns may exist in `src/`

**Storage:**
- SQL schema: `src/memory/schema_v3.sql` (multi-schema Postgres design)
- Chroma: likely `chroma_storage/` directory
- Redis: configured in `src/config/database.py`
- File-based: `text_refs` with `storage_uri` pattern in schema

**Research components evident from file names:**
- `src/research/` — `acquisition/` (frontier, crawler), `condensation/` (pipeline), `archivist/` (retrieval), `reasoning/` (agent), etc.
- `src/memory/` — storage adapters (postgres, chroma, redis)

**GSD artifacts:**
- Existing `phase1_implementation_plan.md` already detailed — can be used as reference but not assumed correct until verified

---

### Reusable Assets for This Phase

**Nothing to reuse** — this is an inventory/audit phase. We will produce new documentation, not code.

---

### Established Patterns

**None established yet** — this is the first hardening phase. We'll discover patterns during execution.

---

### Integration Points

This phase produces:
- `SYSTEM_MAP.md` — comprehensive topology
- `ENTRYPOINT_INVENTORY.md` — catalog of all executable surfaces
- `ARCHITECTURE_TRACEABILITY.md` — claim → evidence mapping

These will be **read by all subsequent phases** as reference material.

</code_context>

<deferred>
## Deferred Ideas

None — this phase is self-contained inventory.

</deferred>

---

*Phase: 01 — Ground-Truth System Inventory*
*Context gathered: 2025-03-27*
