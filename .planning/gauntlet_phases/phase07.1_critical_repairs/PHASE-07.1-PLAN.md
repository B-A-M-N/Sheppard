---
phase: "07.1"
sub_phase: true
parent_phase: "07-validation"
name: "Critical Repairs — Pre-signoff Remediation"
purpose: "Fix critical blockers and verification gaps before milestone completion"
status: in_progress
start_date: 2026-03-28
milestone: v1.0
---

# Phase 07.1: Critical Repairs Plan

**One-liner:** Address integration-critical issues discovered during milestone audit: missing DB migration, false validation signals, and deferred runtime verifications.

**Parent Phase:** 07-validation (must complete before final signoff)

**Gate:** This phase must complete successfully before milestone v1.0 can be marked ready.

---

## Critical Tasks (Strict Order)

### R1 — Database Migration (Blocker)
- **Gap:** `exhausted_modes_json` column missing from `mission.mission_nodes`
- **Action:** Add `exhausted_modes_json JSONB` (or TEXT) column via migration
- **Verification:** Frontier checkpoint succeeds without error; column exists in DB
- **Failure gate:** STOP — no further tasks until migration applied

### R2 — Re-verify Phase 06 Fixes (Truth Check)
- **Purpose:** Confirm academic filtering and deep mining fixes actually exist in runtime
- **Actions:**
  - Inspect code to confirm `academic_only=True` is wired in system construction
  - Confirm break-on-first-success removed from crawler
  - Run a short discovery mission with verbose logging to capture:
    - Non-academic URLs rejected (filtering evidence)
    - Multiple pages fetched (page 2+ accessed)
- **Verification:** Log excerpts showing filtering and multi-page exploration
- **Failure gate:** If fixes missing, create immediate code patches before proceeding

### R3 — Runtime Validation for Deferred Invariants
- **V-11:** Exhausted modes survive restart
  - Run mission → checkpoint → restart → verify modes preserved
- **V-12:** Academic filtering enforced
  - Verify enqueue rejects non-academic when `academic_only=True`
- **Verification:** Test passes; log/show evidence
- **Failure gate:** Fixes required if either fails

### R4 — Fix Test Integrity

#### V09 Lifecycle Test
- **Problem:** Uses `DummyFrontier`, not real `AdaptiveFrontier`
- **Fix:** Replace with real frontier (mock external dependencies only, e.g., LLM, network)
- **Verification:** Test exercises actual checkpoint/restart and node persistence paths

#### V10 Backpressure Test
- **Problem:** Tests `enqueue_job` directly, not crawler integration
- **Fill gap:** Add integration scenario:
  - Fill queue to depth limit
  - Call `discover_and_enqueue` with test URLs
  - Assert enqueue rejects and backpressure flag set
- **Verification:** Enhanced test file with end-to-end assertion

### R5 — Re-run Phase 06 + Phase 07 Verification
- After all repairs, re-execute verification protocols:
  - Phase 06 gap-closure verification (PHASE-06-VERIFICATION-GAPCLOSURE.md)
  - Phase 07 orchestration validation (PHASE-07-VERIFICATION.md)
- **Gate:** Both must produce PASS with no new gaps
- **If not:** Return to relevant earlier repair task

---

## Required Artifacts

1. **PHASE-07.1-SUMMARY.md** — what was broken, what was fixed, decisions made
2. **PHASE-07.1-VERIFICATION.md** — evidence package:
   - DB schema proof (column exists)
   - Runtime logs (filtering, deep mining)
   - Restart persistence proof
   - Updated test files
   - Re-verification results for Phase 06 & 07

---

## Constraints

- **No scope creep:** Only items in R1–R5 allowed
- **Do NOT** create final milestone audit yet
- **Do NOT** proceed to next phase until this phase completes with PASS
- **Atomic commits:** Each repair gets its own commit with descriptive message

---

## Success Criteria

✅ All 5 tasks complete with documented evidence
✅ Re-verified Phase 06 & Phase 07 both PASS
✅ No open blockers remaining
✅ Milestone v1.0 can proceed to final audit

---

**Status:** Ready to execute
