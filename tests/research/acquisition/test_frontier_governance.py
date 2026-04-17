"""Tests for AdaptiveFrontier governance and termination semantics."""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', 'src')))

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from research.acquisition.frontier import AdaptiveFrontier, ApprovalContext, FrontierNode

@pytest.mark.asyncio
async def test_zero_yield_triggers_failure_after_threshold():
    """Mission should fail after MAX_CONSECUTIVE_ZERO_YIELD consecutive zero-yield nodes."""
    mock_sm = MagicMock()
    budget_status = MagicMock()
    budget_status.usage_ratio = 0.1
    budget_status.raw_bytes = 0
    budget_status.ceiling_bytes = 1024 * 1024 * 1024
    budget_status.pending_source_count = 0
    budget_status.condensed_bytes = 0
    budget_status.condensation_running = False
    mock_sm.budget.get_status.return_value = budget_status
    mock_sm.crawler.discover_and_enqueue = AsyncMock(return_value=0)
    mock_adapter = MagicMock()
    mock_adapter.list_mission_nodes = AsyncMock(return_value=[])
    mock_adapter.get_visited_urls = AsyncMock(return_value=set())
    mock_adapter.upsert_mission_node = AsyncMock()
    mock_adapter.get_mission = AsyncMock(return_value={'domain_profile_id': 'test'})
    mock_adapter.get_domain_profile = AsyncMock(return_value=None)
    mock_adapter.upsert_domain_profile = AsyncMock()
    mock_adapter.update_mission_status = AsyncMock()
    mock_adapter.get_queue_depth = AsyncMock(return_value=0)
    mock_adapter.get_discovery_entities = AsyncMock(return_value=[])
    mock_adapter.checkpoint_frontier = AsyncMock()
    mock_sm.adapter = mock_adapter
    mock_sm.ollama = MagicMock()
    mock_sm.ollama.complete = AsyncMock(return_value='{"policy": {"class": "general"}, "nodes": ["node1", "node2"]}')
    mock_sm.query = AsyncMock(return_value="some context")

    frontier = AdaptiveFrontier(mock_sm, "mission123", "Test Topic")
    frontier.nodes["test node"] = FrontierNode(concept="test node", status="underexplored")

    with patch('asyncio.sleep', AsyncMock()):
        await frontier.run()

    assert frontier.failed
    assert frontier.failure_reason == "NO_DISCOVERY"
    assert frontier.consecutive_zero_yield >= AdaptiveFrontier.MAX_CONSECUTIVE_ZERO_YIELD


@pytest.mark.asyncio
async def test_respawn_nodes_with_none_parent():
    """_respawn_nodes should handle parent_node=None without crashing."""
    mock_sm = MagicMock()
    mock_sm.budget.get_status.return_value = MagicMock(usage_ratio=0.1)
    mock_sm.crawler.discover_and_enqueue = AsyncMock(return_value=5)
    mock_adapter = MagicMock()
    mock_adapter.list_mission_nodes = AsyncMock(return_value=[])
    mock_adapter.get_visited_urls = AsyncMock(return_value=set())
    mock_adapter.upsert_mission_node = AsyncMock()
    mock_adapter.get_mission = AsyncMock(return_value={'domain_profile_id': 'test'})
    mock_adapter.get_domain_profile = AsyncMock(return_value=None)
    mock_adapter.upsert_domain_profile = AsyncMock()
    mock_adapter.update_mission_status = AsyncMock()
    mock_adapter.get_queue_depth = AsyncMock(return_value=0)
    mock_adapter.checkpoint_frontier = AsyncMock()
    mock_sm.adapter = mock_adapter
    mock_sm.ollama = MagicMock()
    # Return a node name with length > 10 to pass the filter
    mock_sm.ollama.complete = AsyncMock(return_value='new technical node')
    mock_sm.query = AsyncMock(return_value="context")

    frontier = AdaptiveFrontier(mock_sm, "mission123", "Test Topic")
    # No initial nodes; call _respawn_nodes directly with None
    with patch('asyncio.sleep', AsyncMock()):
        await frontier._respawn_nodes(None)

    # Should have at least one new node added
    assert len(frontier.nodes) >= 1
    # Ensure that the node concept is not empty/garbage
    concepts = list(frontier.nodes.keys())
    assert any("node" in c.lower() for c in concepts)


