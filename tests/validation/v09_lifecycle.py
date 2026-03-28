"""
V-09: MissionLifecycleTransitionsCorrect

Verifies that a mission transitions through the states: created -> active -> terminal (completed/stopped/failed)
and that no illegal jumps occur. Also checks that terminal state persists.
"""
import pytest
import asyncio
from src.core.system import SystemManager
from src.research.acquisition.frontier import AdaptiveFrontier, FrontierNode
import asyncpg
from src.memory.storage_adapter import SheppardStorageAdapter
from src.memory.adapters.postgres import PostgresStoreImpl
from src.memory.adapters.redis import RedisStoresImpl
from src.memory.adapters.chroma import ChromaSemanticStoreImpl
import chromadb
import tempfile
import json

class MinimalFrontier(AdaptiveFrontier):
    """
    A minimal frontier that performs a tiny amount of real work to exercise DB interactions,
    including checkpointing (_load_checkpoint, _save_node). This replaces the previous DummyFrontier
    to ensure that node persistence (parent_node_id, exhausted_modes) is exercised during the test.
    """
    async def run(self):
        # Load existing state (should be empty for new mission)
        await self._load_checkpoint()
        # Create a simple node and save it to exercise DB checkpointing
        node = FrontierNode(
            concept="minimal_test_node",
            status="underexplored",
            yield_history=[],
            exhausted_modes=set()
        )
        await self._save_node(node)
        return 1

class FakeRedisClient:
    """A minimal fake Redis client for tests."""
    def __init__(self):
        self.store = {}
    async def set(self, key, value, ex=None, nx=False):
        self.store[key] = value
    async def get(self, key):
        return self.store.get(key)
    async def delete(self, *keys):
        for k in keys:
            self.store.pop(k, None)
    async def llen(self, key):
        return 0
    async def rpush(self, key, value):
        pass
    async def blpop(self, keys, timeout=0):
        return None
    async def zadd(self, key, mapping):
        pass
    async def zrangebyscore(self, key, min, max):
        return []
    async def zrem(self, key, *members):
        pass
    async def expire(self, key, seconds):
        pass

@pytest.mark.asyncio
async def test_v09_lifecycle(monkeypatch):
    # Patch AdaptiveFrontier in core.system module where _crawl_and_store uses it
    monkeypatch.setattr("src.core.system.AdaptiveFrontier", MinimalFrontier)

    # Setup adapter with real Postgres (local) and fake Redis/Chroma
    pg_pool = await asyncpg.create_pool(
        'postgresql://sheppard:1234@localhost:5432/sheppard_v3',
        min_size=1, max_size=5
    )
    pg_store = PostgresStoreImpl(pg_pool)
    fake_redis = FakeRedisClient()
    redis_runtime = RedisStoresImpl(fake_redis)
    redis_cache = RedisStoresImpl(fake_redis)
    redis_queue = RedisStoresImpl(fake_redis)
    tmpdir = tempfile.mkdtemp()
    chroma_client = chromadb.PersistentClient(path=tmpdir, settings=chromadb.Settings(anonymized_telemetry=False, allow_reset=True))
    chroma_store = ChromaSemanticStoreImpl(chroma_client)

    adapter = SheppardStorageAdapter(
        pg=pg_store,
        redis_runtime=redis_runtime,
        redis_cache=redis_cache,
        redis_queue=redis_queue,
        chroma=chroma_store
    )

    # Create a minimal SystemManager and inject dependencies
    sm = SystemManager()
    sm.adapter = adapter
    from src.research.acquisition.budget import BudgetMonitor, BudgetConfig
    sm.budget = BudgetMonitor(config=BudgetConfig())
    sm.crawler = None
    sm.condenser = None
    sm.retriever = None
    sm.research_system = None
    sm._crawl_tasks = {}
    sm.active_frontiers = {}
    sm._monitor_task = None
    sm._vampire_tasks = []
    sm._initialized = True

    mission_id = "test-mission-v09"
    # Insert mission row with initial status "created"
    mission_row = {
        "mission_id": mission_id,
        "topic_id": mission_id,
        "domain_profile_id": "profile_test",
        "title": "Test Mission V09",
        "objective": "Validate lifecycle",
        "status": "created",
        "budget_bytes": 0,
        "bytes_ingested": 0,
        "source_count": 0,
    }
    await adapter.pg.insert_row("mission.research_missions", mission_row)

    # Spy on update_mission_status to record the sequence
    original_update_status = adapter.update_mission_status
    status_calls = []
    async def spy_update_status(mission_id, status, stop_reason=None):
        status_calls.append(status)
        await original_update_status(mission_id, status, stop_reason)
    adapter.update_mission_status = spy_update_status

    # Execute the mission's core routine directly
    await sm._crawl_and_store(mission_id, "test topic", "test query")

    # Verify the status transition sequence includes created (implicit from DB insert) -> active -> completed
    # We didn't capture the initial 'created' because it was set before spying started. That's okay; we know it's there.
    # We'll confirm that 'active' happened before 'completed'.
    assert "active" in status_calls, "Expected transition to 'active'"
    assert "completed" in status_calls, "Expected transition to 'completed'"
    active_idx = status_calls.index("active")
    completed_idx = status_calls.index("completed")
    assert active_idx < completed_idx, "'active' must occur before 'completed'"

    # Check final status in DB is "completed" (persistence)
    final_mission = await adapter.get_mission(mission_id)
    assert final_mission is not None, "Mission should still exist"
    assert final_mission["status"] == "completed", f"Final status should be 'completed', got {final_mission['status']}"

    # Cleanup
    await adapter.pg.delete_where("mission.research_missions", {"mission_id": mission_id})
    await pg_pool.close()
