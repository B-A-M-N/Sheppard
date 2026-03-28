"""
V-04: Cross-component consistency

Verifies that data stored in Postgres and indexed into Chroma are consistent after stabilization.
Tests atoms: after store_atom_with_evidence, the atom should be retrievable from both DB and Chroma with matching content.
"""
import pytest
import asyncio
import json
import tempfile
import uuid
import asyncpg
import chromadb
from src.memory.storage_adapter import SheppardStorageAdapter, SemanticProjectionBuilder
from src.memory.adapters.postgres import PostgresStoreImpl as PostgresImpl
from src.memory.adapters.redis import RedisStoresImpl as RedisImpl
from src.memory.adapters.chroma import ChromaSemanticStoreImpl as ChromaImpl

class FakeRedisClient:
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
async def test_v04_consistency():
    # Generate unique IDs to avoid collisions across runs
    suffix = uuid.uuid4().hex[:8]
    mission_id = f"test-mission-v04-{suffix}"
    profile_id = f"profile_{mission_id}"

    # Setup Postgres pool (use local test DB)
    pg_pool = await asyncpg.create_pool(
        'postgresql://sheppard:1234@localhost:5432/sheppard_v3',
        min_size=1, max_size=5
    )
    pg_store = PostgresImpl(pg_pool)

    # Fake Redis clients for runtime, cache, queue
    fake_redis = FakeRedisClient()
    redis_runtime = RedisImpl(fake_redis)
    redis_cache = RedisImpl(fake_redis)
    redis_queue = RedisImpl(fake_redis)

    # Chroma with temporary directory
    tmpdir = tempfile.mkdtemp()
    chroma_client = chromadb.PersistentClient(path=tmpdir, settings=chromadb.Settings(anonymized_telemetry=False, allow_reset=True))
    chroma_store = ChromaImpl(chroma_client)

    # Build adapter
    adapter = SheppardStorageAdapter(
        pg=pg_store,
        redis_runtime=redis_runtime,
        redis_cache=redis_cache,
        redis_queue=redis_queue,
        chroma=chroma_store
    )

    try:
        # Create required domain profile first (foreign key)
        profile_row = {
            "profile_id": profile_id,
            "name": f"Test Profile {suffix}",
            "domain_type": "mixed",
            "description": "Test profile for V04",
            "config_json": "{}"
        }
        await adapter.pg.insert_row("config.domain_profiles", profile_row)

        # Create mission row (needed for foreign keys)
        mission_row = {
            "mission_id": mission_id,
            "topic_id": mission_id,
            "domain_profile_id": profile_id,
            "title": "Test Mission for V04",
            "objective": "Validate consistency",
            "status": "active",
            "budget_bytes": 0,
            "bytes_ingested": 0,
            "source_count": 0,
        }
        await adapter.pg.insert_row("mission.research_missions", mission_row)

        # Create a source to be used for evidence
        source_id = f"source-v04-{suffix}"
        source_row = {
            "source_id": source_id,
            "mission_id": mission_id,
            "topic_id": mission_id,
            "url": "http://example.com/test",
            "normalized_url": "http://example.com/test",
            "normalized_url_hash": f"hash{suffix}",
            "domain": "example.com",
            "title": "Test Source",
            "source_class": "web",
            "content_hash": f"contenthash{suffix}",
            "canonical_text_ref": None,
            "status": "fetched",
            "metadata_json": "{}"
        }
        await adapter.pg.insert_row("corpus.sources", source_row)

        # Create a chunk for the source (required for evidence)
        chunk_id = f"chunk-v04-{suffix}"
        chunk_row = {
            "chunk_id": chunk_id,
            "source_id": source_id,
            "mission_id": mission_id,
            "topic_id": mission_id,
            "chunk_index": 0,
            "chunk_hash": f"chunkhash{suffix}",
            "inline_text": "This is a chunk of the test source text for V04 consistency."
        }
        await adapter.pg.insert_row("corpus.chunks", chunk_row)

        # Create an atom
        atom_id = f"atom-v04-{suffix}"
        atom_row = {
            "atom_id": atom_id,
            "topic_id": mission_id,
            "domain_profile_id": profile_id,
            "atom_type": "claim",
            "title": "Test Atom",
            "statement": "This is a test statement for V04 consistency.",
            "summary": "Test summary for V04",
            "confidence": 0.8,
            "importance": 0.7,
            "stability": "medium",
            "lineage_json": json.dumps({
                "mission_id": mission_id,
                "extraction_mode": "validation_test"
            }),
            "metadata_json": "{}"
        }
        evidence_rows = [{
            "source_id": source_id,
            "evidence_strength": 0.9,
            "supports_statement": True,
            "chunk_id": chunk_id
        }]

        # Store atom with evidence (this indexes to Chroma and caches in Redis)
        await adapter.store_atom_with_evidence(atom_row, evidence_rows)

        # Allow a short stabilization period (as per contract 5s, but we use 0.5s for test)
        await asyncio.sleep(0.5)

        # 1. Fetch from DB via adapter.get_atom
        db_atom = await adapter.get_atom(atom_id)
        assert db_atom is not None, "Atom must exist in DB"

        # 2. Fetch from Chroma index directly
        collection = adapter.chroma.client.get_collection("knowledge_atoms")
        result = collection.get(ids=[atom_id])
        assert result and atom_id in result['ids'], "Atom not found in Chroma index"
        idx = result['ids'].index(atom_id)
        idx_doc = result['documents'][idx]
        idx_meta = result['metadatas'][idx]

        # 3. Build expected document and metadata from DB atom using projection
        expected_doc = SemanticProjectionBuilder.build_atom_document(db_atom)
        expected_meta = SemanticProjectionBuilder.build_atom_metadata(db_atom)

        # 4. Compare document content
        assert idx_doc == expected_doc, f"Document mismatch: index has '{idx_doc}' vs expected '{expected_doc}'"

        # 5. Compare metadata fields (atom_id, topic_id, domain_profile_id, atom_type, confidence, importance, stability, core_atom_flag, contradiction_flag)
        for key in expected_meta:
            assert idx_meta.get(key) == expected_meta[key], f"Metadata mismatch for {key}: got {idx_meta.get(key)} expected {expected_meta[key]}"

        # Cleanup: clear Chroma collection to avoid leftovers
        await adapter.chroma.clear_collection("knowledge_atoms")
    finally:
        # Cleanup database records (best effort)
        try:
            if 'atom_id' in locals():
                try:
                    await adapter.pg.delete_where("knowledge.atom_evidence", {"atom_id": atom_id})
                except Exception:
                    pass
                try:
                    await adapter.pg.delete_where("knowledge.knowledge_atoms", {"atom_id": atom_id})
                except Exception:
                    pass
        except Exception:
            pass
        try:
            if 'mission_id' in locals():
                await adapter.pg.delete_where("mission.research_missions", {"mission_id": mission_id})
        except Exception:
            pass
        try:
            if 'profile_id' in locals():
                await adapter.pg.delete_where("config.domain_profiles", {"profile_id": profile_id})
        except Exception:
            pass
        await pg_pool.close()
