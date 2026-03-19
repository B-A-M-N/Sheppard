"""
memory/manager.py — Sheppard V2 Memory Manager

Central coordinator for knowledge persistence.
Manages:
  - Level A (Sources) in raw Postgres
  - Level B, C, D in both Postgres (structured) and ChromaDB (semantic)
  - Concept Graph (recursive relationships)
  - Project Artifacts
  - Meta-memory (system self-improvement)
"""

import asyncio
import logging
import os
import hashlib
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Union

import asyncpg
from chromadb import PersistentClient
from chromadb.config import Settings as ChromaSettings

from src.config.settings import settings
from src.memory.models import Memory, MemorySearchResult
from src.llm.client import OllamaClient

logger = logging.getLogger(__name__)

class MemoryManager:
    """
    Advanced multi-layered memory manager for Sheppard V2.
    Uses Postgres for structured relational data and ChromaDB for semantic retrieval.
    """

    def __init__(self):
        self.pg_pool: Optional[asyncpg.Pool] = None
        self.chroma: Optional[PersistentClient] = None
        self.ollama: Optional[OllamaClient] = None
        self._initialized = False
        
        # Collections map
        self._collections = {}

    async def initialize(self) -> None:
        """Initialize Postgres and ChromaDB connections."""
        if self._initialized:
            return

        try:
            # 1. Connect to Postgres
            # Using PGPASSWORD env or settings
            dsn = os.getenv("POSTGRES_DSN", "postgresql://sheppard:1234@localhost:5432/semantic_memory")
            self.pg_pool = await asyncpg.create_pool(dsn=dsn, min_size=5, max_size=20)
            
            # 2. Connect to ChromaDB
            persist_dir = settings.CHROMADB_PERSIST_DIRECTORY or "./data/chromadb"
            self.chroma = PersistentClient(path=persist_dir)
            
            # 3. Pre-load collections
            for name in ["knowledge_atoms", "thematic_syntheses", "advisory_briefs", "project_artifacts"]:
                self._collections[name] = self.chroma.get_or_create_collection(
                    name=name,
                    metadata={"hnsw:space": "cosine"}
                )

            self._initialized = True
            logger.info("[Memory] Sheppard V2 Memory Manager initialized")
        except Exception as e:
            logger.error(f"[Memory] Initialization failed: {e}")
            raise

    def set_ollama_client(self, client: OllamaClient) -> None:
        self.ollama = client

    async def cleanup(self) -> None:
        if self.pg_pool:
            await self.pg_pool.close()
        self._initialized = False

    # ────────────────────────────────────────────────────────────
    # SECTION 1: TOPIC + SESSION
    # ────────────────────────────────────────────────────────────

    async def create_topic(self, name: str, description: str) -> str:
        """Create a new topic container. Returns topic_id (UUID)."""
        async with self.pg_pool.acquire() as conn:
            row = await conn.fetchrow(
                "INSERT INTO topics (name, description) VALUES ($1, $2) "
                "ON CONFLICT (name) DO UPDATE SET description = $2 "
                "RETURNING id",
                name, description
            )
            return str(row['id'])

    async def update_topic_status(self, topic_id: str, status: str) -> None:
        async with self.pg_pool.acquire() as conn:
            await conn.execute(
                "UPDATE topics SET crawl_status = $1, last_updated_at = NOW() WHERE id = $2",
                status, uuid.UUID(topic_id)
            )

    async def create_session(self, topic_id: str, seed_query: str, ceiling_bytes: int, **kwargs) -> str:
        async with self.pg_pool.acquire() as conn:
            row = await conn.fetchrow(
                "INSERT INTO crawl_sessions (topic_id, seed_query, ceiling_bytes, academic_only) "
                "VALUES ($1, $2, $3, $4) RETURNING id",
                uuid.UUID(topic_id), seed_query, ceiling_bytes, kwargs.get('academic_only', False)
            )
            return str(row['id'])

    async def get_topic_size(self, topic_name: str) -> int:
        """Get current raw bytes for a topic."""
        async with self.pg_pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT raw_bytes_total FROM topics WHERE name = $1",
                topic_name
            )
            return row['raw_bytes_total'] if row else 0

    # ────────────────────────────────────────────────────────────
    # SECTION 2: LEVEL A — SOURCES
    # ────────────────────────────────────────────────────────────

    async def store_source(self, topic_id: str, **data) -> str:
        """Store a raw crawled source."""
        async with self.pg_pool.acquire() as conn:
            # We use content_hash for dedup
            content_hash = data.get('checksum') or hashlib.md5(data['content'].encode()).hexdigest()
            
            row = await conn.fetchrow(
                """
                INSERT INTO sources (topic_id, url, title, domain, source_type, raw_bytes, content_hash, raw_file_path)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                ON CONFLICT (topic_id, content_hash) DO UPDATE SET last_captured_at = NOW()
                RETURNING id
                """,
                uuid.UUID(topic_id), data['url'], data.get('title'), data.get('domain'),
                data.get('source_type', 'web'), data.get('raw_bytes', 0), content_hash, data.get('raw_file_path')
            )
            
            # Update topic total
            await conn.execute(
                "UPDATE topics SET raw_bytes_total = raw_bytes_total + $1, source_count = source_count + 1 WHERE id = $2",
                data.get('raw_bytes', 0), uuid.UUID(topic_id)
            )
            return str(row['id'])

    async def get_uncondensed_sources(self, topic_id: str, limit: int = 10) -> List[Dict]:
        async with self.pg_pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT id, topic_id, url, title, raw_file_path, raw_bytes FROM sources "
                "WHERE topic_id = $1 AND condensed = FALSE LIMIT $2",
                uuid.UUID(topic_id), limit
            )
            # Load content from disk
            results = []
            for r in rows:
                d = dict(r)
                if d['raw_file_path'] and os.path.exists(d['raw_file_path']):
                    with open(d['raw_file_path'], 'r') as f:
                        d['content'] = f.read()
                results.append(d)
            return results

    async def mark_sources_condensed(self, source_ids: List[Union[str, Any]]) -> None:
        async with self.pg_pool.acquire() as conn:
            # asyncpg sometimes returns UUID objects directly, or strings
            import uuid
            uuids = []
            for sid in source_ids:
                if isinstance(sid, uuid.UUID):
                    uuids.append(sid)
                else:
                    uuids.append(uuid.UUID(str(sid)))
            await conn.execute("UPDATE sources SET condensed = TRUE WHERE id = ANY($1)", uuids)

    # ────────────────────────────────────────────────────────────
    # SECTION 3: LEVEL B — ATOMS
    # ────────────────────────────────────────────────────────────

    async def store_atom(self, topic_id: str, session_id: Optional[str], **data) -> str:
        async with self.pg_pool.acquire() as conn:
            import uuid
            row = await conn.fetchrow(
                """
                INSERT INTO knowledge_atoms (topic_id, session_id, atom_type, content, source_ids, confidence)
                VALUES ($1, $2, $3, $4, $5, $6) RETURNING id
                """,
                uuid.UUID(str(topic_id)), 
                uuid.UUID(str(session_id)) if session_id else None,
                data['atom_type'], data['content'], 
                [uuid.UUID(str(sid)) for sid in data['source_ids']],
                data.get('confidence', 0.7)
            )
            atom_id = str(row['id'])
            
            # Update topic count
            await conn.execute("UPDATE topics SET atom_count = atom_count + 1 WHERE id = $1", uuid.UUID(str(topic_id)))
            return atom_id

    async def update_atom_chroma_id(self, atom_id: str, chroma_id: str) -> None:
        async with self.pg_pool.acquire() as conn:
            await conn.execute("UPDATE knowledge_atoms SET chroma_chunk_id = $1 WHERE id = $2", chroma_id, uuid.UUID(str(atom_id)))

    # ────────────────────────────────────────────────────────────
    # SECTION 4: LEVEL C/D — SYNTHESIS & BRIEF
    # ────────────────────────────────────────────────────────────

    async def store_synthesis(self, topic_id: str, session_id: Optional[str], **data) -> str:
        async with self.pg_pool.acquire() as conn:
            import uuid
            row = await conn.fetchrow(
                """
                INSERT INTO thematic_syntheses (topic_id, session_id, synthesis_type, title, content, source_atom_ids)
                VALUES ($1, $2, $3, $4, $5, $6) RETURNING id
                """,
                uuid.UUID(str(topic_id)), 
                uuid.UUID(str(session_id)) if session_id else None,
                data['synthesis_type'], data['title'], data['content'], 
                [uuid.UUID(str(aid)) for aid in data.get('source_atom_ids', [])]
            )
            return str(row['id'])

    async def update_synthesis_chroma_id(self, synthesis_id: str, chroma_id: str) -> None:
        async with self.pg_pool.acquire() as conn:
            await conn.execute("UPDATE thematic_syntheses SET chroma_chunk_id = $1 WHERE id = $2", chroma_id, uuid.UUID(synthesis_id))

    async def store_advisory_brief(self, topic_id: str, session_id: Optional[str], **data) -> str:
        async with self.pg_pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO advisory_briefs (topic_id, session_id, what_matters, what_is_contested, what_is_likely_true, what_needs_testing, how_applies_to_projects, open_questions)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8) RETURNING id
                """,
                uuid.UUID(topic_id), uuid.UUID(session_id) if session_id else None,
                data.get('what_matters'), data.get('what_is_contested'), data.get('what_is_likely_true'),
                data.get('what_needs_testing'), data.get('how_applies_to_projects'), data.get('open_questions')
            )
            return str(row['id'])

    # ────────────────────────────────────────────────────────────
    # SECTION 5: RETRIEVAL
    # ────────────────────────────────────────────────────────────

    async def lexical_search_atoms(self, terms: List[str], topic_id: Optional[str] = None, limit: int = 10) -> List[Dict]:
        """PG_TRGM powered lexical search for exact terms."""
        async with self.pg_pool.acquire() as conn:
            query = """
                SELECT content, atom_type, confidence, similarity(content, $1) as score
                FROM knowledge_atoms
                WHERE content % $1
            """
            params = [" ".join(terms)]
            if topic_id:
                query += " AND topic_id = $2::uuid"
                params.append(uuid.UUID(topic_id))
            
            # Dynamically set the limit parameter index
            limit_idx = 2 if not topic_id else 3
            query += f" ORDER BY score DESC LIMIT ${limit_idx}"
            params.append(limit)
            
            rows = await conn.fetch(query, *params)
            return [dict(r) for r in rows]

    async def chroma_query(self, collection: str, query_text: str, n_results: int = 5, where: Optional[Dict] = None) -> Dict:
        coll = self._collections.get(collection)
        if not coll:
            # Try to get dynamically
            coll = self.chroma.get_collection(name=collection)
            self._collections[collection] = coll
            
        return coll.query(
            query_texts=[query_text],
            n_results=n_results,
            where=where
        )

    async def store_chunk(self, collection: str, topic_id: str, doc_id: str, content: str, embedding: List[float], metadata: Dict) -> str:
        coll = self._collections.get(collection)
        chunk_id = f"chk_{uuid.uuid4().hex[:12]}"
        
        # Ensure topic_id is in metadata for filtering
        metadata['topic_id'] = topic_id
        metadata['doc_id'] = doc_id
        
        coll.add(
            ids=[chunk_id],
            embeddings=[embedding],
            documents=[content],
            metadatas=[metadata]
        )
        return chunk_id

    # ────────────────────────────────────────────────────────────
    # META-MEMORY & LOGGING
    # ────────────────────────────────────────────────────────────

    async def record_meta_memory(self, **data) -> None:
        async with self.pg_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO meta_memory (entity_type, entity_id, observation_type, score, notes, topic_id, session_id)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                """,
                data['entity_type'], data['entity_id'], data['observation_type'],
                data.get('score'), data.get('notes'), 
                uuid.UUID(data['topic_id']) if data.get('topic_id') else None,
                uuid.UUID(data['session_id']) if data.get('session_id') else None
            )

    async def log_distillation(self, report: Any) -> None:
        async with self.pg_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO distillation_log (topic_id, session_id, trigger_type, level_b_atoms, level_c_syntheses, 
                                            level_b_bytes, level_c_bytes, fidelity_estimate, duration_secs)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                """,
                uuid.UUID(report.topic_id), uuid.UUID(report.session_id) if report.session_id else None,
                report.priority.value, report.atoms_created, report.syntheses_created,
                report.level_b_bytes, report.level_c_bytes, report.fidelity_estimate, report.duration_secs
            )

    # ────────────────────────────────────────────────────────────
    # LEGACY / BACKWARD COMPAT (preserving existing functionality)
    # ────────────────────────────────────────────────────────────

    async def store(self, memory: Union[Memory, Dict[str, Any]], **kwargs) -> str:
        """Original store method — redirects to V2 'general' flow."""
        if isinstance(memory, dict):
            memory = Memory(**memory)
        
        # For simple chitchat/generic data, we use a default topic
        topic_id = await self.create_topic("General", "Generic chat and background knowledge")
        
        # If it has an embedding, use it; else generate
        if not memory.embedding and self.ollama:
            memory.embedding = await self.ollama.generate_embedding(memory.content)
            
        # Store as an 'atom' of type 'claim'
        return await self.store_atom(
            topic_id=topic_id,
            session_id=None,
            atom_type="claim",
            content=memory.content,
            source_ids=[],
            confidence=0.8
        )

    async def search(self, query: str, limit: int = 5, **kwargs) -> List[MemorySearchResult]:
        """Original search method — redirects to V2 hybrid retrieval."""
        # Simple implementation for now to satisfy existing calls
        results = await self.chroma_query("knowledge_atoms", query, n_results=limit)
        
        search_results = []
        if results and results.get('documents'):
            for doc, meta, dist in zip(results['documents'][0], results['metadatas'][0], results['distances'][0]):
                search_results.append(MemorySearchResult(
                    content=doc,
                    relevance_score=1.0 - dist,
                    timestamp=datetime.now().isoformat(),
                    metadata=meta
                ))
        return search_results
