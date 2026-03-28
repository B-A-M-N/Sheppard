"""
Archivist index management using injected ChromaSemanticStore.

This module provides Chroma operations for Archivist's research collection
without direct client creation.
"""
from typing import Sequence
from src.memory.storage_adapter import ChromaSemanticStore
import hashlib

_chroma_store: ChromaSemanticStore | None = None


def init(chroma_store: ChromaSemanticStore) -> None:
    """Initialize the Archivist index with a shared ChromaSemanticStore."""
    global _chroma_store
    _chroma_store = chroma_store


def _get_store() -> ChromaSemanticStore:
    """Get the initialized ChromaSemanticStore, raising if not set."""
    if _chroma_store is None:
        raise RuntimeError("Archivist index not initialized. Call init() first.")
    return _chroma_store


async def clear_index(collection_name: str = "archivist_research") -> None:
    """Deletes the collection to clear all previous data."""
    store = _get_store()
    await store.clear_collection(collection_name)


async def add_chunks(
    chunks: list[str],
    embeddings: list[list[float]],
    metadatas: list[dict],
    collection_name: str = "archivist_research"
) -> None:
    """
    Add chunks with their embeddings and metadata to the index.
    Uses hash of text as ID to prevent duplicates.
    """
    store = _get_store()
    ids = [hashlib.md5(c.encode()).hexdigest() for c in chunks]
    rows = [(id, chunk, meta) for id, chunk, meta in zip(ids, chunks, metadatas)]
    await store.index_documents(collection_name, rows, embeddings=embeddings)
