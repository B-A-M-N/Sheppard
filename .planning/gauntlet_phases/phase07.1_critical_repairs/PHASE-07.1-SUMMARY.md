---
phase: "07.1"
parent_phase: "07-validation"
name: "Critical Repairs — Pre-signoff Remediation"
status: completed
completed_date: 2026-03-28
---

# Phase 07.1: Critical Repairs Summary

**One-liner:** Fixed critical blockers and verification gaps discovered during milestone audit: missing database migration, false validation signals, and deferred runtime verifications.

**Context:** This repair phase was created in response to the milestone audit which found:
- Missing `exhausted_modes_json` column (blocker)
- V09 and V10 tests using unrealistic mocks (false confidence)
- Contradiction between Phase 06 gap closure claims and actual integration
- V-11 and V-12 deferred invariants unverified

These issues meant the milestone **was not ready for completion**. This phase addressed them systematically.

---

## Tasks Completed

### R1 — Database Migration (Blocker)

**Problem:** `MissionNode.to_pg_row()` includes `exhausted_modes_json`, but `mission.mission_nodes` table lacked the column. Any frontier checkpoint would crash.

**Fix:**
- Updated `src/memory/schema_v3.sql` to add `exhausted_modes_json JSONB NOT NULL DEFAULT '[]'::jsonb`.
- Created migration file `.planning/gauntlet_phases/phase07.1_critical_repairs/MIGRATION_add_exhausted_modes_json.sql`.

**Status:** Migration artifact ready; requires manual application to the database when available. Schema updated for future deployments.

---

### R2 — Re-verify Phase 06 Fixes (Truth Check)

**Purpose:** Confirm that the Phase 06 gap closures (academic filtering, deep mining) are actually present in the runtime code.

**Findings:** Code inspection confirmed both fixes are correctly implemented:
- **Academic filtering:** `system.py` line 128 passes `academic_only=True` to `FirecrawlLocalClient`; `crawler.py` lines 185-186 and 306-307 enforce the filter at enqueue boundary.
- **Deep mining:** `crawler.py` lines 294-297 loop pages 1–5 with only empty-page break; no `if page_new_count > 0: break` present.

**Conclusion:** The integration checker's contradiction was due to outdated assessment; the fixes are present and correct. No code changes required.

---

### R3 — Runtime Validation (V-11, V-12)

Created new tests to verify deferred invariants that were critical to confirm:

- **V-11: Exhausted modes survive restart**
  - File: `tests/validation/v11_exhausted_modes_persistence.py`
  - Tests that frontier checkpoint saves `exhausted_modes` to DB and restores it correctly across restart.
  - Uses real Postgres and a full AdaptiveFrontier roundtrip.

- **V-12: Academic filtering enforced**
  - File: `tests/validation/v12_academic_filtering.py`
  - Tests that when `academic_only=True`, non-academic URLs are rejected at the enqueue boundary.
  - Exercises `discover_and_enqueue` with mixed URLs and verifies only academic URLs are queued.

Both tests are ready to run after the migration is applied (V-11 requires the `exhausted_modes_json` column).

---

### R4 — Fix Test Integrity

**V09 Lifecycle Test**
- **Before:** Used `DummyFrontier` which bypassed all frontier DB interactions, masking potential failures.
- **After:** Replaced with `MinimalFrontier` (subclass of real `AdaptiveFrontier`) that performs a minimal checkpoint cycle (`_load_checkpoint` + `_save_node`). This exercises node persistence without requiring full mission runtime.
- File: `tests/validation/v09_lifecycle.py` (modified)

**V10 Backpressure Test**
- **Before:** Only tested `RedisStoresImpl.enqueue_job` at the store level; did not verify that the crawler respects backpressure.
- **After:** Added integration test `test_v10_backpressure_crawler_integration` that:
  - Sets `MAX_QUEUE_DEPTH = 5`
  - Calls `discover_and_enqueue` with many URLs
  - Verifies that exactly 5 enqueues occur, the queue depth never exceeds 5, and the backpressure flag stops further processing.
- File: `tests/validation/v10_backpressure.py` (enhanced)

---

## Required Artifacts

| Artifact | Status |
|----------|--------|
| `.planning/gauntlet_phases/phase07.1_critical_repairs/MIGRATION_add_exhausted_modes_json.sql` | Created |
| `src/memory/schema_v3.sql` (updated) | Modified |
| `tests/validation/v11_exhausted_modes_persistence.py` | Created |
| `tests/validation/v12_academic_filtering.py` | Created |
| `tests/validation/v09_lifecycle.py` | Modified |
| `tests/validation/v10_backpressure.py` | Modified |
| `PHASE-07.1-SUMMARY.md` (this file) | Created |
| `PHASE-07.1-VERIFICATION.md` | Created (next) |

---

## Outcome

All critical issues identified in the milestone audit have been addressed:

✅ Database migration defined and schema updated
✅ Phase 06 fixes confirmed present (no code changes needed)
✅ Deferred invariants (V-11, V-12) now have runtime verification tests
✅ V09 and V10 tests improved to use real components and cover integration

**System Status:** READY FOR VALIDATION EXECUTION (POST-MIGRATION REQUIRED)

All repair artifacts are in place, but **no runtime validation has occurred**. The migration must be applied and the test suite must execute and pass before the system is verified stable.

---

**Execution Steps (Strict Order):**
1. **Apply migration** to `sheppard_v3` database (see MIGRATION_add_exhausted_modes_json.sql)
2. **Verify column exists:**
   ```sql
   SELECT column_name FROM information_schema.columns WHERE table_name='mission_nodes' AND column_name='exhausted_modes_json';
   ```
   Expected output: `exhausted_modes_json`
3. **Run validation suite:**
   ```bash
   pytest tests/validation/ -v
   ```
4. **Confirm all tests pass**, specifically:
   - `v09_lifecycle` (lifecycle with real frontier)
   - `v10_backpressure` (both component + integration)
   - `v11_exhausted_modes_persistence` (requires migration)
   - `v12_academic_filtering`
5. **If any test fails** — return to Phase 07.1, debug, and repeat steps 1–4.
6. **Only after all tests pass** — proceed to final milestone audit (`gsd:audit-milestone`).
