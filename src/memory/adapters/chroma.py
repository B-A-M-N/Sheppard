"""
memory/adapters/chroma.py
Concrete ChromaDB semantic backend implementation.
"""
import asyncio
from typing import Any, Dict, Sequence, List, Optional
import chromadb
from src.memory.storage_adapter import SearchHit
from src.memory.chroma_process_lock import with_chroma_lock

JsonDict = dict[str, Any]

class ChromaSemanticStoreImpl:
    def __init__(self, client: chromadb.ClientAPI):
        self.client = client
        self._collections = {}
        # Note: using global process-wide lock instead of per-instance asyncio.Lock()

    async def _get_collection(self, name: str):
        """Get or create collection (caller must hold lock)."""
        if name not in self._collections:
            self._collections[name] = await asyncio.to_thread(
                self.client.get_or_create_collection, name=name
            )
        return self._collections[name]

    async def index_document(self, collection: str, object_id: str, document: str, metadata: JsonDict, embedding: list[float] | None = None) -> None:
        async with with_chroma_lock():
            coll = await self._get_collection(collection)
            if embedding is not None:
                await asyncio.to_thread(
                    coll.upsert,
                    ids=[object_id],
                    documents=[document],
                    metadatas=[metadata],
                    embeddings=[embedding]
                )
            else:
                await asyncio.to_thread(
                    coll.upsert,
                    ids=[object_id],
                    documents=[document],
                    metadatas=[metadata]
                )

    async def index_documents(self, collection: str, rows: Sequence[tuple[str, str, JsonDict]], embeddings: list[list[float]] | None = None) -> None:
        if not rows:
            return
        async with with_chroma_lock():
            coll = await self._get_collection(collection)
            ids = [r[0] for r in rows]
            docs = [r[1] for r in rows]
            metas = [r[2] for r in rows]
            kwargs: Dict[str, Any] = {"ids": ids, "documents": docs, "metadatas": metas}
            if embeddings is not None:
                if len(embeddings) != len(rows):
                    raise ValueError("embeddings length must match rows")
                kwargs["embeddings"] = embeddings
            await asyncio.to_thread(coll.upsert, **kwargs)

    async def search(self, collection: str, query_text: str, where: Optional[JsonDict] = None, limit: int = 20) -> list[SearchHit]:
        async with with_chroma_lock():
            coll = await self._get_collection(collection)
            kwargs: Dict[str, Any] = {
                "query_texts": [query_text],
                "n_results": limit
            }
            if where:
                kwargs["where"] = where

            results = await asyncio.to_thread(coll.query, **kwargs)

            hits: list[SearchHit] = []
            if results and results.get('ids') and results['ids'][0]:
                ids = results['ids'][0]
                distances = results.get('distances', [[0.0] * len(ids)])[0]
                metadatas = results.get('metadatas', [[{}] * len(ids)])[0]

                for doc_id, dist, meta in zip(ids, distances, metadatas):
                    # Cosine distance to relevance score
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
            # Batch query
            if not isinstance(query_texts, list) or not query_texts:
                raise ValueError("query_texts must be a non-empty list of strings")
            query_mode = "batch"
        elif query_text is not None:
            query_mode = "single"
        elif query_embeddings is not None:
            query_mode = "embedding"
        else:
            raise ValueError("Must provide either query_text, query_texts, or query_embeddings")

        async with with_chroma_lock():
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

            results = await asyncio.to_thread(coll.query, **kwargs)
            return results

    async def delete_document(self, collection: str, object_id: str) -> None:
        async with with_chroma_lock():
            coll = await self._get_collection(collection)
            await asyncio.to_thread(coll.delete, ids=[object_id])

    async def clear_collection(self, name: str) -> None:
        """Delete the entire collection. Ignores error if it doesn't exist."""
        async with with_chroma_lock():
            try:
                await asyncio.to_thread(self.client.delete_collection, name)
            except Exception:
                pass  # Collection may not exist
            if name in self._collections:
                del self._collections[name]
