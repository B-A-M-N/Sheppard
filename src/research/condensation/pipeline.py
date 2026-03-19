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
from src.memory.manager import MemoryManager

logger = logging.getLogger(__name__)

@dataclass
class ExtractionCluster:
    topic_id: str
    concept: str
    sources: List[Dict] = field(default_factory=list)
    atoms: List[Dict] = field(default_factory=list)

class DistillationPipeline:
    def __init__(self, ollama: OllamaClient, memory: MemoryManager, budget: BudgetMonitor):
        self.ollama = ollama
        self.memory = memory
        self.budget = budget
        self._semaphore = asyncio.Semaphore(2)

    async def run(self, topic_id: str, priority: CondensationPriority):
        """Metabolic Distillation pass."""
        async with self._semaphore:
            # 1. Fetch raw sources that haven't been distilled
            sources = await self.memory.get_uncondensed_sources(topic_id, limit=20)
            if not sources: return

            # 2. Semantic Clustering (Grouping similar material)
            clusters = await self._cluster_sources(sources)
            
            total_atoms = 0
            for cluster in clusters:
                # 3. Differential Extraction (Mining the signal)
                atoms = await self._mine_differentials(cluster)
                
                # 4. Storage & Indexing
                for atom in atoms:
                    atom_id = await self.memory.store_atom(
                        topic_id=topic_id,
                        session_id=None,
                        atom_type=atom.get('type', 'claim'),
                        content=atom.get('content', ''),
                        source_ids=[s['id'] for s in cluster.sources],
                        confidence=atom.get('confidence', 0.7)
                    )
                    
                    # Semantic Indexing
                    emb = await self.ollama.embed(atom.get('content', ''))
                    await self.memory.store_chunk(
                        collection="knowledge_atoms",
                        topic_id=topic_id,
                        doc_id=atom_id,
                        content=atom.get('content', ''),
                        embedding=emb,
                        metadata={"type": atom.get('type'), "topic": topic_id}
                    )
                    total_atoms += 1

            # 5. Mark sources as distilled
            await self.memory.mark_sources_condensed([s['id'] for s in sources])
            
            # 6. Budget Feedback
            await self.budget.record_condensation_result(
                topic_id=topic_id,
                raw_bytes_freed=sum(s.get('raw_bytes', 0) for s in sources),
                condensed_bytes_added=total_atoms * 500 # Estimate
            )
            
            logger.info(f"[Distillery] Topic {topic_id} Distilled: {len(sources)} sources -> {total_atoms} atoms.")

    async def _cluster_sources(self, sources: List[Dict]) -> List[ExtractionCluster]:
        """Group sources by concept proximity."""
        # Simple clustering for the scaffold
        clusters = [ExtractionCluster(topic_id=sources[0]['topic_id'], concept="batch_general", sources=sources)]
        return clusters

    async def _mine_differentials(self, cluster: ExtractionCluster) -> List[Dict]:
        """
        Extract unique signal and contradictions from a group of similar sources.
        """
        from src.utils.console import console
        combined_text = "\n\n---\n\n".join([f"SOURCE {i}: {s['content'][:4000]}" for i, s in enumerate(cluster.sources)])
        
        prompt = f"""
Compare the following sources and extract a list of unique Knowledge Atoms.
An atom is a single, precise factual assertion, technical specification, or event.

CRITICAL:
- If multiple sources agree, extract it once.
- If sources provide different details (names, versions, specs), extract all variants.
- If sources contradict, mark as contradiction.

Output your response as a single valid JSON object with this structure:
{{
  "thought": "your internal reasoning for this batch",
  "atoms": [
    {{
      "type": "claim|evidence|event|procedure|contradiction",
      "content": "the precise statement",
      "citations": ["[S0]", "[S1]"],
      "confidence": 0.9
    }}
  ]
}}

SOURCES:
{combined_text}
"""
        console.print(f"[dim][Distillery] Mining differentials from {len(cluster.sources)} sources...[/dim]")
        resp = await self.ollama.complete(
            task=TaskType.EXTRACT_ATOMS, 
            prompt=prompt,
            system_prompt="You are a Technical Knowledge Extractor. You MUST output ONLY valid JSON. Start with {{ and end with }}."
        )
        
        try:
            # Look for the last JSON block if multiple exist
            json_match = re.search(r'\{.*\}', resp, re.DOTALL)
            if json_match:
                # Clean up whitespace and potential markdown artifacts
                clean_json = json_match.group(0).strip()
                data = json.loads(clean_json)
                atoms = data.get('atoms', [])
                if atoms:
                    console.print(f"[bold blue][Distillery][/bold blue] Extracted [green]{len(atoms)}[/green] knowledge atoms.")
                return atoms
            else:
                logger.error(f"[Distillery] No JSON found in response: {resp[:200]}...")
                return []
        except Exception as e:
            logger.error(f"[Distillery] JSON parse failed: {e}. Raw: {resp[:200]}")
            return []
