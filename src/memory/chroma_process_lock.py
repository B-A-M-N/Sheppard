"""
Process-wide global lock for all ChromaDB operations.

This lock ensures that only ONE thread in the entire process can execute
ChromaDB collection operations (add, upsert, query, delete, etc.) at a time.

This is necessary because:
- ChromaDB's Rust layer (ONNX) is not thread-safe for concurrent access
- asyncio.Lock only protects within the event loop thread, not across ThreadPoolExecutor
- Multiple subsystems (MemoryManager, ChromaMemoryStore, adapters) must share the same guard

Usage:
    from src.memory.chroma_process_lock import with_chroma_lock

    async def some_operation():
        async with with_chroma_lock():
            # Chroma collection operation here
            collection.add(...)
"""

import asyncio
import threading
from contextlib import asynccontextmanager

# A single RLock for the entire process, shared by all Chroma access points
_global_chroma_lock = threading.RLock()


def get_chroma_process_lock() -> threading.RLock:
    """Return the global process-wide Chroma lock."""
    return _global_chroma_lock


@asynccontextmanager
async def with_chroma_lock():
    """
    Async context manager that acquires the global threading lock.
    Safe to use from both async tasks and sync code (via await).
    """
    loop = asyncio.get_event_loop()
    # Run the blocking lock acquisition in a thread to avoid blocking event loop
    await loop.run_in_executor(None, _global_chroma_lock.acquire)
    try:
        yield
    finally:
        _global_chroma_lock.release()


# For synchronous code paths (if any)
def chroma_lock_sync() -> threading.RLock:
    """
    Return the global lock for use in sync context managers.
    Example: with chroma_lock_sync(): ...
    """
    return _global_chroma_lock
