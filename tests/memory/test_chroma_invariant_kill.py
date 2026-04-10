"""
Kill tests for ChromaDB concurrency invariant.

These tests verify that the bypass paths identified in 12-G are eliminated:
- VectorStoreManager removed (dead code that created its own client and used per-layer locks)
- CleanupManager does not instantiate StorageManager (which could trigger bypass)
- StorageManager does not create its own PersistentClient
"""

import pytest
from pathlib import Path


def test_cleanup_manager_uses_adapter_not_storage_manager():
    """
    KILL TEST: CleanupManager must not instantiate StorageManager.

    BEFORE FIX: CleanupManager created StorageManager() -> bypass path
    AFTER FIX: CleanupManager accepts injected chroma_store and does not create StorageManager.
    """
    cleanup_path = Path(__file__).resolve().parents[2] / "src" / "core" / "memory" / "cleanup.py"
    with open(cleanup_path, 'r') as f:
        content = f.read()

    assert 'StorageManager()' not in content, (
        "CleanupManager must not instantiate StorageManager."
    )
    assert 'chroma_store' in content, (
        "CleanupManager should accept a chroma_store parameter for dependency injection."
    )


def test_storage_manager_does_not_create_chroma_client():
    """
    KILL TEST: StorageManager should not create its own PersistentClient or
    directly use Chroma collections.

    StorageManager is legacy V2 code. If it remains, it must not instantiate
    chromadb.PersistentClient.
    """
    sm_path = Path(__file__).resolve().parents[2] / "src" / "core" / "memory" / "storage" / "storage_manager.py"
    with open(sm_path, 'r') as f:
        content = f.read()

    # Should NOT create PersistentClient
    if 'chromadb.PersistentClient' in content:
        pytest.fail(
            "StorageManager must not instantiate chromadb.PersistentClient. "
            "StorageManager should not directly use Chroma."
        )


def test_vector_store_manager_removed():
    """
    KILL TEST: VectorStoreManager was identified as a bypass path (created its own
    PersistentClient and used per-layer locks). It is dead code and should be removed.

    AFTER FIX: VectorStoreManager file should not exist.
    """
    vsm_path = Path(__file__).resolve().parents[2] / "src" / "core" / "memory" / "storage" / "vector_store.py"
    assert not vsm_path.exists(), (
        "VectorStoreManager should be removed. It is dead code and violates the single-client invariant."
    )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
