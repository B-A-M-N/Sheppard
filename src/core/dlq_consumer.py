"""
DLQ Consumer — background worker that re-processes failed extraction/condensation stages.
Reads from audit.dead_letter_queue, re-enqueues URLs for re-scraping.
"""
import asyncio
import json
import logging
import os

logger = logging.getLogger(__name__)

POLL_INTERVAL = int(os.environ.get("DLQ_POLL_INTERVAL", "60"))
MAX_BATCH_SIZE = 10


class DLQConsumer:
    def __init__(self, pg_adapter, redis_adapter):
        self.pg = pg_adapter
        self.redis = redis_adapter
        self._running = False

    async def run(self):
        """Main consumer loop."""
        self._running = True
        logger.info("[DLQ] Consumer started")

        while self._running:
            try:
                processed = await self._process_batch()
                if processed == 0:
                    await asyncio.sleep(POLL_INTERVAL)
                else:
                    await asyncio.sleep(5)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[DLQ] Consumer error: {e}")
                await asyncio.sleep(POLL_INTERVAL)

        logger.info("[DLQ] Consumer stopped")

    async def _process_batch(self) -> int:
        """Process one batch of pending DLQ entries. Returns count processed."""
        try:
            entries = await self.pg.fetch_many(
                "audit.dead_letter_queue",
                where={"status": "pending"},
                limit=MAX_BATCH_SIZE,
            )
        except Exception as e:
            logger.debug(f"[DLQ] Table not ready: {e}")
            return 0
        if not entries:
            return 0

        processed = 0
        for entry in entries:
            entry_id = entry["id"]
            stage = entry.get("stage", "")
            retry_count = entry.get("retry_count", 0)
            max_retries = entry.get("max_retries", 3)
            payload = json.loads(entry.get("payload", "{}"))
            source_id = entry.get("source_id", "")

            if retry_count >= max_retries:
                await self.pg.update_row(
                    "audit.dead_letter_queue", "id",
                    {"id": entry_id, "status": "abandoned", "retry_count": retry_count},
                )
                logger.warning(f"[DLQ] Abandoned {stage} failure for {source_id} "
                              f"(attempt {retry_count}/{max_retries})")
            elif stage == "extraction":
                url = payload.get("url", "")
                mission_id = payload.get("mission_id", "")
                if url and mission_id:
                    await self.redis.enqueue_job("queue:scraping", {
                        "url": url,
                        "mission_id": mission_id,
                        "topic_id": payload.get("topic_id", mission_id),
                        "url_hash": payload.get("url_hash", ""),
                        "retry_count": retry_count + 1,
                    })
                    await self.pg.update_row(
                        "audit.dead_letter_queue", "id",
                        {"id": entry_id, "status": "retrying", "retry_count": retry_count + 1},
                    )
                    logger.info(f"[DLQ] Re-enqueued {url} for scraping "
                               f"(attempt {retry_count + 1}/{max_retries})")
                    processed += 1
                else:
                    logger.warning(f"[DLQ] Skipping extraction retry — missing URL or mission_id")
                    await self.pg.update_row(
                        "audit.dead_letter_queue", "id",
                        {"id": entry_id, "status": "abandoned", "retry_count": retry_count},
                    )
            elif stage == "condensation":
                await self.pg.update_row(
                    "audit.dead_letter_queue", "id",
                    {"id": entry_id, "status": "abandoned", "retry_count": retry_count + 1},
                )
                logger.info(f"[DLQ] Condensation failure for {source_id} — "
                           f"re-run condensation pipeline manually (attempt {retry_count + 1}/{max_retries})")
                processed += 1
            else:
                logger.warning(f"[DLQ] Unknown stage '{stage}' for entry {entry_id}")
                processed += 1

        return processed

    def stop(self):
        self._running = False
