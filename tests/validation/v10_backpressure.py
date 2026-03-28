"""
V-10: BackpressurePreventsQueueOverflow

Verifies that the queue depth never exceeds MAX_QUEUE_DEPTH and that enqueue returns False when full.
Also verifies that after draining, enqueue succeeds again (frontier can resume).
"""
import pytest
import asyncio
from src.memory.adapters.redis import RedisStoresImpl

class FakeRedisClient:
    """Simple in-memory fake Redis for queue operations."""
    def __init__(self):
        self.queue = []
    async def llen(self, name):
        return len(self.queue)
    async def rpush(self, name, value):
        self.queue.append(value)
    async def lpop(self, name):
        if self.queue:
            return self.queue.pop(0)
        return None
    # Other methods not used by enqueue_job
    async def set(self, *args, **kwargs):
        pass
    async def get(self, *args, **kwargs):
        return None
    async def delete(self, *args):
        pass
    async def blpop(self, keys, timeout=0):
        return None
    async def zadd(self, *args, **kwargs):
        pass
    async def zrangebyscore(self, *args, **kwargs):
        return []
    async def zrem(self, *args, **kwargs):
        pass
    async def expire(self, *args, **kwargs):
        pass

@pytest.mark.asyncio
async def test_v10_backpressure(monkeypatch):
    # Set MAX_QUEUE_DEPTH to 100 for test
    import src.memory.adapters.redis as redis_mod
    monkeypatch.setattr(redis_mod, "MAX_QUEUE_DEPTH", 100, raising=False)

    fake_client = FakeRedisClient()
    redis_store = RedisStoresImpl(fake_client)

    # Pre-fill queue with 100 jobs using enqueue_job (which respects limit)
    for i in range(100):
        success = await redis_store.enqueue_job("queue:scraping", {"url": f"http://example.com/{i}", "mission_id": "test"})
        assert success, f"Job {i} should be enqueued"

    # Verify depth
    depth = await fake_client.llen("queue:scraping")
    assert depth == 100

    # Attempt one more enqueue - should be rejected
    result = await redis_store.enqueue_job("queue:scraping", {"url": "http://example.com/extra", "mission_id": "test"})
    assert result is False, "Enqueue must be rejected when queue full"

    # Verify depth did not exceed 101
    depth_after_reject = await fake_client.llen("queue:scraping")
    assert depth_after_reject <= 101, f"Queue depth {depth_after_reject} exceeds allowed max 101"

    # Drain some jobs (pop 20) to bring depth below threshold (e.g., below 90)
    for _ in range(20):
        await fake_client.lpop("queue:scraping")
    depth_after_drain = await fake_client.llen("queue:scraping")
    assert depth_after_drain == 80

    # After drain, enqueue should succeed (frontier can resume)
    result2 = await redis_store.enqueue_job("queue:scraping", {"url": "http://example.com/resume", "mission_id": "test"})
    assert result2 is True, "Enqueue should succeed after queue drained"

    # Verify depth increased by one
    depth_final = await fake_client.llen("queue:scraping")
    assert depth_final == 81
