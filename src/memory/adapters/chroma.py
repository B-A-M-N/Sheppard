"""
memory/adapters/chroma.py
Concrete ChromaDB semantic backend implementation.

IMPORTANT: All native Chroma calls (coll.upsert, coll.query, coll.delete) are
wrapped in `_chroma_*_safe` functions that acquire the global lock INSIDE the
worker thread. The lock must be acquired in the SAME thread that executes the
native call — acquiring it outside the executor (in the event loop thread) does
NOT protect the worker thread.

See: src/memory/chroma_process_lock.py
"""
import asyncio
from typing import Any, Dict, Sequence, List, Optional
import chromadb
from src.memory.storage_adapter import SearchHit
from src.memory.chroma_process_lock import chroma_lock_ctx

JsonDict = dict[str, Any]


# ── Safe wrappers: lock acquired INSIDE the worker thread ──────────────

def _chroma_upsert_safe(coll, **kwargs):
    """Upsert wrapper — lock held inside executor worker thread."""
    with chroma_lock_ctx():
        return coll.upsert(**kwargs)


def _chroma_query_safe(coll, **kwargs):
    """Query wrapper — lock held inside executor worker thread."""
    with chroma_lock_ctx():
        return coll.query(**kwargs)


def _chroma_delete_safe(coll, **kwargs):
    """Delete wrapper — lock held inside executor worker thread."""
    with chroma_lock_ctx():
        return coll.delete(**kwargs)


def _chroma_get_or_create_safe(client, **kwargs):
    """Get-or-create collection wrapper — lock held inside executor worker."""
    with chroma_lock_ctx():
        return client.get_or_create_collection(**kwargs)


def _chroma_delete_collection_safe(client, name):
    """Delete collection wrapper — lock held inside executor worker."""
    with chroma_lock_ctx():
        return client.delete_collection(name=name)


# ── Adapter implementation ─────────────────────────────────────────────

class ChromaSemanticStoreImpl:
    def __init__(self, client: chromadb.ClientAPI):
        self.client = client
        self._collections = {}

    async def _get_collection(self, name: str):
        """Get or create collection (thread-safe via wrapper)."""
        if name not in self._collections:
            self._collections[name] = await asyncio.to_thread(
                _chroma_get_or_create_safe, self.client, name=name
            )
        return self._collections[name]

    async def index_document(self, collection: str, object_id: str, document: str, metadata: JsonDict, embedding: list[float] | None = None) -> None:
        coll = await self._get_collection(collection)
        kwargs: Dict[str, Any] = {
            "ids": [object_id],
            "documents": [document],
            "metadatas": [metadata]
        }
        if embedding is not None:
            kwargs["embeddings"] = [embedding]
        await asyncio.to_thread(_chroma_upsert_safe, coll, **kwargs)

    async def index_documents(self, collection: str, rows: Sequence[tuple[str, str, JsonDict]], embeddings: list[list[float]] | None = None) -> None:
        if not rows:
            return
        coll = await self._get_collection(collection)
        ids = [r[0] for r in rows]
        docs = [r[1] for r in rows]
        metas = [r[2] for r in rows]
        kwargs: Dict[str, Any] = {"ids": ids, "documents": docs, "metadatas": metas}
        if embeddings is not None:
            if len(embeddings) != len(rows):
                raise ValueError("embeddings length must match rows")
            kwargs["embeddings"] = embeddings
        await asyncio.to_thread(_chroma_upsert_safe, coll, **kwargs)

    async def search(self, collection: str, query_text: str, where: Optional[JsonDict] = None, limit: int = 20) -> list[SearchHit]:
        coll = await self._get_collection(collection)
        kwargs: Dict[str, Any] = {
            "query_texts": [query_text],
            "n_results": limit
        }
        if where:
            kwargs["where"] = where

        results = await asyncio.to_thread(_chroma_query_safe, coll, **kwargs)

        hits: list[SearchHit] = []
        if results and results.get('ids') and results['ids'][0]:
            ids = results['ids'][0]
            distances = results.get('distances', [[0.0] * len(ids)])[0]
            metadatas = results.get('metadatas', [[{}] * len(ids)])[0]

            for doc_id, dist, meta in zip(ids, distances, metadatas):
                score = 1.0 - dist
                hits.append(SearchHit(object_id=doc_id, score=score, metadata=meta))

        return hits

    async def query(self, collection: str, query_text: str | None = None, query_texts: List[str] | None = None, query_embeddings: list[float] | None = None, where: Optional[JsonDict] = None, limit: int = 20) -> Dict:
        """
        Raw query to Chroma collection. Returns full result dict with
        documents, metadatas, distances, ids.

        Supports single query (query_text) or batch (query_texts).
        """
        if query_texts is not None:
            if not isinstance(query_texts, list) or not query_texts:
                raise ValueError("query_texts must be a non-empty list of strings")
            query_mode = "batch"
        elif query_text is not None:
            query_mode = "single"
        elif query_embeddings is not None:
            query_mode = "embedding"
        else:
            raise ValueError("Must provide either query_text, query_texts, or query_embeddings")

        coll = await self._get_collection(collection)
        kwargs: Dict[str, Any] = {
            "n_results": limit
        }
        if query_mode == "batch":
            kwargs["query_texts"] = query_texts
        elif query_mode == "single":
            kwargs["query_texts"] = [query_text]
        else:  # embedding
            kwargs["query_embeddings"] = [query_embeddings]
        if where:
            kwargs["where"] = where

        results = await asyncio.to_thread(_chroma_query_safe, coll, **kwargs)
        return results

    async def delete_document(self, collection: str, object_id: str) -> None:
        coll = await self._get_collection(collection)
        await asyncio.to_thread(_chroma_delete_safe, coll, ids=[object_id])

    async def clear_collection(self, name: str) -> None:
        """Delete the entire collection. Ignores error if it doesn't exist."""
        try:
            await asyncio.to_thread(_chroma_delete_collection_safe, self.client, name)
        except Exception:
            pass  # Collection may not exist
        if name in self._collections:
            del self._collections[name]
