"""
tests/test_smelter_status_transition.py

Verifies that DistillationPipeline correctly updates source status:
- 'condensed' when at least one atom is stored
- 'rejected' when zero atoms are extracted

This closes the soft acceptance bug identified in Phase 09.
"""
import pytest
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

import asyncio
from unittest.mock import patch, MagicMock, AsyncMock

from research.condensation.pipeline import DistillationPipeline


@pytest.mark.asyncio
async def test_condensed_when_atoms_stored():
    """Sources with extracted atoms should be marked as 'condensed'."""
    # Create mocks
    mock_adapter = MagicMock()
    mock_adapter.pg = MagicMock()
    mock_adapter.pg.fetch_many = AsyncMock(return_value=[
        {"source_id": "src1", "mission_id": "m1", "status": "fetched", "canonical_text_ref": "ref1", "url": "http://example.com"}
    ])
    mock_adapter.pg.update_row = AsyncMock()
    mock_adapter.get_text_ref = AsyncMock(return_value={"inline_text": "sample content"})
    mock_adapter.get_mission = AsyncMock(return_value={"domain_profile_id": "test", "topic_id": "test"})
    mock_adapter.store_atom_with_evidence = AsyncMock()
    mock_adapter.list_chunks_for_source = AsyncMock(return_value=[
        {"chunk_id": "chunk1", "inline_text": "sample content"}
    ])

    mock_ollama = MagicMock()
    async def mock_chat(messages, stream=False, temperature=None):
        class Chunk:
            content = '{"atoms": [{"type": "claim", "content": "test atom", "confidence": 0.9}]}'
        yield Chunk()
    mock_ollama.chat = mock_chat

    # Budget mock must have async record_condensation_result
    mock_budget = MagicMock()
    mock_budget.record_condensation_result = AsyncMock()

    pipeline = DistillationPipeline(mock_ollama, None, mock_budget, adapter=mock_adapter)

    # Patch extract_technical_atoms
    with patch('research.condensation.pipeline.extract_technical_atoms', AsyncMock(return_value=[
        {"type": "claim", "content": "atom", "confidence": 0.9}
    ])):
        await pipeline.run("m1", MagicMock())

    # Check that update_row was called with 'condensed' for this source
    update_calls = [c for c in mock_adapter.pg.update_row.call_args_list if c[0][1] == "source_id"]
    assert len(update_calls) > 0, f"Expected update_row to be called"
    statuses = [c[0][2]["status"] for c in update_calls]
    assert "condensed" in statuses, f"Expected 'condensed' in statuses, got {statuses}"


@pytest.mark.asyncio
async def test_rejected_when_zero_atoms():
    """Sources with zero extracted atoms should be marked as 'rejected'."""
    mock_adapter = MagicMock()
    mock_adapter.pg = MagicMock()
    mock_adapter.pg.fetch_many = AsyncMock(return_value=[
        {"source_id": "src2", "mission_id": "m1", "status": "fetched", "canonical_text_ref": "ref2", "url": "http://example.com"}
    ])
    mock_adapter.pg.update_row = AsyncMock()
    mock_adapter.get_text_ref = AsyncMock(return_value={"inline_text": "sample content"})
    mock_adapter.get_mission = AsyncMock(return_value={"domain_profile_id": "test", "topic_id": "test"})
    mock_adapter.store_atom_with_evidence = AsyncMock()
    mock_adapter.list_chunks_for_source = AsyncMock(return_value=[
        {"chunk_id": "chunk1", "inline_text": "sample content"}
    ])

    mock_ollama = MagicMock()
    async def mock_chat(messages, stream=False, temperature=None):
        class Chunk:
            content = '{"atoms": []}'
        yield Chunk()
    mock_ollama.chat = mock_chat

    mock_budget = MagicMock()
    mock_budget.record_condensation_result = AsyncMock()

    pipeline = DistillationPipeline(mock_ollama, None, mock_budget, adapter=mock_adapter)

    with patch('research.condensation.pipeline.extract_technical_atoms', AsyncMock(return_value=[])):
        await pipeline.run("m1", MagicMock())

    update_calls = [c for c in mock_adapter.pg.update_row.call_args_list if c[0][1] == "source_id"]
    assert len(update_calls) > 0, f"Expected update_row to be called"
    statuses = [c[0][2]["status"] for c in update_calls]
    assert "rejected" in statuses, f"Expected 'rejected' in statuses, got {statuses}"


@pytest.mark.asyncio
async def test_error_on_missing_text_ref():
    """Sources without canonical_text_ref should be marked as 'error'."""
    mock_adapter = MagicMock()
    mock_adapter.pg = MagicMock()
    mock_adapter.pg.fetch_many = AsyncMock(return_value=[
        {"source_id": "src3", "mission_id": "m1", "status": "fetched", "url": "http://example.com"}
    ])
    mock_adapter.pg.update_row = AsyncMock()
    mock_adapter.get_mission = AsyncMock(return_value={"domain_profile_id": "test", "topic_id": "test"})

    mock_ollama = MagicMock()
    mock_budget = MagicMock()
    mock_budget.record_condensation_result = AsyncMock()
    
    pipeline = DistillationPipeline(mock_ollama, None, mock_budget, adapter=mock_adapter)

    await pipeline.run("m1", MagicMock())

    update_calls = [c for c in mock_adapter.pg.update_row.call_args_list if c[0][1] == "source_id"]
    assert len(update_calls) > 0
    statuses = [c[0][2]["status"] for c in update_calls]
    assert "error" in statuses
