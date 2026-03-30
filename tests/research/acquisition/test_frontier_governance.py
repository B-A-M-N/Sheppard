"""Tests for AdaptiveFrontier governance and termination semantics."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from research.acquisition.frontier import AdaptiveFrontier, FrontierNode

@pytest.mark.asyncio
async def test_zero_yield_triggers_failure_after_threshold():
    """Mission should fail after MAX_CONSECUTIVE_ZERO_YIELD consecutive zero-yield nodes."""
    mock_sm = MagicMock()
    mock_sm.budget.get_status.return_value = MagicMock(usage_ratio=0.1)
    mock_sm.crawler.discover_and_enqueue = AsyncMock(return_value=0)
    mock_adapter = MagicMock()
    mock_adapter.list_mission_nodes = AsyncMock(return_value=[])
    mock_adapter.get_visited_urls = AsyncMock(return_value=set())
    mock_adapter.upsert_mission_node = AsyncMock()
    mock_adapter.get_mission = AsyncMock(return_value={'domain_profile_id': 'test'})
    mock_adapter.get_domain_profile = AsyncMock(return_value=None)
    mock_adapter.upsert_domain_profile = AsyncMock()
    mock_adapter.update_mission_status = AsyncMock()
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
