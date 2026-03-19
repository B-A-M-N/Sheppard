"""
reasoning/retriever.py  (Revised)

4-stage retrieval stack with role-based context assembly.

Stage order:
  1. Lexical prefilter    — exact/near-exact match for tech names, error strings,
                            library names, acronyms. Fast, runs first.
  2. Semantic retrieval   — ChromaDB vector similarity across all knowledge levels
  3. Structural retrieval — same session, same source cluster, same project subsystem,
                            same concept family
  4. Re-ranking           — scores by: query relevance, source trust, recency,
                            tech density, project proximity, contradiction value

Context is assembled by ROLE, not just top-K score:
  2-3 definitions
  3-5 strongest evidence items
  2 contrasting viewpoints / contradictions
  2 project-linked artifacts
  1-2 unresolved issues

This produces far better reasoning than "top 12 nearest chunks."
"""

import asyncio
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────
# Retrieval data structures
# ──────────────────────────────────────────────────────────────

@dataclass
class RetrievedItem:
    """One item from any retrieval stage, normalized."""
    content: str
    source: str
    strategy: str                           # lexical | semantic | structural | project
    knowledge_level: str = "B"              # A | B | C | D
    item_type: str = "claim"                # atom_type, synthesis_type, or "brief"
    relevance_score: float = 0.0
    trust_score: float = 0.5
    recency_days: int = 9999                # days since captured
    tech_density: float = 0.5              # proxy for technical content richness
    project_proximity: float = 0.0          # 0 if not project-linked
    is_contradiction: bool = False
    citation_key: Optional[str] = None
    concept_name: Optional[str] = None
    metadata: Dict = field(default_factory=dict)

    @property
    def composite_score(self) -> float:
        """
        Re-ranking composite score.
        Weights tuned to prioritize project-linked, high-trust, recent items.
        """
        recency_factor = max(0.2, 1.0 - (self.recency_days / 365))
        return (
            self.relevance_score * 0.35
            + self.trust_score * 0.20
            + recency_factor * 0.10
            + self.tech_density * 0.15
            + self.project_proximity * 0.20
        )


@dataclass
class RetrievalQuery:
    text: str
    project_filter: Optional[str] = None
    topic_filter: Optional[str] = None
    max_results: int = 12
    # Role-based slot sizes
    max_definitions: int = 3
    max_evidence: int = 5
    max_contradictions: int = 2
    max_project_artifacts: int = 2
    max_unresolved: int = 2
    # Stage controls
    lexical_prefilter: bool = True
    graph_depth: int = 2
    knowledge_levels: List[str] = field(
        default_factory=lambda: ["B", "C", "D"]
    )


@dataclass
class RoleBasedContext:
    """The assembled context block, organized by role."""
    definitions: List[RetrievedItem] = field(default_factory=list)
    evidence: List[RetrievedItem] = field(default_factory=list)
    contradictions: List[RetrievedItem] = field(default_factory=list)
    project_artifacts: List[RetrievedItem] = field(default_factory=list)
    unresolved: List[RetrievedItem] = field(default_factory=list)

    @property
    def all_items(self) -> List[RetrievedItem]:
        return (
            self.definitions
            + self.evidence
            + self.contradictions
            + self.project_artifacts
            + self.unresolved
        )

    @property
    def is_empty(self) -> bool:
        return len(self.all_items) == 0


# ──────────────────────────────────────────────────────────────
# Main retriever class
# ──────────────────────────────────────────────────────────────

