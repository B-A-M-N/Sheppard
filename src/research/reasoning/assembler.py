"""
reasoning/assembler.py

The "Librarian" for Tier 4 Selective Synthesis.
Builds role-based evidence packets from the atom store for the synthesis engine.
"""

import asyncio
import json
import logging
import re
import time
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field

from src.llm.client import OllamaClient
from src.llm.model_router import TaskType
from src.memory.manager import MemoryManager
from src.research.reasoning.retriever import RetrievalQuery, RoleBasedContext
from src.research.reasoning.v3_retriever import V3Retriever
from src.research.reasoning.ranking import RankingConfig, apply_ranking
from src.research.derivation.engine import DerivationEngine
from src.research.reasoning.analytical_operators import run_all_operators
from src.research.graph.claim_graph import build_evidence_graph

logger = logging.getLogger(__name__)

# Maximum number of concurrent section retrievals (tunable)
RETRIEVAL_CONCURRENCY_LIMIT = 8

@dataclass
class SectionPlan:
    order: int
    title: str
    purpose: str
    target_evidence_roles: List[str]

@dataclass
class EvidencePacket:
    topic_name: str
    section_title: str
    section_objective: str
    atoms: List[Dict] = field(default_factory=list)
    contradictions: List[Dict] = field(default_factory=list)
    atom_ids_used: List[str] = field(default_factory=list)
    retrieval_profile: Optional[Dict[str, float]] = None  # populated during diagnostics only
    derived_claims: List = field(default_factory=list)
    analytical_bundles: List = field(default_factory=list)
    evidence_graph: Any = None

