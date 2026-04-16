"""
reasoning/synthesis_service.py

Orchestrates Tier 4 Selective Synthesis.
Connects the Librarian (EvidenceAssembler) to the Writer (ArchivistSynthAdapter).
"""

import logging
import uuid
from typing import Optional

from src.llm.client import OllamaClient
from src.research.reasoning.assembler import EvidenceAssembler, EvidencePacket
from src.research.archivist.synth_adapter import ArchivistSynthAdapter

logger = logging.getLogger(__name__)

# Minimum number of atoms required for a section to be synthesized
MIN_EVIDENCE_FOR_SECTION = 3

class SynthesisService:
    def __init__(self, ollama: OllamaClient, memory, assembler: EvidenceAssembler, adapter=None):
        self.ollama = ollama
        self.memory = memory  # V2 MemoryManager deprecated; should be None in V3
        self.assembler = assembler
        self.adapter = adapter
        self.archivist = ArchivistSynthAdapter(ollama)

    async def generate_master_brief(self, mission_id: str) -> Optional[str]:
        """Generate a full Master Brief for a given topic."""
        from src.utils.console import console
        from src.research.domain_schema import SynthesisArtifact

        # Retrieve mission to get topic name and validate
        if self.adapter:
            mission = await self.adapter.get_mission(mission_id)
            if not mission:
                logger.error(f"[Synthesis] Mission not found: {mission_id}")
                return None
            topic_name = mission.get('title') or mission.get('topic_name') or f"Topic {mission_id}"
        else:
            # Fallback: treat mission_id as topic identifier
            topic_name = f"Topic {mission_id}"

        console.print(f"\n[bold magenta][Synthesis][/bold magenta] Initiating Tier 4 Master Brief for: '{topic_name}'")

        # 1. Generate Section Plan
        console.print("[dim]  - Architecting report structure...[/dim]")
        plan = await self.assembler.generate_section_plan(topic_name)
        console.print(f"[dim]  - Plan finalized with {len(plan)} sections.[/dim]")

        # Use a deterministic authority_record_id; create if missing
        auth_id = f"dar_{mission_id[:8]}"
        artifact_id = str(uuid.uuid4())

        # Ensure authority record exists (for FK integrity)
        if self.adapter:
            existing_auth = await self.adapter.get_authority_record(auth_id)
            if not existing_auth:
                # Create minimal authority record derived from mission
                authority_record = {
                    "authority_record_id": auth_id,
                    "topic_id": mission_id,
                    "domain_profile_id": mission.get("domain_profile_id", "default"),  # Use mission's profile if available
                    "title": f"Authority: {topic_name}",
                    "canonical_title": topic_name,
                    "scope_json": {},
                    "status_json": {"maturity": "pre_liminary", "confidence": 0.0, "freshness": "stale"},
                    "frontier_summary_json": {},
                    "corpus_layer_json": {},
                    "atom_layer_json": {"core_atom_ids": [], "related_atom_ids": []},
                    "synthesis_layer_json": {},
                    "advisory_layer_json": {},
                    "lineage_layer_json": {},
                    "reuse_json": {}
                }
                await self.adapter.upsert_authority_record(authority_record)

        previous_context = ""
        full_report = ""
        sections_to_store = []  # Collect sections for batch storage after artifact creation
        citations_to_store = []  # Collect citations for batch storage after artifact creation

        # 2a. Retrieve evidence for ALL sections concurrently
        console.print("[dim]  - Retrieving evidence for all sections concurrently...[/dim]")
        all_packets = await self.assembler.assemble_all_sections(mission_id, topic_name, plan)
        console.print(f"[dim]  - Evidence retrieved for {len(all_packets)} sections.[/dim]")

        # 2b. Write Sections Iteratively (LLM synthesis must remain sequential for previous_context)
        for section in sorted(plan, key=lambda x: x.order):
            console.print(f"\n[bold blue][Section {section.order}][/bold blue] {section.title}")

            # Use pre-fetched packet from concurrent retrieval
            packet = all_packets.get(section.order, EvidencePacket(
                topic_name=topic_name,
                section_title=section.title,
                section_objective=section.purpose
            ))

            # Determine if evidence is sufficient
            # Only skip Archivist if there are NO atoms at all.
            # If there is at least 1 atom, let Archivist write, then validate claim coverage.
            if len(packet.atoms) == 0:
                console.print("[yellow]  - No atoms retrieved; marking section insufficient.[/yellow]")
                prose = "[INSUFFICIENT EVIDENCE FOR SECTION]"
            else:
                # Write Prose via Archivist
                console.print("[dim]  - Archivist synthesizing prose...[/dim]")
                prose = await self.archivist.write_section(packet, previous_context)

                # Grounding validation — this is the truth contract gate
                if not self._validate_grounding(prose, packet):
                    logger.error(f"[Synthesis] Grounding validation failed for section: {section.title}")
                    console.print("[red]  - Grounding validation failed; section content rejected.[/red]")
                    prose = "[INSUFFICIENT EVIDENCE FOR SECTION]"
                else:
                    console.print("[green]  - Prose validated.[/green]")

            # Prepare section data for storage (deferred until after artifact exists)
            section_dict = {
                "artifact_id": artifact_id,
                "section_name": section.title,
                "section_order": section.order,
                "summary": prose,
                "mission_id": mission_id,
                "atom_ids_used": list(packet.atom_ids_used) if packet.atom_ids_used else []
            }
            sections_to_store.append(section_dict)

            # Collect citations for batch storage (deferred)
            if prose != "[INSUFFICIENT EVIDENCE FOR SECTION]" and packet.atom_ids_used:
                citations = [
                    {
                        "artifact_id": artifact_id,
                        "section_name": section.title,
                        "atom_id": atom_id,
                        "metadata_json": {}
                    }
                    for atom_id in packet.atom_ids_used
                ]
                citations_to_store.extend(citations)

            # Update rolling context
            previous_context += f"\n\n## {section.title}\n{prose}"
            full_report += f"\n\n## {section.title}\n{prose}"
            console.print("[green]  - Section complete.[/green]")

        # 3. Finalize Brief
        if self.adapter:
            artifact = SynthesisArtifact(
                artifact_id=artifact_id,
                authority_record_id=auth_id,
                artifact_type="master_brief",
                title=f"Master Brief: {topic_name}",
                abstract="Executive Summary automatically generated.",
                inline_text=full_report,
                mission_id=mission_id
            )
            await self.adapter.store_synthesis_artifact(artifact.to_pg_row())
            # Now that artifact exists in DB, store collected sections and citations (FK constraints satisfied)
            await self.adapter.store_synthesis_sections(sections_to_store)
            if citations_to_store:
                await self.adapter.store_synthesis_citations(citations_to_store)

            # Populate authority record atom layer from atoms actually used in synthesis.
            # This converts the placeholder empty lists into a real atom substrate.
            all_atom_ids = list({
                atom_id
                for s in sections_to_store
                for atom_id in s.get("atom_ids_used", [])
            })
            if all_atom_ids:
                try:
                    await self.adapter.upsert_authority_record({
                        "authority_record_id": auth_id,
                        "atom_layer_json": {
                            "core_atom_ids": all_atom_ids,
                            "related_atom_ids": [],
                        },
                        "status_json": {
                            "maturity": "synthesized",
                            "confidence": 0.7,
                            "freshness": "current",
                        },
                    })
                    logger.info(f"[Synthesis] Authority record {auth_id} updated with {len(all_atom_ids)} core atoms")
                except Exception as e:
                    logger.warning(f"[Synthesis] Failed to update authority atom layer: {e}")

        console.print("\n[bold green][DONE][/bold green] Master Brief successfully synthesized and stored in Level D Memory.")
        return full_report

    def _validate_grounding(self, prose: str, packet: EvidencePacket) -> bool:
        """Validate that every sentence has at least one citation and that cited atoms support the claim via lexical overlap."""
        import re

        # Split prose into sentences (simple split on sentence-ending punctuation)
        sentences = re.split(r'[.!?]+', prose)
        sentences = [s.strip() for s in sentences if s.strip()]

        # Build lookup of global_id -> atom text (lowercased)
        global_to_text = {}
        for atom in packet.atoms:
            gid = atom.get('global_id', '')
            if gid:
                global_to_text[gid] = atom.get('text', '').lower()

        # Set of atom IDs actually used (for presence check)
        valid_atom_ids = set(packet.atom_ids_used)

        for sentence in sentences:
            # Extract citations like [A123] or [S4]
            citations = re.findall(r'\[([A-Z]?\d+)\]', sentence)
            if not citations:
                logger.debug(f"[Validation] Sentence missing citation: '{sentence}'")
                return False

            # Check that each cited label corresponds to an atom in the packet and that at least one has lexical overlap
            found_valid_support = False
            for label in citations:
                global_id = f"[{label}]"
                if global_id not in global_to_text:
                    # Citation key not present in the evidence packet
                    logger.debug(f"[Validation] Citation {global_id} not found in evidence packet.")
                    return False
                atom_text = global_to_text[global_id]

                # Remove all citation tags from sentence to get claim text
                cleaned_sentence = re.sub(r'\[([A-Z]?\d+)\]', '', sentence).lower()
                # Tokenize into words (simple whitespace split, filter short tokens)
                sentence_tokens = {tok for tok in cleaned_sentence.split() if len(tok) > 2}
                atom_tokens = {tok for tok in atom_text.split() if len(tok) > 2}
                # Check for any overlap
                if sentence_tokens & atom_tokens:
                    found_valid_support = True
                # If no overlap, continue checking other citations in same sentence; one valid is enough

            if not found_valid_support:
                logger.debug(f"[Validation] Sentence has no supporting overlap: '{sentence}'")
                return False

        return True
