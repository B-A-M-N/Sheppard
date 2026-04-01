"""
Process-wide global lock for all ChromaDB operations.

This lock ensures that only ONE thread in the entire process can execute
ChromaDB collection operations (add, upsert, query, delete, etc.) at a time.

This is necessary because:
- ChromaDB's Rust layer (ONNX) is not thread-safe for concurrent access
- asyncio.Lock only protects within the event loop thread, not across ThreadPoolExecutor
- ONNX Runtime creates its own internal threads — serialization at the app boundary
  is not enough unless ONNX is also single-threaded
- Multiple subsystems (MemoryManager, ChromaMemoryStore, adapters) must share the same guard

Two-prong defense:
1. Global threading.Lock serializes all Chroma/ONNX entry — lock acquired INSIDE worker
2. ONNX forced single-threaded via env vars (set BEFORE any chromadb/import)
"""

import os as _os

# ── Force ONNX Runtime single-threaded (MUST precede any chromadb import)
_onnx_env_overrides = {
    "OMP_NUM_THREADS": "1",
    "MKL_NUM_THREADS": "1",
    "OPENBLAS_NUM_THREADS": "1",
    "NUMEXPR_NUM_THREADS": "1",
    "VECLIB_MAXIMUM_THREADS": "1",
}

for _key, _val in _onnx_env_overrides.items():
    _os.environ.setdefault(_key, _val)

import threading
from contextlib import contextmanager

# A single non-reentrant Lock for the entire process, shared by all Chroma access points.
# Non-reentrant (not RLock): prevents accidental nested acquisition within the same thread.
_global_chroma_lock = threading.Lock()


def get_chroma_process_lock() -> threading.Lock:
    """Return the global process-wide Chroma lock."""
    return _global_chroma_lock


@contextmanager
def chroma_lock_ctx():
    """
    Synchronous context manager for the global lock.
    MUST be used inside executor worker threads that execute Chroma/ONNX calls.
    The lock is acquired INSIDE the worker thread, not outside it.
    """
    _global_chroma_lock.acquire()
    try:
        yield
    finally:
        _global_chroma_lock.release()
