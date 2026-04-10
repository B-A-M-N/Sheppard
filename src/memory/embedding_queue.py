"""
Deferred embedding write queue.
Pattern: PG write succeeds → Chroma attempted → on failure, queue for retry.
Redis = active queue, Postgres = durability backup.
NEVER stores raw vectors in Postgres — regenerates on retry.
"""
import asyncio
import json
import logging
import time

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
BACKOFF_BASE = 1  # seconds
BACKOFF_MAX = 30


class DeferredEmbedQueue:
    def __init__(self, pg_adapter, redis_adapter, ollama_client, chroma_store):
        self.pg = pg_adapter
        self.redis = redis_adapter
        self.ollama = ollama_client
        self.chroma = chroma_store
        self._running = False

    async def enqueue(self, content_hash: str, source_id: str,
                      collection: str, doc_id: str, mission_id: str = "") -> None:
        """Queue a failed Chroma write for retry."""
        payload = {
            "content_hash": content_hash,
            "source_id": source_id,
            "collection": collection,
            "doc_id": doc_id,
            "mission_id": mission_id,
            "enqueued_at": time.time(),
        }

        # Redis active queue
        try:
            await self.redis.rpush("embed:pending", json.dumps(payload))
        except Exception:
            logger.warning("[EmbedQueue] Redis unavailable — using PG-only durability")

        # Postgres durability backup
        await self.pg.insert_row("audit.dead_letter_queue", {
            "source_id": source_id,
            "stage": "embedding",
            "error_class": "ChromaWriteFailure",
            "error_detail": f"Chroma write failed for doc {doc_id}",
            "retry_count": 0,
            "max_retries": MAX_RETRIES,
            "last_seen_worker": "pipeline:condensation",
            "payload": json.dumps(payload),
            "status": "pending",
        })

    async def process_pending(self) -> int:
        """Process one pending item. Returns 1 if processed, 0 if queue empty."""
        # Pop from Redis
        item_json = None
        try:
            item_json = await self.redis.lpop("embed:pending")
        except Exception:
            pass

        if not item_json:
            # Fallback: check PG
            row = await self.pg.fetch_one(
                "audit.dead_letter_queue",
                {"stage": "embedding", "status": "pending"},
            )
            if not row:
                return 0
            item_json = row["payload"]

        try:
            payload = json.loads(item_json)
        except (json.JSONDecodeError, TypeError):
            return 0

        content_hash = payload.get("content_hash", "")
        source_id = payload.get("source_id", "")
        doc_id = payload.get("doc_id", "")
        collection = payload.get("collection", "knowledge_atoms")

        # Regenerate embedding from PG text content
        text_row = await self.pg.fetch_one("corpus.text_refs", {"blob_id": f"blob:{source_id}"})
        if not text_row or not text_row.get("inline_text"):
            logger.error(f"[EmbedQueue] No text found for source {source_id}")
            return 0

        try:
            embedding = await self.ollama.embed(text_row["inline_text"])
            await self.chroma.index_document(doc_id, embedding, collection)
            logger.info(f"[EmbedQueue] Retry succeeded for {doc_id}")
            return 1
        except Exception as e:
            logger.warning(f"[EmbedQueue] Retry failed for {doc_id}: {e}")
            return 0

    async def worker(self):
        """Background worker that processes the pending queue."""
        self._running = True
        backoff = BACKOFF_BASE
        while self._running:
            processed = await self.process_pending()
            if processed:
                backoff = BACKOFF_BASE  # Reset on success
            else:
                backoff = min(backoff * 2, BACKOFF_MAX)
            await asyncio.sleep(backoff)

    def stop(self):
        self._running = False
