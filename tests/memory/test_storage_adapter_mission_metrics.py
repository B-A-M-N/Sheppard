from types import SimpleNamespace

import pytest

from src.memory.storage_adapter import SheppardStorageAdapter


class FakePG:
    def __init__(self):
        self.rows = {
            "mission.research_missions": {
                "mission-1": {
                    "mission_id": "mission-1",
                    "status": "active",
                    "bytes_ingested": 100,
                    "source_count": 2,
                }
            }
        }

    async def fetch_one(self, table, where):
        if table != "mission.research_missions":
            return None
        return dict(self.rows[table][where["mission_id"]])

    async def upsert_row(self, table, key, row):
        self.rows[table][row["mission_id"]] = dict(row)


class FakeRedisRuntime:
    def __init__(self):
        self.states = {}

    async def set_active_state(self, key, value, ttl_s=None):
        self.states[key] = value


@pytest.mark.asyncio
async def test_increment_mission_ingestion_stats_updates_db_and_runtime_cache():
    pg = FakePG()
    redis_runtime = FakeRedisRuntime()
    adapter = SheppardStorageAdapter(
        pg=pg,
        redis_runtime=redis_runtime,
        redis_cache=SimpleNamespace(),
        redis_queue=SimpleNamespace(),
        chroma=SimpleNamespace(),
    )

    await adapter._increment_mission_ingestion_stats("mission-1", 250)

    row = pg.rows["mission.research_missions"]["mission-1"]
    assert row["bytes_ingested"] == 350
    assert row["source_count"] == 3
    assert redis_runtime.states["mission:active:mission-1"]["bytes_ingested"] == 350
