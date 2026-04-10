"""
memory/adapters/redis.py
Concrete Redis backend implementation.
"""
import json
import logging
import time
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Optional
import redis.asyncio as redis
from src.memory.storage_adapter import LockHandle

logger = logging.getLogger(__name__)
JsonDict = dict[str, Any]

# Queue backpressure configuration
MAX_QUEUE_DEPTH = 10000

class RedisStoresImpl:
    """
    Implements RedisRuntimeStore, RedisCacheStore, and RedisQueueStore.
    """
    def __init__(self, client: redis.Redis):
        self.client = client

    def _serialize(self, payload: JsonDict) -> str:
        def default(obj):
            if isinstance(obj, datetime):
                return obj.isoformat()
            raise TypeError(f"Object of type {obj.__class__.__name__} is not JSON serializable")
        return json.dumps(payload, default=default)

    # RuntimeStore
    async def acquire_lock(self, key: str, ttl_s: int) -> LockHandle | None:
        token = str(time.time())
        acquired = await self.client.set(key, token, ex=ttl_s, nx=True)
        if acquired:
            expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl_s)
            return LockHandle(key=key, token=token, expires_at=expires_at)
        return None

    async def refresh_lock(self, handle: LockHandle, ttl_s: int) -> LockHandle | None:
        current = await self.client.get(handle.key)
        if current and current.decode('utf-8') == handle.token:
            await self.client.expire(handle.key, ttl_s)
            handle.expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl_s)
            return handle
        return None

    async def release_lock(self, handle: LockHandle) -> None:
        current = await self.client.get(handle.key)
        if current and current.decode('utf-8') == handle.token:
            await self.client.delete(handle.key)

    async def set_active_state(self, key: str, payload: JsonDict, ttl_s: int | None = None) -> None:
        serialized = self._serialize(payload)
        if ttl_s:
            await self.client.set(key, serialized, ex=ttl_s)
        else:
            await self.client.set(key, serialized)

    async def get_active_state(self, key: str) -> JsonDict | None:
        data = await self.client.get(key)
        if data:
            return json.loads(data)
        return None

    async def delete_active_state(self, key: str) -> None:
        await self.client.delete(key)

    # CacheStore
    async def cache_hot_object(self, kind: str, object_id: str, payload: JsonDict, ttl_s: int) -> None:
        key = f"{kind}:hot:{object_id}"
        await self.client.set(key, self._serialize(payload), ex=ttl_s)

    async def get_hot_object(self, kind: str, object_id: str) -> JsonDict | None:
        key = f"{kind}:hot:{object_id}"
        data = await self.client.get(key)
        if data:
            return json.loads(data)
        return None

    async def invalidate_hot_object(self, kind: str, object_id: str) -> None:
        key = f"{kind}:hot:{object_id}"
        await self.client.delete(key)

    # QueueStore
    async def enqueue_job(self, queue_name: str, payload: JsonDict) -> bool:
        depth = await self.client.llen(queue_name)
        if depth >= MAX_QUEUE_DEPTH:
            logger.warning(f"Queue depth {depth} exceeds limit {MAX_QUEUE_DEPTH} — rejecting job")
            return False
        await self.client.rpush(queue_name, self._serialize(payload))
        return True

    async def get_queue_depth(self, queue_name: str) -> int:
        return await self.client.llen(queue_name)

    async def dequeue_job(self, queue_name: str, timeout_s: int = 0) -> JsonDict | None:
        result = await self.client.blpop(queue_name, timeout=timeout_s)
        if result:
            return json.loads(result[1])
        return None

    async def schedule_retry(self, queue_name: str, payload: JsonDict, when_epoch_s: int) -> None:
        retry_key = f"retry:{queue_name}"
        await self.client.zadd(retry_key, {self._serialize(payload): when_epoch_s})

    async def move_due_retries(self, queue_name: str, now_epoch_s: int) -> int:
        retry_key = f"retry:{queue_name}"
        due_items = await self.client.zrangebyscore(retry_key, 0, now_epoch_s)
        count = 0
        for item in due_items:
            await self.client.rpush(queue_name, item)
            await self.client.zrem(retry_key, item)
            count += 1
        return count

    # Discovery Entity Storage — feeds entities back into Frontier for expansion
    async def store_discovery_entities(self, mission_id: str, entities: list[str]) -> None:
        """Store extracted entities as a Redis set for Frontier to consume."""
        entity_key = f"discovery:entities:{mission_id}"
        # Add all entities to a Redis set (auto-deduplicates)
        if entities:
            await self.client.sadd(entity_key, *entities)
            # Set TTL to 7 days to prevent stale entity buildup
            await self.client.expire(entity_key, 7 * 24 * 3600)

    async def get_discovery_entities(self, mission_id: str) -> list[str]:
        """Retrieve stored entities for a mission — used by Frontier for query expansion."""
        entity_key = f"discovery:entities:{mission_id}"
        raw = await self.client.smembers(entity_key)
        return [e.decode('utf-8') if isinstance(e, bytes) else e for e in raw]
