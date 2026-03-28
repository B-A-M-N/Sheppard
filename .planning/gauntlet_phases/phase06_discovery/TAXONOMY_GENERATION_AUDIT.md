# Taxonomy Generation Audit

## Claim Under Review

Discovery is driven by structured, LLM-generated research nodes representing a topic taxonomy, not flat keyword search.

## Decomposition Prompt Analysis

`_frame_research_policy` (frontier.py lines 200-215) constructs a prompt that asks the LLM to:

1. Define the "Evidence Stack" — what counts as proof in the specific field
2. Define "Authority" — what kinds of sources are most reliable
3. Decompose the subject into 15 foundational, highly specific research nodes

The target count of 15 is hardcoded as numbered labels directly in the prompt string: `"node 1", "node 2", ..., "node 15"`. The LLM may return fewer or more than 15; the count is a prompt instruction, not a programmatic constraint.

The extraction loop at lines 251-263 iterates `data.get('nodes', [])` with no minimum count enforcement. Each candidate node string is cleaned with `re.sub(r'^(Node\s*\d+:?|\d+[\.\)]\s*)', '', n, flags=re.IGNORECASE).strip()` (lines 253-254). Only names longer than 3 characters are accepted (line 254: `if clean_n and len(clean_n) > 3`). There is no assertion, log warning, or fallback trigger based on the number of nodes successfully extracted from the LLM response.

The 5 hardcoded fallback nodes (lines 266-277) are activated when LLM generation fails or JSON parsing fails entirely. They are:

```
[topic_name]
[topic_name] technical architecture
[topic_name] implementation details
[topic_name] failure modes
[topic_name] best practices
```

These are interpolated with the mission's `topic_name` at construction time.

## Node Count Analysis

- **Prompt requests:** 15 nodes (hardcoded in prompt text, lines 200-215)
- **Extraction enforces:** 0 minimum (lines 251-263 — no count check after iteration)
- **Fallback provides:** exactly 5 (lines 266-277)

Node count is LLM-dependent. A compliant LLM response produces up to 15. A degraded response (partial JSON, truncated output, model refusal) may produce 1-14. If extraction yields `node_count == 0` (line 263: `raise ValueError("No valid nodes extracted")`), the fallback branch fires and 5 nodes are used. There is no branch for `1 <= node_count < 5` that triggers a warning or supplementation.

## parent_node_id Gap

This is the central finding of this audit document.

`MissionNode` declares `parent_node_id` as an optional field at domain_schema.py line 107:

```python
parent_node_id: Optional[str] = None
```

`_save_node` (frontier.py lines 157-171) constructs `MissionNode` as follows:

```python
async def _save_node(self, node: FrontierNode):
    """Checkpoint a single node."""
    import uuid
    from src.research.domain_schema import MissionNode

    node_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{self.mission_id}:{node.concept}"))

    v3_node = MissionNode(
        node_id=node_id,
        mission_id=self.mission_id,
        label=node.concept,
        concept_form=node.concept,
        status=node.status
    )
    await self.sm.adapter.upsert_mission_node(v3_node.to_pg_row())
```

`parent_node_id` is not set in this constructor call. It defaults to `None` for every node written, regardless of whether the node is a root-level decomposition node or a child spawned by `_respawn_nodes`.

`_respawn_nodes` (frontier.py lines 329-352) spawns child nodes when a parent concept has low yield. It receives a `parent_node` argument that contains the parent concept. However, the `_save_node(node)` call within `_respawn_nodes` at line 348 does not pass `parent_node_id` to the saved node. The parent-child relationship is known in memory at spawn time but is discarded at the DB write boundary.

**Result:** Every node written to the database has `parent_node_id = None`. The node graph is structurally flat at runtime. The schema supports hierarchy; the runtime does not use it.

## Fallback Behavior

When LLM generation fails or JSON parsing fails, 5 hardcoded fallback nodes are activated (frontier.py lines 266-277). The 5 fallback nodes for a mission topic `T` are: `T`, `T technical architecture`, `T implementation details`, `T failure modes`, `T best practices`. These are safe general-purpose research anchors. Missions running on fallback nodes have lower topic specificity than missions that successfully parse an LLM decomposition: the fallback nodes are structural templates, not domain-specific decompositions. The fallback is a correct degradation path — it prevents the frontier from having zero nodes — but it bypasses the taxonomy generation claim entirely.

## Classification

**PARTIAL** — structure present in schema (`parent_node_id` field in `MissionNode`) and in prompt engineering (15-node decomposition request). Enforcement absent in the runtime path: `_save_node` and `_respawn_nodes` both omit `parent_node_id` at the DB write boundary; node count is not enforced after LLM extraction.

## What Would Constitute PASS

- `parent_node_id` populated in both `_save_node` (when called from `_frame_research_policy`, setting `parent_node_id = None` for root nodes is acceptable) and in `_respawn_nodes` (setting `parent_node_id = parent_node_id` to the parent's DB node_id), so that the persisted graph reflects actual ancestry
- Node count >= some minimum (e.g., 5) enforced after LLM extraction in `_frame_research_policy`, with a warning log and optional supplement from fallback nodes rather than a silent under-count
