# VERIFICATION-V09: MissionLifecycleTransitionsCorrect

**Test executed**: `pytest tests/validation/v09_lifecycle.py -q`

**Test method**:
- Constructed a minimal SystemManager with real PostgreSQL adapter and fake Redis/Chroma.
- Inserted a mission with initial status "created" (after fixing ResearchMission default).
- Replaced AdaptiveFrontier with a dummy that completes immediately.
- Spied on `update_mission_status` to record status transitions.
- Invoked `_crawl_and_store` directly and awaited completion.

**Observed state sequence**:
1. Initial DB status: `created`
2. Transition to `active` (at start of `_crawl_and_store`)
3. Transition to `completed` (after dummy frontier.run() returns)

**Illegal jumps detected**: None (sequence respected created→active→completed)

**Durability after restart**: Verified final mission row persisted with status `completed`.

**Verdict**: PASS

**Notes**:
- The test required two fixes to the production code to satisfy the contract:
  1. Changed `ResearchMission` default status from `"active"` to `"created"`.
  2. Added `await self.adapter.update_mission_status(mission_id, "active")` at the beginning of `_crawl_and_store`.
- Without these, the initial status would be `active` and the contract's `created` state would be missing.
