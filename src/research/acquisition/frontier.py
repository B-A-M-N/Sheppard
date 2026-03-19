"""
acquisition/frontier.py — Universal Research Metabolism

Architectural Shift:
- Domain-Agnostic: No hardcoded search types (no fixed 'GitHub' or 'ArXiv' bias).
- Policy-Driven: The system generates a custom 'Research Policy' for every topic.
- Epistemic-First: Modes are defined by the type of truth they seek, not the site they search.
"""

import asyncio
import json
import logging
import re
from typing import Dict, List, Set, Any, Optional, Tuple
from dataclasses import dataclass, field

from src.utils.console import console
from src.llm.model_router import TaskType

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────
# Epistemic Yield Objectives (The Marketplace)
# ──────────────────────────────────────────────────────────────

class EpistemicMode:
    GROUNDING = "grounding"       # Finding core facts, definitions, and primary records
    EXPANSION = "expansion"       # Branching into related sub-concepts and context
    DIALECTIC = "dialectic"       # Seeking conflict, critique, and counter-arguments
    VERIFICATION = "verification" # Hunting for high-authority proof or evidentiary artifacts

MODES = {
    EpistemicMode.GROUNDING: "Establish the core factual basis and primary definitions.",
    EpistemicMode.EXPANSION: "Broaden the context into adjacent fields and missing sub-topics.",
    EpistemicMode.DIALECTIC: "Actively seek out contradictions, disputes, and expert disagreements.",
    EpistemicMode.VERIFICATION: "Search for high-authority evidence (Specs, Court Docs, Data, etc)."
}

@dataclass
class ResearchPolicy:
    """Topic-specific rules generated at runtime."""
    subject_class: str = "general"
    authority_indicators: List[str] = field(default_factory=list)
    evidence_types: List[str] = field(default_factory=list)
    search_strategy: str = "balanced"

@dataclass
class FrontierNode:
    concept: str
    status: str = "underexplored"  # underexplored, active, saturated
    yield_history: List[int] = field(default_factory=list)
    exhausted_modes: Set[str] = field(default_factory=set)

# ──────────────────────────────────────────────────────────────
# Adaptive Controller
# ──────────────────────────────────────────────────────────────

