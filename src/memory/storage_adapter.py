"""
memory/storage_adapter.py

The Universal I/O Layer for the Domain Authority Foundry.
Enforces the strict Triad Discipline:
- Postgres: Owns identity, structure, lineage, and truth.
- Chroma: Owns semantic proximity and discovery.
- Redis: Owns motion, heat, and coordination.

Every write method must obey the invariant:
1. Write to Postgres (Canonical)
2. Project to Chroma (Semantic)
3. Project to Redis (Hot Cache/State)
"""

from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal, Protocol, Sequence, Union
import logging
import json
import hashlib
import uuid

logger = logging.getLogger(__name__)

JsonDict = dict[str, Any]

# =========================================================
# Generic result wrappers
# =========================================================

@dataclass(slots=True)
class Page:
    items: list[Any]
    next_cursor: str | None = None

@dataclass(slots=True)
class SearchHit:
    object_id: str
    score: float
    metadata: JsonDict

@dataclass(slots=True)
class LockHandle:
    key: str
    token: str
    expires_at: datetime

# =========================================================
# Store protocols (Async)
# =========================================================

class ConfigStore(Protocol):
    async def upsert_domain_profile(self, profile: JsonDict) -> None: ...
    async def get_domain_profile(self, profile_id: str) -> JsonDict | None: ...
    async def list_domain_profiles(self) -> list[JsonDict]: ...

class MissionStore(Protocol):
    async def create_mission(self, mission: JsonDict) -> None: ...
    async def get_mission(self, mission_id: str) -> JsonDict | None: ...
    async def update_mission_status(
        self,
        mission_id: str,
        status: str,
        stop_reason: str | None = None,
    ) -> None: ...

    async def append_mission_event(self, mission_id: str, event: JsonDict) -> None: ...
    async def list_mission_events(
        self,
        mission_id: str,
        limit: int = 200,
        cursor: str | None = None,
    ) -> Page: ...

    async def upsert_mission_node(self, node: JsonDict) -> None: ...
    async def get_mission_node(self, node_id: str) -> JsonDict | None: ...
    async def list_mission_nodes(self, mission_id: str, status: str | None = None) -> list[JsonDict]: ...

    async def record_mode_run(self, mode_run: JsonDict) -> None: ...
    async def list_mode_runs(self, mission_id: str, node_id: str | None = None) -> list[JsonDict]: ...

    async def checkpoint_frontier(self, mission_id: str, snapshot: JsonDict) -> None: ...
    async def get_latest_frontier_checkpoint(self, mission_id: str) -> JsonDict | None: ...

class CorpusStore(Protocol):
    async def register_source(self, source: JsonDict) -> None: ...
    async def get_source(self, source_id: str) -> JsonDict | None: ...
    async def get_source_by_url_hash(self, mission_id: str, normalized_url_hash: str) -> JsonDict | None: ...
    async def list_sources(self, mission_id: str, topic_id: str | None = None) -> list[JsonDict]: ...
    async def get_visited_urls(self, mission_id: str) -> set[str]: ...

    async def record_source_fetch(self, fetch_event: JsonDict) -> None: ...

    async def store_text_ref(self, text_ref: JsonDict) -> None: ...
    async def get_text_ref(self, blob_id: str) -> JsonDict | None: ...

    async def create_chunks(self, chunks: Sequence[JsonDict]) -> None: ...
    async def get_chunk(self, chunk_id: str) -> JsonDict | None: ...
    async def list_chunks_for_source(self, source_id: str) -> list[JsonDict]: ...
    async def list_chunks_for_cluster(self, cluster_id: str) -> list[JsonDict]: ...

    async def create_cluster(self, cluster: JsonDict) -> None: ...
    async def add_cluster_members(self, cluster_id: str, members: Sequence[JsonDict]) -> None: ...
    async def get_cluster(self, cluster_id: str) -> JsonDict | None: ...
    async def list_clusters(self, mission_id: str) -> list[JsonDict]: ...

    async def store_cluster_differential(self, cluster_id: str, differential: JsonDict) -> None: ...

class KnowledgeStore(Protocol):
    async def upsert_atom(self, atom: JsonDict) -> None: ...
    async def get_atom(self, atom_id: str) -> JsonDict | None: ...
    async def list_atoms_for_topic(
        self,
        topic_id: str,
        atom_types: Sequence[str] | None = None,
    ) -> list[JsonDict]: ...

    async def bind_atom_evidence(self, atom_id: str, evidence_rows: Sequence[JsonDict]) -> None: ...
    async def replace_atom_relationships(self, atom_id: str, relationships: Sequence[JsonDict]) -> None: ...
    async def replace_atom_entities(self, atom_id: str, entities: Sequence[JsonDict]) -> None: ...

    async def create_contradiction_set(self, contradiction_set: JsonDict) -> None: ...
    async def add_contradiction_members(self, contradiction_set_id: str, members: Sequence[JsonDict]) -> None: ...
    async def get_contradiction_set(self, contradiction_set_id: str) -> JsonDict | None: ...

    async def create_evidence_bundle(self, bundle: JsonDict, persist: bool = False) -> None: ...
    async def get_evidence_bundle(self, bundle_id: str) -> JsonDict | None: ...

