"""
reasoning/synthesis_service.py

Orchestrates Tier 4 Selective Synthesis.
Connects the Librarian (EvidenceAssembler) to the Writer (ArchivistSynthAdapter).
"""

import logging
import uuid
from typing import Optional

from src.llm.client import OllamaClient
from src.memory.manager import MemoryManager
from src.research.reasoning.assembler import EvidenceAssembler
from src.research.archivist.synth_adapter import ArchivistSynthAdapter

logger = logging.getLogger(__name__)

class SynthesisService:
    def __init__(self, ollama: OllamaClient, memory: MemoryManager, assembler: EvidenceAssembler, adapter=None):
        self.ollama = ollama
        self.memory = memory
        self.assembler = assembler
        self.adapter = adapter
        self.archivist = ArchivistSynthAdapter(ollama)

    async def generate_master_brief(self, topic_id: str) -> Optional[str]:
        """Generate a full Master Brief for a given topic."""
        from src.utils.console import console
        from src.research.domain_schema import SynthesisArtifact
        
        async with self.memory.pg_pool.acquire() as conn:
            topic = await conn.fetchrow("SELECT id, name FROM topics WHERE id = $1", uuid.UUID(str(topic_id)))
            if not topic:
                logger.error(f"[Synthesis] Topic not found: {topic_id}")
                return None
                
            topic_name = topic['name']
            
            console.print(f"\n[bold magenta][Synthesis][/bold magenta] Initiating Tier 4 Master Brief for: '{topic_name}'")
            
            # 1. Generate Section Plan
            console.print("[dim]  - Architecting report structure...[/dim]")
            plan = await self.assembler.generate_section_plan(topic_name)
            console.print(f"[dim]  - Plan finalized with {len(plan)} sections.[/dim]")
            
            # Use a mock authority_record_id for now if we haven't promoted the topic fully
            auth_id = f"dar_{topic_id[:8]}" 
            artifact_id = str(uuid.uuid4())
            
            previous_context = ""
            full_report = ""
            
            # 3. Write Sections Iteratively
            for section in sorted(plan, key=lambda x: x.order):
                console.print(f"\n[bold blue][Section {section.order}][/bold blue] {section.title}")
                console.print(f"[dim]  - Gathering Evidence ({', '.join(section.target_evidence_roles)})...[/dim]")
                
                # Assemble Evidence
                packet = await self.assembler.build_evidence_packet(str(topic_id), topic_name, section)
                
                if not packet.atoms:
                    console.print("[yellow]  - Warning: Minimal evidence found for this section.[/yellow]")
                    
                # Write Prose
                console.print("[dim]  - Archivist synthesizing prose...[/dim]")
                prose = await self.archivist.write_section(packet, previous_context)
                
                # Save Section to DB
                if self.adapter:
                    await self.adapter.store_synthesis_section({
                        "artifact_id": artifact_id,
                        "section_name": section.title,
                        "section_order": section.order,
                        "inline_text": prose # We don't have text_refs fully implemented yet, use summary/inline if needed, but DB schema uses content_ref. Let's adapt if needed.
                    })
                
                # Update rolling context
                previous_context += f"\n\n## {section.title}\n{prose}"
                full_report += f"\n\n## {section.title}\n{prose}"
                console.print("[green]  - Section complete.[/green]")
                
            # 4. Finalize Brief
            if self.adapter:
                artifact = SynthesisArtifact(
                    artifact_id=artifact_id,
                    authority_record_id=auth_id,
                    artifact_type="master_brief",
                    title=f"Master Brief: {topic_name}",
                    abstract="Executive Summary automatically generated.",
                    inline_text=full_report
                )
                await self.adapter.store_synthesis_artifact(artifact.to_pg_row())
            
            console.print("\n[bold green][DONE][/bold green] Master Brief successfully synthesized and stored in Level D Memory.")
            return full_report
