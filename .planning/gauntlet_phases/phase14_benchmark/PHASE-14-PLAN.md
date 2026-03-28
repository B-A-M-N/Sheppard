# PHASE 14 — BENCHMARK & EVALUATION CONTRACT AUDIT

## Mission

Audit the benchmark framework and verify that reported scores reflect real system behavior, with clear scope and reproducibility.

## GSD Workflow

- Discuss: What do scores mean?
- Plan: Map benchmark to actual system behavior
- Execute: Inspect benchmark code and datasets
- Verify: Produce CLAIM_SCOPE_CORRECTION.md

## Prompt for Agent

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

Deliverables (write to .planning/gauntlet_phases/phase14_benchmark/):
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

## Deliverables

- **BENCHMARK_AUDIT.md**
- **SCORE_SEMANTICS_REPORT.md**
- **REPRODUCIBILITY_REVIEW.md**
- **CLAIM_SCOPE_CORRECTION.md**
- **PHASE-14-VERIFICATION.md**

## Verification Template

```markdown
# Phase 14 Verification

## Score Definitions

- [ ] Each metric has precise formula
- [ ] Scope is limited to what benchmark actually tests
- [ ] Environment dependencies documented
- [ ] Reproducibility verified (can rerun)

## Evidence

- (benchmark code, scoring formulas)

## Verdict

**Status:** PASS / PARTIAL / FAIL

## Overclaims

- (where README exceeds what benchmark measures)
```

## Completion Criteria

PASS when all scores are narrow, explicit, honest, and reproducible.
