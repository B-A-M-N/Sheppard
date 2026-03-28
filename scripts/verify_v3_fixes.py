#!/usr/bin/env python3
import asyncio, os, sys, uuid
os.environ['CHROMA_TELEMETRY_DISABLED'] = '1'
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + '/..')

from src.config.database import DatabaseConfig
from src.memory.adapters.postgres import PostgresStoreImpl
from src.memory.adapters.redis import RedisStoresImpl
from src.memory.adapters.chroma import ChromaSemanticStoreImpl
from src.memory.storage_adapter import SheppardStorageAdapter
from src.research.reasoning.v3_retriever import V3Retriever
from src.research.reasoning.retriever import RetrievalQuery
import asyncpg
import redis.asyncio as redis
import chromadb

async def main():
    pg_pool = await asyncpg.create_pool(DatabaseConfig.DB_URLS["sheppard_v3"], min_size=2, max_size=5)
    pg = PostgresStoreImpl(pg_pool)
    r = redis.Redis.from_url("redis://localhost:6379", decode_responses=False)
    redis_store = RedisStoresImpl(r)
    chroma = ChromaSemanticStoreImpl(chromadb.PersistentClient(path=DatabaseConfig.CHROMA_SETTINGS["persist_directory"]))
    adapter = SheppardStorageAdapter(pg, redis_store, redis_store, redis_store, chroma)

    # Unique IDs for this run
    uid = uuid.uuid4().hex[:8]
    profile_id = f"vrf_profile_{uid}"
    mission_id = f"vrf_mission_{uid}"
    topic_id = f"vrf_topic_{uid}"

    try:
        # Create domain profile and mission
        await pg.insert_row("config.domain_profiles", {
            "profile_id": profile_id,
            "name": "Verification",
            "domain_type": "test",
            "description": "V3 verification"
        })
        await pg.insert_row("mission.research_missions", {
            "mission_id": mission_id,
            "topic_id": topic_id,
            "domain_profile_id": profile_id,
            "title": "Verification Mission",
            "objective": "Verify V3 fixes",
            "status": "active",
            "budget_bytes": 0,
            "bytes_ingested": 0,
            "source_count": 0,
            "metadata_json": {}
        })

        # Test 1: Chunking
        test_text = "Hello world test content " * 10
        source = {"mission_id": mission_id, "topic_id": topic_id, "url": "http://test", "title": "Test"}
        source_id = await adapter.ingest_source(source, test_text)
        chunks = await pg.fetch_many("corpus.chunks", {"source_id": source_id})
        assert len(chunks) > 0, "No chunks created"
        chunk_id = chunks[0]["chunk_id"]
        print(f"[1] Chunking: OK (created {len(chunks)} chunk)")

        # Test 2: Atomic store
        atom = {
            "atom_id": f"atom_{uid}",
            "mission_id": mission_id,
            "topic_id": topic_id,
            "domain_profile_id": profile_id,
            "title": "Test Atom",
            "statement": "Some statement",
            "atom_type": "fact",
            "qualifiers_json": {},
            "scope_json": {},
            "lineage_json": {},
            "metadata_json": {}
        }
        evidence = [{"source_id": source_id, "chunk_id": chunk_id, "evidence_strength": 0.9, "supports_statement": True}]
        await adapter.store_atom_with_evidence(atom, evidence)
        atom_db = await pg.fetch_one("knowledge.knowledge_atoms", {"atom_id": atom["atom_id"]})
        assert atom_db is not None, "Atom not stored"
        ev_db = await pg.fetch_many("knowledge.atom_evidence", {"atom_id": atom["atom_id"]})
        assert len(ev_db) == 1, "Evidence not stored"
        print("[2] Atomic atom+evidence: OK")

        # Test 3: V3 Retriever
        v3 = V3Retriever(adapter)
        q = RetrievalQuery(text="statement", topic_filter=topic_id, max_results=5)
        ctx = await v3.retrieve(q)
        assert not ctx.is_empty and len(ctx.evidence) > 0, "Retriever returned nothing"
        print(f"[3] V3Retriever: retrieved {len(ctx.evidence)} item(s)")

        print("ALL TESTS PASSED")
        return True

    finally:
        # Cleanup cascade: mission deletes propagate to atoms, evidence, sources, chunks
        try:
            await pg.delete_where("mission.research_missions", {"mission_id": mission_id})
        except Exception as e:
            print(f"Cleanup warning: {e}")
        try:
            await pg.delete_where("config.domain_profiles", {"profile_id": profile_id})
        except Exception as e:
            pass
        await pg_pool.close()

if __name__ == "__main__":
    success = True
    try:
        success = asyncio.run(main()) is True
    except Exception as e:
        print(f"TEST FAILED: {e}")
        import traceback; traceback.print_exc()
        success = False
    sys.exit(0 if success else 1)
