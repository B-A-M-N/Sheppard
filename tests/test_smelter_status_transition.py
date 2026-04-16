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

# Gate 0a requires at least 50 words; use this in all tests that need real content
_LONG_CONTENT = (
    "Python is a high-level general-purpose programming language. Its design philosophy emphasizes "
    "code readability with the use of significant indentation. Python is dynamically typed and "
    "garbage-collected. It supports multiple programming paradigms including structured, object-oriented, "
    "and functional programming. It is often described as a batteries-included language due to its "
    "comprehensive standard library. Guido van Rossum began working on Python in the late 1980s."
)


def _make_pg_mock():
    """Build a pg mock with all async methods wired up, including pool.acquire/release."""
    pg = MagicMock()
    pg.update_row = AsyncMock()
    pg.fetch_one = AsyncMock(return_value=None)
    pg.insert_row = AsyncMock()
    conn = AsyncMock()
    conn.execute = AsyncMock(return_value="UPDATE 1")
    pg.pool = MagicMock()
    pg.pool.acquire = AsyncMock(return_value=conn)
    pg.pool.release = AsyncMock()
    return pg, conn


@pytest.mark.asyncio
async def test_condensed_when_atoms_stored():
    """Sources with extracted atoms should be marked as 'condensed'."""
    mock_adapter = MagicMock()
    pg, mock_conn = _make_pg_mock()
    mock_adapter.pg = pg
    mock_adapter.pg.fetch_many = AsyncMock(return_value=[
        {"source_id": "src1", "mission_id": "m1", "status": "fetched", "canonical_text_ref": "ref1", "url": "http://example.com"}
    ])
    mock_adapter.get_text_ref = AsyncMock(return_value={"inline_text": _LONG_CONTENT})
    mock_adapter.get_mission = AsyncMock(return_value={"domain_profile_id": "test", "topic_id": "test"})
    mock_adapter.store_atom_with_evidence = AsyncMock()
    mock_adapter.get_mission_atoms = AsyncMock(return_value=[])
    mock_adapter.list_chunks_for_source = AsyncMock(return_value=[
        {"chunk_id": "chunk1", "inline_text": _LONG_CONTENT}
    ])

    mock_ollama = MagicMock()
    async def mock_chat(messages, stream=False, temperature=None):
        class Chunk:
            content = '{"atoms": [{"type": "claim", "content": "test atom", "confidence": 0.9}]}'
        yield Chunk()
    mock_ollama.chat = mock_chat

    mock_budget = MagicMock()
    mock_budget.record_condensation_result = AsyncMock()
    mock_budget.record_source_condensed = AsyncMock()

    pipeline = DistillationPipeline(mock_ollama, None, mock_budget, adapter=mock_adapter)

    with patch('research.condensation.pipeline.extract_technical_atoms', AsyncMock(return_value=[
        {"type": "claim", "content": "atom", "confidence": 0.9}
    ])):
        await pipeline.run("m1", MagicMock())

    # Status transitions go through conn.execute (state_machine.py): (sql, new_status, source_id, old_status)
    execute_calls = mock_conn.execute.call_args_list
    status_args = [c[0][1] for c in execute_calls if len(c[0]) > 1 and "UPDATE corpus.sources" in str(c[0][0])]
    assert len(status_args) > 0, f"Expected status transitions via conn.execute"
    assert "condensed" in status_args, f"Expected 'condensed' in status transitions, got {status_args}"


@pytest.mark.asyncio
async def test_rejected_when_zero_atoms():
    """Sources with zero extracted atoms should be marked as 'rejected'."""
    mock_adapter = MagicMock()
    pg, mock_conn = _make_pg_mock()
    mock_adapter.pg = pg
    mock_adapter.pg.fetch_many = AsyncMock(return_value=[
        {"source_id": "src2", "mission_id": "m1", "status": "fetched", "canonical_text_ref": "ref2", "url": "http://example.com"}
    ])
    mock_adapter.get_text_ref = AsyncMock(return_value={"inline_text": _LONG_CONTENT})
    mock_adapter.get_mission = AsyncMock(return_value={"domain_profile_id": "test", "topic_id": "test"})
    mock_adapter.store_atom_with_evidence = AsyncMock()
    mock_adapter.list_chunks_for_source = AsyncMock(return_value=[
        {"chunk_id": "chunk1", "inline_text": _LONG_CONTENT}
    ])

    mock_ollama = MagicMock()
    async def mock_chat(messages, stream=False, temperature=None):
        class Chunk:
            content = '{"atoms": []}'
        yield Chunk()
    mock_ollama.chat = mock_chat

    mock_budget = MagicMock()
    mock_budget.record_condensation_result = AsyncMock()
    mock_budget.record_source_condensed = AsyncMock()

    pipeline = DistillationPipeline(mock_ollama, None, mock_budget, adapter=mock_adapter)

    with patch('research.condensation.pipeline.extract_technical_atoms', AsyncMock(return_value=[])):
        await pipeline.run("m1", MagicMock())

    execute_calls = mock_conn.execute.call_args_list
    status_args = [c[0][1] for c in execute_calls if len(c[0]) > 1 and "UPDATE corpus.sources" in str(c[0][0])]
    assert len(status_args) > 0, f"Expected status transitions via conn.execute"
    assert "rejected" in status_args, f"Expected 'rejected' in status transitions, got {status_args}"


@pytest.mark.asyncio
async def test_error_on_missing_text_ref():
    """Sources without canonical_text_ref should be marked as 'error'."""
    mock_adapter = MagicMock()
    pg, mock_conn = _make_pg_mock()
    mock_adapter.pg = pg
    mock_adapter.pg.fetch_many = AsyncMock(return_value=[
        {"source_id": "src3", "mission_id": "m1", "status": "fetched", "url": "http://example.com"}
    ])
    mock_adapter.get_mission = AsyncMock(return_value={"domain_profile_id": "test", "topic_id": "test"})

    mock_ollama = MagicMock()
    mock_budget = MagicMock()
    mock_budget.record_condensation_result = AsyncMock()

    pipeline = DistillationPipeline(mock_ollama, None, mock_budget, adapter=mock_adapter)

    await pipeline.run("m1", MagicMock())

    execute_calls = mock_conn.execute.call_args_list
    status_args = [c[0][1] for c in execute_calls if len(c[0]) > 1 and "UPDATE corpus.sources" in str(c[0][0])]
    assert len(status_args) > 0, f"Expected status transitions via conn.execute"
    assert "error" in status_args, f"Expected 'error' in status transitions, got {status_args}"