def test_governance_filters_reject_unanchored_queries():
    frontier = AdaptiveFrontier(MagicMock(), "mission123", "GPU Scheduling")

    filtered = frontier._apply_governance_filters(
        ["banana republic", "GPU scheduling failure modes", "scheduling policy in gpu clusters"],
        "Kernel launch queues",
    )

    assert "banana republic" not in filtered
    assert any("gpu" in q.lower() for q in filtered)


def test_normalize_node_concept_rejects_prompt_artifacts():
    frontier = AdaptiveFrontier(MagicMock(), "mission123", "AI Agents")

    assert frontier._normalize_node_concept(
        "Here are 3-5 new, specific sub-topics that could be added to the research subject:",
        parent_concept="AI Agents",
    ) is None


def test_normalize_node_concept_keeps_relevant_topic():
    frontier = AdaptiveFrontier(MagicMock(), "mission123", "AI Agents")

    cleaned = frontier._normalize_node_concept(
        '1. Authentication and Authorization of AI Agents',
        parent_concept="AI Agents",
    )

    assert cleaned == "Authentication and Authorization of AI Agents"


def test_low_yield_plateau_triggers_convergence():
    frontier = AdaptiveFrontier(MagicMock(), "mission123", "GPU Scheduling")
    frontier._novelty_window = [1, 1, 0, 1]

    assert frontier._is_low_yield_plateau() is True


@pytest.mark.asyncio
async def test_select_next_action_awaits_saturated_node_save():
    frontier = AdaptiveFrontier(MagicMock(), "mission123", "GPU Scheduling")
    saturated = FrontierNode(
        concept="done node",
        status="underexplored",
        exhausted_modes={"grounding", "verification", "dialectic", "expansion"},
    )
    frontier.nodes = {
        saturated.concept: saturated,
    }
    events = []

    async def fake_save(node):
        events.append(("saved", node.concept, node.status))

    frontier._save_node = fake_save

    node, mode = await frontier._select_next_action()
    events.append(("returned", node, mode))

    assert node is None
    assert mode is None
    assert saturated.status == "saturated"
    assert events == [
        ("saved", "done node", "saturated"),
        ("returned", None, None),
    ]


# ──────────────────────────────────────────────────────────────
# Staged approval policy tests (_get_approval_context)
# ──────────────────────────────────────────────────────────────

def _frontier_with_budget(usage_ratio: float, respawn_count: int = 0) -> AdaptiveFrontier:
    mock_sm = MagicMock()
    mock_sm.budget.get_status.return_value = MagicMock(usage_ratio=usage_ratio)
    frontier = AdaptiveFrontier(mock_sm, "mission123", "GPU Scheduling")
    frontier.respawn_count = respawn_count
    return frontier


def test_no_approval_needed_when_budget_low_and_respawns_few():
    frontier = _frontier_with_budget(0.40, respawn_count=0)
    assert frontier._get_approval_context() is None


def test_budget_pressure_gate_triggers_at_92_percent():
    """BUDGET_PRESSURE fires when budget >= 0.92, regardless of respawn count."""
    frontier = _frontier_with_budget(0.93, respawn_count=0)
    ctx = frontier._get_approval_context()
    assert ctx is not None
    assert ctx.reason_code == "BUDGET_PRESSURE"
    assert ctx.usage_ratio >= 0.92


def test_budget_pressure_gate_does_not_trigger_at_91_percent():
    frontier = _frontier_with_budget(0.91, respawn_count=0)
    ctx = frontier._get_approval_context()
    # May still be None or a different gate; must NOT be BUDGET_PRESSURE
    assert ctx is None or ctx.reason_code != "BUDGET_PRESSURE"


def test_scope_expansion_gate_triggers_at_four_respawns():
    """SCOPE_EXPANSION fires when respawn_count >= 4, regardless of budget."""
    frontier = _frontier_with_budget(0.30, respawn_count=4)
    ctx = frontier._get_approval_context()
    assert ctx is not None
    assert ctx.reason_code == "SCOPE_EXPANSION"
    assert ctx.respawn_count >= 4


