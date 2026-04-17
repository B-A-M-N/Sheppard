import pytest

from src.core.dlq_consumer import DLQConsumer


class FakePG:
    def __init__(self, entries):
        self.entries = entries
        self.updates = []

    async def fetch_many(self, _table, where=None, limit=None):
        return self.entries

    async def update_row(self, table, key_field, payload):
        self.updates.append((table, key_field, payload))


class FakeRedis:
    def __init__(self):
        self.calls = []

    async def enqueue_job(self, queue_name, payload):
        self.calls.append((queue_name, payload))
        return True


@pytest.mark.asyncio
async def test_dlq_extraction_retry_uses_enqueue_job():
    pg = FakePG([
        {
            "id": 1,
            "stage": "extraction",
            "retry_count": 0,
            "max_retries": 3,
            "payload": '{"url": "https://example.com/a", "mission_id": "m1", "topic_id": "t1", "url_hash": "abc"}',
            "source_id": "source-1",
        }
    ])
    redis = FakeRedis()
    consumer = DLQConsumer(pg, redis)

    processed = await consumer._process_batch()

    assert processed == 1
    assert redis.calls == [
        (
            "queue:scraping",
            {
                "url": "https://example.com/a",
                "mission_id": "m1",
                "topic_id": "t1",
                "url_hash": "abc",
                "retry_count": 1,
            },
        )
    ]
    assert pg.updates == [
        (
            "audit.dead_letter_queue",
            "id",
            {"id": 1, "status": "retrying", "retry_count": 1},
        )
    ]
