# PHASE 07 — DISTRIBUTED QUEUE & WORKER AUDIT

## Mission

Audit the distributed worker model, shared queue behavior, concurrency controls, and failure handling.

## GSD Workflow

- Discuss: Understand worker deployment model
- Plan: Map queue semantics and worker lifecycle
- Execute: Inspect code, identify hazards
- Verify: Produce WORKER_MODEL_AUDIT.md

## Prompt for Agent

```
You are executing Phase 07 for Sheppard V3: Distributed Queue & Worker Audit.

Mission:
Audit the distributed worker model, shared queue behavior, concurrency controls, and failure handling.

Objectives:
1. Verify the Redis queue contract
2. Verify multiple workers can consume safely
3. Verify duplicate consumption protection
4. Verify retry and poison-job handling
5. Verify worker heartbeats, liveness, or equivalent observability
6. Verify remote node/offloader behavior is real

Required method:
- Inspect worker code
- Inspect queue semantics
- Inspect lock usage
- Inspect job lifecycle
- Inspect any heartbeat/worker registry mechanisms
- Identify concurrency hazards and race conditions

Deliverables (write to .planning/gauntlet_phases/phase07_workers/):
- WORKER_MODEL_AUDIT.md
- QUEUE_SEMANTICS_REPORT.md
- DUPLICATION_AND_LOCKING_AUDIT.md
- DISTRIBUTED_FAILURE_MODES.md
- PHASE-07-VERIFICATION.md

Mandatory questions:
- At-least-once or exactly-once?
- How are stuck jobs detected?
- What happens if a worker dies after claiming work?
- Can two workers process the same URL?
- Is node identity meaningful or cosmetic?

Hard fail conditions:
- Duplicate processing is uncontrolled
- Queue claims are optimistic but unenforced
- Dead worker recovery is undefined
- "distributed" is only conceptual

Completion bar:
PASS only if distributed processing semantics are explicit and defended.
```

## Deliverables

- **WORKER_MODEL_AUDIT.md**
- **QUEUE_SEMANTICS_REPORT.md**
- **DUPLICATION_AND_LOCKING_AUDIT.md**
- **DISTRIBUTED_FAILURE_MODES.md**
- **PHASE-07-VERIFICATION.md**

## Verification Template

```markdown
# Phase 07 Verification

## Worker Semantics

- [ ] Queue semantics defined (at-least-once? exactly-once?)
- [ ] Duplicate consumption prevented (mechanism described)
- [ ] Dead worker detection exists
- [ ] Poison job handling defined
- [ ] Remote node coordination verified

## Evidence

- (Redis lock scripts, worker loop code)

## Verdict

**Status:** PASS / PARTIAL / FAIL

## Concurrency Hazards

- (race conditions, missing locks)
```

## Completion Criteria

PASS when distributed processing is proven safe, idempotent, and recoverable.