class EvidenceAssembler:
    def __init__(self, ollama: OllamaClient, memory: MemoryManager, retriever: V3Retriever, adapter=None):
        self.ollama = ollama
        self.memory = memory
        self.retriever = retriever
        self.adapter = adapter

    async def generate_section_plan(self, topic_name: str) -> List[SectionPlan]:
        """Ask the LLM to architect the Master Brief."""
        prompt = f"""
You are the Chief Architect of a research institute.
Your task is to outline a comprehensive 'Master Brief' on the following subject:
SUBJECT: {topic_name}

Break the report down into 5 to 8 logical sections based on the nature of the subject. 
(e.g., if it's historical: Context, Major Events, Turning Points, Dispute/Contradictions. If it's technical: Definitions, Architecture, Failure Modes, Best Practices).

Output ONLY valid JSON in this format:
{{
  "sections": [
    {{
      "title": "Section Name",
      "purpose": "What this section must achieve",
      "target_roles": ["keywords describing the type of evidence needed, e.g., definitions, statistics, contradictions, methodologies, primary_sources"]
    }}
  ]
}}
"""
        resp = await self.ollama.complete(
            task=TaskType.DECOMPOSITION,
            prompt=prompt,
            system_prompt="You are a JSON-only architect. Output ONLY valid JSON."
        )
        
        try:
            match = re.search(r'\{.*\}', resp, re.DOTALL)
            data = json.loads(match.group(0)) if match else json.loads(resp)
            
            plan = []
            for i, sec in enumerate(data.get("sections", [])):
                plan.append(SectionPlan(
                    order=i+1,
                    title=sec.get("title", f"Section {i+1}"),
                    purpose=sec.get("purpose", ""),
                    target_evidence_roles=sec.get("target_roles", [])
                ))
            return plan
        except Exception as e:
            logger.error(f"[Assembler] Failed to generate section plan: {e}")
            # Fallback plan
            return [
                SectionPlan(1, "Executive Summary", "Summarize core concepts and definitions.", ["definitions", "core_concepts"]),
                SectionPlan(2, "Detailed Analysis", "Explore the subject's mechanisms, events, or main arguments.", ["mechanisms", "methodologies", "arguments"]),
                SectionPlan(3, "Critical Perspectives", "Highlight disputes, contradictions, or failure modes.", ["contradictions", "disputes", "failure_modes"])
            ]

    async def build_evidence_packet(self, mission_id: str, topic_name: str, section: SectionPlan) -> EvidencePacket:
        """Gather specific atoms for a section (legacy single-query path)."""
        packet = EvidencePacket(
            topic_name=topic_name,
            section_title=section.title,
            section_objective=section.purpose
        )

        # Use V3Retriever to pull atoms relevant to the section's purpose
        query_text = f"{topic_name} {section.title} {' '.join(section.target_evidence_roles)}"
        q = RetrievalQuery(text=query_text, mission_filter=mission_id, max_results=15)

        # Pull standard atoms
        # --- Per-section timing instrumentation ---
        _t0 = time.perf_counter()
        retrieved_context = await self.retriever.retrieve(q)
        _retrieve_ms = (time.perf_counter() - _t0) * 1000
        logger.debug(
            f"[Assembler] Section '{section.title}' retrieval: {_retrieve_ms:.1f}ms "
            f"({len(retrieved_context.all_items)} items)"
        )

        # Build packet from retrieved context
        await self._build_from_context(mission_id, section, retrieved_context, packet, q)

        return packet

    async def _build_from_context(self, mission_id: str, section: SectionPlan, context: RoleBasedContext, packet: EvidencePacket, query: Optional[RetrievalQuery] = None) -> None:
        """
        Fill an EvidencePacket from a retrieved context.
        Extracted to share logic between single-query and batched paths.
        Mutates packet in-place.
        """
        # Deduplicate and extract the raw atom dictionaries, capturing atom IDs
        seen_ids = set()
        collected = []        # list of (atom_dict, atom_id) for deterministic sorting
        items_parallel = []   # parallel RetrievedItem list for ranking signals
        for item in context.all_items:
            # Atom ID is stored in metadata as 'atom_id' (from V3Retriever/Chroma index)
            if item.metadata and item.metadata.get('atom_id'):
                aid = item.metadata['atom_id']
                if aid not in seen_ids:
                    seen_ids.add(aid)
                    atom_dict = {
                        "global_id": f"[{item.citation_key}]" if item.citation_key else f"[A{len(seen_ids)}]",
                        "text": item.content,
                        "type": item.item_type,
                        "metadata": {"source": item.source}
                    }
                    collected.append((atom_dict, aid))
                    items_parallel.append(item)

        # Opt-in ranking: sort by composite score (desc) with global_id tiebreaker (RANK-01/02/03/04)
        # Default (enable_ranking=False) preserves current global_id sort for backward compatibility.
        if query is not None and getattr(query, 'enable_ranking', False):
            from research.reasoning.ranking import apply_ranking, RankingConfig
            cfg = query.ranking_config if query.ranking_config is not None else RankingConfig()
            collected = apply_ranking(collected, items_parallel, cfg)
        else:
            # Current behavior: deterministic lexical sort by global_id
            collected.sort(key=lambda pair: pair[0]['global_id'])

        # Derivation: compute derived claims from sorted atoms (Phase 12-A)
        packet.derived_claims = DerivationEngine().run(items_parallel)

        # Analytical operators: compute comparative bundles (Phase 12-B)
        packet.analytical_bundles = run_all_operators(items_parallel)

        # Unpack into packet
        for atom_dict, atom_id in collected:
            packet.atoms.append(atom_dict)
            packet.atom_ids_used.append(atom_id)

        # If the section targets contradictions, pull explicitly from the contradictions table
        if "contradictions" in [r.lower() for r in section.target_evidence_roles] or "risks" in section.title.lower():
            conflicts = await self._get_unresolved_contradictions(mission_id, limit=5)
            for c in conflicts:
                packet.contradictions.append({
                    "contradiction_set_id": c.get("contradiction_set_id", ""),
                    "description": c['description'],
                    "claim_a": c['atom_a_content'],
                    "claim_b": c['atom_b_content'],
                    "atom_a_id": c.get('atom_a_global_id', ''),
                    "atom_b_id": c.get('atom_b_global_id', ''),
                })

        # Capture detailed retrieval profile if available (diagnostics only)
        if hasattr(context, '_profile'):
            packet.retrieval_profile = context._profile

        # Evidence graph: connect atoms, derived claims, bundles, contradictions (Phase 12-C)
        packet.evidence_graph = build_evidence_graph(
            items_parallel, packet.derived_claims, packet.analytical_bundles, packet.contradictions
        )

    async def _get_unresolved_contradictions(self, mission_id: str, limit: int = 5) -> List[Dict]:
        """V3-native contradiction retrieval via direct PG adapter query.

        Returns unresolved contradictions from the V3 contradiction tables
        using the live adapter pool rather than a private side pool.
        """
        pg = getattr(self.adapter, "pg", None) or getattr(getattr(self.retriever, "adapter", None), "pg", None)
        if not pg:
            logger.warning("[Assembler] No adapter PG pool available; skipping contradictions")
            return []

        async with pg.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT cs.summary AS description,
                       cs.contradiction_set_id,
                       a1.atom_id AS atom_a_global_id,
                       a1.statement AS atom_a_content,
                       a2.atom_id AS atom_b_global_id,
                       a2.statement AS atom_b_content
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
                str(mission_id), limit
            )
            return [dict(r) for r in rows]

    async def assemble_all_sections(        self, mission_id: str, topic_name: str, sections: List[SectionPlan]
    ) -> Dict[int, EvidencePacket]:
        """
        Retrieve evidence for all sections using batched retrieval when possible.
        Falls back to sequential per-section retrieval on batch failure.
        Returns dict keyed by section.order -> EvidencePacket.
        """
        from utils.structured_logger import async_span_ctx
        async with async_span_ctx("retrieval", mission_id):
            return await self._assemble_all_sections_impl(mission_id, topic_name, sections)

    async def _assemble_all_sections_impl(
        self, mission_id: str, topic_name: str, sections: List[SectionPlan]
    ) -> Dict[int, EvidencePacket]:
        """
        Retrieve evidence for all sections using batched retrieval when possible.
        Falls back to sequential per-section retrieval on batch failure.
        Returns dict keyed by section.order -> EvidencePacket.
        """
        sorted_sections = sorted(sections, key=lambda s: s.order)

        # Build RetrievalQuery for each section
        queries: List[RetrievalQuery] = []
        for section in sorted_sections:
            query_text = f"{topic_name} {section.title} {' '.join(section.target_evidence_roles)}"
            queries.append(RetrievalQuery(text=query_text, mission_filter=mission_id, max_results=15))

        # Attempt batched retrieval
        contexts: List[RoleBasedContext] = []
        batch_failed = False
        try:
            contexts = await self.retriever.retrieve_many(queries)
        except Exception as e:
            logger.warning(f"[Assembler] Batch retrieval failed: {e}; falling back to sequential")
            batch_failed = True

        packets: Dict[int, EvidencePacket] = {}

        if not batch_failed and len(contexts) == len(sorted_sections):
            # Build packets from batched contexts
            for i, (section, ctx) in enumerate(zip(sorted_sections, contexts)):
                packet = EvidencePacket(
                    topic_name=topic_name,
                    section_title=section.title,
                    section_objective=section.purpose
                )
                await self._build_from_context(mission_id, section, ctx, packet, queries[i])
                packets[section.order] = packet
        else:
            # Fallback: sequential per-section retrieval (preserves original behavior)
            for section in sorted_sections:
                try:
                    packet = await self.build_evidence_packet(mission_id, topic_name, section)
                    packets[section.order] = packet
                except Exception as e:
                    logger.error(f"[Assembler] Section {section.order} retrieval failed: {e}")
                    packets[section.order] = EvidencePacket(
                        topic_name=topic_name,
                        section_title=f"Section {section.order}",
                        section_objective=""
                    )

        return packets
