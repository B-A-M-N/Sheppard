"""
Embedding registry — tracks which embedding model/version produced which vectors.
Source of truth for rebuild decisions. NOT stored in Chroma metadata.
"""
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class EmbeddingRegistry:
    def __init__(self, pg_adapter, embed_model: str, embed_host: str, embed_dim: int):
        self.pg = pg_adapter
        self.embed_model = embed_model
        self.embed_host = embed_host
        self.embed_dim = embed_dim

    async def write_entry(self, source_id: str, content_hash: str,
                          chroma_doc_id: str, collection: str = "knowledge_atoms") -> None:
        """Record a successful embedding."""
        await self.pg.insert_row("audit.embedding_registry", {
            "source_id": source_id,
            "content_hash": content_hash,
            "embedding_model": self.embed_model,
            "embedding_version": "v1",
            "embed_host": self.embed_host,
            "embed_dim": self.embed_dim,
            "chroma_doc_id": chroma_doc_id,
            "chroma_collection": collection,
            "status": "active",
        })

    async def is_stale(self, source_id: str, content_hash: str) -> bool:
        """Check if an embedding is stale (model mismatch)."""
        row = await self.pg.fetch_one("audit.embedding_registry", {
            "source_id": source_id,
            "content_hash": content_hash,
        })
        if not row:
            return True  # Never embedded
        return row["embedding_model"] != self.embed_model

    async def mark_all_stale(self) -> int:
        """Mark all embeddings from a different model as stale. Returns count."""
        conn = await self.pg.pool.acquire()
        try:
            result = await conn.execute(
                "UPDATE audit.embedding_registry SET status = 'stale' WHERE embedding_model != $1",
                self.embed_model
            )
            count = int(result.split()[-1]) if result else 0
            logger.warning(f"[EmbeddingRegistry] Marked {count} embeddings as stale")
            return count
        finally:
            await self.pg.pool.release(conn)

    async def on_startup_verify(self) -> bool:
        """Compare current model config against registry. Returns False if mismatch."""
        rows = await self.pg.fetch_many(
            "audit.embedding_registry",
            where={},
            limit=1,
        )
        if not rows:
            return True  # No prior embeddings — fresh install

        latest = rows[0]
        if latest["embedding_model"] != self.embed_model:
            logger.warning(
                f"[EmbeddingRegistry] Model changed: {latest['embedding_model']} -> {self.embed_model}. "
                f"Marking existing embeddings as stale."
            )
            await self.mark_all_stale()
            return False
        return True
