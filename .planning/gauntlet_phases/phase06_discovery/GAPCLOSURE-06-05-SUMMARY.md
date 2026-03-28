# Task 06-05: Persist exhausted_modes across restarts

## Summary
Implemented persistence of `exhausted_modes` per node via checkpoint. The set of epistemic modes already tried for a node now survives mission restarts.

## Changes Made
- **domain_schema.py**:
  - Added `exhausted_modes: List[str] = Field(default_factory=list)` to `MissionNode`.
  - Modified `to_pg_row()` to exclude `exhausted_modes` from direct model dump and store it as `exhausted_modes_json` column.
- **frontier.py**:
  - `_save_node`: now passes `exhausted_modes=list(node.exhausted_modes)` when constructing `MissionNode`.
  - `_load_checkpoint`: reads `exhausted_modes_json` from DB rows, parses it, and initializes `FrontierNode.exhausted_modes` as a set.

## Behavior
- When a mode is marked exhausted in `_select_next_action` (line 125), `_save_node` persists the updated list.
- On restart, `_load_checkpoint` restores each node's exhausted_modes, preventing re-running the same mode.
- The node saturation logic now works correctly across restarts.

## Verification
- Schema change: existing `mission.mission_nodes` table requires a new `exhausted_modes_json` column (TEXT/JSON). Migration needed in production.
- Code inspection confirms serialization/deserialization symmetry (list ↔ set).
- Manual verification: create a node, run one mode, restart frontier; confirm that the same mode is not re-selected.

## Artifacts
- **Modified files**: `src/research/domain_schema.py`, `src/research/acquisition/frontier.py`
- **Commit**: `0d48f8e` (fix(06-discovery): checkpoint exhausted_modes to persist across restarts)
