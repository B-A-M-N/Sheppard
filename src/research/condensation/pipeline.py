"""
condensation/pipeline.py — Differential Knowledge Distillery

Architectural Shift:
- Coverage before compression: Wait for document clusters before mining.
- Diversity before certainty: Explicitly extract unique differentials between similar sources.
- Contradiction before consensus: Conflict is preserved as a first-class memory object.
"""

import asyncio
import json
import logging
import math
import os
import re
from typing import Dict, List, Set, Any, Optional
from dataclasses import dataclass, field

from src.research.acquisition.budget import BudgetMonitor, CondensationPriority
from src.llm.client import OllamaClient
from src.llm.model_router import TaskType

from src.utils.console import console
from src.utils.json_validator import JSONValidator, extract_technical_atoms

logger = logging.getLogger(__name__)

@dataclass
class ExtractionCluster:
    topic_id: str
    concept: str
    sources: List[Dict] = field(default_factory=list)
    atoms: List[Dict] = field(default_factory=list)

class DistillationPipeline:
    def __init__(self, ollama: OllamaClient, memory, budget: BudgetMonitor, adapter=None):
        self.ollama = ollama
        self.memory = memory  # V2 removed; expected None in V3
        self.budget = budget
        self.adapter = adapter
        self._semaphore = asyncio.Semaphore(2)

    async def run(self, mission_id: str, priority: CondensationPriority):
        """Metabolic Distillation pass using V3 Triad (Sequential-Atomic)."""
        topic_id = mission_id # Bridge for budget hooks
        async with self._semaphore:
            # 1. Fetch raw technical ore from V3 Corpus
            # We process a small batch sequentially to ensure high quality with 8B models
            sources = await self.adapter.pg.fetch_many(
                "corpus.sources", 
                where={"mission_id": mission_id, "status": "fetched"},
                limit=5
            )
            if not sources: return

            import uuid
            from src.research.domain_schema import KnowledgeAtom, AtomLineage
            
            total_atoms = 0
            for s in sources:
                # Get the content
                text_ref = s.get("canonical_text_ref")
                if not text_ref: 
                    # Mark as failed/skipped if no text ref
                    await self.adapter.pg.update_row("corpus.sources", "source_id", {"source_id": s["source_id"], "status": "error"})
                    continue
                
                ref = await self.adapter.get_text_ref(text_ref)
                if not ref or not ref.get("inline_text"):
                    await self.adapter.pg.update_row("corpus.sources", "source_id", {"source_id": s["source_id"], "status": "error"})
                    continue
                
                content = ref["inline_text"]
                source_id = s["source_id"]
                
                # 2. Extract technical atoms (Robust Validation Loop)
                mission_row = await self.adapter.get_mission(mission_id)
                topic_name = mission_row.get("title", "AI Research") if mission_row else "AI Research"
                
                console.print(f"[dim][Distillery] Smelting: {s.get('url', source_id)[:60]}...[/dim]")
                
                try:
                    atoms_data = await extract_technical_atoms(self.ollama, content, topic_name)
                    
                    # 3. Storage & Indexing
                    for atom_dict in atoms_data:
                        if not isinstance(atom_dict, dict): continue
                        
                        atom_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{mission_id}:{source_id}:{atom_dict.get('content', '')[:200]}"))
                        profile_id = mission_row.get("domain_profile_id") if mission_row else f"profile_{mission_id[:8]}"
                        
                        atom = KnowledgeAtom(
                            atom_id=atom_id,
                            topic_id=mission_row.get("topic_id") if mission_row else mission_id,
                            domain_profile_id=profile_id,
                            atom_type=atom_dict.get('type', 'claim'),
                            title=atom_dict.get('content', '')[:50] + "...",
                            statement=atom_dict.get('content', ''),
                            summary=atom_dict.get('content', ''),
                            confidence=atom_dict.get('confidence', 0.7),
                            importance=0.8 if atom_dict.get('type') == 'contradiction' else 0.5,
                            lineage=AtomLineage(
                                mission_id=mission_id,
                                extraction_mode="atomic_distillation"
                            ),
                            metadata={"type": atom_dict.get('type'), "source_id": source_id}
                        )
                        
                        # Store atom and evidence atomically via V3 Adapter
                        atom_row = atom.to_pg_row()
                        evidence_rows = [{
                            "source_id": source_id,
                            "evidence_strength": 0.9,
                            "supports_statement": True
                        }]
                        await self.adapter.store_atom_with_evidence(atom_row, evidence_rows)

                        total_atoms += 1

                    # 5. Mark individual source as condensed immediately
                    await self.adapter.pg.update_row(
                        "corpus.sources", 
                        "source_id", 
                        {"source_id": source_id, "status": "condensed"}
                    )
                except Exception as e:
                    logger.error(f"[Distillery] Smelting failed for {source_id}: {e}")
                    await self.adapter.pg.update_row("corpus.sources", "source_id", {"source_id": source_id, "status": "error"})

            console.print(f"[bold green][Refinery][/bold green] Batch complete. Smelted technical atoms: [white]{total_atoms}[/white]")
            
            # 6. Higher-Order Refinement
            if total_atoms > 0:
                if priority in [CondensationPriority.HIGH, CondensationPriority.CRITICAL]:
                    await self.resolve_contradictions(mission_id)
            
            # 7. Budget Feedback
            await self.budget.record_condensation_result(
                topic_id=topic_id,
                raw_bytes_freed=sum(len(str(s).encode()) for s in sources), # Approximated
                condensed_bytes_added=total_atoms * 500 # Estimate
            )

    async def _cluster_sources(self, sources: List[Dict]) -> List[ExtractionCluster]:
        """Group sources by concept proximity."""
        # Simple clustering for the scaffold
        clusters = [ExtractionCluster(topic_id=sources[0]['topic_id'], concept="batch_general", sources=sources)]
        return clusters

    async def resolve_contradictions(self, topic_id: str):
        """The Courtroom: Actively resolves open contradictions."""
        # Implementation pending V3 migration...
        pass

    async def consolidate_atoms(self, topic_id: str):
        """The Forgetting Curve: Merges redundant atoms into Golden Atoms."""
        # Implementation pending V3 migration...
        pass
