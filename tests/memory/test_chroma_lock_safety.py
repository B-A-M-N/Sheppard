"""
Phase 12-G: Lock-Inside-Executor Kill Tests

These tests verify the critical invariant fix:
  - The global lock is a threading.Lock (non-reentrant)
  - chroma_lock_ctx acquires/releases correctly
  - Concurrent operations through safe wrappers are serialized

The root cause we're fixing: the old `async with with_chroma_lock()` pattern
held the lock in the event-loop thread, but `asyncio.to_thread()` ran native
Chroma calls on different worker threads that did NOT hold the lock.

The fix: all chromadb calls run inside `_chroma_*_safe` wrappers that acquire
the lock synchronously IN the worker thread.
"""

import concurrent.futures
import threading
import pytest

from src.memory.chroma_process_lock import (
    chroma_lock_ctx,
    get_chroma_process_lock,
)


# ============================================================================
# Test Cases
# ============================================================================

def test_lock_is_non_reentrant():
    """Lock must be threading.Lock (not RLock) to prevent nested acquisition."""
    lock = get_chroma_process_lock()
    assert type(lock).__name__ == "lock", (
        f"Expected threading.Lock, got {type(lock).__name__}. "
        "Non-reentrant lock prevents accidental nested acquisition."
    )


def test_chroma_lock_ctx_acquire_release():
    """Verify chroma_lock_ctx works correctly as a sync context manager."""
    lock = get_chroma_process_lock()
    assert not lock.locked()

    with chroma_lock_ctx():
        assert lock.locked()

    # Lock must be released after context exit
    assert not lock.locked()


def test_chroma_lock_ctx_exception_safety():
    """Verify lock is released even if an exception is raised inside context."""
    lock = get_chroma_process_lock()
    with pytest.raises(RuntimeError):
        with chroma_lock_ctx():
            assert lock.locked()
            raise RuntimeError("test")

    assert not lock.locked(), "Lock must be released even on exception"


def test_concurrent_serialization():
    """
    Verify that when multiple threads try to do 'work' through safe wrappers,
    only one runs at a time. This proves the executor boundary rule.
    """
    execution_log = []
    log_lock = threading.Lock()

    def fake_chropa_operation(thread_id):
        with chroma_lock_ctx():
            with log_lock:
                execution_log.append(("enter", thread_id, threading.get_ident()))
            # Simulate ChromaDB native call (blocking)
            import time
            time.sleep(0.05)
            with log_lock:
                execution_log.append(("exit", thread_id, threading.get_ident()))

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(fake_chropa_operation, i) for i in range(5)]
        concurrent.futures.wait(futures)

    # Verify serialization: at any point in time, only one operation should be active
    active = 0
    max_active = 0
    for action, _, _ in execution_log:
        if action == "enter":
            active += 1
            max_active = max(max_active, active)
        else:
            active -= 1

    assert active == 0, f"Not all operations exited. Active: {active}"
    assert max_active == 1, (
        f"Operations were not serialized — max simultaneous: {max_active}. "
        f"Execution log: {execution_log}"
    )


def test_no_with_chroma_lock_imports():
    """
    Static check: no file in src/ should import with_chroma_lock —
    it no longer exists. The async lock pattern is the root cause.
    """
    from pathlib import Path
    import ast

    project_root = Path(__file__).resolve().parents[2]

    violations = []
    for py_file in (project_root / "src").rglob("*.py"):
        try:
            tree = ast.parse(py_file.read_text())
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    if alias.name == "with_chroma_lock":
                        violations.append(str(py_file))

    assert not violations, (
        f"Files still importing removed function with_chroma_lock: {violations}. "
        "All Chroma calls must use _chroma_*_safe wrappers instead."
    )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