class AuthorityStore(Protocol):
    async def upsert_authority_record(self, record: JsonDict) -> None: ...
    async def get_authority_record(self, authority_record_id: str) -> JsonDict | None: ...
    async def list_authority_records(
        self,
        topic_id: str | None = None,
        domain_profile_id: str | None = None,
    ) -> list[JsonDict]: ...

    async def set_authority_core_atoms(self, authority_record_id: str, rows: Sequence[JsonDict]) -> None: ...
    async def set_authority_related_records(self, authority_record_id: str, rows: Sequence[JsonDict]) -> None: ...
    async def set_authority_advisories(self, authority_record_id: str, rows: Sequence[JsonDict]) -> None: ...

    async def store_synthesis_artifact(self, artifact: JsonDict) -> None: ...
    async def store_synthesis_sections(self, sections: Sequence[JsonDict]) -> None: ...
    async def store_synthesis_citations(self, citations: Sequence[JsonDict]) -> None: ...

    async def get_synthesis_artifact(self, artifact_id: str) -> JsonDict | None: ...
    async def list_synthesis_artifacts(
        self,
        authority_record_id: str,
        artifact_type: str | None = None,
    ) -> list[JsonDict]: ...

    async def ingest_source(self, source: JsonDict, text_content: str) -> str: ...

class ApplicationStore(Protocol):
    async def create_application_query(self, query: JsonDict) -> None: ...
    async def get_application_query(self, application_query_id: str) -> JsonDict | None: ...
    async def store_application_output(self, output: JsonDict) -> None: ...
    async def bind_application_evidence(
        self,
        application_query_id: str,
        rows: Sequence[JsonDict],
    ) -> None: ...

class RuntimeStore(Protocol):
    async def enqueue_job(self, queue_name: str, payload: JsonDict) -> None: ...
    async def dequeue_job(self, queue_name: str, timeout_s: int = 0) -> JsonDict | None: ...
    async def schedule_retry(self, queue_name: str, payload: JsonDict, when_epoch_s: int) -> None: ...
    async def move_due_retries(self, queue_name: str, now_epoch_s: int) -> int: ...

    async def acquire_lock(self, key: str, ttl_s: int) -> LockHandle | None: ...
    async def refresh_lock(self, handle: LockHandle, ttl_s: int) -> LockHandle | None: ...
    async def release_lock(self, handle: LockHandle) -> None: ...

    async def set_active_state(self, key: str, payload: JsonDict, ttl_s: int | None = None) -> None: ...
    async def get_active_state(self, key: str) -> JsonDict | None: ...
    async def delete_active_state(self, key: str) -> None: ...

    async def cache_hot_object(self, kind: str, object_id: str, payload: JsonDict, ttl_s: int) -> None: ...
    async def get_hot_object(self, kind: str, object_id: str) -> JsonDict | None: ...
    async def invalidate_hot_object(self, kind: str, object_id: str) -> None: ...

class SemanticIndexStore(Protocol):
    async def index_chunk(self, chunk: JsonDict) -> None: ...
    async def index_chunks(self, chunks: Sequence[JsonDict]) -> None: ...

    async def index_atom(self, atom: JsonDict) -> None: ...
    async def index_authority_record(self, record: JsonDict) -> None: ...
    async def index_synthesis_artifact(self, artifact: JsonDict) -> None: ...

    async def search_chunks(
        self,
        query_text: str,
        where: JsonDict | None = None,
        limit: int = 20,
    ) -> list[SearchHit]: ...

    async def search_atoms(
        self,
        query_text: str,
        where: JsonDict | None = None,
        limit: int = 20,
    ) -> list[SearchHit]: ...

    async def search_authority_records(
        self,
        query_text: str,
        where: JsonDict | None = None,
        limit: int = 10,
    ) -> list[SearchHit]: ...

    async def search_synthesis_artifacts(
        self,
        query_text: str,
        where: JsonDict | None = None,
        limit: int = 10,
    ) -> list[SearchHit]: ...

    async def delete_index_object(
        self,
        collection: Literal[
            "corpus_chunks",
            "knowledge_atoms",
            "authority_records",
            "synthesis_artifacts",
        ],
        object_id: str,
    ) -> None: ...

class StorageAdapter(
    ConfigStore,
    MissionStore,
    CorpusStore,
    KnowledgeStore,
    AuthorityStore,
    ApplicationStore,
    RuntimeStore,
    SemanticIndexStore,
    Protocol,
):
    pass

# =========================================================
# Semantic projection builders
# =========================================================

