"""
cmk/store.py — Persistence layer for the Cognitive Memory Kernel.

Handles:
  - Redis caching for concepts and embeddings (fast runtime access)
  - Postgres persistence for concepts table (durable storage)

Designed to work alongside Sheppard's existing Postgres/Redis adapters.
"""

import json
import logging
from typing import Dict, Any, List, Optional, Sequence

from .types import CMKAtom, Concept
from .config import CMKConfig

logger = logging.getLogger(__name__)


class CMKStore:
    """
    Persistence layer for CMK data.

    Dual backend:
      - Redis: fast cache for concepts + atom embeddings
      - Postgres: durable storage for concepts table
    """

    def __init__(self, config: CMKConfig, redis_client=None, pg_pool=None):
        """
        Args:
            config: CMK configuration
            redis_client: Redis client (from your existing adapter)
            pg_pool: asyncpg pool (from your existing adapter)
        """
        self.config = config
        self.redis = redis_client
        self.pg_pool = pg_pool

    # ── Concept persistence ──

    async def save_concepts(self, concepts: List[Concept]) -> int:
        """
        Save concepts to Postgres.

        Args:
            concepts: List of Concept nodes to persist

        Returns:
            Number of concepts saved
        """
        if not self.pg_pool:
            logger.debug("[CMKStore] Postgres not available, skipping concept save")
            return 0

        count = 0
        async with self.pg_pool.acquire() as conn:
            for concept in concepts:
                try:
                    await conn.execute(
                        f"""
                        INSERT INTO {self.config.store.concepts_table}
                            (id, name, summary, atom_ids, centroid, reliability, centrality,
                             topic_id, mission_id, relationships)
                        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                        ON CONFLICT (id) DO UPDATE SET
                            name = EXCLUDED.name,
                            summary = EXCLUDED.summary,
                            atom_ids = EXCLUDED.atom_ids,
                            centroid = EXCLUDED.centroid,
                            reliability = EXCLUDED.reliability,
                            centrality = EXCLUDED.centrality,
                            updated_at = NOW()
                        """,
                        concept.id,
                        concept.name,
                        concept.summary,
                        concept.atom_ids,
                        json.dumps(concept.centroid) if concept.centroid else None,
                        concept.reliability,
                        concept.centrality,
                        concept.topic_id or None,
                        concept.mission_id or None,
                        json.dumps(concept.relationships),
                    )
                    count += 1
                except Exception as e:
                    logger.warning(f"[CMKStore] Failed to save concept {concept.id}: {e}")

        # Also cache in Redis
        if self.redis and count > 0:
            await self._cache_concepts(concepts)

        return count

    async def load_concepts(self, topic_id: Optional[str] = None) -> List[Concept]:
        """
        Load concepts from Postgres.

        Args:
            topic_id: Optional topic filter

        Returns:
            List of Concept nodes
        """
        # Try Redis cache first
        if self.redis:
            cached = await self._load_cached_concepts(topic_id)
            if cached:
                return cached

        if not self.pg_pool:
            return []

        try:
            async with self.pg_pool.acquire() as conn:
                query = f"SELECT * FROM {self.config.store.concepts_table}"
                params = []

                if topic_id:
                    query += " WHERE topic_id = $1"
                    params.append(topic_id)

                query += " ORDER BY reliability DESC"

                rows = await conn.fetch(query, *params)
        except Exception as e:
            if "does not exist" in str(e) or "relation" in str(e).lower():
                logger.warning(
                    f"[CMKStore] Table {self.config.store.concepts_table!r} not found in V3 schema — "
                    "CMK will operate on empty concept substrate. "
                    "Run the CMK schema migration to enable persistent concepts."
                )
            else:
                logger.warning(f"[CMKStore] load_concepts failed: {e}")
            return []

        concepts = []
        for row in rows:
            try:
                centroid = json.loads(row["centroid"]) if row.get("centroid") else []
                relationships = json.loads(row["relationships"]) if row.get("relationships") else {
                    "supports": [], "contradicts": [], "refines": [],
                }

                concept = Concept(
                    id=row["id"],
                    name=row["name"],
                    summary=row["summary"],
                    atom_ids=row["atom_ids"] or [],
                    centroid=centroid,
                    reliability=float(row["reliability"] or 0.5),
                    centrality=float(row["centrality"] or 0.5),
                    topic_id=row.get("topic_id", ""),
                    mission_id=row.get("mission_id", ""),
                    relationships=relationships,
                )
                concepts.append(concept)
            except Exception as e:
                logger.warning(f"[CMKStore] Failed to load concept {row.get('id')}: {e}")

        return concepts

    async def load_atoms(
        self,
        atom_ids: Optional[Sequence[str]] = None,
        topic_id: Optional[str] = None,
        mission_id: Optional[str] = None,
        limit: int = 500,
    ) -> List[CMKAtom]:
        """
        Load CMK-compatible atoms from the canonical V3 atom store.

        This backfills the in-memory atom substrate when CMK concepts are loaded
        from Postgres after a restart.
        """
        if not self.pg_pool:
            return []

        clauses: list[str] = []
        params: list[Any] = []
        p = 1

        if atom_ids:
            clauses.append(f"atom_id = ANY(${p}::text[])")
            params.append(list(atom_ids))
            p += 1

        if topic_id:
            clauses.append(f"topic_id = ${p}")
            params.append(topic_id)
            p += 1

        if mission_id:
            clauses.append(f"mission_id = ${p}")
            params.append(mission_id)
            p += 1

        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(limit)

        try:
            async with self.pg_pool.acquire() as conn:
                rows = await conn.fetch(
                    f"""
                    SELECT atom_id, statement, atom_type, confidence, importance, novelty,
                           mission_id, topic_id, metadata_json
                    FROM knowledge.knowledge_atoms
                    {where}
                    ORDER BY created_at DESC
                    LIMIT ${p}
                    """,
                    *params,
                )
        except Exception as e:
            logger.warning(f"[CMKStore] load_atoms failed: {e}")
            return []

        atoms: list[CMKAtom] = []
        for row in rows:
            try:
                atom = CMKAtom.from_knowledge_atom(dict(row))
                embedding = await self.load_atom_embedding(atom.id)
                if embedding:
                    atom.embedding = embedding
                atoms.append(atom)
            except Exception as e:
                logger.warning(f"[CMKStore] Failed to load atom {row.get('atom_id')}: {e}")

        return atoms

    # ── Atom embedding caching ──

    async def cache_atom_embedding(self, atom_id: str, embedding: List[float]) -> bool:
        """Cache an atom's embedding in Redis."""
        if not self.redis or not self.config.store.redis_enabled:
            return False

        try:
            key = f"cmk:embed:{atom_id}"
            await self.redis.set(key, json.dumps(embedding), ex=self.config.store.redis_ttl_seconds)
            return True
        except Exception as e:
            logger.debug(f"[CMKStore] Redis cache failed for {atom_id}: {e}")
            return False

    async def load_atom_embedding(self, atom_id: str) -> Optional[List[float]]:
        """Load an atom's embedding from Redis cache."""
        if not self.redis or not self.config.store.redis_enabled:
            return None

        try:
            key = f"cmk:embed:{atom_id}"
            data = await self.redis.get(key)
            if data:
                return json.loads(data)
        except Exception as e:
            logger.debug(f"[CMKStore] Redis load failed for {atom_id}: {e}")

        return None

    # ── Internal helpers ──

    async def _cache_concepts(self, concepts: List[Concept]) -> bool:
        """Cache concepts in Redis for fast retrieval."""
        if not self.redis:
            return False

        try:
            key = "cmk:concepts:all"
            data = [
                {
                    "id": c.id,
                    "name": c.name,
                    "summary": c.summary,
                    "atom_ids": c.atom_ids,
                    "centroid": c.centroid,
                    "reliability": c.reliability,
                    "centrality": c.centrality,
                    "topic_id": c.topic_id,
                    "mission_id": c.mission_id,
                    "relationships": c.relationships,
                }
                for c in concepts
            ]
            await self.redis.set(key, json.dumps(data), ex=self.config.store.redis_ttl_seconds)
            return True
        except Exception as e:
            logger.debug(f"[CMKStore] Redis concept cache failed: {e}")
            return False

    async def _load_cached_concepts(self, topic_id: Optional[str] = None) -> Optional[List[Concept]]:
        """Load concepts from Redis cache."""
        if not self.redis:
            return None

        try:
            key = "cmk:concepts:all"
            data = await self.redis.get(key)
            if not data:
                return None

            concepts = []
            for item in json.loads(data):
                if topic_id and item.get("topic_id") != topic_id:
                    continue

                concept = Concept(
                    id=item["id"],
                    name=item["name"],
                    summary=item["summary"],
                    atom_ids=item["atom_ids"],
                    centroid=item["centroid"],
                    reliability=item["reliability"],
                    centrality=item["centrality"],
                    topic_id=item.get("topic_id", ""),
                    mission_id=item.get("mission_id", ""),
                    relationships=item.get("relationships", {}),
                )
                concepts.append(concept)

            return concepts
        except Exception as e:
            logger.debug(f"[CMKStore] Redis concept load failed: {e}")
            return None
