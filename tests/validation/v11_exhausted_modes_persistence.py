"""
V-11: ExhaustedModesSurviveRestart

Verifies that exhausted_modes (epistemic mode history) are correctly persisted to the database
and restored when a frontier is restarted (checkpoint/load cycle).
"""
import pytest
import asyncio
import json
import asyncpg
from src.memory.storage_adapter import SheppardStorageAdapter
from src.memory.adapters.postgres import PostgresStoreImpl
from src.memory.adapters.redis import RedisStoresImpl
from src.memory.adapters.chroma import ChromaSemanticStoreImpl
from src.core.system import SystemManager
from src.research.acquisition.budget import BudgetMonitor, BudgetConfig
from src.research.acquisition.frontier import AdaptiveFrontier, FrontierNode
import chromadb
import tempfile

class FakeRedisClient:
    """Minimal fake Redis for tests."""
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
async def test_v11_exhausted_modes_persistence():
    """Test that exhausted_modes are saved to DB and restored on frontier restart."""

    # Setup adapter with real Postgres and fake Redis/Chroma
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
    chroma_client = chromadb.PersistentClient(
        path=tmpdir,
        settings=chromadb.Settings(anonymized_telemetry=False, allow_reset=True)
    )
    chroma_store = ChromaSemanticStoreImpl(chroma_client)

    adapter = SheppardStorageAdapter(
        pg=pg_store,
        redis_runtime=redis_runtime,
        redis_cache=redis_cache,
        redis_queue=redis_queue,
        chroma=chroma_store
    )

    # Create SystemManager
    sm = SystemManager()
    sm.adapter = adapter
    sm.budget = BudgetMonitor(config=BudgetConfig())
    sm.initialized = True

    mission_id = "test-mission-v11"

    # Cleanup any previous run data (idempotent test start)
    try:
        await adapter.pg.delete_where("mission.mission_nodes", {"mission_id": mission_id})
        await adapter.pg.delete_where("mission.research_missions", {"mission_id": mission_id})
        await adapter.pg.delete_where("mission.domain_profiles", {"domain_profile_id": "profile_test"})
    except Exception:
        pass  # Ignore if tables don't exist or rows absent

    # Insert domain_profiles row required by FK constraint
    try:
        await adapter.pg.insert_row("mission.domain_profiles", {
            "domain_profile_id": "profile_test",
            "topic_id": mission_id,
            "profile_name": "Test Profile V11",
        })
    except Exception:
        pass  # Row may already exist

    # Insert mission row
    mission_row = {
        "mission_id": mission_id,
        "topic_id": mission_id,
        "domain_profile_id": "profile_test",
        "title": "Test V11 Persistence",
        "objective": "Verify exhausted_modes survive restart",
        "status": "created",
        "budget_bytes": 0,
        "bytes_ingested": 0,
        "source_count": 0,
    }
    await adapter.pg.insert_row("mission.research_missions", mission_row)

    # Create first frontier instance
    frontier = AdaptiveFrontier(sm, mission_id, "test topic")

    # Create a FrontierNode with specific exhausted_modes
    test_concept = "test_node_v11"
    node = FrontierNode(
        concept=test_concept,
        status="underexplored",
        yield_history=[],
        exhausted_modes={"GROUNDING", "EXPANSION"}
    )

    # Save the node to checkpoint
    await frontier._save_node(node)

    # Verify database row contains the correct exhausted_modes_json
    rows = await adapter.pg.fetch_many(
        "mission.mission_nodes",
        where={"mission_id": mission_id, "label": test_concept}
    )
    assert len(rows) == 1, "Node row should exist in DB"
    db_exhausted_raw = rows[0]['exhausted_modes_json']
    # JSONB may return directly as list, or as string; normalize
    if isinstance(db_exhausted_raw, str):
        db_exhausted = set(json.loads(db_exhausted_raw))
    else:
        db_exhausted = set(db_exhausted_raw)
    assert db_exhausted == {"GROUNDING", "EXPANSION"}, f"DB exhausted_modes mismatch: {db_exhausted}"

    # Simulate restart: create new frontier with same mission_id
    frontier2 = AdaptiveFrontier(sm, mission_id, "test topic")
    # Load checkpoint from DB
    await frontier2._load_checkpoint()

    # Verify that the loaded node has the same exhausted_modes
    assert test_concept in frontier2.nodes, "Node should be loaded into frontier2"
    loaded_node = frontier2.nodes[test_concept]
    assert loaded_node.exhausted_modes == {"GROUNDING", "EXPANSION"}, f"Loaded exhausted_modes mismatch: {loaded_node.exhausted_modes}"

    # Cleanup: remove test data
    await adapter.pg.delete_where("mission.mission_nodes", {"mission_id": mission_id})
    await adapter.pg.delete_where("mission.research_missions", {"mission_id": mission_id})
    try:
        await adapter.pg.delete_where("mission.domain_profiles", {"domain_profile_id": "profile_test"})
    except Exception:
        pass
    await pg_pool.close()