class SemanticProjectionBuilder:
    """Builds deterministic semantic documents for Chroma."""

    @staticmethod
    def build_chunk_document(chunk: JsonDict) -> str:
        text = chunk.get("inline_text") or chunk.get("text", "")
        return str(text).strip()

    @staticmethod
    def build_chunk_metadata(chunk: JsonDict) -> JsonDict:
        return {
            "chunk_id": chunk["chunk_id"],
            "source_id": chunk.get("source_id"),
            "mission_id": chunk.get("mission_id"),
            "topic_id": chunk.get("topic_id"),
            "domain_profile_id": chunk.get("domain_profile_id"),
            "source_class": chunk.get("source_class"),
            "trust_score": chunk.get("trust_score"),
            "quality_score": chunk.get("quality_score"),
            "cluster_id": chunk.get("cluster_id"),
            "captured_at": chunk.get("captured_at"),
        }

    @staticmethod
    def build_atom_document(atom: JsonDict) -> str:
        parts = [
            atom.get("title", ""),
            atom.get("statement", ""),
            atom.get("summary", ""),
        ]
        qualifiers = atom.get("qualifiers_json") or atom.get("qualifiers") or {}
        caveats = qualifiers.get("caveats", [])
        counterpoints = qualifiers.get("counterpoints", [])
        if caveats:
            parts.append("Caveats: " + " | ".join(map(str, caveats[:5])))
        if counterpoints:
            parts.append("Counterpoints: " + " | ".join(map(str, counterpoints[:5])))
        return "\n".join(p for p in parts if p).strip()

    @staticmethod
    def build_atom_metadata(atom: JsonDict) -> JsonDict:
        return {
            "atom_id": atom["atom_id"],
            "authority_record_id": atom.get("authority_record_id"),
            "topic_id": atom.get("topic_id"),
            "domain_profile_id": atom.get("domain_profile_id"),
            "atom_type": atom.get("atom_type"),
            "confidence": atom.get("confidence"),
            "importance": atom.get("importance"),
            "stability": atom.get("stability"),
            "core_atom_flag": atom.get("core_atom_flag", False),
            "contradiction_flag": atom.get("contradiction_flag", False),
        }

    @staticmethod
    def build_authority_record_document(record: JsonDict) -> str:
        scope = record.get("scope_json") or record.get("scope") or {}
        advisory = record.get("advisory_layer_json") or record.get("advisory_layer") or {}
        included = scope.get("included", [])
        framing = scope.get("framing_statement", "")
        decision_rules = advisory.get("decision_rules", [])
        transfer = advisory.get("transferability_notes", [])
        contradictions = record.get("major_contradictions", [])

        parts = [
            record.get("title", ""),
            framing,
        ]
        if included:
            parts.append("Scope: " + " | ".join(map(str, included[:10])))
        if decision_rules:
            parts.append("Decision rules: " + " | ".join(map(str, decision_rules[:10])))
        if contradictions:
            parts.append("Major contradictions: " + " | ".join(map(str, contradictions[:10])))
        if transfer:
            parts.append("Transferability: " + " | ".join(map(str, transfer[:10])))
        return "\n".join(p for p in parts if p).strip()

    @staticmethod
    def build_authority_record_metadata(record: JsonDict) -> JsonDict:
        status = record.get("status_json") or record.get("status") or {}
        atom_layer = record.get("atom_layer_json") or record.get("atom_layer") or {}
        return {
            "authority_record_id": record["authority_record_id"],
            "topic_id": record.get("topic_id"),
            "domain_profile_id": record.get("domain_profile_id"),
            "maturity": status.get("maturity"),
            "confidence": status.get("confidence"),
            "freshness": status.get("freshness"),
            "core_atom_count": len(atom_layer.get("core_atom_ids", [])),
        }

    @staticmethod
    def build_synthesis_artifact_document(artifact: JsonDict) -> str:
        parts = [
            artifact.get("title", ""),
            artifact.get("abstract", ""),
            artifact.get("inline_text", ""),
        ]
        return "\n".join(p for p in parts if p).strip()

    @staticmethod
    def build_synthesis_artifact_metadata(artifact: JsonDict) -> JsonDict:
        return {
            "artifact_id": artifact["artifact_id"],
            "authority_record_id": artifact.get("authority_record_id"),
            "artifact_type": artifact.get("artifact_type"),
            "topic_id": artifact.get("topic_id"),
            "section_name": artifact.get("section_name"),
            "freshness_state": artifact.get("freshness_state"),
        }

# =========================================================
# Backend delegate stubs (Async)
# =========================================================

