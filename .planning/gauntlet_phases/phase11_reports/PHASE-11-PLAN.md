# PHASE 11 — REPORT GENERATION AUDIT

## Mission

Audit report generation to verify that reports are built from stored atoms and lineage rather than ad hoc re-reasoning over thin context.

## GSD Workflow

- Discuss: What is a report?
- Plan: Trace report generation path
- Execute: Verify input provenance
- Verify: Produce REPORT_INPUT_PROVENANCE.md

## Prompt for Agent

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

Deliverables (write to .planning/gauntlet_phases/phase11_reports/):
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

## Deliverables

- **REPORT_PIPELINE_AUDIT.md**
- **REPORT_INPUT_PROVENANCE.md**
- **REPORT_EVIDENCE_CARRYTHROUGH.md**
- **PHASE-11-VERIFICATION.md**

## Verification Template

```markdown
# Phase 11 Verification

## Report Provenance

- [ ] Reports built only from stored atoms
- [ ] Regeneration possible from Postgres only
- [ ] Citations link to source metadata
- [ ] Report tied to mission_id
- [ ] Evidence carry-through verified

## Evidence

- (report generation code, sample output with citations)

## Verdict

**Status:** PASS / PARTIAL / FAIL

## Lineage Breaks

- (where report content cannot be traced to atoms)
```

## Completion Criteria

PASS when reports are 100% derived from stored atoms and can be regenerated from Postgres alone.
