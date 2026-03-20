"""
memory/adapters/chroma.py
Concrete ChromaDB semantic backend implementation.
"""
import asyncio
from typing import Any, Dict, Sequence, List, Optional
import chromadb
from src.memory.storage_adapter import SearchHit

JsonDict = dict[str, Any]

class ChromaSemanticStoreImpl:
    def __init__(self, client: chromadb.ClientAPI):
        self.client = client
        self._collections = {}

    async def _get_collection(self, name: str):
        if name not in self._collections:
            self._collections[name] = await asyncio.to_thread(
                self.client.get_or_create_collection, name=name
            )
        return self._collections[name]

    async def index_document(self, collection: str, object_id: str, document: str, metadata: JsonDict) -> None:
        coll = await self._get_collection(collection)
        await asyncio.to_thread(
            coll.upsert,
            ids=[object_id],
            documents=[document],
            metadatas=[metadata]
        )

    async def index_documents(self, collection: str, rows: Sequence[tuple[str, str, JsonDict]]) -> None:
        if not rows: return
        coll = await self._get_collection(collection)
        ids = [r[0] for r in rows]
        docs = [r[1] for r in rows]
        metas = [r[2] for r in rows]
        await asyncio.to_thread(
            coll.upsert,
            ids=ids,
            documents=docs,
            metadatas=metas
        )

    async def search(self, collection: str, query_text: str, where: Optional[JsonDict] = None, limit: int = 20) -> list[SearchHit]:
        coll = await self._get_collection(collection)
        kwargs = {
            "query_texts": [query_text],
            "n_results": limit
        }
        if where:
            kwargs["where"] = where
            
        results = await asyncio.to_thread(coll.query, **kwargs)
        
        hits = []
        if results and results.get('ids') and results['ids'][0]:
            ids = results['ids'][0]
            distances = results.get('distances', [[0.0] * len(ids)])[0]
            metadatas = results.get('metadatas', [[{}] * len(ids)])[0]
            
            for doc_id, dist, meta in zip(ids, distances, metadatas):
                # Cosine distance to relevance score
                score = 1.0 - dist
                hits.append(SearchHit(object_id=doc_id, score=score, metadata=meta))
                
        return hits

    async def delete_document(self, collection: str, object_id: str) -> None:
        coll = await self._get_collection(collection)
        await asyncio.to_thread(coll.delete, ids=[object_id])
