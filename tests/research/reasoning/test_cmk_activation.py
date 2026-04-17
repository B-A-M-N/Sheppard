"""
Tests for V3Retriever.activate_cmk — verifies the async activation path
actually fires and doesn't silently swallow activation due to the old
run_until_complete anti-pattern.
"""

import asyncio
import pytest

from src.research.reasoning.v3_retriever import V3Retriever
from src.retrieval.models import RetrievedItem


def _make_item(atom_id: str) -> RetrievedItem:
    return RetrievedItem(
        content="test content",
        source="test",
        strategy="semantic",
        citation_key=f"[{atom_id}]",
        metadata={"atom_id": atom_id},
    )


class FakeCMKRuntime:
    def __init__(self):
        self.activated = []

    async def activate_atom(self, atom_id: str, amount: float = 1.0):
        self.activated.append((atom_id, amount))
        return amount


@pytest.mark.asyncio
async def test_activate_cmk_fires_for_each_atom():
    """activate_cmk must call cmk_runtime.activate_atom for every item with atom_id."""
    runtime = FakeCMKRuntime()
    items = [_make_item("a1"), _make_item("a2"), _make_item("a3")]

    await V3Retriever.activate_cmk(items, runtime)

    assert len(runtime.activated) == 3
    assert ("a1", 0.1) in runtime.activated
    assert ("a2", 0.1) in runtime.activated
    assert ("a3", 0.1) in runtime.activated


@pytest.mark.asyncio
async def test_activate_cmk_no_op_when_no_runtime():
    """activate_cmk is a no-op when cmk_runtime is None."""
    items = [_make_item("a1")]
    await V3Retriever.activate_cmk(items, None)  # must not raise


@pytest.mark.asyncio
async def test_activate_cmk_no_op_when_no_items():
    """activate_cmk is a no-op when atom list is empty."""
    runtime = FakeCMKRuntime()
    await V3Retriever.activate_cmk([], runtime)
    assert runtime.activated == []


@pytest.mark.asyncio
async def test_activate_cmk_skips_items_without_atom_id():
    """Items with no atom_id in metadata are silently skipped."""
    runtime = FakeCMKRuntime()
    item_with_id = _make_item("a1")
    item_no_meta = RetrievedItem(
        content="no meta",
        source="test",
        strategy="semantic",
        metadata=None,
    )
    item_empty_meta = RetrievedItem(
        content="empty meta",
        source="test",
        strategy="semantic",
        metadata={},
    )

    await V3Retriever.activate_cmk(
        [item_with_id, item_no_meta, item_empty_meta], runtime
    )

    assert len(runtime.activated) == 1
    assert runtime.activated[0][0] == "a1"


@pytest.mark.asyncio
async def test_activate_cmk_continues_on_per_item_error():
    """A failure on one atom must not block activation of subsequent atoms."""

    class ErrorOnFirstRuntime:
        def __init__(self):
            self.activated = []
            self._count = 0

        async def activate_atom(self, atom_id: str, amount: float = 1.0):
            self._count += 1
            if self._count == 1:
                raise RuntimeError("simulated failure")
            self.activated.append(atom_id)

    runtime = ErrorOnFirstRuntime()
    items = [_make_item("fail"), _make_item("ok")]

    await V3Retriever.activate_cmk(items, runtime)

    # Second atom was activated despite first failing
    assert "ok" in runtime.activated


@pytest.mark.asyncio
async def test_activate_cmk_is_awaitable_inside_running_loop():
    """
    Verify activate_cmk can be awaited from within an already-running event loop
    (the old run_until_complete pattern would raise RuntimeError here).
    """
    runtime = FakeCMKRuntime()
    items = [_make_item("loop-test")]

    # This runs inside pytest-asyncio's event loop — if the old broken path were
    # still in place, run_until_complete would raise RuntimeError.
    await V3Retriever.activate_cmk(items, runtime)

    assert len(runtime.activated) == 1