def test_scope_expansion_gate_does_not_trigger_at_three_respawns():
    frontier = _frontier_with_budget(0.30, respawn_count=3)
    ctx = frontier._get_approval_context()
    # Three respawns at low budget should not trigger any gate
    assert ctx is None


def test_budget_and_scope_gate_triggers_at_combo():
    """BUDGET_AND_SCOPE fires when respawn >= 2 AND budget >= 0.85."""
    frontier = _frontier_with_budget(0.88, respawn_count=2)
    ctx = frontier._get_approval_context()
    assert ctx is not None
    assert ctx.reason_code == "BUDGET_AND_SCOPE"


def test_budget_and_scope_gate_respects_respawn_floor():
    """combo gate does NOT fire at only 1 respawn even at 88% budget."""
    frontier = _frontier_with_budget(0.88, respawn_count=1)
    ctx = frontier._get_approval_context()
    assert ctx is None


def test_budget_and_scope_gate_respects_budget_floor():
    """combo gate does NOT fire at 2 respawns if budget is only 80%."""
    frontier = _frontier_with_budget(0.80, respawn_count=2)
    ctx = frontier._get_approval_context()
    assert ctx is None


def test_approval_context_is_dataclass():
    """ApprovalContext fields are accessible as expected."""
    ctx = ApprovalContext(
        reason_code="BUDGET_PRESSURE",
        reason_detail="test detail",
        usage_ratio=0.95,
        respawn_count=1,
    )
    assert ctx.reason_code == "BUDGET_PRESSURE"
    assert ctx.usage_ratio == 0.95


def test_budget_pressure_takes_priority_over_scope_expansion():
    """When both scope and budget thresholds are crossed, BUDGET_PRESSURE wins."""
    # usage_ratio >= 0.92 AND respawn_count >= 4 simultaneously
    frontier = _frontier_with_budget(0.95, respawn_count=5)
    ctx = frontier._get_approval_context()
    assert ctx is not None
    assert ctx.reason_code == "BUDGET_PRESSURE"


# ──────────────────────────────────────────────────────────────
# _fail_mission stop_reason encoding
# ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_fail_mission_encodes_approval_reason_in_stop_reason():
    """_fail_mission must write APPROVAL_REQUIRED:<reason_code> to the DB."""
    mock_adapter = MagicMock()
    mock_adapter.update_mission_status = AsyncMock()
    mock_sm = MagicMock()
    mock_sm.budget.get_status.return_value = MagicMock(usage_ratio=0.5)
    mock_sm.adapter = mock_adapter

    frontier = AdaptiveFrontier(mock_sm, "mission-xyz", "Test")
    ctx = ApprovalContext(
        reason_code="BUDGET_PRESSURE",
        reason_detail="detail",
        usage_ratio=0.93,
        respawn_count=0,
    )
    await frontier._fail_mission("APPROVAL_REQUIRED", ctx)

    assert frontier.failure_reason == "APPROVAL_REQUIRED:BUDGET_PRESSURE"
    mock_adapter.update_mission_status.assert_awaited_once()
    call_kwargs = mock_adapter.update_mission_status.call_args
    assert call_kwargs.kwargs.get("stop_reason") == "APPROVAL_REQUIRED:BUDGET_PRESSURE"


@pytest.mark.asyncio
async def test_fail_mission_without_ctx_uses_plain_reason():
    """_fail_mission with no approval_ctx keeps original plain-string stop_reason."""
    mock_adapter = MagicMock()
    mock_adapter.update_mission_status = AsyncMock()
    mock_sm = MagicMock()
    mock_sm.adapter = mock_adapter

    frontier = AdaptiveFrontier(mock_sm, "mission-abc", "Test")
    await frontier._fail_mission("NO_DISCOVERY")

    assert frontier.failure_reason == "NO_DISCOVERY"
    call_kwargs = mock_adapter.update_mission_status.call_args
    assert call_kwargs.kwargs.get("stop_reason") == "NO_DISCOVERY"
