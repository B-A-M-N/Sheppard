# Phase 05C — BudgetMonitor topic_id Cleanup

## Status: NOT STARTED

## Problem

BudgetMonitor and related control paths still carry deprecated `topic_id` assumptions via a compatibility bridge. This is V2 residue in the V3 pipeline.

## Goal

Standardize BudgetMonitor and all related hooks on `mission_id` only. Remove the bridge.

## Required Changes

- Identify all `topic_id` usage in budget/control paths (grep scope)
- Replace `topic_id` with `mission_id` in interfaces, callbacks, and call sites
- Remove compatibility bridge logic after replacements confirmed
- Verify budget-triggered behaviors (pause, stop, limit enforcement) still function

## Acceptance Criteria

- No budget/control path depends on `topic_id`
- `mission_id` is the sole runtime identifier in V3 pipeline control
- Grep/audit shows zero live `topic_id` bridge usage in V3 path
- Budget-triggered behaviors verified functional post-cleanup

## Key Files

- BudgetMonitor class (locate via grep: `class BudgetMonitor`)
- Any callbacks/hooks using `topic_id` in budget context
- `system.py` (mission creation and control path)

## Deliverables

- `PLAN.md` — concrete implementation steps
- `SUMMARY.md` — what changed and why
- `VERIFICATION.md` — grep evidence of zero bridge + functional test, PASS/FAIL decision
