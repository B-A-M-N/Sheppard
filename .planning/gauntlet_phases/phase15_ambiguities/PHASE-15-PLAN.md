# PHASE 15 — AMBIGUITY EXTRACTION & CORRECTION REGISTER

## Mission

Produce a complete ambiguity and contradiction ledger for the system, docs, architecture claims, contracts, defaults, and execution semantics.

## GSD Workflow

- Discuss: What is unclear?
- Plan: Consolidate ambiguity findings from all prior phases
- Execute: Create master register
- Verify: Produce CORRECTION_BACKLOG.md

## Prompt for Agent

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

Deliverables (write to .planning/gauntlet_phases/phase15_ambiguities/):
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

## Deliverables

- **AMBIGUITY_REGISTER.md** — All ambiguous items with classification
- **CONTRADICTION_LEDGER.md** — All contradicting claims
- **CORRECTION_BACKLOG.md** — Actionable fixes grouped by priority
- **PHASE-15-VERIFICATION.md**

## Verification Template

```markdown
# Phase 15 Verification

## Ambiguity Extraction

- [ ] All prior findings consolidated
- [ ] Each ambiguity given unique ID
- [ ] Severity assessed
- [ ] Correction recommended for each

## Evidence

- (references to prior phase outputs)

## Verdict

**Status:** PASS / PARTIAL / FAIL

## Unaddressed Ambiguities

- (if any gaps remain uncategorized)
```

## Completion Criteria

PASS when every unclear area is documented with a specific correction action.
