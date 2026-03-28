# Phase 03.0 Remediation — Critical Fixes (A1–A4)

**Date**: 2026-03-27
**Status**: IN PROGRESS
**Trigger**: PHASE-05-AMBIGUITIES.md identified blocking violations
**Scope**: Surgical fixes only — remove V2 memory dependencies, lock identity model

---

## Critical Blockers (A1–A4)

| ID | Description | Severity | Target |
|----|-------------|----------|--------|
| A1 | V2 Memory Still Used (system.py cleanup/status calls) | HARD FAIL | system.py |
| A2 | Frontier Dual Persistence (V2 reads+writes) | HARD FAIL | frontier.py |
| A3 | Vampire Dual Writes (store_source legacy support) | HARD FAIL | system.py |
| A4 | Topic vs Mission ID Identity Split | HARD FAIL | system.py, frontier.py |

---

## Remediation Plan

### Fix 1: Remove V2 Memory Calls in SystemManager (A1, A3)

**File**: `src/core/system.py`

**Changes**:
1. Remove `self.memory` attribute entirely (line 66: currently `self.memory = None`)
2. Remove `self.memory.cleanup()` call (line 293)
3. Remove `self.memory.store_source(...)` block (lines 351–359)
4. Remove `self.memory.update_topic_status(...)` calls (lines 384, 390, 418)
5. Remove any conditional `if self.memory:` guards

**Rationale**: V2 memory is deprecated. V3 adapter handles all persistence. Status tracking is either redundant or should use adapter.

---

### Fix 2: Lock Identity Model to mission_id (A4)

**Files**: `src/core/system.py`, `src/research/acquisition/frontier.py`

**Changes in system.py**:
1. Remove `topic_id` parameter from `_crawl_and_store` signature (line 369)
   - Keep only `mission_id: str`, derive `topic_name` from mission record if needed
2. Update `learn()` method to pass only `mission_id` (no separate topic_id)
3. Remove line 175 (`topic_id = mission_id`) — mission_id is already canonical
4. Update `_vampire_loop` job handling:
   - Remove `topic_id` job field (line 317)
   - Use only `mission_id`
   - Remove fallback `mission_id = job.get("mission_id") or topic_id` (line 319)
5. Update any other methods that reference `topic_id`

**Changes in frontier.py**:
1. Update `AdaptiveFrontier.__init__`:
   - Remove `topic_id` parameter
   - Keep only `mission_id: str`
   - Remove `self.topic_id` assignment
2. Update all references to `self.topic_id` → remove or replace with `self.mission_id`
3. Update `_load_checkpoint`:
   - Line 142: remove `self.visited_urls` load from V2 memory (or implement V3 equivalent)
   - Line 158: remove V2 fallback block entirely
4. Update `_save_node`:
   - Remove line 187 V2 write
   - Keep only V3 adapter call (line 184)

**Rationale**: Single canonical identifier eliminates identity confusion and enforces triad.

---

### Fix 3: Remove Frontier V2 Persistence (A2)

**File**: `src/research/acquisition/frontier.py`

**Changes**:
1. Delete `_load_checkpoint` V2 fallback (lines 157–165)
2. Delete `_save_node` line 187 (`await self.sm.memory.upsert_frontier_node(...)`)
3. Verify `self.sm.memory` not used anywhere in frontier.py

**Optional**: If frontier state needs persistence, ensure it goes only through `self.sm.adapter` methods (which already exists at line 184).

---

### Fix 4: Verify BudgetMonitor Alignment (A5 Related)

**File**: Likely `src/core/budget.py` or similar

**Actions**:
1. Search for `BudgetMonitor` or `self.budget` usage
2. Identify methods that take `topic_id`
3. Plan migration to `mission_id` (may be deferred to Phase 03 if complex)

**Note**: This is a **gap** not a blocker for Phase 05. Document but may not fix immediately.

---

## Acceptance Criteria

After fixes:

- ✅ Zero `self.memory` references in `system.py` (search confirms)
- ✅ Zero `self.sm.memory` references in `frontier.py`
- ✅ `SystemManager` initializes without `MemoryManager` import
- ✅ All V3 components use only `mission_id` identifier
- ✅ System boots and `/learn` runs without V2 memory errors
- ✅ Phase 03.0 verification passes (all 6 criteria ✅)

---

## Verification Steps

1. Run code search: `grep -rn "self\.memory\." src/core/system.py src/research/acquisition/frontier.py`
2. Run: `python3 -c "from src.core.system import SystemManager; print('import ok')"`
3. Dry-run init: `python3 -c "import asyncio; from src.core.system import SystemManager; sm = SystemManager(); asyncio.run(sm.initialize())"`
4. Check logs: No MemoryManager import, no V2 DB connections

---

## Commit Strategy

- Commit as: `fix(phase030): remove V2 memory dependencies; lock identity to mission_id`
- Include files:
  - `src/core/system.py` (primary)
  - `src/research/acquisition/frontier.py` (identity + V2 removal)
  - Possibly `src/core/budget.py` if quick wins
- Do NOT include extensive refactor — surgical only

---

## Next After Fix

1. Update `03.0-VERIFICATION.md` to PASS
2. Update `PHASE-03-VERIFICATION.md` to reflect reduced violation set
3. Re-evaluate Phase 05 blocking status (A1–A4 resolved, remaining gaps may be addressed in Phase 03)

---

**Start execution.**