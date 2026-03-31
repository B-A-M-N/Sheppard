"""
DEPRECATED: This module is dead production code.
Active retriever is at src/research/reasoning/v3_retriever.py.
Active types are at src/research/reasoning/retriever.py.
This file is retained only because tests/retrieval/test_retriever.py imports from it.
Do NOT add new functionality here. Do NOT import this in production code.

V3-specific retriever that queries the V3 knowledge store.

This retriever queries ChromaDB's knowledge_atoms collection and returns
a RoleBasedContext with sequential citation keys. It does not apply any
confidence threshold filtering; all results up to the limit are included.
"""

import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List

from .models import RetrievedItem, RoleBasedContext

logger = logging.getLogger(__name__)


class V3Retriever:
    """
    Retrieves from V3 knowledge store using semantic search over
    knowledge_atoms via the StorageAdapter's Chroma backend.

    The retriever is passive: it returns all matches without filtering
    by confidence scores.
    """

    def __init__(self, adapter):
        """
        Initialize with a storage adapter that provides a chroma.query method.

        Args:
            adapter: An object with attribute `chroma` that has an async
                     query(collection, query_text, where, limit) method.
        """
        self.adapter = adapter

    async def retrieve(
        self,
        query_text: str,
        topic_filter: Optional[str] = None,
        max_results: int = 12
    ) -> RoleBasedContext:
        """
        Perform retrieval against the knowledge_atoms collection.

        Args:
            query_text: The user query string.
            topic_filter: Optional topic ID to restrict results.
            max_results: Maximum number of items to return.

        Returns:
            RoleBasedContext with evidence populated. Other roles (definitions,
            contradictions, etc.) remain empty for this phase.
        """
        where = {}
        if topic_filter:
            where["topic_id"] = topic_filter

        items: List[RetrievedItem] = []

        try:
            result = await self.adapter.chroma.query(
                collection="knowledge_atoms",
                query_text=query_text,
                where=where if where else None,
                limit=max_results
            )
            # Expecting ChromaDB result format:
            # {'documents': [[...]], 'metadatas': [[...]], 'distances': [[...]]}
            if result and result.get('documents') and result['documents'][0]:
                docs = result['documents'][0]
                metas = result['metadatas'][0]
                dists = result['distances'][0]

                for doc, meta, distance in zip(docs, metas, dists):
                    relevance = 1.0 - float(distance)
                    item = RetrievedItem(
                        content=doc,
                        source=meta.get("source_url", "v3_knowledge"),
                        strategy="semantic",
                        knowledge_level=meta.get("knowledge_level", "B"),
                        item_type=meta.get("atom_type", "claim"),
                        relevance_score=relevance,
                        trust_score=meta.get("trust_score", 0.5),
                        recency_days=self._days_since(meta.get("captured_at")),
                        tech_density=meta.get("tech_density", 0.5),
                        citation_key=None,  # assigned later by build_context_block
                        metadata=meta
                    )
                    items.append(item)

                logger.info(f"[V3Retriever] Retrieved {len(items)} items for query.")
            else:
                logger.info("[V3Retriever] No results found.")
        except Exception as e:
            logger.error(f"[V3Retriever] Query failed: {e}", exc_info=True)
            # Re-raise or return empty context; we choose to propagate to let caller handle.
            raise

        ctx = RoleBasedContext()
        ctx.evidence = items
        return ctx

    def build_context_block(
        self,
        ctx: RoleBasedContext,
        project_name: Optional[str] = None,
        show_sources: bool = True
    ) -> str:
        """
        Format the RoleBasedContext into a structured LLM-injectable block.

        Sequential citation keys [A001], [A002], ... are assigned to all items
        in a deterministic order. The order is: definitions, evidence,
        contradictions, project_artifacts, unresolved.

        Args:
            ctx: The populated context.
            project_name: Optional project name (unused currently).
            show_sources: If True, append citation key to each item.

        Returns:
            A formatted string block ready for injection into a system prompt.
        """
        if ctx.is_empty:
            return ""

        # Assign sequential citation keys
        counter = 1
        for item in ctx.all_items:
            item.citation_key = f"[A{counter:03d}]"
            counter += 1

        sections: List[str] = []

        if ctx.definitions:
            sections.append("### Definitions & Key Concepts")
            for item in ctx.definitions:
                cite = f" {item.citation_key}" if show_sources else ""
                name = f"**{item.concept_name}**: " if getattr(item, 'concept_name', None) else ""
                sections.append(f"- {name}{item.content}{cite}")

        if ctx.evidence:
            sections.append("### Supporting Evidence")
            for item in ctx.evidence:
                cite = f" {item.citation_key}" if show_sources else ""
                sections.append(f"- {item.content}{cite}")

        if ctx.contradictions:
            sections.append("### Conflicting Evidence")
            for item in ctx.contradictions:
                cite = f" {item.citation_key}" if show_sources else ""
                sections.append(f"- {item.content}{cite}")

        if ctx.project_artifacts:
            sections.append("### Project-Specific Context")
            for item in ctx.project_artifacts:
                cite = f" {item.citation_key}" if show_sources else ""
                sections.append(f"- {item.content}{cite}")

        if ctx.unresolved:
            sections.append("### Unresolved Questions")
            for item in ctx.unresolved:
                # Unresolved items typically don't need citations
                sections.append(f"- {item.content}")

        return "\n".join(sections)

    def _days_since(self, date_str: Optional[str]) -> int:
        """Calculate days since a timestamp string, or return large default."""
        if not date_str:
            return 9999
        try:
            dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return (datetime.now(timezone.utc) - dt).days
        except Exception:
            return 9999
