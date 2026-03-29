"""
tests/test_smelter_status_transition.py

Verifies that DistillationPipeline correctly updates source status:
- 'condensed' when at least one atom is stored
- 'rejected' when zero atoms are extracted

This closes the soft acceptance bug identified in Phase 09.
"""
import pytest
import sys
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock
from pathlib import Path
import importlib.util

# --- Load modules directly bypassing src/__init__ ---
def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod

SRC = Path(__file__).parent.parent / "src"

# Load in dependency order (minimal needed)
load_module('src.research.domain_schema', SRC / 'research' / 'domain_schema.py')
load_module('src.utils.json_validator', SRC / 'utils' / 'json_validator.py')
pipeline_mod = load_module('src.research.condensation.pipeline', SRC / 'research' / 'condensation' / 'pipeline.py')


@pytest.mark.asyncio
async def test_condensed_when_atoms_stored():
    # Create mocks
    mock_adapter = MagicMock()
    mock_adapter.pg = MagicMock()
    mock_adapter.get_text_ref = AsyncMock(return_value={"inline_text": "sample content"})
    mock_adapter.get_mission = AsyncMock(return_value={"domain_profile_id": "test", "topic_id": "test"})
    mock_adapter.store_atom_with_evidence = AsyncMock()

    mock_ollama = MagicMock()
    async def mock_chat(messages, stream=False, temperature=None):
        class Chunk:
            content = '{"atoms": [{"type": "claim", "content": "test atom", "confidence": 0.9}]}'
        yield Chunk()
    mock_ollama.chat = mock_chat

    pipeline = pipeline_mod.DistillationPipeline(mock_ollama, None, MagicMock(), adapter=mock_adapter)

    source = {"source_id": "src1", "mission_id": "m1", "status": "fetched", "canonical_text_ref": "ref1", "url": "http://example.com"}

    with patch.object(pipeline.adapter.pg, 'fetch_many', return_value=[source]), \
         patch('src.research.condensation.pipeline.extract_technical_atoms', AsyncMock(return_value=[{"type": "claim", "content": "atom", "confidence": 0.9}])):
        await pipeline.run("m1", MagicMock())

    # Check that update_row was called with 'condensed' for this source
    update_calls = [c for c in mock_adapter.pg.update_row.call_args_list if c[0][1] == "source_id"]
    statuses = [c[0][2]["status"] for c in update_calls]
    assert "condensed" in statuses, f"Expected 'condensed' in statuses, got {statuses}"


@pytest.mark.asyncio
async def test_rejected_when_zero_atoms():
    mock_adapter = MagicMock()
    mock_adapter.pg = MagicMock()
    mock_adapter.get_text_ref = AsyncMock(return_value={"inline_text": "sample content"})
    mock_adapter.get_mission = AsyncMock(return_value={"domain_profile_id": "test", "topic_id": "test"})
    mock_adapter.store_atom_with_evidence = AsyncMock()

    mock_ollama = MagicMock()
    async def mock_chat(messages, stream=False, temperature=None):
        class Chunk:
            content = '{"atoms": []}'
        yield Chunk()
    mock_ollama.chat = mock_chat

    pipeline = pipeline_mod.DistillationPipeline(mock_ollama, None, MagicMock(), adapter=mock_adapter)

    source = {"source_id": "src2", "mission_id": "m1", "status": "fetched", "canonical_text_ref": "ref2", "url": "http://example.com"}

    with patch.object(pipeline.adapter.pg, 'fetch_many', return_value=[source]), \
         patch('src.research.condensation.pipeline.extract_technical_atoms', AsyncMock(return_value=[])):
        await pipeline.run("m1", MagicMock())

    update_calls = [c for c in mock_adapter.pg.update_row.call_args_list if c[0][1] == "source_id"]
    statuses = [c[0][2]["status"] for c in update_calls]
    assert "rejected" in statuses, f"Expected 'rejected' in statuses, got {statuses}"