class HybridRetriever:
    """
    4-stage retriever with role-based context assembly.

    The critical upgrade from v1:
    - Stage 1 (lexical) fires FIRST — catches exact tech names before
      vector search which can miss them (e.g. "mxbai-embed-large", "SOLLOL")
    - Stage 4 (re-rank) scores on 6 signals, not just distance
    - Assembly fills named roles rather than top-K — prevents the LLM
      from getting 12 evidence items with zero definitions or contradictions
    """

    def __init__(self, memory_manager):
        self.memory = memory_manager

    async def retrieve(self, query: RetrievalQuery) -> RoleBasedContext:
        """
        Main entry point. Runs all 4 stages and assembles by role.
        """
        # Stage 1: Lexical prefilter
        lexical_hits: List[RetrievedItem] = []
        if query.lexical_prefilter:
            lexical_hits = await self._stage1_lexical(query)

        # Stage 2 + 3: Semantic + Structural (parallel)
        semantic_task = asyncio.create_task(self._stage2_semantic(query))
        structural_task = asyncio.create_task(self._stage3_structural(query))

        semantic_hits, structural_hits = await asyncio.gather(
            semantic_task, structural_task, return_exceptions=True
        )
        if isinstance(semantic_hits, Exception):
            logger.warning(f"[Retriever] Semantic stage failed: {semantic_hits}")
            semantic_hits = []
        if isinstance(structural_hits, Exception):
            logger.warning(f"[Retriever] Structural stage failed: {structural_hits}")
            structural_hits = []

        # Combine all candidates
        candidates = lexical_hits + semantic_hits + structural_hits

        # Stage 4: Re-rank
        ranked = await self._stage4_rerank(candidates, query)

        # Assemble into role-based context
        context = self._assemble_by_role(ranked, query)

        total = len(context.all_items)
        logger.info(
            f"[Retriever] '{query.text[:50]}' → "
            f"defs:{len(context.definitions)} "
            f"evid:{len(context.evidence)} "
            f"contra:{len(context.contradictions)} "
            f"proj:{len(context.project_artifacts)} "
            f"open:{len(context.unresolved)} "
            f"(total {total})"
        )
        return context

    # ──────────────────────────────────────────────────────────────
    # Stage 1: Lexical Prefilter
    # ──────────────────────────────────────────────────────────────

    async def _stage1_lexical(self, query: RetrievalQuery) -> List[RetrievedItem]:
        """
        Exact and near-exact text search against knowledge_atoms content.
        Critical for: library names, error strings, acronyms, version numbers,
        project names (SOLLOL, FlockParser), specific algorithm names.

        Uses Postgres pg_trgm full-text search — much faster than embedding
        for exact/near-exact lookups.
        """
        try:
            # Extract likely exact-match terms (capitalized, quoted, or hyphenated)
            exact_terms = self._extract_exact_terms(query.text)
            if not exact_terms:
                return []

            # Validate topic_id is a UUID if provided
            topic_id = None
            if query.topic_filter:
                import uuid
                try:
                    if len(str(query.topic_filter)) == 36:
                        topic_id = str(uuid.UUID(str(query.topic_filter)))
                except (ValueError, AttributeError):
                    pass

            results = await self.memory.lexical_search_atoms(
                terms=exact_terms,
                topic_id=topic_id,
                limit=10,
            )

            items = []
            for r in results:
                items.append(RetrievedItem(
                    content=r["content"],
                    source=r.get("source_url", "lexical_match"),
                    strategy="lexical",
                    knowledge_level="B",
                    item_type=r.get("atom_type", "claim"),
                    relevance_score=r.get("similarity", 0.9),   # lexical gets high base relevance
                    trust_score=r.get("trust_score", 0.5),
                    recency_days=r.get("recency_days", 999),
                    tech_density=0.8,                            # lexical hits are usually technical
                    citation_key=r.get("citation_key"),
                    metadata=r,
                ))
            return items

        except Exception as e:
            logger.warning(f"[Stage1] Lexical search failed: {e}")
            return []

    def _extract_exact_terms(self, text: str) -> List[str]:
        """
        Pull likely exact-match terms from the query.
        Looks for: ALL_CAPS, CamelCase, hyphenated-terms, quoted "phrases".
        """
        terms = []
        # Quoted phrases
        terms.extend(re.findall(r'"([^"]+)"', text))
        # CamelCase identifiers
        terms.extend(re.findall(r'\b[A-Z][a-zA-Z]{2,}(?:[A-Z][a-zA-Z]+)+\b', text))
        # ALL_CAPS abbreviations (3+ chars)
        terms.extend(re.findall(r'\b[A-Z]{3,}\b', text))
        # Hyphenated technical terms
        terms.extend(re.findall(r'\b[a-z]+-[a-z]+(?:-[a-z]+)*\b', text))
        # Version strings
        terms.extend(re.findall(r'\bv\d+\.\d+\b', text))

        # Deduplicate, min length 3
        return list({t for t in terms if len(t) >= 3})

    # ──────────────────────────────────────────────────────────────
    # Stage 2: Semantic Retrieval
    # ──────────────────────────────────────────────────────────────

    async def _stage2_semantic(self, query: RetrievalQuery) -> List[RetrievedItem]:
        """
        Vector similarity search across each enabled knowledge level's
        ChromaDB collection. Levels searched:
          "B"  → knowledge_atoms collection
          "C"  → thematic_syntheses collection
          "D"  → advisory_briefs collection
        """
        items = []
        collections = {
            "B": "knowledge_atoms",
            "C": "thematic_syntheses",
            "D": "advisory_briefs",
        }

        tasks = {
            level: self.memory.chroma_query(
                collection=collections[level],
                query_text=query.text,
                n_results=8,
                where={"topic_id": query.topic_filter} if query.topic_filter else None,
            )
            for level in query.knowledge_levels
            if level in collections
        }

        results = await asyncio.gather(*tasks.values(), return_exceptions=True)

        for level, result in zip(tasks.keys(), results):
            if isinstance(result, Exception):
                logger.debug(f"[Stage2] Level {level} query failed: {result}")
                continue
            try:
                for doc, meta, distance in zip(
                    result["documents"][0],
                    result["metadatas"][0],
                    result["distances"][0],
                ):
                    relevance = 1.0 - distance
                    items.append(RetrievedItem(
                        content=doc,
                        source=meta.get("source_url", "chromadb"),
                        strategy="semantic",
                        knowledge_level=level,
                        item_type=meta.get("atom_type") or meta.get("synthesis_type") or "brief",
                        relevance_score=relevance,
                        trust_score=meta.get("trust_score", 0.5),
                        recency_days=self._days_since(meta.get("captured_at")),
                        tech_density=meta.get("tech_density", 0.5),
                        citation_key=meta.get("citation_key"),
                        metadata=meta,
                    ))
            except Exception as e:
                logger.debug(f"[Stage2] Result parse error for level {level}: {e}")

        return items

    # ──────────────────────────────────────────────────────────────
    # Stage 3: Structural Retrieval
    # ──────────────────────────────────────────────────────────────

    async def _stage3_structural(self, query: RetrievalQuery) -> List[RetrievedItem]:
        """
        Retrieves items based on structural relationships rather than
        semantic similarity:
          - Concept graph traversal (related concepts)
          - Project artifact search (if project_filter set)
          - Contradiction retrieval (contested claims)
          - Citation lookup (for "where did this come from?")
        """
        tasks = [
            self._structural_concept_graph(query),
            self._structural_contradictions(query),
            self._structural_citations(query),
        ]
        if query.project_filter:
            tasks.append(self._structural_project(query))

        results = await asyncio.gather(*tasks, return_exceptions=True)
        items = []
        for result in results:
            if not isinstance(result, Exception):
                items.extend(result)
        return items

    async def _structural_concept_graph(self, query: RetrievalQuery) -> List[RetrievedItem]:
        """Graph traversal from matched concepts."""
        try:
            seeds = await self.memory.find_concepts_by_text(
                query.text,
                topic_id=query.topic_filter,
                limit=3,
            )
            items = []
            for seed in seeds:
                related = await self.memory.traverse_concept_graph(
                    concept_id=seed["id"],
                    max_depth=query.graph_depth,
                )
                for concept in related:
                    depth_decay = 1.0 / (1 + concept.get("depth", 0) * 0.3)
                    items.append(RetrievedItem(
                        content=f"**{concept['name']}**: {concept.get('definition', '')}",
                        source="concept_graph",
                        strategy="structural",
                        knowledge_level="B",
                        item_type="definition",
                        relevance_score=depth_decay,
                        trust_score=0.7,   # graph-derived — decent signal
                        recency_days=999,
                        concept_name=concept["name"],
                        metadata=concept,
                    ))
            return items
        except Exception as e:
            logger.debug(f"[Stage3] Concept graph failed: {e}")
            return []

    async def _structural_contradictions(
        self, query: RetrievalQuery
    ) -> List[RetrievedItem]:
        """
        Retrieves unresolved contradictions related to the query.
        Contradictions are explicitly valuable — they flag where the
        system has conflicting evidence and the LLM should hedge.
        """
        try:
            results = await self.memory.search_contradictions(
                query_text=query.text,
                topic_id=query.topic_filter,
                limit=3,
            )
            items = []
            for r in results:
                content = (
                    f"[CONTESTED] {r.get('atom_a', '')}\n"
                    f"vs.\n"
                    f"{r.get('atom_b', '')}\n"
                    f"({r.get('description', '')})"
                )
                items.append(RetrievedItem(
                    content=content,
                    source="contradiction_registry",
                    strategy="structural",
                    knowledge_level="B",
                    item_type="disagreement",
                    relevance_score=r.get("relevance", 0.6),
                    trust_score=0.5,
                    is_contradiction=True,
                    metadata=r,
                ))
            return items
        except Exception as e:
            logger.debug(f"[Stage3] Contradiction retrieval failed: {e}")
            return []

    async def _structural_citations(
        self, query: RetrievalQuery
    ) -> List[RetrievedItem]:
        """Citation-grounded evidence retrieval."""
        try:
            results = await self.memory.search_citations(
                query_text=query.text,
                topic_id=query.topic_filter,
                limit=4,
            )
            return [
                RetrievedItem(
                    content=r.get("excerpt", ""),
                    source=r.get("source_url", "unknown"),
                    strategy="structural",
                    knowledge_level="A",   # citations point to Level A evidence
                    item_type="claim",
                    relevance_score=r.get("text_rank_score", 0.5),
                    trust_score=r.get("trust_score", 0.5),
                    citation_key=r.get("citation_key"),
                    metadata=r,
                )
                for r in results
            ]
        except Exception as e:
            logger.debug(f"[Stage3] Citation retrieval failed: {e}")
            return []

    async def _structural_project(
        self, query: RetrievalQuery
    ) -> List[RetrievedItem]:
        """Project-specific retrieval from dedicated collection + application notes."""
        items = []
        project_name = query.project_filter

        try:
            # ChromaDB project collection
            results = await self.memory.chroma_query(
                collection=f"project_{project_name.lower()}",
                query_text=query.text,
                n_results=5,
            )
            for doc, meta, distance in zip(
                results["documents"][0],
                results["metadatas"][0],
                results["distances"][0],
            ):
                items.append(RetrievedItem(
                    content=doc,
                    source=meta.get("file_path", project_name),
                    strategy="structural",
                    knowledge_level="B",
                    item_type="project_artifact",
                    relevance_score=(1.0 - distance),
                    trust_score=0.9,        # your own code — high trust
                    project_proximity=1.0,
                    metadata=meta,
                ))
        except Exception:
            pass  # collection may not exist yet

        # Application notes from Postgres project_knowledge_links
        try:
            notes = await self.memory.get_project_concept_applications(
                project_name=project_name,
                query_text=query.text,
                limit=3,
            )
            for note in notes:
                items.append(RetrievedItem(
                    content=note.get("application_note", ""),
                    source=f"project_link:{project_name}",
                    strategy="structural",
                    knowledge_level="C",
                    item_type="project_application",
                    relevance_score=note.get("relevance", 0.5),
                    trust_score=0.9,
                    project_proximity=1.0,
                    concept_name=note.get("concept_name"),
                    metadata=note,
                ))
        except Exception as e:
            logger.debug(f"[Stage3] Project application notes failed: {e}")

        return items

    # ──────────────────────────────────────────────────────────────
    # Stage 4: Re-ranking
    # ──────────────────────────────────────────────────────────────

    async def _stage4_rerank(
        self,
        candidates: List[RetrievedItem],
        query: RetrievalQuery,
    ) -> List[RetrievedItem]:
        """
        Re-scores all candidates with composite score across 6 signals.
        Deduplicates by content prefix before ranking.

        Score signals:
          relevance_score   — query match quality (from retrieval stage)
          trust_score       — source domain authority
          recency_factor    — decays older content (1yr half-life)
          tech_density      — proxy for technical content richness
          project_proximity — 1.0 if from project, 0.0 otherwise
          contradiction_value — small bonus for contested claims (useful for hedging)
        """
        # Dedup by content prefix
        seen = set()
        unique = []
        for item in candidates:
            prefix = item.content[:120].strip()
            if prefix and prefix not in seen and item.content.strip():
                seen.add(prefix)
                unique.append(item)

        # Apply project upweight if relevant
        if query.project_filter:
            for item in unique:
                if item.project_proximity > 0:
                    item.relevance_score = min(1.0, item.relevance_score * 1.15)

        # Sort by composite score
        return sorted(unique, key=lambda x: x.composite_score, reverse=True)

    # ──────────────────────────────────────────────────────────────
    # Role-based context assembly
    # ──────────────────────────────────────────────────────────────

    def _assemble_by_role(
        self,
        ranked: List[RetrievedItem],
        query: RetrievalQuery,
    ) -> RoleBasedContext:
        """
        Fills named slots rather than just taking top-K.
        This ensures the LLM always gets:
          - definitions (for grounding)
          - evidence (for factual backing)
          - contradictions (for epistemic honesty)
          - project artifacts (for actionability)
          - unresolved issues (for intellectual honesty)

        Items are consumed from the ranked list greedily by role fit.
        An item can only appear in one role.
        """
        ctx = RoleBasedContext()
        used_ids = set()

        def take(item: RetrievedItem) -> bool:
            item_id = id(item)
            if item_id in used_ids:
                return False
            used_ids.add(item_id)
            return True

        # 1. Definitions — prefer atom_type="definition" or concept graph items
        for item in ranked:
            if len(ctx.definitions) >= query.max_definitions:
                break
            if item.item_type in ("definition", "concept_map") or item.concept_name:
                if take(item):
                    ctx.definitions.append(item)

        # 2. Project artifacts — prefer items with project_proximity > 0
        if query.project_filter:
            for item in ranked:
                if len(ctx.project_artifacts) >= query.max_project_artifacts:
                    break
                if item.project_proximity > 0 and take(item):
                    ctx.project_artifacts.append(item)

        # 3. Contradictions — pull contested items
        for item in ranked:
            if len(ctx.contradictions) >= query.max_contradictions:
                break
            if item.is_contradiction and take(item):
                ctx.contradictions.append(item)

        # 4. Unresolved issues — open_question or open_problems synthesis
        for item in ranked:
            if len(ctx.unresolved) >= query.max_unresolved:
                break
            if item.item_type in ("open_question", "open_problems") and take(item):
                ctx.unresolved.append(item)

        # 5. Evidence — fill remaining slots from highest-scoring unused items
        for item in ranked:
            if len(ctx.evidence) >= query.max_evidence:
                break
            if take(item):
                ctx.evidence.append(item)

        return ctx

    # ──────────────────────────────────────────────────────────────
    # Context block formatter (for LLM injection)
    # ──────────────────────────────────────────────────────────────

    def build_context_block(
        self,
        ctx: RoleBasedContext,
        project_name: Optional[str] = None,
        show_sources: bool = True,
    ) -> str:
        """
        Formats the role-based context into a structured LLM-injectable block.

        The structure mirrors the reasoning response format:
          1. What is known (definitions)
          2. Strongest evidence
          3. Where evidence conflicts
          4. Project-specific context
          5. What remains unresolved
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
                level_tag = f"[L{item.knowledge_level}]"
                cite = f" {item.citation_key}" if item.citation_key and show_sources else ""
                trust = f" (trust: {item.trust_score:.1f})" if show_sources else ""
                sections.append(f"- {level_tag} {item.content}{cite}{trust}")

        if ctx.contradictions:
            sections.append("\n### Contested / Conflicting Evidence")
            for item in ctx.contradictions:
                sections.append(f"- ⚠ {item.content}")

        if ctx.project_artifacts and project_name:
            sections.append(f"\n### {project_name} Context")
            for item in ctx.project_artifacts:
                note = f" → {item.metadata.get('application_note', '')}" if item.metadata.get("application_note") else ""
                sections.append(f"- {item.content}{note}")

        if ctx.unresolved:
            sections.append("\n### Unresolved / Open Questions")
            for item in ctx.unresolved:
                sections.append(f"- ? {item.content}")

        return "\n".join(sections)

    # ──────────────────────────────────────────────────────────────
    # Utilities
    # ──────────────────────────────────────────────────────────────

    def _days_since(self, timestamp_str: Optional[str]) -> int:
        if not timestamp_str:
            return 9999
        try:
            captured = datetime.fromisoformat(timestamp_str)
            if captured.tzinfo is None:
                captured = captured.replace(tzinfo=timezone.utc)
            delta = datetime.now(timezone.utc) - captured
            return delta.days
        except Exception:
            return 9999
