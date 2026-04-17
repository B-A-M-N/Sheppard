"""
reasoning/synthesis_service.py

Orchestrates Tier 4 Selective Synthesis.
Connects the Librarian (EvidenceAssembler) to the Writer (ArchivistSynthAdapter).
"""

import logging
import uuid
import json
from datetime import datetime, timezone
from typing import Optional, List, Sequence, Any

from src.llm.client import OllamaClient
from src.research.reasoning.assembler import EvidenceAssembler, EvidencePacket
from src.research.archivist.synth_adapter import ArchivistSynthAdapter
from src.research.reasoning.trust_state import derive_trust_state

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
            domain_profile_id = mission.get("domain_profile_id", "default")
        else:
            # Fallback: treat mission_id as topic identifier
            topic_name = f"Topic {mission_id}"
            domain_profile_id = "default"

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
                    "domain_profile_id": domain_profile_id,
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
        all_contradictions = [] # Collect contradictions from all sections

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
            
            if packet.contradictions:
                all_contradictions.extend(packet.contradictions)

            # Determine if evidence is sufficient
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
                "atom_ids_used": list(packet.atom_ids_used) if packet.atom_ids_used else [],
                "metadata_json": {
                    "section_guidance": packet.section_guidance,
                    "evidence_graph": self._summarize_evidence_graph(packet),
                },
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
            all_atom_ids = sorted({
                atom_id for s in sections_to_store for atom_id in s.get("atom_ids_used", [])
            })
            if all_atom_ids:
                try:
                    authority_update = self._build_authority_maturation_update(
                        authority_record_id=auth_id,
                        mission_id=mission_id,
                        domain_profile_id=domain_profile_id,
                        topic_name=topic_name,
                        artifact_id=artifact_id,
                        all_atom_ids=all_atom_ids,
                        sections_to_store=sections_to_store,
                        contradictions=all_contradictions,
                    )
                    await self.adapter.upsert_authority_record({
                        **authority_update["record"],
                        "atom_layer_json": {
                            "core_atom_ids": all_atom_ids,
                            "related_atom_ids": authority_update["record"]["atom_layer_json"].get("related_atom_ids", []),
                        },
                    })
                    await self.adapter.set_authority_core_atoms(
                        auth_id,
                        [{"atom_id": aid, "rank": idx, "reason": "Used in master brief"} for idx, aid in enumerate(all_atom_ids)]
                    )
                    
                    if all_contradictions:
                        # Ensure we only send unique contradiction sets and ONLY keys the table has
                        unique_contradictions = []
                        seen_sets = set()
                        for c in all_contradictions:
                            cs_id = c.get('contradiction_set_id')
                            if cs_id and cs_id not in seen_sets:
                                unique_contradictions.append({"contradiction_set_id": cs_id})
                                seen_sets.add(cs_id)
                        
                        if unique_contradictions:
                            await self.adapter.set_authority_contradictions(auth_id, unique_contradictions)
                    await self.adapter.set_authority_related_records(auth_id, authority_update["related_records"])
                    await self.adapter.set_authority_advisories(auth_id, authority_update["advisories"])
                            
                except Exception as e:
                    logger.warning(f"[Synthesis] Failed to update authority atom layer: {e}")

        console.print(f"\n[bold green][DONE][/bold green] Master Brief successfully synthesized and stored in Level D Memory.")
        return full_report

    def _build_authority_maturation_update(
        self,
        authority_record_id: str,
        mission_id: str,
        domain_profile_id: str,
        topic_name: str,
        artifact_id: str,
        all_atom_ids: list[str],
        sections_to_store: list[dict[str, Any]],
        contradictions: list[dict[str, Any]],
    ) -> dict[str, Any]:
        generated_at = datetime.now(timezone.utc).isoformat()
        insufficient_sections = [
            section["section_name"]
            for section in sections_to_store
            if section.get("summary") == "[INSUFFICIENT EVIDENCE FOR SECTION]"
        ]
        contradiction_descriptions = []
        advisories = []
        for contradiction in contradictions:
            description = contradiction.get("description") or contradiction.get("summary") or "Unresolved contradiction in synthesis evidence."
            if description not in contradiction_descriptions:
                contradiction_descriptions.append(description)
                advisories.append({
                    "advisory_type": "contradiction_risk",
                    "statement": description,
                    "priority": 90,
                    "metadata_json": {
                        "contradiction_set_id": contradiction.get("contradiction_set_id"),
                        "claim_a": contradiction.get("claim_a"),
                        "claim_b": contradiction.get("claim_b"),
                    },
                })
        for idx, section_name in enumerate(insufficient_sections):
            advisories.append({
                "advisory_type": "coverage_gap",
                "statement": f"Section '{section_name}' lacked enough evidence for synthesis.",
                "priority": max(10, 70 - idx),
                "metadata_json": {"section_name": section_name},
            })

        related_ids = set()
        for contradiction in contradictions:
            for key in (
                "authority_record_id",
                "related_authority_record_id",
                "other_authority_record_id",
                "opposing_authority_record_id",
            ):
                candidate = contradiction.get(key)
                if candidate and candidate != authority_record_id:
                    related_ids.add(candidate)
        related_records = [
            {
                "related_authority_record_id": related_id,
                "relation_type": "contradiction_context",
            }
            for related_id in sorted(related_ids)
        ]

        maturity = "contested" if contradiction_descriptions else "synthesized"
        confidence = min(0.92, round(0.6 + (len(all_atom_ids) * 0.02), 2))
        advisory_layer = {
            "decision_rules": [entry["statement"] for entry in advisories if entry["advisory_type"] == "contradiction_risk"][:5],
            "coverage_gaps": insufficient_sections,
            "major_contradictions": contradiction_descriptions[:5],
            "last_matured_at": generated_at,
        }
        record = {
            "authority_record_id": authority_record_id,
            "topic_id": mission_id,
            "domain_profile_id": domain_profile_id,
            "title": f"Authority: {topic_name}",
            "canonical_title": topic_name,
            "atom_layer_json": {
                "core_atom_ids": all_atom_ids,
                "related_atom_ids": [],
            },
            "status_json": {
                "maturity": maturity,
                "confidence": confidence,
                "freshness": "current",
                "section_count": len(sections_to_store),
                "artifact_count": 1,
                "contradiction_count": len(contradiction_descriptions),
                "advisory_count": len(advisories),
                "ready_for_application": not insufficient_sections,
                "last_synthesized_at": generated_at,
            },
            "synthesis_layer_json": {
                "master_brief_artifact_id": artifact_id,
                "section_names": [section["section_name"] for section in sections_to_store],
                "insufficient_sections": insufficient_sections,
                "contradiction_count": len(contradiction_descriptions),
                "last_synthesized_at": generated_at,
            },
            "advisory_layer_json": advisory_layer,
            "reuse_json": {
                "ready_for_application": not insufficient_sections,
                "reusable_section_count": len(sections_to_store) - len(insufficient_sections),
                "artifact_ids": [artifact_id],
                "last_artifact_id": artifact_id,
                "core_atom_ids": all_atom_ids,
                "last_updated_at": generated_at,
            },
        }
        record["status_json"]["trust_state"] = derive_trust_state(
            record["status_json"],
            record["advisory_layer_json"],
            record["reuse_json"],
        )
        return {
            "record": record,
            "related_records": related_records,
            "advisories": advisories,
        }

    @staticmethod
    def _summarize_evidence_graph(packet: EvidencePacket) -> dict[str, Any]:
        graph = getattr(packet, "evidence_graph", None)
        if not graph:
            return {"node_count": 0, "edge_count": 0, "contradiction_nodes": 0}
        contradiction_nodes = sum(
            1 for node in graph.nodes.values()
            if getattr(node, "node_type", None) == "contradiction"
        )
        return {
            "node_count": len(getattr(graph, "nodes", {})),
            "edge_count": len(getattr(graph, "edges", {})),
            "contradiction_nodes": contradiction_nodes,
            "guidance_count": len(packet.section_guidance or []),
        }

    def _validate_grounding(self, prose: str, packet: EvidencePacket) -> bool:
        """Validate that every sentence has at least one citation and that cited atoms support the claim via lexical overlap."""
        import re

        # Split prose into sentences
        sentences = re.split(r'[.!?]+', prose)
        sentences = [s.strip() for s in sentences if s.strip()]

        # Build lookup of global_id -> atom text (lowercased)
        global_to_text = {}
        for atom in packet.atoms:
            gid = atom.get('global_id', '')
            if not gid and 'atom_id' in atom:
                gid = atom.get('atom_id', '')
            if gid:
                global_to_text[gid] = atom.get('text', atom.get('statement', '')).lower()

        for sentence in sentences:
            # Extract citations like [A123] or [S4] or just [1]
            citations = re.findall(r'\[([A-Z]?\d+)\]', sentence)
            if not citations:
                logger.debug(f"[Validation] Sentence missing citation: '{sentence}'")
                return False

            found_valid_support = False
            for label in citations:
                # Try multiple possible key formats
                possible_keys = [label, f"[{label}]", f"A{label}", f"S{label}"]
                atom_text = None
                for k in possible_keys:
                    if k in global_to_text:
                        atom_text = global_to_text[k]
                        break
                
                if atom_text:
                    # Remove all citation tags from sentence to get claim text
                    cleaned_sentence = re.sub(r'\[([A-Z]?\d+)\]', '', sentence).lower()
                    # Tokenize into words (simple whitespace split, filter short tokens)
                    sentence_tokens = {tok for tok in cleaned_sentence.split() if len(tok) > 2}
                    atom_tokens = {tok for tok in atom_text.split() if len(tok) > 2}
                    # Check for any overlap (at least 1 word)
                    if sentence_tokens.intersection(atom_tokens):
                        found_valid_support = True
                        break
            
            if not found_valid_support:
                logger.debug(f"[Validation] No cited atom provides lexical support for: '{sentence}'")
                return False

        return True

def _utcnow() -> datetime:
    return datetime.now(timezone.utc)
