# PHASE 17 — ENFORCEMENT & GOVERNANCE LAYER SPEC

## Mission

Define the governance mechanisms required to keep Sheppard honest over time.

## GSD Workflow

- Discuss: What needs enforcing?
- Plan: Design gates and state machines
- Execute: Write spec with enforcement mechanisms
- Verify: Produce GOVERNANCE_SPEC.md

## Prompt for Agent

```
You are executing Phase 17 for Sheppard V3: Enforcement & Governance Layer Spec.

Mission:
Define the governance mechanisms required to keep Sheppard honest over time.

Objectives:
1. Define mission lifecycle states
2. Define truth vs. projection contracts
3. Define required verification gates
4. Define operator-visible status surfaces
5. Define event logging / pulse requirements
6. Define anti-silent-failure requirements

Required method:
- Use prior findings to identify where enforcement is needed
- Focus on preventing regressions and false completion claims
- Produce implementable governance contracts, not vague principles

Deliverables (write to .planning/gauntlet_phases/phase17_governance/):
- GOVERNANCE_SPEC.md
- MISSION_STATE_MACHINE.md
- EVIDENCE_AND_VERIFICATION_GATES.md
- STATUS_SURFACE_REQUIREMENTS.md
- PHASE-17-VERIFICATION.md

Mandatory concepts:
- proposed truth vs proven truth (cannot claim completion without evidence)
- mission status transitions (what moves where and when)
- failure visibility (all failures must be observable)
- rebuildability guarantees (system can recover from any store loss)
- completion evidence (what must exist to mark phase done)

Spec must include:
- State machine diagrams or tables
- Gate conditions (boolean predicates)
- Required event types and when they must be emitted
- Status commands (/status must show what?)
- Completion verification checklist

Hard fail conditions:
- Governance is merely descriptive
- No hard gate exists between "ran" and "verified"
- No state model exists for mission lifecycle

Completion bar:
PASS only if the spec can be used to mechanically constrain future development.
```

## Deliverables

- **GOVERNANCE_SPEC.md** — Complete governance spec
- **MISSION_STATE_MACHINE.md** — States and transitions
- **EVIDENCE_AND_VERIFICATION_GATES.md** — What must be true to transition
- **STATUS_SURFACE_REQUIREMENTS.md** — What /status must show
- **PHASE-17-VERIFICATION.md**

## Verification Template

```markdown
# Phase 17 Verification

## Governance Mechanisms

- [ ] State machine defined
- [ ] Gates are boolean and testable
- [ ] Events required on transitions
- [ ] Operator visibility defined
- [ ] Anti-silent-failure mechanisms present

## Evidence

- (state machine diagram, gate definitions)

## Verdict

**Status:** PASS / PARTIAL / FAIL

## Missing Enforcement

- (transitions without gates, missing events)
```

## Completion Criteria

PASS when the spec provides mechanically enforceable constraints on all critical state transitions.
