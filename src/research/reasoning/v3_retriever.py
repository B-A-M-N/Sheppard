"""
V3-specific retriever that queries the V3 knowledge store.

This retriever replaces HybridRetriever for V3 activation, ensuring
query operations read from the V3 knowledge.knowledge_atoms and
corpus.chunks via the StorageAdapter.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional

from .retriever import (
    RetrievalQuery,
    RoleBasedContext,
    RetrievedItem,
)

logger = logging.getLogger(__name__)


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

        # Build where clause for mission/topic filtering
        where = {}
        if query.mission_filter:
            where["mission_id"] = query.mission_filter
        elif query.topic_filter:
            where["topic_id"] = query.topic_filter

        # Semantic search on knowledge_atoms (Level B)
        try:
            result = await self.adapter.chroma.query(
                collection="knowledge_atoms",
                query_text=query.text,
                where=where if where else None,
                limit=query.max_results
            )

            if result and result.get('documents') and result['documents'][0]:
                logger.info(f"[V3Retriever] Found {len(result['documents'][0])} semantic matches.")

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
            else:
                logger.info("[V3Retriever] No semantic matches found.")
        except Exception as e:
            logger.error(f"[V3Retriever] Semantic search failed: {e}", exc_info=True)

        # TODO: Stage 1 Lexical prefilter (Postgres ILIKE on atoms)
        # TODO: Stage 3 Structural (graph traversal from core_atom_ids)
        # TODO: Stage 4 Re-ranking with trust, recency, project proximity

        # Assemble into role-based context
        ctx = RoleBasedContext()
        ctx.evidence = items
        # For now, definitions, contradictions, project_artifacts, unresolved remain empty
        # They can be populated in later refinements

        return ctx

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
