"""
acquisition/frontier.py — Universal Research Metabolism (Persistence-Enabled)

Architectural Shift:
- Domain-Agnostic: No hardcoded search types.
- Policy-Driven: Runtime-generated 'Research Policy' per subject.
- Persistent: Checkpoint system saves/loads mission state from PostgreSQL.
"""

import asyncio
import json
import logging
import re
from typing import Dict, List, Set, Any, Optional, Tuple, Union
from dataclasses import dataclass, field

from src.utils.console import console
from src.llm.model_router import TaskType

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────
# Epistemic Yield Objectives
# ──────────────────────────────────────────────────────────────

class EpistemicMode:
    GROUNDING = "grounding"       # Facts, definitions
    EXPANSION = "expansion"       # Adjacent fields
    DIALECTIC = "dialectic"       # Conflicts, disputes
    VERIFICATION = "verification" # Artifacts, proof

MODES = {
    EpistemicMode.GROUNDING: "Establish core factual basis and definitions.",
    EpistemicMode.EXPANSION: "Broaden context into adjacent fields.",
    EpistemicMode.DIALECTIC: "Seek contradictions and disagreements.",
    EpistemicMode.VERIFICATION: "Search for high-authority evidence/artifacts."
}

@dataclass
class ResearchPolicy:
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

    def to_dict(self) -> dict:
        return {
            "concept": self.concept,
            "status": self.status,
            "yield_history": self.yield_history,
            "exhausted_modes": list(self.exhausted_modes)
        }

# ──────────────────────────────────────────────────────────────
# Adaptive Controller
# ──────────────────────────────────────────────────────────────

