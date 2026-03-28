# PHASE 04 — DATA MODEL & LINEAGE INTEGRITY

## Mission

Verify that lineage is real, complete, and queryable.

## Objectives

1. Identify the mission model
2. Identify the source/document model
3. Identify the atom model
4. Identify the report/output model
5. Verify all relationships and foreign-key-like bindings
6. Verify whether lineage can be reconstructed without guessing

## GSD Workflow

- Discuss: Understand current schema
- Plan: Map all entity relationships
- Execute: Inspect schemas, trace lineage creation/consumption
- Verify: Produce LINEAGE_MAP.md

## Prompt for Agent

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

Deliverables (write to .planning/gauntlet_phases/phase04_lineage/):
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

## Deliverables

- **LINEAGE_MAP.md** — Visual/structured map of entity relationships
- **ENTITY_RELATIONSHIP_AUDIT.md** — Detailed audit of all relationships
- **ORPHAN_RISK_REPORT.md** — Where orphans can occur and why
- **PHASE-04-VERIFICATION.md** — Verdict

## Verification Template

```markdown
# Phase 04 Verification

## Lineage Integrity

- [ ] Every atom has at least one source reference
- [ ] Every source links to a mission
- [ ] Every report traces to atoms
- [ ] Foreign keys or equivalent constraints exist
- [ ] Lineage survives reprocessing (idempotent)

## Evidence

- (schema constraints, code traces)

## Verdict

**Status:** PASS / PARTIAL / FAIL

## Orphan Risks

- (list scenarios where lineage breaks)
```

## Completion Criteria

PASS when lineage is structurally enforced and can be traced end-to-end without gaps.
