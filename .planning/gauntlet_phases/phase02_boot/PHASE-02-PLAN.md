# PHASE 02 — RUNTIME & BOOT PATH VALIDATION

## Mission

Verify the real startup path, initialization sequence, dependency requirements, and boot-time failure modes.

## Objectives

1. Validate all documented startup commands
2. Validate environment loading and required configuration
3. Validate service dependency assumptions
4. Identify all boot blockers, silent failures, and hidden prerequisites
5. Prove whether the system can start cleanly from a fresh environment

## GSD Workflow

This phase should be executed via standard GSD workflow:
- Discuss: Clarify boot sequence questions
- Plan: Create execution plan for validation
- Execute: Perform inspection and testing
- Verify: Produce BOOT_SEQUENCE.md with findings

## Prompt for Agent

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

Deliverables (write to .planning/gauntlet_phases/phase02_boot/):
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

## Expected Deliverables

```
.planning/gauntlet_phases/phase02_boot/
  BOOT_SEQUENCE.md
  CONFIG_REQUIREMENTS.md
  STARTUP_FAILURE_MATRIX.md
  PHASE-02-VERIFICATION.md
```

## Verification Template

`PHASE-02-VERIFICATION.md` must include:

```markdown
# Phase 02 Verification

## Boot Sequence Validated

- [ ] Startup command(s) identified
- [ ] All required services listed
- [ ] Environment variables documented
- [ ] Failure modes tested
- [ ] Error clarity assessed

## Evidence

- (commands run, files inspected)

## Verdict

**Status:** PASS / PARTIAL / FAIL

## Critical Gaps

- (any missing requirements, silent failures, etc.)
```

## Completion Criteria

PASS when a new operator could start the system fromscratch following the documented path without guesswork or hidden prerequisites.