class AdaptiveFrontier:
    def __init__(self, system_manager, topic_id: str, topic_name: str, mission_id: str = None):
        self.sm = system_manager
        self.topic_id = topic_id
        self.topic_name = topic_name
        self.mission_id = mission_id or topic_id
        self.policy = ResearchPolicy()
        self.nodes: Dict[str, FrontierNode] = {}
        self.visited_urls: Set[str] = set()
        self.total_ingested = 0

    async def run(self):
        """Metabolic Control Loop."""
        # 1. Load existing state if it exists
        await self._load_checkpoint()
        
        # 2. Policy Generation (or Load)
        await self._frame_research_policy()
        
        while True:
            # Check budget
            status = self.sm.budget.get_status(self.topic_id)
            if status and status.usage_ratio >= 1.0:
                console.print(f"[bold red][Frontier][/bold red] Storage ceiling reached. Terminating acquisition.")
                break
            
            # 3. Select Next Action
            node, mode = self._select_next_action()
            if not node: 
                console.print(f"[bold cyan][Frontier][/bold cyan] Current frontier saturated. Generating fresh perspectives...")
                await self._respawn_nodes(None) 
                node, mode = self._select_next_action()
                if not node: break

            console.print(f"\n[bold yellow][Frontier][/bold yellow] Dispatching search for: [white]{node.concept}[/white] ({mode})")
            
            # 4. Dynamic Query Engineering
            queries = await self._engineer_queries(node, mode)
            
            # 5. Execute Discovery Batch (Producer Mode)
            round_yield = 0
            for q in queries:
                enqueued = await self.sm.crawler.discover_and_enqueue(
                    topic_id=self.topic_id,
                    topic_name=self.topic_name,
                    query=q,
                    mission_id=self.mission_id,
                    visited_urls=self.visited_urls
                )
                round_yield += enqueued
                self.total_ingested += enqueued
                
            console.print(f"[bold blue][Frontier][/bold blue] Enqueued {round_yield} new targets for vampires.")

            # 6. Thermal Management
            if round_yield == 0:
                console.print(f"[bold red][Frontier][/bold red] Zero discovery for node '{node.concept}'. Triggering Thermal Recovery.")
                await asyncio.sleep(10)

            # 7. Feedback & Checkpoint
            node.yield_history.append(round_yield)
            node.exhausted_modes.add(mode)
            await self._save_node(node)
            
            if round_yield >= 5:
                await self._respawn_nodes(node)
            
            # Small throttle between nodes to let vampires breathe
            await asyncio.sleep(5)

        return self.total_ingested

    async def _load_checkpoint(self):
        """Restore previous state from DB."""
        console.print(f"[bold cyan][Frontier][/bold cyan] Loading persistent state for topic: [white]{self.topic_id}[/white]")
        
        # Load Visited URLs
        self.visited_urls = await self.sm.memory.get_visited_urls(self.topic_id)
        if self.visited_urls:
            console.print(f"[dim]  - Pre-loaded {len(self.visited_urls)} visited URLs.[/dim]")
            
        # Load Nodes using V3 Adapter
        db_nodes = await self.sm.adapter.list_mission_nodes(self.mission_id)
        for n in db_nodes:
            self.nodes[n['label']] = FrontierNode(
                concept=n['label'],
                status=n['status'],
                yield_history=[], # Omitting complex unpack for now
                exhausted_modes=set()
            )
        
        # Fallback to legacy node load if none found
        if not db_nodes:
            legacy_nodes = await self.sm.memory.get_frontier_nodes(self.topic_id)
            for n in legacy_nodes:
                self.nodes[n['concept']] = FrontierNode(
                    concept=n['concept'],
                    status=n['status'],
                    yield_history=n['yield_history'],
                    exhausted_modes=set(n['exhausted_modes'])
                )
                
        if self.nodes:
            console.print(f"[dim]  - Pre-loaded {len(self.nodes)} research nodes from DB.[/dim]")

    async def _save_node(self, node: FrontierNode):
        """Checkpoint a single node."""
        import uuid
        from src.research.domain_schema import MissionNode
        
        node_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{self.mission_id}:{node.concept}"))
        
        v3_node = MissionNode(
            node_id=node_id,
            mission_id=self.mission_id,
            label=node.concept,
            concept_form=node.concept,
            status=node.status
        )
        await self.sm.adapter.upsert_mission_node(v3_node.to_pg_row())
        
        # Legacy save for safety
        await self.sm.memory.upsert_frontier_node(self.topic_id, **node.to_dict())

    async def _frame_research_policy(self):
        """Load policy from DB or generate new one using V3 schema."""
        import json
        import re
        from src.research.domain_schema import DomainProfile, SourcePreferences
        from src.utils.text_processing import repair_json

        mission = await self.sm.adapter.get_mission(self.mission_id)
        profile_id = mission.get("domain_profile_id") if mission else f"profile_{self.mission_id[:8]}"
        
        existing_profile = await self.sm.adapter.get_domain_profile(profile_id)
        
        if existing_profile and existing_profile.get("config_json"):
            try:
                config = json.loads(existing_profile["config_json"])
                if config.get("source_preferences", {}).get("preferred_classes"):
                    console.print(f"[bold blue][Frontier][/bold blue] Resuming with existing V3 Domain Profile.")
                    self.policy = ResearchPolicy(
                        subject_class=existing_profile.get("domain_type", "mixed"),
                        authority_indicators=config.get("source_preferences", {}).get("preferred_classes", []),
                        evidence_types=[]
                    )
                    return
            except:
                pass

        console.print(f"[bold cyan][Frontier][/bold cyan] Designing new V3 domain profile...")
        prompt = f"""
Analyze the subject: {self.topic_name}
1. Define the 'Evidence Stack' (What counts as proof in this specific field?).
2. Define 'Authority' (What kind of sources are most reliable for this subject?).
3. Decompose into 15 foundational, highly specific research nodes to explore. 

Output valid JSON:
{{
  "policy": {{
    "class": "investigative|scientific|historical|technical|etc",
    "authority": ["site types or specific domains"],
    "evidence": ["artifact types"]
  }},
  "nodes": ["node 1", "node 2", ..., "node 15"]
}}
"""
        resp = await self.sm.ollama.complete(TaskType.DECOMPOSITION, prompt)
        try:
            # Robust JSON extraction
            import re
            from src.utils.text_processing import repair_json
            data = {}
            try:
                data = repair_json(resp)
            except:
                # If repair fails, try to grep the nodes specifically
                node_match = re.search(r'"nodes":\s*\[(.*?)\]', resp, re.DOTALL)
                if node_match:
                    nodes_raw = re.findall(r'"(.*?)"', node_match.group(1))
                    data = {"nodes": nodes_raw, "policy": {"class": "investigative"}}
            
            p = data.get('policy', {})
            # Create/Update V3 Profile
            profile = DomainProfile(
                profile_id=profile_id,
                name=f"Profile for {self.topic_name}",
                description=self.topic_name,
                domain_type=p.get('class', 'mixed'),
                source_preferences=SourcePreferences(
                    preferred_classes=p.get('authority', [])
                )
            )
            await self.sm.adapter.upsert_domain_profile(profile.to_pg_row())
            
            self.policy = ResearchPolicy(
                subject_class=profile.domain_type,
                authority_indicators=profile.source_preferences.preferred_classes,
                evidence_types=p.get('evidence', [])
            )
            
            node_count = 0
            for n in data.get('nodes', []):
                # Clean node name (remove "Node 1:", "1.", etc)
                clean_n = re.sub(r'^(Node\s*\d+:?|\d+[\.\)]\s*)', '', n, flags=re.IGNORECASE).strip()
                if clean_n and len(clean_n) > 3:
                    node = FrontierNode(concept=clean_n)
                    self.nodes[clean_n] = node
                    await self._save_node(node)
                    node_count += 1
            
            if node_count > 0:
                console.print(f"[bold blue][Frontier][/bold blue] Initialized {node_count} research nodes. Depth locked.")
            else:
                raise ValueError("No valid nodes extracted")

        except Exception as e:
            logger.error(f"[Frontier] Policy generation failed: {e}. Activating Fallback Depth.")
            fallbacks = [
                self.topic_name, 
                f"{self.topic_name} technical architecture", 
                f"{self.topic_name} implementation details",
                f"{self.topic_name} failure modes",
                f"{self.topic_name} best practices"
            ]
            for fn in fallbacks:
                node = FrontierNode(concept=fn)
                self.nodes[fn] = node
                await self._save_node(node)

    def _select_next_action(self) -> Tuple[Optional[FrontierNode], Optional[str]]:
        active = [n for n in self.nodes.values() if n.status == "underexplored"]
        if not active: return None, None
        
        active.sort(key=lambda n: len(n.exhausted_modes))
        node = active[0]
        
        for mode in [EpistemicMode.GROUNDING, EpistemicMode.VERIFICATION, EpistemicMode.DIALECTIC, EpistemicMode.EXPANSION]:
            if mode not in node.exhausted_modes:
                return node, mode
        
        node.status = "saturated"
        asyncio.create_task(self._save_node(node))
        return self._select_next_action()

    async def _engineer_queries(self, node: FrontierNode, mode: str) -> List[str]:
        prompt = f"""
SUBJECT: {self.topic_name}
CONCEPT: {node.concept}
MODE: {mode} ({MODES[mode]})

Generate 3 search queries with varying complexity:
1. KEYWORD: 3-4 highly specific keywords related to the concept.
2. PHRASE: A concise search phrase (5-8 words).
3. INTENT: A high-intent, specific question a researcher would ask.

CRITICAL:
- NO "Node X" or "Node X:" prefixes.
- NO Boolean logic, quotes, or operators.
- Think like a professional researcher in this specific field.
- Response must be 3 lines, one query per line.
"""
        resp = await self.sm.ollama.complete(TaskType.QUERY_EXPANSION, prompt)
        clean_queries = []
        for q in resp.split('\n'):
            # Aggressive cleaning of prefixes and junk
            c = re.sub(r'^(Node\s*\d+:?|\d+[\.\)]\s*)', '', q.strip(), flags=re.IGNORECASE).strip()
            c = c.replace('"', '').replace("'", "").replace("(", "").replace(")", "")
            c = re.sub(r'^(find|search|explain|analyze|what is|how to)\s+', '', c, flags=re.IGNORECASE)
            for term in [" AND ", " OR ", " NOT "]: c = c.replace(term, " ")
            if len(c) > 3: clean_queries.append(c)
        
        # Always include the raw concept as the ultimate anchor
        # Ensure the concept itself is cleaned too
        clean_concept = re.sub(r'^(Node\s*\d+:?|\d+[\.\)]\s*)', '', node.concept, flags=re.IGNORECASE).strip()
        if clean_concept not in clean_queries:
            clean_queries.insert(0, clean_concept)
            
        return clean_queries[:4]

    async def _respawn_nodes(self, parent_node: Optional[FrontierNode]):
        parent_concept = parent_node.concept if parent_node else self.topic_name
        console.print(f"[bold cyan][Frontier][/bold cyan] Spawning deeper nodes for [white]{parent_concept}[/white]...")
        
        current_context = await self.sm.query(text=parent_concept, topic_filter=self.topic_id, max_results=10)
        
        prompt = f"""
Research Subject: {self.topic_name} | Area: {parent_concept}
Knowledge: {current_context[:2000]}
Identify 3-5 new, specific sub-topics MISSING from this context. No quotes. One per line.
"""
        resp = await self.sm.ollama.complete(TaskType.QUERY_EXPANSION, prompt)
        
        new_count = 0
        for line in resp.split('\n'):
            clean = re.sub(r'^\d+[\.\)]\s*', '', line.strip()).replace('"', '').replace("'", "")
            if len(clean) > 10 and clean.lower() not in [n.lower() for n in self.nodes.keys()]:
                node = FrontierNode(concept=clean)
                self.nodes[clean] = node
                await self._save_node(node)
                new_count += 1
        
        if new_count > 0:
            console.print(f"[bold blue][Frontier][/bold blue] Expansion: Added {new_count} technical nodes to DB.")

    def _is_saturated(self) -> bool:
        return all(n.status == "saturated" for n in self.nodes.values())

    async def apply_nudge(self, instruction: str):
        """Human-in-the-loop steering. Updates policy and active nodes."""
        from src.utils.text_processing import repair_json
        console.print(f"[bold magenta][Frontier] Applying Steering Nudge:[/bold magenta] {instruction}")
        
        prompt = f"""
Research Subject: {self.topic_name}
Current Policy: {self.policy}
Current Active Nodes: {[n for n, node in self.nodes.items() if node.status != 'saturated']}

User Steering Instruction: "{instruction}"

Update the policy and frontier nodes based on the user's instruction.
Output valid JSON:
{{
  "policy_updates": {{
    "authority": ["updated list of site types"],
    "evidence": ["updated list of artifact types"]
  }},
  "nodes_to_drop": ["exact node names to mark saturated"],
  "nodes_to_add": ["new node 1", "new node 2"]
}}
"""
        resp = await self.sm.ollama.complete(TaskType.DECOMPOSITION, prompt)
        try:
            data = repair_json(resp)
            
            # Update Policy
            p_updates = data.get('policy_updates', {})
            if 'authority' in p_updates:
                self.policy.authority_indicators = p_updates['authority']
            if 'evidence' in p_updates:
                self.policy.evidence_types = p_updates['evidence']
                
            from src.research.domain_schema import DomainProfile, SourcePreferences
            profile_id = f"profile_{self.mission_id[:8]}"
            profile = DomainProfile(
                profile_id=profile_id,
                name=f"Profile for {self.topic_name}",
                description=self.topic_name,
                domain_type=self.policy.subject_class,
                source_preferences=SourcePreferences(
                    preferred_classes=self.policy.authority_indicators
                )
            )
            await self.sm.adapter.upsert_domain_profile(profile.to_pg_row())
            
            # Drop nodes
            dropped = 0
            for drop_name in data.get('nodes_to_drop', []):
                if drop_name in self.nodes:
                    self.nodes[drop_name].status = "saturated"
                    await self._save_node(self.nodes[drop_name])
                    dropped += 1
                    
            # Add nodes
            added = 0
            for add_name in data.get('nodes_to_add', []):
                if add_name not in self.nodes:
                    node = FrontierNode(concept=add_name)
                    self.nodes[add_name] = node
                    await self._save_node(node)
                    added += 1
                    
            console.print(f"[bold magenta][Frontier] Nudge Applied:[/bold magenta] Dropped {dropped} nodes, added {added} nodes. Policy updated.")
        except Exception as e:
            console.print(f"[bold red][Frontier] Failed to parse nudge instructions: {e}[/bold red]")