class PostgresStore(Protocol):
    async def upsert_row(self, table: str, key_fields: Union[str, Sequence[str]], row: JsonDict) -> None: ...
    async def insert_row(self, table: str, row: JsonDict) -> None: ...
    async def update_row(self, table: str, key_field: str, row: JsonDict) -> None: ...
    async def bulk_insert(self, table: str, rows: Sequence[JsonDict]) -> None: ...
    async def bulk_upsert(self, table: str, key_fields: Sequence[str], rows: Sequence[JsonDict]) -> None: ...
    async def fetch_one(self, table: str, where: JsonDict) -> JsonDict | None: ...
    async def fetch_many(
        self,
        table: str,
        where: JsonDict | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> list[JsonDict]: ...
    async def delete_where(self, table: str, where: JsonDict) -> None: ...

class RedisQueueStore(Protocol):
    async def enqueue_job(self, queue_name: str, payload: JsonDict) -> None: ...
    async def dequeue_job(self, queue_name: str, timeout_s: int = 0) -> JsonDict | None: ...
    async def schedule_retry(self, queue_name: str, payload: JsonDict, when_epoch_s: int) -> None: ...
    async def move_due_retries(self, queue_name: str, now_epoch_s: int) -> int: ...

class RedisRuntimeStore(Protocol):
    async def acquire_lock(self, key: str, ttl_s: int) -> LockHandle | None: ...
    async def refresh_lock(self, handle: LockHandle, ttl_s: int) -> LockHandle | None: ...
    async def release_lock(self, handle: LockHandle) -> None: ...
    async def set_active_state(self, key: str, payload: JsonDict, ttl_s: int | None = None) -> None: ...
    async def get_active_state(self, key: str) -> JsonDict | None: ...
    async def delete_active_state(self, key: str) -> None: ...

class RedisCacheStore(Protocol):
    async def cache_hot_object(self, kind: str, object_id: str, payload: JsonDict, ttl_s: int) -> None: ...
    async def get_hot_object(self, kind: str, object_id: str) -> JsonDict | None: ...
    async def invalidate_hot_object(self, kind: str, object_id: str) -> None: ...

class ChromaSemanticStore(Protocol):
    async def index_document(self, collection: str, object_id: str, document: str, metadata: JsonDict, embedding: list[float] | None = None) -> None: ...
    async def index_documents(self, collection: str, rows: Sequence[tuple[str, str, JsonDict]], embeddings: list[list[float]] | None = None) -> None: ...
    async def search(self, collection: str, query_text: str, where: JsonDict | None = None, limit: int = 20) -> list[SearchHit]: ...
    async def query(self, collection: str, query_text: str | None = None, query_embeddings: list[float] | None = None, where: JsonDict | None = None, limit: int = 20) -> Dict: ...
    async def delete_document(self, collection: str, object_id: str) -> None: ...
    async def clear_collection(self, name: str) -> None: ...

# =========================================================
# Concrete adapter (Async)
# =========================================================

class SheppardStorageAdapter(StorageAdapter):
    def __init__(
        self,
        pg: PostgresStore,
        redis_runtime: RedisRuntimeStore,
        redis_cache: RedisCacheStore,
        redis_queue: RedisQueueStore,
        chroma: ChromaSemanticStore,
        projection_builder: SemanticProjectionBuilder | None = None,
    ) -> None:
        self.pg = pg
        self.redis_runtime = redis_runtime
        self.redis_cache = redis_cache
        self.redis_queue = redis_queue
        self.chroma = chroma
        self.projection = projection_builder or SemanticProjectionBuilder()

    # =====================================================
    # ConfigStore
    # =====================================================

    async def upsert_domain_profile(self, profile: JsonDict) -> None:
        await self.pg.upsert_row("config.domain_profiles", "profile_id", profile)
        await self.redis_cache.cache_hot_object("profile", profile["profile_id"], profile, ttl_s=3600)

    async def get_domain_profile(self, profile_id: str) -> JsonDict | None:
        cached = await self.redis_cache.get_hot_object("profile", profile_id)
        if cached is not None: return cached
        row = await self.pg.fetch_one("config.domain_profiles", {"profile_id": profile_id})
        if row is not None: await self.redis_cache.cache_hot_object("profile", profile_id, row, ttl_s=3600)
        return row

    async def list_domain_profiles(self) -> list[JsonDict]:
        return await self.pg.fetch_many("config.domain_profiles", order_by="name ASC")

    # =====================================================
    # MissionStore
    # =====================================================

    async def create_mission(self, mission: JsonDict) -> None:
        await self.pg.insert_row("mission.research_missions", mission)
        await self.redis_runtime.set_active_state(f"mission:active:{mission['mission_id']}", mission)

    async def get_mission(self, mission_id: str) -> JsonDict | None:
        active = await self.redis_runtime.get_active_state(f"mission:active:{mission_id}")
        if active is not None: return active
        return await self.pg.fetch_one("mission.research_missions", {"mission_id": mission_id})

    async def update_mission_status(self, mission_id: str, status: str, stop_reason: str | None = None) -> None:
        row = await self.pg.fetch_one("mission.research_missions", {"mission_id": mission_id})
        if row is None: raise KeyError(f"Mission not found: {mission_id}")
        row["status"] = status
        if stop_reason is not None: row["stop_reason"] = stop_reason
        row["updated_at"] = _utcnow()
        await self.pg.upsert_row("mission.research_missions", "mission_id", row)
        await self.redis_runtime.set_active_state(f"mission:active:{mission_id}", row)

    async def append_mission_event(self, mission_id: str, event: JsonDict) -> None:
        payload = dict(event)
        payload["mission_id"] = mission_id
        await self.pg.insert_row("mission.mission_events", payload)

    async def list_mission_events(self, mission_id: str, limit: int = 200, cursor: str | None = None) -> Page:
        rows = await self.pg.fetch_many("mission.mission_events", where={"mission_id": mission_id}, order_by="created_at DESC", limit=limit)
        return Page(items=rows, next_cursor=None)

    async def upsert_mission_node(self, node: JsonDict) -> None:
        await self.pg.upsert_row("mission.mission_nodes", "node_id", node)
        await self.redis_runtime.set_active_state(f"mission:node:{node['node_id']}", node)

    async def get_mission_node(self, node_id: str) -> JsonDict | None:
        active = await self.redis_runtime.get_active_state(f"mission:node:{node_id}")
        if active is not None: return active
        return await self.pg.fetch_one("mission.mission_nodes", {"node_id": node_id})

    async def list_mission_nodes(self, mission_id: str, status: str | None = None) -> list[JsonDict]:
        where: JsonDict = {"mission_id": mission_id}
        if status is not None: where["status"] = status
        return await self.pg.fetch_many("mission.mission_nodes", where=where, order_by="priority DESC")

    async def record_mode_run(self, mode_run: JsonDict) -> None:
        await self.pg.upsert_row("mission.mission_mode_runs", "mode_run_id", mode_run)
        await self.redis_runtime.set_active_state(f"mode:run:{mode_run['mode_run_id']}", mode_run, ttl_s=86400)

    async def list_mode_runs(self, mission_id: str, node_id: str | None = None) -> list[JsonDict]:
        where: JsonDict = {"mission_id": mission_id}
        if node_id is not None: where["node_id"] = node_id
        return await self.pg.fetch_many("mission.mission_mode_runs", where=where, order_by="started_at DESC")

    async def checkpoint_frontier(self, mission_id: str, snapshot: JsonDict) -> None:
        await self.pg.insert_row("mission.mission_frontier_snapshots", {"mission_id": mission_id, "frontier_json": snapshot})
        await self.redis_runtime.set_active_state(f"mission:frontier:{mission_id}", snapshot)

    async def get_latest_frontier_checkpoint(self, mission_id: str) -> JsonDict | None:
        active = await self.redis_runtime.get_active_state(f"mission:frontier:{mission_id}")
        if active is not None: return active
        rows = await self.pg.fetch_many("mission.mission_frontier_snapshots", where={"mission_id": mission_id}, order_by="created_at DESC", limit=1)
        return rows[0]["frontier_json"] if rows else None

    # =====================================================
    # CorpusStore
    # =====================================================

    async def register_source(self, source: JsonDict) -> None:
        await self.pg.upsert_row("corpus.sources", "source_id", source)
        await self.redis_runtime.set_active_state(f"source:hot:{source['source_id']}", source, ttl_s=3600)

    async def get_source(self, source_id: str) -> JsonDict | None:
        active = await self.redis_runtime.get_active_state(f"source:hot:{source_id}")
        if active is not None: return active
        return await self.pg.fetch_one("corpus.sources", {"source_id": source_id})

    async def get_source_by_url_hash(self, mission_id: str, normalized_url_hash: str) -> JsonDict | None:
        return await self.pg.fetch_one(
            "corpus.sources",
            {"mission_id": mission_id, "normalized_url_hash": normalized_url_hash}
        )

    async def list_sources(self, mission_id: str, topic_id: str | None = None) -> list[JsonDict]:
        where: JsonDict = {"mission_id": mission_id}
        if topic_id is not None: where["topic_id"] = topic_id
        return await self.pg.fetch_many("corpus.sources", where=where, order_by="created_at DESC")

    async def get_visited_urls(self, mission_id: str) -> set[str]:
        rows = await self.list_sources(mission_id)
        return {r["normalized_url"] for r in rows if r.get("normalized_url")}

    async def record_source_fetch(self, fetch_event: JsonDict) -> None:
        await self.pg.insert_row("corpus.source_fetches", fetch_event)

    async def store_text_ref(self, text_ref: JsonDict) -> None:
        await self.pg.upsert_row("corpus.text_refs", "blob_id", text_ref)

    async def get_text_ref(self, blob_id: str) -> JsonDict | None:
        return await self.pg.fetch_one("corpus.text_refs", {"blob_id": blob_id})

    async def create_chunks(self, chunks: Sequence[JsonDict]) -> None:
        if not chunks: return
        await self.pg.bulk_upsert("corpus.chunks", ["chunk_id"], list(chunks))
        await self.index_chunks(chunks)

    async def get_chunk(self, chunk_id: str) -> JsonDict | None:
        cached = await self.redis_cache.get_hot_object("chunk", chunk_id)
        if cached is not None: return cached
        row = await self.pg.fetch_one("corpus.chunks", {"chunk_id": chunk_id})
        if row is not None: await self.redis_cache.cache_hot_object("chunk", chunk_id, row, ttl_s=3600)
        return row

    async def list_chunks_for_source(self, source_id: str) -> list[JsonDict]:
        return await self.pg.fetch_many("corpus.chunks", where={"source_id": source_id}, order_by="chunk_index ASC")

    async def list_chunks_for_cluster(self, cluster_id: str) -> list[JsonDict]:
        return await self.pg.fetch_many("corpus.chunks", where={"cluster_id": cluster_id}, order_by="chunk_index ASC")

    async def create_cluster(self, cluster: JsonDict) -> None:
        await self.pg.upsert_row("corpus.clusters", "cluster_id", cluster)

    async def add_cluster_members(self, cluster_id: str, members: Sequence[JsonDict]) -> None:
        if not members: return
        rows = [dict(m, cluster_id=cluster_id) for m in members]
        await self.pg.bulk_upsert("corpus.cluster_members", ["cluster_id", "chunk_id"], rows)

    async def get_cluster(self, cluster_id: str) -> JsonDict | None:
        return await self.pg.fetch_one("corpus.clusters", {"cluster_id": cluster_id})

    async def list_clusters(self, mission_id: str) -> list[JsonDict]:
        return await self.pg.fetch_many("corpus.clusters", where={"mission_id": mission_id}, order_by="created_at DESC")

    async def store_cluster_differential(self, cluster_id: str, differential: JsonDict) -> None:
        row = dict(differential)
        row["cluster_id"] = cluster_id
        await self.pg.upsert_row("corpus.cluster_differentials", "cluster_id", row)

    # =====================================================
    # KnowledgeStore
    # =====================================================

    async def upsert_atom(self, atom: JsonDict) -> None:
        await self.pg.upsert_row("knowledge.knowledge_atoms", "atom_id", atom)
        await self.index_atom(atom)
        await self.redis_cache.cache_hot_object("atom", atom["atom_id"], atom, ttl_s=3600)

    async def get_atom(self, atom_id: str) -> JsonDict | None:
        cached = await self.redis_cache.get_hot_object("atom", atom_id)
        if cached is not None: return cached
        row = await self.pg.fetch_one("knowledge.knowledge_atoms", {"atom_id": atom_id})
        if row is not None: await self.redis_cache.cache_hot_object("atom", atom_id, row, ttl_s=3600)
        return row

    async def list_atoms_for_topic(self, topic_id: str, atom_types: Sequence[str] | None = None) -> list[JsonDict]:
        rows = await self.pg.fetch_many("knowledge.knowledge_atoms", where={"topic_id": topic_id}, order_by="importance DESC")
        if not atom_types: return rows
        allowed = set(atom_types)
        return [row for row in rows if row.get("atom_type") in allowed]

    async def bind_atom_evidence(self, atom_id: str, evidence_rows: Sequence[JsonDict]) -> None:
        if not evidence_rows: return
        rows = [dict(row, atom_id=atom_id) for row in evidence_rows]
        await self.pg.bulk_upsert("knowledge.atom_evidence", ["atom_id", "source_id", "chunk_id"], rows)

    async def store_atom_with_evidence(self, atom: JsonDict, evidence_rows: Sequence[JsonDict]) -> None:
        """
        Atomically store an atom and its evidence in a single transaction.
        Guarantees: either both atom and evidence are persisted, or neither.
        Indexing and caching are performed after transaction commit.
        """
        if not evidence_rows:
            raise ValueError("Atom must have at least one evidence row to satisfy V3 integrity invariant")

        atom_id = atom["atom_id"]
        rows_with_atom = [dict(row, atom_id=atom_id) for row in evidence_rows]

        async with self.pg.pool.acquire() as conn:
            async with conn.transaction():
                # --- Upsert atom ---
                columns = list(atom.keys())
                values = self.pg._prepare_values(atom)
                col_str = ", ".join(columns)
                val_str = ", ".join(f"${i+1}" for i in range(len(values)))
                key_fields = ["atom_id"]
                update_parts = [f"{col} = EXCLUDED.{col}" for col in columns if col not in key_fields]
                update_str = ", ".join(update_parts)
                query = f"INSERT INTO knowledge.knowledge_atoms ({col_str}) VALUES ({val_str})"
                key_str = ", ".join(key_fields)
                if update_parts:
                    query += f" ON CONFLICT ({key_str}) DO UPDATE SET {update_str}"
                else:
                    query += f" ON CONFLICT ({key_str}) DO NOTHING"
                await conn.execute(query, *values)

                # --- Bulk upsert evidence ---
                ev_columns = list(rows_with_atom[0].keys())
                ev_col_str = ", ".join(ev_columns)
                # Build multi-row values
                placeholders = []
                ev_flat_values = []
                for row in rows_with_atom:
                    prepared = self.pg._prepare_values(row)
                    start_idx = len(ev_flat_values) + 1
                    row_ph = ", ".join(f"${i}" for i in range(start_idx, start_idx + len(prepared)))
                    placeholders.append(f"({row_ph})")
                    ev_flat_values.extend(prepared)

                ev_query = f"INSERT INTO knowledge.atom_evidence ({ev_col_str}) VALUES " + ", ".join(placeholders)
                ev_key_fields = ["atom_id", "source_id", "chunk_id"]
                ev_update_parts = [f"{col} = EXCLUDED.{col}" for col in ev_columns if col not in ev_key_fields]
                if ev_update_parts:
                    ev_update_str = ", ".join(ev_update_parts)
                    ev_query += f" ON CONFLICT ({', '.join(ev_key_fields)}) DO UPDATE SET {ev_update_str}"
                else:
                    ev_query += f" ON CONFLICT ({', '.join(ev_key_fields)}) DO NOTHING"

                await conn.execute(ev_query, *ev_flat_values)

        # Index and cache after successful commit
        await self.index_atom(atom)
        await self.redis_cache.cache_hot_object("atom", atom_id, atom, ttl_s=3600)

    async def replace_atom_relationships(self, atom_id: str, relationships: Sequence[JsonDict]) -> None:
        await self.pg.delete_where("knowledge.atom_relationships", {"atom_id": atom_id})
        if relationships:
            rows = [dict(r, atom_id=atom_id) for r in relationships]
            await self.pg.bulk_insert("knowledge.atom_relationships", rows)

    async def replace_atom_entities(self, atom_id: str, entities: Sequence[JsonDict]) -> None:
        await self.pg.delete_where("knowledge.atom_entities", {"atom_id": atom_id})
        if entities:
            rows = [dict(e, atom_id=atom_id) for e in entities]
            await self.pg.bulk_insert("knowledge.atom_entities", rows)

    async def create_contradiction_set(self, contradiction_set: JsonDict) -> None:
        await self.pg.upsert_row("knowledge.contradiction_sets", "contradiction_set_id", contradiction_set)

    async def add_contradiction_members(self, contradiction_set_id: str, members: Sequence[JsonDict]) -> None:
        if not members: return
        rows = [dict(m, contradiction_set_id=contradiction_set_id) for m in members]
        await self.pg.bulk_upsert("knowledge.contradiction_members", ["contradiction_set_id", "atom_id"], rows)

    async def get_contradiction_set(self, contradiction_set_id: str) -> JsonDict | None:
        return await self.pg.fetch_one("knowledge.contradiction_sets", {"contradiction_set_id": contradiction_set_id})

    async def create_evidence_bundle(self, bundle: JsonDict, persist: bool = False) -> None:
        bundle_id = bundle["bundle_id"]
        await self.redis_runtime.set_active_state(f"bundle:active:{bundle_id}", bundle, ttl_s=86400)
        if not persist: return
        await self.pg.upsert_row("knowledge.evidence_bundles", "bundle_id", bundle)
        role_buckets = bundle.get("role_buckets", {})
        bundle_atoms: list[JsonDict] = []
        for role_bucket, atom_ids in role_buckets.items():
            for index, atom_id in enumerate(atom_ids):
                bundle_atoms.append({
                    "bundle_id": bundle_id, "atom_id": atom_id, "role_bucket": role_bucket, "position_index": index
                })
        if bundle_atoms: await self.pg.bulk_upsert("knowledge.bundle_atoms", ["bundle_id", "atom_id"], bundle_atoms)

    async def get_evidence_bundle(self, bundle_id: str) -> JsonDict | None:
        active = await self.redis_runtime.get_active_state(f"bundle:active:{bundle_id}")
        if active is not None: return active
        return await self.pg.fetch_one("knowledge.evidence_bundles", {"bundle_id": bundle_id})

    # =====================================================
    # AuthorityStore
    # =====================================================

    async def upsert_authority_record(self, record: JsonDict) -> None:
        await self.pg.upsert_row("authority.authority_records", "authority_record_id", record)
        await self.index_authority_record(record)
        await self.redis_cache.cache_hot_object("authority", record["authority_record_id"], record, ttl_s=3600)

    async def get_authority_record(self, authority_record_id: str) -> JsonDict | None:
        cached = await self.redis_cache.get_hot_object("authority", authority_record_id)
        if cached is not None: return cached
        row = await self.pg.fetch_one("authority.authority_records", {"authority_record_id": authority_record_id})
        if row is not None: await self.redis_cache.cache_hot_object("authority", authority_record_id, row, ttl_s=3600)
        return row

    async def list_authority_records(self, topic_id: str | None = None, domain_profile_id: str | None = None) -> list[JsonDict]:
        where: JsonDict = {}
        if topic_id is not None: where["topic_id"] = topic_id
        if domain_profile_id is not None: where["domain_profile_id"] = domain_profile_id
        return await self.pg.fetch_many("authority.authority_records", where=where or None, order_by="updated_at DESC")

    async def set_authority_core_atoms(self, authority_record_id: str, rows: Sequence[JsonDict]) -> None:
        await self.pg.delete_where("authority.authority_core_atoms", {"authority_record_id": authority_record_id})
        if rows:
            payload = [dict(r, authority_record_id=authority_record_id) for r in rows]
            await self.pg.bulk_insert("authority.authority_core_atoms", payload)

    async def set_authority_related_records(self, authority_record_id: str, rows: Sequence[JsonDict]) -> None:
        await self.pg.delete_where("authority.authority_related_records", {"authority_record_id": authority_record_id})
        if rows:
            payload = [dict(r, authority_record_id=authority_record_id) for r in rows]
            await self.pg.bulk_insert("authority.authority_related_records", payload)

    async def set_authority_advisories(self, authority_record_id: str, rows: Sequence[JsonDict]) -> None:
        await self.pg.delete_where("authority.authority_advisories", {"authority_record_id": authority_record_id})
        if rows:
            payload = [dict(r, authority_record_id=authority_record_id) for r in rows]
            await self.pg.bulk_insert("authority.authority_advisories", payload)

    async def store_synthesis_artifact(self, artifact: JsonDict) -> None:
        await self.pg.upsert_row("authority.synthesis_artifacts", "artifact_id", artifact)
        await self.index_synthesis_artifact(artifact)
        await self.redis_runtime.set_active_state(f"synth:active:{artifact['artifact_id']}", artifact, ttl_s=86400)

    async def store_synthesis_sections(self, sections: Sequence[JsonDict]) -> None:
        if not sections: return
        await self.pg.bulk_upsert("authority.synthesis_sections", ["artifact_id", "section_name"], list(sections))

    async def store_synthesis_citations(self, citations: Sequence[JsonDict]) -> None:
        if not citations: return
        await self.pg.bulk_insert("authority.synthesis_citations", list(citations))

    async def get_synthesis_artifact(self, artifact_id: str) -> JsonDict | None:
        active = await self.redis_runtime.get_active_state(f"synth:active:{artifact_id}")
        if active is not None: return active
        return await self.pg.fetch_one("authority.synthesis_artifacts", {"artifact_id": artifact_id})

    async def list_synthesis_artifacts(self, authority_record_id: str, artifact_type: str | None = None) -> list[JsonDict]:
        where: JsonDict = {"authority_record_id": authority_record_id}
        if artifact_type is not None: where["artifact_type"] = artifact_type
        return await self.pg.fetch_many("authority.synthesis_artifacts", where=where, order_by="updated_at DESC")

    async def ingest_source(self, source: JsonDict, text_content: str) -> str:
        """Atomic ingestion of a source across the V3 triad."""
        # uuid and hashlib imported at module level

        # 1. Create Text Reference (The Blob)
        blob_id = str(uuid.uuid4())
        await self.pg.insert_row("corpus.text_refs", {
            "blob_id": blob_id,
            "inline_text": text_content,
            "byte_size": len(text_content.encode())
        })

        # 2. Canonical Store (Postgres)
        source_id = source.get("source_id") or str(uuid.uuid4())
        source["source_id"] = source_id
        source["content_hash"] = hashlib.md5(text_content.encode()).hexdigest()
        source["status"] = "fetched"

        # Map fields to match V3 schema in a single complete row
        pg_row = {
            "source_id": source_id,
            "mission_id": source["mission_id"],
            "topic_id": source["topic_id"],
            "url": source["url"],
            "normalized_url": source.get("normalized_url", source["url"]),
            "normalized_url_hash": source.get("normalized_url_hash", source["content_hash"]),
            "domain": source.get("domain"),
            "title": source.get("title"),
            "source_class": source.get("source_class", "web"),
            "content_hash": source["content_hash"],
            "canonical_text_ref": blob_id,
            "status": "fetched",
            "metadata_json": json.dumps(source.get("metadata", {}))
        }

        await self.pg.upsert_row("corpus.sources", ["mission_id", "normalized_url_hash"], pg_row)

        # 3. Create Chunks (V3 Lineage Bridge)
        # Import chunking function lazily to avoid circular imports
        from src.research.archivist.chunker import chunk_text
        chunk_strings = chunk_text(text_content)

        chunk_rows = []
        for idx, chunk_text_str in enumerate(chunk_strings):
            chunk_id = str(uuid.uuid4())
            chunk_hash = hashlib.md5(chunk_text_str.encode()).hexdigest()
            chunk_rows.append({
                "chunk_id": chunk_id,
                "source_id": source_id,
                "mission_id": source["mission_id"],
                "topic_id": source["topic_id"],
                "chunk_index": idx,
                "chunk_hash": chunk_hash,
                "inline_text": chunk_text_str,
                "text_ref": blob_id,
                "metadata_json": json.dumps({
                    "token_count": len(chunk_text_str.split()),  # approximate
                    "chunk_size": len(chunk_text_str)
                })
            })

        await self.create_chunks(chunk_rows)

        # 4. Hot Cache
        await self.redis_cache.cache_hot_object("source", source_id, pg_row, ttl_s=3600)

        return source_id

    # =====================================================
    # ApplicationStore
    # =====================================================

    async def create_application_query(self, query: JsonDict) -> None:
        await self.pg.insert_row("application.application_queries", query)
        await self.redis_runtime.set_active_state(f"aq:active:{query['application_query_id']}", query, ttl_s=86400)

    async def get_application_query(self, application_query_id: str) -> JsonDict | None:
        active = await self.redis_runtime.get_active_state(f"aq:active:{application_query_id}")
        if active is not None: return active
        return await self.pg.fetch_one("application.application_queries", {"application_query_id": application_query_id})

    async def store_application_output(self, output: JsonDict) -> None:
        await self.pg.insert_row("application.application_outputs", output)

    async def bind_application_evidence(self, application_query_id: str, rows: Sequence[JsonDict]) -> None:
        if not rows: return
        payload = [dict(r, application_query_id=application_query_id) for r in rows]
        await self.pg.bulk_upsert("application.application_evidence", ["application_query_id", "authority_record_id", "atom_id", "bundle_id"], payload)

    # =====================================================
    # RuntimeStore
    # =====================================================

    async def enqueue_job(self, queue_name: str, payload: JsonDict) -> None:
        await self.redis_queue.enqueue_job(queue_name, payload)

    async def dequeue_job(self, queue_name: str, timeout_s: int = 0) -> JsonDict | None:
        return await self.redis_queue.dequeue_job(queue_name, timeout_s=timeout_s)

    async def schedule_retry(self, queue_name: str, payload: JsonDict, when_epoch_s: int) -> None:
        await self.redis_queue.schedule_retry(queue_name, payload, when_epoch_s)

    async def move_due_retries(self, queue_name: str, now_epoch_s: int) -> int:
        return await self.redis_queue.move_due_retries(queue_name, now_epoch_s)

    async def acquire_lock(self, key: str, ttl_s: int) -> LockHandle | None:
        return await self.redis_runtime.acquire_lock(key, ttl_s)

    async def refresh_lock(self, handle: LockHandle, ttl_s: int) -> LockHandle | None:
        return await self.redis_runtime.refresh_lock(handle, ttl_s)

    async def release_lock(self, handle: LockHandle) -> None:
        await self.redis_runtime.release_lock(handle)

    async def set_active_state(self, key: str, payload: JsonDict, ttl_s: int | None = None) -> None:
        await self.redis_runtime.set_active_state(key, payload, ttl_s)

    async def get_active_state(self, key: str) -> JsonDict | None:
        return await self.redis_runtime.get_active_state(key)

    async def delete_active_state(self, key: str) -> None:
        await self.redis_runtime.delete_active_state(key)

    async def cache_hot_object(self, kind: str, object_id: str, payload: JsonDict, ttl_s: int) -> None:
        await self.redis_cache.cache_hot_object(kind, object_id, payload, ttl_s)

    async def get_hot_object(self, kind: str, object_id: str) -> JsonDict | None:
        return await self.redis_cache.get_hot_object(kind, object_id)

    async def invalidate_hot_object(self, kind: str, object_id: str) -> None:
        await self.redis_cache.invalidate_hot_object(kind, object_id)

    # =====================================================
    # SemanticIndexStore
    # =====================================================

    async def index_chunk(self, chunk: JsonDict) -> None:
        document = self.projection.build_chunk_document(chunk)
        metadata = self.projection.build_chunk_metadata(chunk)
        await self.chroma.index_document("corpus_chunks", chunk["chunk_id"], document, metadata)

    async def index_chunks(self, chunks: Sequence[JsonDict]) -> None:
        rows = []
        for chunk in chunks:
            rows.append((chunk["chunk_id"], self.projection.build_chunk_document(chunk), self.projection.build_chunk_metadata(chunk)))
        if rows: await self.chroma.index_documents("corpus_chunks", rows)

    async def index_atom(self, atom: JsonDict) -> None:
        document = self.projection.build_atom_document(atom)
        metadata = self.projection.build_atom_metadata(atom)
        await self.chroma.index_document("knowledge_atoms", atom["atom_id"], document, metadata)

    async def index_authority_record(self, record: JsonDict) -> None:
        document = self.projection.build_authority_record_document(record)
        metadata = self.projection.build_authority_record_metadata(record)
        await self.chroma.index_document("authority_records", record["authority_record_id"], document, metadata)

    async def index_synthesis_artifact(self, artifact: JsonDict) -> None:
        document = self.projection.build_synthesis_artifact_document(artifact)
        metadata = self.projection.build_synthesis_artifact_metadata(artifact)
        await self.chroma.index_document("synthesis_artifacts", artifact["artifact_id"], document, metadata)

    async def search_chunks(self, query_text: str, where: JsonDict | None = None, limit: int = 20) -> list[SearchHit]:
        return await self.chroma.search("corpus_chunks", query_text, where=where, limit=limit)

    async def search_atoms(self, query_text: str, where: JsonDict | None = None, limit: int = 20) -> list[SearchHit]:
        return await self.chroma.search("knowledge_atoms", query_text, where=where, limit=limit)

    async def search_authority_records(self, query_text: str, where: JsonDict | None = None, limit: int = 10) -> list[SearchHit]:
        return await self.chroma.search("authority_records", query_text, where=where, limit=limit)

    async def search_synthesis_artifacts(self, query_text: str, where: JsonDict | None = None, limit: int = 10) -> list[SearchHit]:
        return await self.chroma.search("synthesis_artifacts", query_text, where=where, limit=limit)

    async def delete_index_object(self, collection: Literal["corpus_chunks", "knowledge_atoms", "authority_records", "synthesis_artifacts"], object_id: str) -> None:
        await self.chroma.delete_document(collection, object_id)

def _utcnow() -> datetime:
    return datetime.now(timezone.utc)
