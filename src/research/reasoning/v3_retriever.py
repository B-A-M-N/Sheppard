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

logger = logging.getLogger(__name__)

# Enable profiling via environment variable
PROFILE_RETRIEVAL = os.getenv("PROFILE_RETRIEVAL") == "1"


class V3Retriever:
    """
    Retrieves from V3 knowledge store using semantic search over
    knowledge_atoms and chunks via the StorageAdapter's Chroma backend.

    This is a simplified retriever for V3 activation. Advanced features
    (lexical prefilter, structural traversal, contradiction detection,
    project artifact linking) will be added in later phases.
    """

    def __init__(self, adapter):
        self.adapter = adapter

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
                logger.info("[V3Retriever] No semantic matches found.")
                if PROFILE_RETRIEVAL:
                    t_post_end = time.perf_counter()
        except Exception as e:
            logger.error(f"[V3Retriever] Semantic search failed: {e}", exc_info=True)
            if PROFILE_RETRIEVAL:
                t_query_end = time.perf_counter()
                t_post_end = time.perf_counter()

        # TODO: Stage 1 Lexical prefilter (Postgres ILIKE on atoms)
        # TODO: Stage 3 Structural (graph traversal from core_atom_ids)
        # TODO: Stage 4 Re-ranking with trust, recency, project proximity

        # Assemble into role-based context
        ctx = RoleBasedContext()
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

            ctx = RoleBasedContext()
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
