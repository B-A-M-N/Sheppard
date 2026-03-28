# PHASE 13 — FAILURE MODES & RECOVERY AUDIT

## Mission

Identify, classify, and verify the system's behavior under failure, interruption, malformed output, and partial state conditions.

## GSD Workflow

- Discuss: What can fail?
- Plan: Enumerate failure scenarios
- Execute: Inspect error handling, simulate failures
- Verify: Produce FAILURE_MODE_CATALOG.md

## Prompt for Agent

```
You are executing Phase 13 for Sheppard V3: Failure Modes & Recovery Audit.

Mission:
Identify, classify, and verify the system's behavior under failure, interruption, malformed output, and partial state conditions.

Objectives:
1. Enumerate component failure modes
2. Enumerate data corruption risks
3. Enumerate partial-completion states
4. Verify restart/recovery behavior
5. Verify error surfacing quality

Required method:
- Inspect exception handling
- Inspect retries and failure queues
- Inspect recovery/startup reconciliation logic
- Inspect handling of malformed model outputs
- Inspect partial mission/job states

Deliverables (write to .planning/gauntlet_phases/phase13_failures/):
- FAILURE_MODE_CATALOG.md
- RECOVERY_BEHAVIOR_AUDIT.md
- PARTIAL_STATE_HANDLING_REPORT.md
- ERROR_SURFACING_REVIEW.md
- PHASE-13-VERIFICATION.md

Mandatory scenarios:
- Postgres unavailable
- Redis unavailable
- Chroma unavailable
- Ollama unavailable
- Worker dies mid-job
- Model returns malformed JSON
- Source page is empty/garbage
- Mission halts halfway through

Hard fail conditions:
- Failures are hidden
- Recovery depends on operator intuition
- Partial states are unrecoverable
- Error logs are noisy but unhelpful

Completion bar:
PASS only if failure handling is explicit, bounded, and operator-comprehensible.
```

## Deliverables

- **FAILURE_MODE_CATALOG.md**
- **RECOVERY_BEHAVIOR_AUDIT.md**
- **PARTIAL_STATE_HANDLING_REPORT.md**
- **ERROR_SURFACING_REVIEW.md**
- **PHASE-13-VERIFICATION.md**

## Verification Template

```markdown
# Phase 13 Verification

## Failure Scenarios

For each critical scenario:
- [ ] Postgres down: behavior documented
- [ ] Redis down: behavior documented
- [ ] Chroma down: behavior documented
- [ ] Ollama down: behavior documented
- [ ] Worker crash: recovery exists
- [ ] Malformed JSON: handled safely
- [ ] Empty content: handled gracefully

## Evidence

- (error handling code, retry logic)

## Verdict

**Status:** PASS / PARTIAL / FAIL

## Silent Failures

- (errors that are caught but not surfaced)
```

## Completion Criteria

PASS when every major failure mode has explicit, bounded recovery behavior and errors are surfaced to operator.
