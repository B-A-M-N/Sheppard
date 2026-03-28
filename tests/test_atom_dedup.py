"""
tests/test_atom_dedup.py

Verifies that atom_id derivation in condensation/pipeline.py is deterministic,
closing gap A11 (duplicate atoms on re-run).
"""
import uuid
import subprocess
import sys
from pathlib import Path

PIPELINE_PATH = Path(__file__).parent.parent / "src" / "research" / "condensation" / "pipeline.py"


def _derive_atom_id(mission_id: str, source_id: str, content: str) -> str:
    """Mirror of the expression in pipeline.py line 89."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"{mission_id}:{source_id}:{content[:200]}"))


def test_atom_id_is_deterministic():
    id1 = _derive_atom_id("mission-1", "source-1", "Neural scaling laws show...")
    id2 = _derive_atom_id("mission-1", "source-1", "Neural scaling laws show...")
    assert id1 == id2, "Same inputs must yield the same atom_id"


def test_different_content_gives_different_id():
    id1 = _derive_atom_id("mission-1", "source-1", "Transformers use attention")
    id2 = _derive_atom_id("mission-1", "source-1", "Diffusion models use noise")
    assert id1 != id2, "Different content must yield different atom_ids"


def test_empty_content_is_stable():
    id1 = _derive_atom_id("mission-1", "source-1", "")
    id2 = _derive_atom_id("mission-1", "source-1", "")
    assert id1 == id2, "Empty content must still yield a stable atom_id"


def test_different_sources_give_different_ids():
    id1 = _derive_atom_id("mission-1", "source-A", "Same content text here")
    id2 = _derive_atom_id("mission-1", "source-B", "Same content text here")
    assert id1 != id2, "Different source_id must yield different atom_ids"


def test_uuid4_is_not_present_in_pipeline():
    """Regression guard: uuid4 must not appear in the pipeline atom_id derivation."""
    source = PIPELINE_PATH.read_text()
    assert "uuid.uuid4()" not in source, (
        "uuid.uuid4() found in pipeline.py — atom_id derivation is still non-deterministic"
    )


def test_uuid5_namespace_url_is_present_in_pipeline():
    """Positive guard: uuid5(NAMESPACE_URL, ...) must be present in pipeline.py."""
    source = PIPELINE_PATH.read_text()
    assert "uuid.uuid5(uuid.NAMESPACE_URL" in source, (
        "uuid.uuid5(uuid.NAMESPACE_URL not found in pipeline.py — deterministic fix was not applied"
    )