class AdaptiveFrontier:
    def __init__(self, system_manager, topic_id: str, topic_name: str):
        self.sm = system_manager
        self.topic_id = topic_id
        self.topic_name = topic_name
        self.policy = ResearchPolicy()
        self.nodes: Dict[str, FrontierNode] = {}
        self.visited_urls: Set[str] = set()
        self.total_ingested = 0

    async def run(self):
        """Metabolic Control Loop."""
        # Phase 1: Custom Policy Generation
        await self._frame_research_policy()
        
        while True:
            # 1. Budget check
            status = self.sm.budget.get_status(self.topic_id)
            if status and status.usage_ratio >= 1.0:
                console.print(f"[bold red][Frontier][/bold red] Storage ceiling reached. Terminating acquisition.")
                break
            
            # 2. Select Next Action
            node, mode = self._select_next_action()
            if not node: 
                # If all current nodes are saturated, ask for a "Fresh Perspective" to prevent premature stop
                console.print(f"[bold cyan][Frontier][/bold cyan] Current frontier saturated. Generating fresh perspectives...")
                await self._respawn_nodes(None) 
                node, mode = self._select_next_action()
                if not node: break # Truly exhausted

            console.print(f"\n[bold yellow][Frontier][/bold yellow] Seeking {mode} for: [white]{node.concept}[/white]")
            
            # 3. Dynamic Query Engineering
            queries = await self._engineer_queries(node, mode)
            
            # 4. Execute Acquisition Batch
            round_yield = 0
            for q in queries:
                async for result in self.sm.crawler.crawl_topic(
                    topic_id=self.topic_id,
                    topic_name=self.topic_name,
                    seed_query=q,
                    can_crawl_fn=self.sm.budget.can_crawl,
                    visited_urls=self.visited_urls
                ):
                    console.print(f"[bold green][PASS][/bold green] Ingested ({self.total_ingested+1}): [dim]{result.url}[/dim]")
                    await self.sm.memory.store_source(
                        topic_id=self.topic_id,
                        url=result.url,
                        title=result.title,
                        content=result.markdown,
                        raw_bytes=result.raw_bytes,
                        checksum=result.checksum,
                        domain=result.domain,
                        source_type=result.source_type,
                        raw_file_path=result.raw_file_path,
                    )
                    self.total_ingested += 1
                    round_yield += 1
                
                await asyncio.sleep(5) 

            # 5. Feedback Loop
            node.yield_history.append(round_yield)
            node.exhausted_modes.add(mode)
            
            # Density Check: If high yield, ask LLM to spawn deeper nodes
            if round_yield >= 3:
                await self._respawn_nodes(node)

        return self.total_ingested

    async def _frame_research_policy(self):
        """The core universal shift: LLM designs the policy for the subject."""
        console.print(f"[bold cyan][Frontier][/bold cyan] Designing research policy for: [white]{self.topic_name}[/white]")
        prompt = f"""
Analyze the subject: {self.topic_name}

1. Define the 'Evidence Stack' for this field (What counts as proof?).
2. Define 'Authority' (What kind of sites are the most reliable for THIS subject?).
3. Decompose into 15 foundational, highly technical, and granular research nodes. 

Output valid JSON:
{{
  "policy": {{
    "class": "investigative|scientific|historical|etc",
    "authority": ["list of site types or patterns"],
    "evidence": ["list of artifact types"]
  }},
  "nodes": ["node 1", "node 2", ..., "node 15"]
}}
"""
        resp = await self.sm.ollama.complete(TaskType.DECOMPOSITION, prompt)
        try:
            data = json.loads(re.search(r'\{.*\}', resp, re.DOTALL).group(0))
            p = data.get('policy', {})
            self.policy = ResearchPolicy(
                subject_class=p.get('class', 'general'),
                authority_indicators=p.get('authority', []),
                evidence_types=p.get('evidence', [])
            )
            for n in data.get('nodes', []):
                self.nodes[n] = FrontierNode(concept=n)
            
            console.print(f"[bold blue][Frontier][/bold blue] Policy set: {self.policy.subject_class}. Found {len(self.nodes)} initial nodes.")
        except:
            self.nodes[self.topic_name] = FrontierNode(concept=self.topic_name)

    def _select_next_action(self) -> Tuple[Optional[FrontierNode], Optional[str]]:
        """Marketplace selection based on node freshness."""
        active = [n for n in self.nodes.values() if n.status == "underexplored"]
        if not active: return None, None
        
        # Sort by those with least modes tried
        active.sort(key=lambda n: len(n.exhausted_modes))
        node = active[0]
        
        # Cycle through modes
        for mode in [EpistemicMode.GROUNDING, EpistemicMode.VERIFICATION, EpistemicMode.DIALECTIC, EpistemicMode.EXPANSION]:
            if mode not in node.exhausted_modes:
                return node, mode
        
        node.status = "saturated"
        return self._select_next_action()

    async def _engineer_queries(self, node: FrontierNode, mode: str) -> List[str]:
        """Policy-aware, natural language query generation."""
        prompt = f"""
SUBJECT: {self.topic_name}
CONCEPT: {node.concept}
MODE: {mode} ({MODES[mode]})
POLICY:
- Authority: {self.policy.authority_indicators}
- Evidence Needed: {self.policy.evidence_types}

Generate 2 highly effective, NATURAL LANGUAGE search queries.
CRITICAL CONSTRAINTS:
- NO Boolean logic (No AND, OR, NOT).
- NO parentheses.
- NO 'site:' operators.
- NO quotes.
- Phrase them like a human researcher looking for high-quality data.

Output ONLY the query text, one per line.
"""
        resp = await self.sm.ollama.complete(TaskType.QUERY_EXPANSION, prompt)
        
        raw_queries = resp.split('\n')
        clean_queries = []
        for q in raw_queries:
            c = re.sub(r'^\d+[\.\)]\s*', '', q.strip())
            c = c.replace('"', '').replace("'", "").replace("(", "").replace(")", "")
            for term in [" AND ", " OR ", " NOT "]:
                c = c.replace(term, " ")
            if len(c) > 5:
                clean_queries.append(c)
                
        return clean_queries[:2]

    async def _respawn_nodes(self, parent_node: Optional[FrontierNode]):
        """Growth through discovery: analyzes current knowledge and spawns new research nodes."""
        parent_concept = parent_node.concept if parent_node else self.topic_name
        console.print(f"[bold cyan][Frontier][/bold cyan] Spawning deeper nodes for [white]{parent_concept}[/white]...")
        
        current_context = await self.sm.query(text=parent_concept, topic_filter=self.topic_id, max_results=10)
        
        prompt = f"""
Research Subject: {self.topic_name}
Area: {parent_concept}
Current Knowledge: {current_context[:2000]}

Identify 3-5 new, highly specific sub-topics or технические technical concepts that are MISSING or under-represented.
Focus on:
- Niche implementation details
- Practical pitfalls and edge cases
- Competitive technical comparisons
- Unanswered questions

Return ONLY the sub-topics, one per line. No numbering, no quotes.
"""
        resp = await self.sm.ollama.complete(TaskType.QUERY_EXPANSION, prompt)
        
        new_count = 0
        for line in resp.split('\n'):
            clean = re.sub(r'^\d+[\.\)]\s*', '', line.strip()).replace('"', '').replace("'", "")
            if len(clean) > 10 and clean.lower() not in [n.lower() for n in self.nodes.keys()]:
                self.nodes[clean] = FrontierNode(concept=clean)
                new_count += 1
        
        if new_count > 0:
            console.print(f"[bold blue][Frontier][/bold blue] Expansion: Added {new_count} new technical nodes to the frontier.")

    def _is_saturated(self) -> bool:
        return all(n.status == "saturated" for n in self.nodes.values())
