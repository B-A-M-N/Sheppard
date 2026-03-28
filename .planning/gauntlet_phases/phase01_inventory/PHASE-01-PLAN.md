# PHASE 01 — GROUND-TRUTH SYSTEM INVENTORY

## Mission

Create a complete, evidence-bound inventory of the real system as implemented, not as described aspirationally.

## Objectives

1. Enumerate all entrypoints (main.py, workers, CLI)
2. Enumerate all worker processes
3. Enumerate all storage systems and their usage
4. Enumerate all queues, schemas, collections, tables, indexes
5. Enumerate all CLI commands, slash commands, API routes, background jobs
6. Identify all declared architecture claims in README/docs and verify whether each exists in code

## Required Method

- Inspect repository structure
- Inspect startup scripts
- Inspect main application entrypoints
- Inspect worker/orchestration code
- Inspect memory/storage code
- Inspect configuration/env loading code
- Inspect docs/README for architecture claims
- Build traceability from claim → file → symbol/function/class

## Execution Command

```bash
# Use GSD orchestrator
/gsd:do
```

## Prompt to Execute

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

Deliverables:
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

## Expected Deliverables

```
.planning/gauntlet_phases/phase01_inventory/
  SYSTEM_MAP.md
  ENTRYPOINT_INVENTORY.md
  ARCHITECTURE_TRACEABILITY.md
  PHASE-01-VERIFICATION.md
```

## Verification Template

Create `PHASE-01-VERIFICATION.md` with:

```markdown
# Phase 01 Verification

## Objectives Checked

- [ ] All entrypoints enumerated
- [ ] All workers listed
- [ ] All storage systems mapped
- [ ] All queues identified
- [ ] All architecture claims traced

## Evidence Collected

- Files inspected: (list)
- Commands executed: (list)
- Tests run: (list)

## Verdict

**Status:** PASS / PARTIAL / FAIL

**Justification:**
(Detail what was found, what was missing, contradictions)

## Critical Findings

- (List any major discrepancies)

## Next Steps

- (Recommended follow-up)
```

## Hard Fail Conditions

- README claim accepted without code evidence
- Entrypoint omitted
- Storage layer described vaguely
- "Distributed" or "async" left unproven

## Completion Criteria

PASS only when the entire repository can be explained end-to-end with explicit file-level evidence and every architecture claim has been verified.
