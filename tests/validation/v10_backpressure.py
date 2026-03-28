"""
V-10: BackpressurePreventsQueueOverflow

Verifies that the queue depth never exceeds MAX_QUEUE_DEPTH and that enqueue returns False when full.
Also verifies that after draining, enqueue succeeds again (frontier can resume).
"""
import pytest
import asyncio
import types
import json
from src.memory.adapters.redis import RedisStoresImpl
from src.research.acquisition.crawler import FirecrawlLocalClient, CrawlerConfig

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

@pytest.mark.asyncio
async def test_v10_backpressure_crawler_integration(monkeypatch):
    """
    Integration test: Verify that FirecrawlLocalClient.discover_and_enqueue respects backpressure.
    When the Redis queue reaches MAX_QUEUE_DEPTH, further enqueues are rejected, the backpressure_triggered
    flag stops further URL processing, and total_enqueued does not exceed the limit.

    This test uses a single page with 10 URLs. With MAX_QUEUE_DEPTH=5, we expect exactly 5 enqueues,
    proving that backpressure cuts off mid-page and the remaining URLs are never enqueued.
    """
    # Set a small MAX_QUEUE_DEPTH for the test
    import src.memory.adapters.redis as redis_mod
    monkeypatch.setattr(redis_mod, "MAX_QUEUE_DEPTH", 5, raising=False)

    # Fake Redis that tracks queue length
    fake_redis = FakeRedisClient()
    redis_store = RedisStoresImpl(fake_redis)

    # Mock adapter that uses our redis_store.enqueue_job
    class MockAdapter:
        def __init__(self):
            self.redis_queue = redis_store
        async def enqueue_job(self, queue_name: str, payload: dict) -> bool:
            return await self.redis_queue.enqueue_job(queue_name, payload)

    # Mock system_manager with adapter
    mock_sm = types.SimpleNamespace(adapter=MockAdapter())
    # Patch the module-level system_manager in crawler module
    monkeypatch.setattr("src.research.acquisition.crawler.system_manager", mock_sm)

    # Create FirecrawlLocalClient with academic_only=False (doesn't matter)
    client = FirecrawlLocalClient(
        config=CrawlerConfig(),
        on_bytes_crawled=lambda x: None,
        academic_only=False
    )

    # Mock _search: page 1 returns 10 URLs; page 2+ return none
    # This ensures we test that backpressure stops mids-page.
    async def mock_search(query, pageno):
        if pageno == 1:
            return [f"https://example.com/page1-{i}" for i in range(10)]
        return []  # no further pages
    monkeypatch.setattr(client, "_search", mock_search)

    # Call discover_and_enqueue with empty visited set
    total_enqueued = await client.discover_and_enqueue(
        topic_id="test",
        topic_name="Test",
        query="test query",
        mission_id="test-mission-backpressure",
        visited_urls=set()
    )

    # With MAX_QUEUE_DEPTH=5, we expect exactly 5 enqueues before backpressure stops
    assert total_enqueued == 5, f"Expected 5 enqueued due to backpressure, got {total_enqueued}"
    assert len(fake_redis.queue) == 5

    # Verify that all enqueued payloads are unique (no duplicates)
    urls = [json.loads(payload)["url"] for payload in fake_redis.queue]
    assert len(set(urls)) == len(urls), "Enqueued URLs should be unique"

    # Explicitly prove backpressure rejected remaining URLs:
    # The first page had 10 URLs, but only 5 were enqueued.
    # The remaining 5 (indices 5-9) must not appear in the enqueued list.
    enqueued_set = set(urls)
    rejected_urls = [f"https://example.com/page1-{i}" for i in range(5, 10)]
    for rurl in rejected_urls:
        assert rurl not in enqueued_set, f"URL {rurl} should have been rejected due to backpressure, but was enqueued"

