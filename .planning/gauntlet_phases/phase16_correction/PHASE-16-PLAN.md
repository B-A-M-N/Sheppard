# PHASE 16 — CODE CORRECTION PLAN

## Mission

Turn the audit findings into a concrete engineering correction plan that closes truth gaps, execution gaps, and governance gaps.

## GSD Workflow

- Discuss: What fixes are needed?
- Plan: Prioritize by risk and dependency
- Execute: Create task breakdown
- Verify: Produce REMEDIATION_ROADMAP.md

## Prompt for Agent

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

Deliverables (write to .planning/gauntlet_phases/phase16_correction/):
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

## Deliverables

- **REMEDIATION_ROADMAP.md** — Ordered task list with dependencies
- **FIX_PRIORITY_MATRIX.md** — Critical / High / Medium / Low
- **VERIFICATION_REQUIREMENTS_BY_FIX.md** — Test for each fix
- **PHASE-16-VERIFICATION.md**

## Verification Template

```markdown
# Phase 16 Verification

## Plan Quality

- [ ] All critical findings have associated fix
- [ ] Tasks ordered by dependency
- [ ] Each task has verification test
- [ ] Risk assessed for each fix
- [ ] Code vs. docs separated

## Evidence

- (task breakdown, dependency graph)

## Verdict

**Status:** PASS / PARTIAL / FAIL

## Missing Fixes

- (any findings without remediation)
```

## Completion Criteria

PASS when the roadmap is executable, testable, and covers all critical findings.
