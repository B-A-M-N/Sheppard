"""
reasoning/assembler.py

The "Librarian" for Tier 4 Selective Synthesis.
Builds role-based evidence packets from the atom store for the synthesis engine.
"""

import json
import logging
import re
from typing import Dict, List, Any
from dataclasses import dataclass, field

from llm.client import OllamaClient
from llm.model_router import TaskType
from memory.manager import MemoryManager
from research.reasoning.retriever import RetrievalQuery
from research.reasoning.v3_retriever import V3Retriever

logger = logging.getLogger(__name__)

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
        """Gather specific atoms for a section."""
        packet = EvidencePacket(
            topic_name=topic_name,
            section_title=section.title,
            section_objective=section.purpose
        )

        # Use V3Retriever to pull atoms relevant to the section's purpose
        query_text = f"{topic_name} {section.title} {' '.join(section.target_evidence_roles)}"
        q = RetrievalQuery(text=query_text, mission_filter=mission_id, max_results=15)

        # Pull standard atoms
        retrieved_context = await self.retriever.retrieve(q)

        # Deduplicate and extract the raw atom dictionaries, capturing atom IDs
        seen_ids = set()
        collected = []  # list of (atom_dict, atom_id) for deterministic sorting
        for item in retrieved_context.all_items:
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

        return packet
