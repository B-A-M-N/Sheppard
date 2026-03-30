"""
Tier 0.1: Cross-Mission Isolation Tests

Verifies that adapter methods enforce mission boundaries.
These are Nyquist validation tests for the mission isolation invariant.
"""

import pytest
from uuid import uuid4
import asyncpg
import tempfile
import chromadb
from src.memory.storage_adapter import SheppardStorageAdapter
from src.memory.adapters.postgres import PostgresStoreImpl
from src.memory.adapters.redis import RedisStoresImpl
from src.memory.adapters.chroma import ChromaSemanticStoreImpl


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


async def make_adapter():
    """Create a real adapter with real Postgres and fake Redis/Chroma."""
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
    return adapter, pg_pool


async def setup_mission(adapter):
    """Create a domain profile and mission for testing."""
    mission_id = str(uuid4())
    profile_id = f"profile_{mission_id[:8]}"

    # Insert domain profile
    profile = {
        "profile_id": profile_id,
        "name": "Test Profile",
        "domain_type": "mixed",
        "description": "Test domain profile",
        "config_json": {},
        "version": 1,
    }
    await adapter.upsert_domain_profile(profile)

    # Insert mission
    mission = {
        "mission_id": mission_id,
        "topic_id": mission_id,  # for simplicity, topic_id = mission_id
        "domain_profile_id": profile_id,
        "title": "Test Mission",
        "objective": "Test objective",
        "status": "created",
        "budget_bytes": 0,
        "bytes_ingested": 0,
        "source_count": 0,
    }
    await adapter.create_mission(mission)

    return mission_id


@pytest.mark.asyncio
async def test_cross_mission_source_isolation():
    """
    GIVEN two distinct missions (A and B)
    AND mission A has ingested a source with normalized_url_hash = "hash123"
    WHEN mission B calls get_source_by_url_hash("hash123")
    THEN the source from mission A must NOT be returned (must be None)
    """
    adapter, pg_pool = await make_adapter()
    try:
        mission_a = await setup_mission(adapter)
        mission_b = await setup_mission(adapter)

        source_a = {
            "source_id": f"src_{uuid4().hex[:8]}",
            "mission_id": mission_a,
            "topic_id": mission_a,
            "url": "https://example.com/unique-page",
            "normalized_url": "https://example.com/unique-page",
            "normalized_url_hash": "hash123",
            "title": "Mission A Source",
            "source_class": "academic_paper",
            "domain": "example.com",
            "status": "fetched",
            "metadata_json": {},
            "captured_at": "2025-01-01T00:00:00Z",
            "created_at": "2025-01-01T00:00:00Z",
        }
        await adapter.pg.insert_row("corpus.sources", source_a)

        result = await adapter.get_source_by_url_hash(mission_b, "hash123")

        assert result is None, \
            f"Expected None for mission B, but got source from mission A: {result}"
    finally:
        # Cleanup: just close pool; DB can be wiped between test runs
        await pg_pool.close()


@pytest.mark.asyncio
async def test_atoms_do_not_leak_across_missions():
    """
    GIVEN two distinct missions (A and B) sharing the same topic_id
    AND mission A has created knowledge atoms for that topic_id
    WHEN mission B calls list_atoms_for_topic(topic_id)
    THEN only atoms belonging to mission B should be returned (must be empty if B has none)
    """
    adapter, pg_pool = await make_adapter()
    try:
        mission_a = await setup_mission(adapter)
        mission_b = await setup_mission(adapter)
        # Use the same topic_id for both missions to simulate potential leakage
        shared_topic_id = "topic_shared_123"

        # Create atom in mission A on the shared topic
        atom_a = {
            "atom_id": f"atom_{uuid4().hex[:8]}",
            "mission_id": mission_a,
            "topic_id": shared_topic_id,
            "domain_profile_id": f"profile_{mission_a[:8]}",  # reuse profile from setup_mission (profile_id matches mission prefix)
            "atom_type": "claim",
            "title": "Atom from Mission A",
            "statement": "This is a claim from mission A.",
            "summary": "Summary A",
            "confidence": 0.9,
            "importance": 0.8,
            "novelty": 0.5,
            "stability": "medium",
            "scope_json": {},
            "qualifiers_json": {},
            "lineage_json": {"created_by": "test", "mission_id": mission_a, "extraction_mode": "auto"},
            "metadata_json": {},
            "created_at": "2025-01-01T00:00:00Z",
            "updated_at": "2025-01-01T00:00:00Z",
        }
        await adapter.pg.insert_row("knowledge.knowledge_atoms", atom_a)

        # Ensure we have the correct domain_profile_id reference
        # The atom's domain_profile_id should be the one created for mission_a
        # Actually setup_mission created profile with id = f"profile_{mission_id[:8]}"
        # So we should use that.
        atom_a["domain_profile_id"] = f"profile_{mission_a[:8]}"
        # But we already inserted with different value; let's fix by re-preparing.
        # We'll set correctly before insert.
        atom_a["domain_profile_id"] = f"profile_{mission_a[:8]}"
        # The insert already happened above with wrong value? We'll redo:
        # Actually above we inserted atom_a without adjusting domain_profile_id; we set it after insertion. That's a bug.
        # Let's rebuild atom_a with correct domain_profile_id before insert.
        # We'll just clear and re-insert.
        await adapter.pg.delete_where("knowledge.knowledge_atoms", {"atom_id": atom_a["atom_id"]})
        atom_a["domain_profile_id"] = f"profile_{mission_a[:8]}"
        await adapter.pg.insert_row("knowledge.knowledge_atoms", atom_a)

        result = await adapter.list_atoms_for_topic(mission_b, shared_topic_id)

        assert len(result) == 0, \
            f"Expected 0 atoms for mission B, but got {len(result)} leaked atoms: {result}"
        for atom in result:
            assert atom["mission_id"] == mission_b, \
                f"Atom {atom['atom_id']} has mismatched mission_id: {atom['mission_id']} != {mission_b}"
    finally:
        await pg_pool.close()


@pytest.mark.asyncio
async def test_list_sources_respects_mission_id():
    """
    Sanity check: verify existing list_sources correctly filters by mission_id.
    """
    adapter, pg_pool = await make_adapter()
    try:
        mission_a = await setup_mission(adapter)
        mission_b = await setup_mission(adapter)

        source_a = {
            "source_id": f"src_{uuid4().hex[:8]}",
            "mission_id": mission_a,
            "topic_id": mission_a,
            "url": "https://example.com/mission-a",
            "normalized_url": "https://example.com/mission-a",
            "normalized_url_hash": "hash_a",
            "title": "Mission A Source",
            "source_class": "academic_paper",
            "domain": "example.com",
            "status": "fetched",
            "metadata_json": {},
            "captured_at": "2025-01-01T00:00:00Z",
            "created_at": "2025-01-01T00:00:00Z",
        }
        await adapter.pg.insert_row("corpus.sources", source_a)

        sources_a = await adapter.list_sources(mission_a)
        assert any(s["source_id"] == source_a["source_id"] for s in sources_a)

        sources_b = await adapter.list_sources(mission_b)
        assert not any(s["source_id"] == source_a["source_id"] for s in sources_b)
    finally:
        await pg_pool.close()
