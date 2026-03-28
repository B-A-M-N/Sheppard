# PHASE 03 — TRIAD MEMORY CONTRACT AUDIT

## Mission

Audit the full memory architecture and verify that each store has a clear, enforced responsibility with no truth leakage.

## Objectives

1. Map all reads and writes to Postgres
2. Map all reads and writes to Chroma
3. Map all reads and writes to Redis
4. Identify overlap, duplication, leakage, or contract violations
5. Determine whether Chroma can be fully rebuilt from Postgres
6. Determine whether Redis can be lost without losing truth

## GSD Workflow

- Discuss: Clarify triad boundaries
- Plan: Trace all storage access patterns
- Execute: Inspect code, map read/write paths
- Verify: Produce MEMORY_CONTRACT_AUDIT.md

## Prompt for Agent

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

Deliverables (write to .planning/gauntlet_phases/phase03_triad/):
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

## Deliverables

- **MEMORY_CONTRACT_AUDIT.md** — Overall audit of triad discipline
- **STORAGE_WRITE_MATRIX.md** — Table: what writes where, when, why
- **STORAGE_READ_MATRIX.md** — Table: what reads where, in what order
- **REBUILDABILITY_ASSESSMENT.md** — Can Chroma be rebuilt? Can Redis be lost?
- **PHASE-03-VERIFICATION.md** — Verdict with evidence

## Verification Template

```markdown
# Phase 03 Verification

## Triad Discipline Checks

- [ ] Postgres is sole source of truth for atoms, sources, missions
- [ ] Chroma contains ONLY derivable projections
- [ ] Redis contains NO unrecoverable state
- [ ] All writes to canonical data go through Postgres first
- [ ] Rebuild script exists and would work

## Evidence

- (code traces, write path analysis)

## Verdict

**Status:** PASS / PARTIAL / FAIL

## Contract Violations Found

- (list any misplaced data)
```

## Completion Criteria

PASS when storage contracts are explicit, enforceable, and all data is correctly classified.
