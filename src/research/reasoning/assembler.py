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

from llm.client import OllamaClient
from llm.model_router import TaskType
from memory.manager import MemoryManager
from research.reasoning.retriever import RetrievalQuery, RoleBasedContext
from research.reasoning.v3_retriever import V3Retriever

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
        await self._build_from_context(mission_id, section, retrieved_context, packet)

        return packet

    async def _build_from_context(self, mission_id: str, section: SectionPlan, context: RoleBasedContext, packet: EvidencePacket) -> None:
        """
        Fill an EvidencePacket from a retrieved context.
        Extracted to share logic between single-query and batched paths.
        Mutates packet in-place.
        """
        # Deduplicate and extract the raw atom dictionaries, capturing atom IDs
        seen_ids = set()
        collected = []  # list of (atom_dict, atom_id) for deterministic sorting
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

        # Sort atoms by global_id to ensure deterministic order (invariant: deterministic sampling)
        collected.sort(key=lambda pair: pair[0]['global_id'])

        # Unpack into packet
        for atom_dict, atom_id in collected:
            packet.atoms.append(atom_dict)
            packet.atom_ids_used.append(atom_id)

        # If the section targets contradictions, pull explicitly from the contradictions table
        if "contradictions" in [r.lower() for r in section.target_evidence_roles] or "risks" in section.title.lower():
            if self.memory is not None:
                # Use memory to get unresolved contradictions for the mission/topic
                # Note: get_unresolved_contradictions expects topic_id; using mission_id as topic_id per V3 convention
                conflicts = await self.memory.get_unresolved_contradictions(mission_id, limit=5)
                for c in conflicts:
                    packet.contradictions.append({
                        "description": c['description'],
                        "claim_a": c['atom_a_content'],
                        "claim_b": c['atom_b_content']
                    })

        # Capture detailed retrieval profile if available (diagnostics only)
        if hasattr(context, '_profile'):
            packet.retrieval_profile = context._profile

    async def assemble_all_sections(
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
            for section, ctx in zip(sorted_sections, contexts):
                packet = EvidencePacket(
                    topic_name=topic_name,
                    section_title=section.title,
                    section_objective=section.purpose
                )
                await self._build_from_context(mission_id, section, ctx, packet)
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
