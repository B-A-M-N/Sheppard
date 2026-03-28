# PHASE 09 — SMELTER / ATOM EXTRACTION AUDIT

## Mission

Audit the atom extraction path to verify schema correctness, parsing robustness, and evidence integrity.

## GSD Workflow

- Discuss: What is an atom?
- Plan: Inspect extraction pipeline
- Execute: Review prompts, parsers, validation
- Verify: Produce ATOM_SCHEMA_AUDIT.md

## Prompt for Agent

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

Deliverables (write to .planning/gauntlet_phases/phase09_smelter/):
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

## Deliverables

- **ATOM_SCHEMA_AUDIT.md**
- **EXTRACTION_PIPELINE_REPORT.md**
- **JSON_REPAIR_AUDIT.md**
- **ATOM_VALIDATION_AND_REJECTION_RULES.md**
- **PHASE-09-VERIFICATION.md**

## Verification Template

```markdown
# Phase 09 Verification

## Atom Quality

- [ ] Schema is strict and enforced
- [ ] Evidence binding is mandatory
- [ ] Type system consistent (fact/claim/tradeoff/etc)
- [ ] JSON repair safe (does not mutate meaning)
- [ ] Deduplication deterministic

## Evidence

- (extraction prompt, validation code, sample atoms)

## Verdict

**Status:** PASS / PARTIAL / FAIL

## Schema Violations

- (missing required fields, weak evidence)
```

## Completion Criteria

PASS when every stored atom is verifiable, typed, and evidence-backed.
