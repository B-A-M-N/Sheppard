"""
V3-specific retriever that queries the V3 knowledge store.

This retriever replaces HybridRetriever for V3 activation, ensuring
query operations read from the V3 knowledge.knowledge_atoms and
corpus.chunks via the StorageAdapter.
"""

import asyncio
import logging
import os
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional

from .retriever import (
    RetrievalQuery,
    RoleBasedContext,
    RetrievedItem,
)
from src.core.memory.cmk.runtime import CMKRuntime

logger = logging.getLogger(__name__)

# Enable profiling via environment variable
PROFILE_RETRIEVAL = os.getenv("PROFILE_RETRIEVAL") == "1"


class V3Retriever:
    """
    Retrieves from V3 knowledge store using semantic search over
    knowledge_atoms and chunks via the StorageAdapter's Chroma backend.

    Active retrieval stages:
      Stage 1 (Lexical):    Postgres ILIKE keyword search — runs in parallel with semantic
      Stage 2 (Semantic):   ChromaDB vector search on knowledge_atoms
      Stage 3 (Structural): Graph traversal from authority_record core_atom_ids
      Stage 4 (Re-ranking): Composite score (relevance × trust × recency)
    """

    def __init__(self, adapter, cmk_runtime: Optional[CMKRuntime] = None):
        self.adapter = adapter
        self.cmk_runtime = cmk_runtime

    async def retrieve(self, query: RetrievalQuery) -> RoleBasedContext:
        """
        Run retrieval against V3 knowledge stores.

        Currently uses semantic vector search on knowledge_atoms collection.
        Future: Add lexical prefilter, chunk search, structural retrieval.
        """
        items: List[RetrievedItem] = []

        # Initialize timers
        t_start = t_query_start = t_query_end = t_post_start = t_post_end = 0.0
        if PROFILE_RETRIEVAL:
            t_start = time.perf_counter()

        # Build where clause for mission/topic filtering
        where = {}
        if query.mission_filter:
            where["mission_id"] = query.mission_filter
        elif query.topic_filter:
            where["topic_id"] = query.topic_filter

        # Semantic search on knowledge_atoms (Level B)
        try:
            if PROFILE_RETRIEVAL:
                t_query_start = time.perf_counter()
            result = await self.adapter.chroma.query(
                collection="knowledge_atoms",
                query_text=query.text,
                where=where if where else None,
                limit=query.max_results
            )
            if PROFILE_RETRIEVAL:
                t_query_end = time.perf_counter()

            if result and result.get('documents') and result['documents'][0]:
                logger.info(f"[V3Retriever] Found {len(result['documents'][0])} semantic matches.")

                if PROFILE_RETRIEVAL:
                    t_post_start = time.perf_counter()
                for doc, meta, distance in zip(
                    result['documents'][0],
                    result['metadatas'][0],
                    result['distances'][0]
                ):
                    relevance = 1.0 - distance
                    item = RetrievedItem(
                        content=doc,
                        source=meta.get("source_url", "v3_knowledge"),
                        strategy="semantic",
                        knowledge_level="B",
                        item_type=meta.get("atom_type", "claim"),
                        relevance_score=relevance,
                        trust_score=meta.get("trust_score", 0.5),
                        recency_days=self._days_since(meta.get("captured_at")),
                        tech_density=meta.get("tech_density", 0.5),
                        citation_key=meta.get("citation_key"),
                        metadata=meta
                    )
                    items.append(item)
                if PROFILE_RETRIEVAL:
                    t_post_end = time.perf_counter()
            else:
                logger.info("[V3Retriever] No semantic matches found in Chroma.")
                if PROFILE_RETRIEVAL:
                    t_post_end = time.perf_counter()
        except Exception as e:
            logger.error(f"[V3Retriever] Semantic search failed: {e}", exc_info=True)
            if PROFILE_RETRIEVAL:
                t_query_end = time.perf_counter()
                t_post_end = time.perf_counter()

        # ── FALLBACK: Postgres keyword search when Chroma has too few results ──
        # Stage 1: Lexical search runs in parallel with semantic results — always,
        # not only as a fallback.  Dedup by atom_id so a result from both lanes
        # appears only once (semantic version kept since it carries a distance score).
        try:
            pg_items = await self._postgres_fallback(query.text, where, query.max_results)
            seen_ids = {
                m.get("atom_id")
                for item in items
                for m in [item.metadata]
                if isinstance(m, dict) and m.get("atom_id")
            }
            added = 0
            for pg_item in pg_items:
                pg_id = (pg_item.metadata or {}).get("atom_id")
                if pg_id and pg_id not in seen_ids:
                    items.append(pg_item)
                    seen_ids.add(pg_id)
                    added += 1
            if added:
                logger.info(f"[V3Retriever] Lexical stage: +{added} unique keyword matches")
        except Exception as e:
            logger.warning(f"[V3Retriever] Lexical stage failed: {e}")

        # Stage 2.5: Authority-record semantic search.
        # Pulls synthesized authority summaries into the context as definitions /
        # framing guidance rather than raw atom evidence.
        try:
            authority_items = await self._authority_search(query.text, where, max(2, query.max_results // 4))
        except Exception as e:
            logger.debug(f"[V3Retriever] Authority stage failed: {e}")
            authority_items = []

        try:
            contradiction_items = await self._contradiction_search(where, max(2, query.max_results // 4))
        except Exception as e:
            logger.debug(f"[V3Retriever] Contradiction stage failed: {e}")
            contradiction_items = []

        # Stage 3: Structural — pull authority core_atom_ids for the mission and
        # fetch their immediate neighbours from atom_relationships.  Adds atoms
        # that are authoritative for the topic even if they scored low on
        # semantic distance.  Skips silently when no authority data exists.
        try:
            structural_items = await self._structural_traversal(where, query.max_results // 4)
            if structural_items:
                seen_ids = {
                    (item.metadata or {}).get("atom_id")
                    for item in items
                }
                added = 0
                for s_item in structural_items:
                    s_id = (s_item.metadata or {}).get("atom_id")
                    if s_id and s_id not in seen_ids:
                        items.append(s_item)
                        seen_ids.add(s_id)
                        added += 1
                if added:
                    logger.info(f"[V3Retriever] Structural stage: +{added} authority-graph atoms")
        except Exception as e:
            logger.debug(f"[V3Retriever] Structural stage failed: {e}")

        # Stage 4: Re-rank by composite score — relevance (semantic closeness) ×
        # trust × recency decay.  Ensures high-trust, recent atoms surface first
        # regardless of which retrieval lane found them.
        items = self._rerank(items, query.max_results)
        authority_items = self._rerank(authority_items, 3)

        # Assemble into role-based context
        ctx = RoleBasedContext()
        ctx.definitions = authority_items
        ctx.contradictions = contradiction_items
        ctx.evidence = items

        # Attach profiling data if enabled
        if PROFILE_RETRIEVAL:
            query_ms = (t_query_end - t_query_start) * 1000
            post_ms = (t_post_end - t_query_end) * 1000
            total_ms = (t_post_end - t_start) * 1000
            ctx._profile = {
                "query_ms": query_ms,
                "post_ms": post_ms,
                "total_ms": total_ms
            }

        # For now, definitions, contradictions, project_artifacts, unresolved remain empty
        # They can be populated in later refinements

        # CMK Integration: activate retrieved atoms in working memory
        if hasattr(self, 'cmk_runtime') and self.cmk_runtime:
            V3Retriever.activate_cmk(items, self.cmk_runtime)

        return ctx

    async def retrieve_many(self, queries: List[RetrievalQuery]) -> List[RoleBasedContext]:
        """
        Batch retrieval for multiple queries in one ChromaDB call.
        All queries should share the same filter (mission_id or topic_id).
        Returns list of RoleBasedContext in same order as queries.
        """
        if not queries:
            return []

        # Validate common filter
        first = queries[0]
        filter_type = "mission_id" if first.mission_filter else "topic_id" if first.topic_filter else None
        filter_value = first.mission_filter or first.topic_filter
        if filter_type is None:
            raise ValueError("retrieve_many requires all queries to have either mission_filter or topic_filter")
        for q in queries[1:]:
            other = q.mission_filter or q.topic_filter
            if other != filter_value:
                raise ValueError("All queries in retrieve_many must share the same filter value")

        # Build where clause
        where = {filter_type: filter_value}

        # Prepare batch parameters
        query_texts = [q.text for q in queries]
        limits = [q.max_results for q in queries]
        # Use the max limit among queries to ensure enough results for each
        common_limit = max(limits) if limits else 20

        # Profiling
        t_start = time.perf_counter() if PROFILE_RETRIEVAL else None

        try:
            # Batch query: Chroma returns documents[0], metadatas[0], distances[0] as lists of length N
            result = await self.adapter.chroma.query(
                collection="knowledge_atoms",
                query_texts=query_texts,
                where=where,
                limit=common_limit
            )
            t_end = time.perf_counter() if PROFILE_RETRIEVAL else None
        except Exception as e:
            logger.error(f"[V3Retriever] Batch query failed: {e}", exc_info=True)
            # Return exception contexts? We'll raise and let caller handle
            raise

        # Split results into per-query contexts
        contexts: List[RoleBasedContext] = []
        docs_outer: List[List[str]] = result.get('documents', []) if result else []
        metas_outer: List[List[Dict]] = result.get('metadatas', []) if result else []
        dists_outer: List[List[float]] = result.get('distances', []) if result else []

        N = len(queries)

        # If outer lists are empty, return empty contexts for all queries
        if not docs_outer or len(docs_outer) == 0:
            return [RoleBasedContext() for _ in range(N)]

        # Stage 3: Structural traversal — run once (same filter for all queries)
        structural_items: List[RetrievedItem] = []
        try:
            structural_items = await self._structural_traversal(where, common_limit // 4)
        except Exception as e:
            logger.debug(f"[V3Retriever] Structural stage failed in retrieve_many: {e}")

        authority_items: List[RetrievedItem] = []
        try:
            authority_items = await self._authority_search(query_texts[0], where, max(2, common_limit // 4))
        except Exception as e:
            logger.debug(f"[V3Retriever] Authority stage failed in retrieve_many: {e}")

        contradiction_items: List[RetrievedItem] = []
        try:
            contradiction_items = await self._contradiction_search(where, max(2, common_limit // 4))
        except Exception as e:
            logger.debug(f"[V3Retriever] Contradiction stage failed in retrieve_many: {e}")

        # Build per-query contexts
        for i in range(N):
            items: List[RetrievedItem] = []
            # Get the i-th inner list if available; else empty
            docs = docs_outer[i] if i < len(docs_outer) else []
            metas = metas_outer[i] if i < len(metas_outer) else []
            dists = dists_outer[i] if i < len(dists_outer) else []

            for doc, meta, distance in zip(docs, metas, dists):
                relevance = 1.0 - distance
                item = RetrievedItem(
                    content=doc,
                    source=meta.get("source_url", "v3_knowledge"),
                    strategy="semantic",
                    knowledge_level="B",
                    item_type=meta.get("atom_type", "claim"),
                    relevance_score=relevance,
                    trust_score=meta.get("trust_score", 0.5),
                    recency_days=self._days_since(meta.get("captured_at")),
                    tech_density=meta.get("tech_density", 0.5),
                    citation_key=meta.get("citation_key"),
                    metadata=meta
                )
                items.append(item)

            # Stage 1: Lexical — per-query keyword search
            try:
                pg_items = await self._postgres_fallback(queries[i].text, where, limits[i])
                seen_ids = {
                    (item.metadata or {}).get("atom_id")
                    for item in items
                    if isinstance(item.metadata, dict)
                }
                for pg_item in pg_items:
                    pg_id = (pg_item.metadata or {}).get("atom_id")
                    if pg_id and pg_id not in seen_ids:
                        items.append(pg_item)
                        seen_ids.add(pg_id)
            except Exception as e:
                logger.warning(f"[V3Retriever] Lexical stage failed in retrieve_many[{i}]: {e}")

            # Merge structural results (not yet seen)
            if structural_items:
                seen_ids = {
                    (item.metadata or {}).get("atom_id")
                    for item in items
                    if isinstance(item.metadata, dict)
                }
                for s_item in structural_items:
                    s_id = (s_item.metadata or {}).get("atom_id")
                    if s_id and s_id not in seen_ids:
                        items.append(s_item)
                        seen_ids.add(s_id)

            # Stage 4: Re-rank
            items = self._rerank(items, limits[i])

            ctx = RoleBasedContext()
            ctx.definitions = self._rerank(authority_items, 3)
            ctx.contradictions = contradiction_items
            ctx.evidence = items

            if PROFILE_RETRIEVAL:
                total_ms = (t_end - t_start) * 1000 if t_start and t_end else 0.0
                ctx._profile = {
                    "query_ms": total_ms / N,
                    "post_ms": 0.0,
                    "total_ms": total_ms / N
                }

            contexts.append(ctx)

        return contexts

    async def _authority_search(self, query_text: str, where: dict, limit: int) -> List[RetrievedItem]:
        items: List[RetrievedItem] = []
        if limit <= 0:
            return items

        authority_where = {}
        topic_scope = where.get("topic_id") or where.get("mission_id")
        if topic_scope:
            authority_where["topic_id"] = topic_scope

        result = await self.adapter.chroma.query(
            collection="authority_records",
            query_text=query_text,
            where=authority_where if authority_where else None,
            limit=limit,
        )
        if not result or not result.get("documents") or not result["documents"][0]:
            return items

        for doc, meta, distance in zip(
            result["documents"][0],
            result["metadatas"][0],
            result["distances"][0],
        ):
            item = RetrievedItem(
                content=doc,
                source=f"authority:{meta.get('authority_record_id', 'unknown')}",
                strategy="authority",
                knowledge_level="A",
                item_type="authority",
                relevance_score=1.0 - distance,
                trust_score=float(meta.get("confidence") or 0.7),
                recency_days=self._days_since(meta.get("captured_at")),
                tech_density=0.7,
                citation_key=meta.get("authority_record_id"),
                concept_name=meta.get("maturity"),
                metadata=meta or {},
            )
            items.append(item)

        return items

    async def _contradiction_search(self, where: dict, limit: int) -> List[RetrievedItem]:
        if limit <= 0 or not where or not self.adapter:
            return []

        topic_id = where.get("topic_id") or where.get("mission_id")
        if not topic_id:
            return []

        items: List[RetrievedItem] = []
        async with self.adapter.pg.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT cs.contradiction_set_id,
                       cs.summary,
                       a1.atom_id AS atom_a_id,
                       a1.statement AS atom_a_statement,
                       a2.atom_id AS atom_b_id,
                       a2.statement AS atom_b_statement
                FROM knowledge.contradiction_sets cs
                JOIN knowledge.contradiction_members m1
                  ON m1.contradiction_set_id = cs.contradiction_set_id
                JOIN knowledge.knowledge_atoms a1 ON a1.atom_id = m1.atom_id
                JOIN knowledge.contradiction_members m2
                  ON m2.contradiction_set_id = cs.contradiction_set_id
                 AND m2.atom_id > m1.atom_id
                JOIN knowledge.knowledge_atoms a2 ON a2.atom_id = m2.atom_id
                WHERE cs.topic_id = $1
                  AND cs.resolution_status = 'unresolved'
                LIMIT $2
                """,
                topic_id,
                limit,
            )

        for row in rows:
            summary = row["summary"] or "Unresolved contradiction"
            content = f"{summary}: {row['atom_a_statement']} VS {row['atom_b_statement']}"
            items.append(
                RetrievedItem(
                    content=content,
                    source=f"contradiction:{row['contradiction_set_id']}",
                    strategy="contradiction",
                    knowledge_level="B",
                    item_type="contradiction",
                    relevance_score=0.75,
                    trust_score=0.7,
                    recency_days=9999,
                    tech_density=0.6,
                    is_contradiction=True,
                    citation_key=row["contradiction_set_id"],
                    metadata={
                        "contradiction_set_id": row["contradiction_set_id"],
                        "atom_a_id": row["atom_a_id"],
                        "atom_b_id": row["atom_b_id"],
                    },
                )
            )
        return items


    async def _structural_traversal(self, where: dict, limit: int) -> List[RetrievedItem]:
        """Stage 3: Fetch atoms anchored in the authority graph.

        1. Find the authority record for the mission/topic.
        2. Pull core_atom_ids from its atom_layer_json.
        3. Expand one hop via atom_relationships to include related atoms.
        4. Return those atoms as RetrievedItems with strategy='structural'.
        """
        if not where or not self.adapter:
            return []

        topic_id = where.get("topic_id") or where.get("mission_id")
        if not topic_id:
            return []

        items: List[RetrievedItem] = []

        async with self.adapter.pg.pool.acquire() as conn:
            # 1. Find authority record for this topic
            auth_row = await conn.fetchrow(
                """
                SELECT authority_record_id,
                       atom_layer_json -> 'core_atom_ids' AS core_ids
                FROM authority.authority_records
                WHERE topic_id = $1
                  AND atom_layer_json -> 'core_atom_ids' != '[]'::jsonb
                LIMIT 1
                """,
                topic_id,
            )
            if not auth_row or not auth_row["core_ids"]:
                return []

            import json as _json
            core_ids: list = _json.loads(auth_row["core_ids"]) if isinstance(auth_row["core_ids"], str) else auth_row["core_ids"]
            if not core_ids:
                return []

            # 2. Expand one hop via atom_relationships
            expanded_ids = list(core_ids)
            if core_ids:
                neighbour_rows = await conn.fetch(
                    """
                    SELECT DISTINCT related_atom_id
                    FROM knowledge.atom_relationships
                    WHERE atom_id = ANY($1::text[])
                    LIMIT $2
                    """,
                    core_ids,
                    limit * 2,
                )
                for r in neighbour_rows:
                    nid = r["related_atom_id"]
                    if nid not in expanded_ids:
                        expanded_ids.append(nid)

            # 3. Fetch atoms — cap at limit
            atom_rows = await conn.fetch(
                """
                SELECT atom_id, statement, atom_type, confidence, importance,
                       topic_id, created_at
                FROM knowledge.knowledge_atoms
                WHERE atom_id = ANY($1::text[])
                LIMIT $2
                """,
                expanded_ids[:limit * 2],
                limit,
            )

        for row in atom_rows:
            is_core = row["atom_id"] in core_ids
            item = RetrievedItem(
                content=row["statement"] or "",
                source=f"authority:{topic_id[:8]}",
                strategy="structural",
                knowledge_level="A" if is_core else "B",
                item_type=row["atom_type"] or "claim",
                relevance_score=float(row["importance"] or 0.6),
                trust_score=float(row["confidence"] or 0.7),
                recency_days=self._days_since(
                    row["created_at"].isoformat() if row["created_at"] else None
                ),
                metadata={
                    "atom_id": row["atom_id"],
                    "atom_type": row["atom_type"],
                    "is_core_atom": is_core,
                    "topic_id": row["topic_id"],
                },
            )
            items.append(item)

        return items

    def _rerank(self, items: List[RetrievedItem], limit: int) -> List[RetrievedItem]:
        """Stage 4: Composite re-ranking.

        Score = relevance × 0.60 + trust × 0.25 + recency_factor × 0.15
        recency_factor decays from 1.0 (today) toward 0.0 over ~1 year.
        """
        def _score(item: RetrievedItem) -> float:
            relevance = max(0.0, min(1.0, item.relevance_score or 0.5))
            trust     = max(0.0, min(1.0, item.trust_score or 0.5))
            days      = item.recency_days if item.recency_days is not None else 9999
            recency   = 1.0 / (1.0 + days / 365.0)
            return relevance * 0.60 + trust * 0.25 + recency * 0.15

        return sorted(items, key=_score, reverse=True)[:limit]

    def _days_since(self, date_str: Optional[str]) -> int:
        """Calculate days since a timestamp string, or return large default."""
        if not date_str:
            return 9999
        try:
            # Handle ISO format with or without timezone
            dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return (datetime.now(timezone.utc) - dt).days
        except Exception:
            return 9999

    def build_context_block(
        self,
        ctx: RoleBasedContext,
        project_name: Optional[str] = None,
        show_sources: bool = True,
    ) -> str:
        """
        Formats the role-based context into a structured LLM-injectable block.
        Identical format to HybridRetriever for compatibility.
        """
        if ctx.is_empty:
            return ""

        sections = []

        if ctx.definitions:
            sections.append("### Definitions & Key Concepts")
            for item in ctx.definitions:
                name = f"**{item.concept_name}**: " if item.concept_name else ""
                cite = f" {item.citation_key}" if item.citation_key and show_sources else ""
                sections.append(f"- {name}{item.content}{cite}")

        if ctx.evidence:
            sections.append("\n### Supporting Evidence")
            for item in ctx.evidence:
                cite = f" `{item.citation_key}`" if item.citation_key and show_sources else ""
                sections.append(f"- {item.content}{cite}")

        if ctx.contradictions:
            sections.append("\n### Conflicting Evidence")
            for item in ctx.contradictions:
                cite = f" `{item.citation_key}`" if item.citation_key and show_sources else ""
                sections.append(f"- {item.content}{cite}")

        if ctx.project_artifacts:
            sections.append("\n### Project-Specific Context")
            for item in ctx.project_artifacts:
                cite = f" `{item.citation_key}`" if item.citation_key and show_sources else ""
                sections.append(f"- {item.content}{cite}")

        if ctx.unresolved:
            sections.append("\n### Unresolved Questions")
            for item in ctx.unresolved:
                sections.append(f"- {item.content}")

        return "\n".join(sections)

    async def _postgres_fallback(self, query_text: str, where: dict, limit: int) -> List[RetrievedItem]:
        """Keyword search fallback when Chroma has too few results."""
        items: List[RetrievedItem] = []
        query_words = [w for w in query_text.split() if len(w) > 2]
        
        async with self.adapter.pg.pool.acquire() as conn:
            conditions = []
            params = []
            for i, word in enumerate(query_words[:5]):
                conditions.append(f"(LOWER(k.statement) LIKE ${i+1} OR LOWER(k.title) LIKE ${i+1})")
                params.append(f"%{word.lower()}%")
            
            where_clauses = []
            if where:
                for k, v in where.items():
                    param_idx = len(params) + 1
                    where_clauses.append(f"k.{k} = ${param_idx}")
                    params.append(v)
            
            sql = f"""
                SELECT k.atom_id, k.statement, k.title, k.atom_type,
                       k.confidence, k.importance, k.novelty, k.created_at,
                       m.title as mission_title
                FROM knowledge.knowledge_atoms k
                LEFT JOIN mission.research_missions m ON k.mission_id = m.mission_id
                WHERE ({' OR '.join(conditions)})
                {'AND ' + ' AND '.join(where_clauses) if where_clauses else ''}
                ORDER BY k.confidence DESC, k.importance DESC
                LIMIT ${len(params)+1}
            """
            params.append(limit)
            
            rows = await conn.fetch(sql, *params)
            
            for row in rows:
                item = RetrievedItem(
                    content=row['statement'] or row['title'] or '',
                    source=f"pg:{row['mission_title'] or 'unknown'}",
                    strategy="keyword",
                    knowledge_level="B",
                    item_type=row['atom_type'] or 'claim',
                    relevance_score=float(row['confidence'] or 0.5),
                    trust_score=float(row['confidence'] or 0.5),
                    recency_days=self._days_since(str(row['created_at']) if row['created_at'] else None),
                    tech_density=0.5,
                    metadata={
                        "atom_id": row['atom_id'],
                        "atom_type": row['atom_type'],
                        "importance": float(row['importance'] or 0.5),
                        "novelty": float(row['novelty'] or 0.5),
                        "mission_title": row['mission_title'],
                    }
                )
                items.append(item)

        return items

    @staticmethod
    def activate_cmk(atoms: List[RetrievedItem], cmk_runtime: Optional[CMKRuntime]):
        """
        Activate retrieved atoms in CMK working memory.
        Call this after retrieval to boost working memory activation.
        """
        if not cmk_runtime or not atoms:
            return

        import asyncio
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            return

        async def _activate():
            for item in atoms:
                atom_id = item.metadata.get("atom_id") if hasattr(item, 'metadata') and isinstance(item.metadata, dict) else None
                if atom_id:
                    await cmk_runtime.activate_atom(atom_id, amount=0.1)

        try:
            loop.run_until_complete(_activate())
        except Exception:
            pass
