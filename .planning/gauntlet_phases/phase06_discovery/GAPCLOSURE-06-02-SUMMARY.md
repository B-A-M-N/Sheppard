# Task 06-02: Set parent_node_id on node creation

## Summary
Fixed the parent_node_id gap: nodes are now persisted with correct parent-child relationships.

## Changes Made
- **frontier.py**:
  - Added `parent_node_id: Optional[str] = None` to `FrontierNode` dataclass.
  - Modified `_save_node` to accept `parent_node_id` parameter; uses passed value or node's attribute.
  - Updated `_load_checkpoint` to restore `parent_node_id` from DB rows to FrontierNode instances.
  - Updated `_frame_research_policy` to explicitly pass `parent_node_id=None` for root nodes.
  - Updated `_respawn_nodes` to compute parent_node_id (deterministic UUID5) and pass it when saving child nodes.

## Verification
- Code review confirms parent_node_id is correctly propagated.
- No schema change required: `MissionNode` already had `parent_node_id` field.
- When nodes are created:
  - Root nodes have `parent_node_id = NULL`.
  - Child nodes have `parent_node_id` set to the parent's node_id (UUID5 of mission:concept).
- The node hierarchy can now be reconstructed from the `mission.mission_nodes` table via `parent_node_id` links.

## Notes
- The node_id computation uses `uuid.uuid5(uuid.NAMESPACE_URL, f"{mission_id}:{concept}")` and is deterministic, allowing consistent parent linking across restarts.
- Existing nodes in the database from before this fix will have `parent_node_id = NULL`. New nodes will have correct links.

## Artifacts
- **Modified files**: `src/research/acquisition/frontier.py`
- **Commit**: `2831197e` (fix(06-discovery): set parent_node_id in _save_node and _respawn_nodes)
