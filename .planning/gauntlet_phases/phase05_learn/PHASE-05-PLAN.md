# PHASE 05 — `/learn` PIPELINE PATH AUDIT

## Mission

Trace the complete lifecycle of a `/learn` request from input receipt to final atom storage.

## Objectives

1. Identify how `/learn` is parsed
2. Identify how missions are created
3. Identify how topic decomposition happens
4. Identify how discovery/search happens
5. Identify how URLs are queued
6. Identify how scraping is triggered
7. Identify how smelting/distillation is triggered
8. Identify how atoms are stored and indexed

## GSD Workflow

- Discuss: Understand current /learn implementation
- Plan: Map state transitions
- Execute: Trace code paths end-to-end
- Verify: Produce LEARN_EXECUTION_TRACE.md

## Prompt for Agent

```
You are executing Phase 05 for Sheppard V3: /learn Pipeline Path Audit.

Mission:
Trace the complete lifecycle of a /learn request from input receipt to final atom storage.

Objectives:
1. Identify how /learn is parsed
2. Identify how missions are created
3. Identify how topic decomposition happens
4. Identify how discovery/search happens
5. Identify how URLs are queued
6. Identify how scraping is triggered
7. Identify how smelting/distillation is triggered
8. Identify how atoms are stored and indexed

Required method:
- Trace function calls end-to-end
- Produce a state transition map
- Identify async boundaries
- Identify retries, locks, dedupe, and queue semantics
- Identify all points where work can be lost, duplicated, or stall

Deliverables (write to .planning/gauntlet_phases/phase05_learn/):
- LEARN_EXECUTION_TRACE.md
- PIPELINE_STATE_MACHINE.md
- QUEUE_HANDOFF_AUDIT.md
- PHASE-05-VERIFICATION.md

Mandatory state chain:
At minimum document:
INPUT_RECEIVED
→ MISSION_CREATED
→ TOPIC_DECOMPOSED
→ URL_DISCOVERED
→ URL_QUEUED
→ URL_FETCHED
→ CONTENT_NORMALIZED
→ ATOMS_EXTRACTED
→ ATOMS_STORED
→ INDEX_UPDATED

Hard fail conditions:
- A state transition exists only implicitly
- Work can disappear silently
- Deduplication is undefined
- Retry behavior is undefined
- A major step depends on wishcasting

Completion bar:
PASS only if /learn can be described as a concrete state machine with evidence.
```

## Deliverables

- **LEARN_EXECUTION_TRACE.md** — Step-by-step trace with file/function references
- **PIPELINE_STATE_MACHINE.md** — State diagram or table
- **QUEUE_HANDOFF_AUDIT.md** — How work moves between stages
- **PHASE-05-VERIFICATION.md** — Verdict

## Verification Template

```markdown
# Phase 05 Verification

## State Machine

All transitions verified:
- [ ] INPUT_RECEIVED → MISSION_CREATED
- [ ] MISSION_CREATED → TOPIC_DECOMPOSED
- [ ] TOPIC_DECOMPOSED → URL_DISCOVERED
- [ ] URL_DISCOVERED → URL_QUEUED
- [ ] URL_QUEUED → URL_FETCHED
- [ ] URL_FETCHED → CONTENT_NORMALIZED
- [ ] CONTENT_NORMALIZED → ATOMS_EXTRACTED
- [ ] ATOMS_EXTRACTED → ATOMS_STORED
- [ ] ATOMS_STORED → INDEX_UPDATED

## Deduplication Verified

- [ ] URL dedupe mechanism exists
- [ ] Atom dedupe mechanism exists
- [ ] Mechanism is enforced

## Retry Behavior Documented

- [ ] Fetch retry policy defined
- [ ] Distillation retry policy defined
- [ ] Failure states handled

## Evidence

- (function trace, code snippets)

## Verdict

**Status:** PASS / PARTIAL / FAIL

## Gaps

- (missing transitions, undefined behavior)
```

## Completion Criteria

PASS when `/learn` is a fully traced, deterministic state machine with no missing transitions.
