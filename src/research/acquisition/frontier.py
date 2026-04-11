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
import math
import re
from typing import Dict, List, Set, Any, Optional, Tuple, Union
from dataclasses import dataclass, field

from src.utils.console import console
from src.llm.model_router import TaskType
from src.utils.json_validator import JSONValidator

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
    parent_node_id: Optional[str] = None

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
    # Governance limits (tunable)
    MAX_RESPAWN_CYCLES = 3  # Maximum times we can regenerate frontier before failing
    MAX_CONSECUTIVE_ZERO_YIELD = 5  # Maximum consecutive nodes with zero discovery
    QUEUE_BACKPRESSURE_THRESHOLD = 8000  # Pause discovery when queue hits this depth

    def __init__(self, system_manager, mission_id: str, topic_name: str):
        self.sm = system_manager
        self.mission_id = mission_id
        self.topic_name = topic_name
        self.policy = ResearchPolicy()
        self.nodes: Dict[str, FrontierNode] = {}
        self.visited_urls: Set[str] = set()
        self.total_ingested = 0
        self.respawn_count = 0
        self.consecutive_zero_yield = 0
        self.failed = False
        self.failure_reason: Optional[str] = None

        # Convergence tracking
        self._yield_history: List[int] = []  # per-cycle yield
        self._novelty_window: List[int] = []  # last N cycle yields
        self._novelty_window_size = 5

    async def run(self):
        """Metabolic Control Loop."""
        # 1. Load existing state if it exists
        await self._load_checkpoint()

        # 2. Policy Generation (or Load)
        await self._frame_research_policy()

        while True:
            # Check if mission already failed (from previous iteration)
            if self.failed:
                break

            # Check budget
            status = self.sm.budget.get_status(self.mission_id)
            if status and status.usage_ratio >= 1.0:
                await self._fail_mission("BUDGET_EXCEEDED")
                break

            # Queue backpressure: pause discovery if scrape queue is saturated
            queue_depth = await self.sm.adapter.get_queue_depth("queue:scraping")
            if queue_depth >= self.QUEUE_BACKPRESSURE_THRESHOLD:
                console.print(f"[bold orange][Frontier][/bold orange] Queue backpressure: depth={queue_depth}, waiting for vampires to consume...")
                await asyncio.sleep(30)
                continue  # Skip this cycle, let vampires drain the queue

            # Budget status diagnostics
            budget_status = self.sm.budget.get_status(self.mission_id)
            if budget_status:
                raw_mb = budget_status.raw_bytes / (1024**2)
                ceiling_gb = budget_status.ceiling_bytes / (1024**3)
                ratio = budget_status.usage_ratio
                pending = budget_status.pending_source_count
                console.print(f"[dim][Budget] Raw: {raw_mb:.1f}MB / {ceiling_gb:.1f}GB ({ratio:.2%}) | Pending: {pending} | Condensed: {budget_status.condensed_bytes/(1024**2):.1f}MB | Running: {budget_status.condensation_running}[/dim]")

            # 3. Select Next Action
            node, mode = self._select_next_action()
            if not node:
                # All nodes saturated, attempt to respawn new frontier
                console.print(f"[bold cyan][Frontier][/bold cyan] Current frontier saturated. Generating fresh perspectives...")
                if self.respawn_count >= self.MAX_RESPAWN_CYCLES:
                    await self._fail_mission("NO_DISCOVERY")
                    break

                self.respawn_count += 1
                console.print(f"[yellow][Frontier][/yellow] Respawn cycle {self.respawn_count}/{self.MAX_RESPAWN_CYCLES}")
                await self._respawn_nodes(None)
                node, mode = self._select_next_action()
                if not node:
                    # Even after respawn, no nodes available
                    await self._fail_mission("NO_DISCOVERY")
                    break

            console.print(f"\n[bold yellow][Frontier][/bold yellow] Dispatching search for: [white]{node.concept}[/white] ({mode})")

            # 4. Dynamic Query Engineering
            queries = await self._engineer_queries(node, mode)

            # 5. Execute Discovery Batch (Producer Mode)
            round_yield = 0
            for q in queries:
                enqueued = await self.sm.crawler.discover_and_enqueue(
                    topic_id=self.mission_id,
                    topic_name=self.topic_name,
                    query=q,
                    mission_id=self.mission_id,
                    visited_urls=self.visited_urls
                )
                round_yield += enqueued
                self.total_ingested += enqueued

            console.print(f"[bold blue][Frontier][/bold blue] Enqueued {round_yield} new targets for vampires.")

            # 6. Thermal Management & Zero-Yield Detection
            # Only trigger thermal recovery if BOTH URL discovery AND entity discovery are empty
            if round_yield == 0:
                # Check if we have entities to mine as a secondary discovery channel
                entities = await self.sm.adapter.get_discovery_entities(self.mission_id)
                has_entity_backup = len(entities) > 0

                self.consecutive_zero_yield += 1
                console.print(f"[bold red][Frontier][/bold red] Zero discovery for node '{node.concept}'. Consecutive zeros: {self.consecutive_zero_yield}.")

                if has_entity_backup:
                    console.print(f"[bold yellow][Frontier][/bold yellow] Entity backup available ({len(entities)} entities) — delaying thermal recovery.")
                    # Don't increment further if entities exist; give vampires time to consume
                    if self.consecutive_zero_yield >= 2:
                        # Already waited once; now trigger entity-based queries
                        console.print(f"[bold cyan][Frontier][/bold cyan] Trying entity-based discovery with {min(len(entities), 5)} entities...")
                        await self._entity_based_discovery(entities[:5])
                        self.consecutive_zero_yield = 0  # Reset since we tried a new channel
                        continue

                if self.consecutive_zero_yield >= self.MAX_CONSECUTIVE_ZERO_YIELD:
                    await self._fail_mission("NO_DISCOVERY")
                    break
                await asyncio.sleep(10)
            else:
                # Reset consecutive counter on any yield
                self.consecutive_zero_yield = 0

            # 7. Feedback & Checkpoint
            node.yield_history.append(round_yield)
            node.exhausted_modes.add(mode)
            await self._save_node(node)

            # Update convergence tracking
            self._yield_history.append(round_yield)
            self._novelty_window.append(round_yield)
            if len(self._novelty_window) > self._novelty_window_size:
                self._novelty_window = self._novelty_window[-self._novelty_window_size:]

            # Convergence check: stop if frontier has stabilized
            if self._should_converge():
                console.print(f"[bold green][Frontier][/bold green] Frontier converged — novelty rate below threshold, exploration saturated.")
                break

            if round_yield >= 5:
                await self._respawn_nodes(node)

            # Small throttle between nodes to let vampires breathe
            await asyncio.sleep(5)

        return self.total_ingested

    async def _load_checkpoint(self):
        """Restore previous state from DB."""
        console.print(f"[bold cyan][Frontier][/bold cyan] Loading persistent state for mission: [white]{self.mission_id}[/white]")

        # Load Nodes using V3 Adapter
        db_nodes = await self.sm.adapter.list_mission_nodes(self.mission_id)
        for n in db_nodes:
            # Extract exhausted_modes from JSON column or fallback to empty list
            em_raw = n.get('exhausted_modes_json', '[]')
            if isinstance(em_raw, str):
                try:
                    em_list = json.loads(em_raw)
                except json.JSONDecodeError:
                    em_list = []
            else:
                em_list = em_raw if isinstance(em_raw, list) else []
            self.nodes[n['label']] = FrontierNode(
                concept=n['label'],
                status=n['status'],
                yield_history=[], # Omitting complex unpack for now
                exhausted_modes=set(em_list),
                parent_node_id=n.get('parent_node_id')
            )

        self.visited_urls = await self.sm.adapter.get_visited_urls(self.mission_id)

        if self.nodes:
            console.print(f"[dim]  - Pre-loaded {len(self.nodes)} research nodes from DB.[/dim]")
        if self.visited_urls:
            console.print(f"[dim]  - Pre-loaded {len(self.visited_urls)} visited URLs from DB.[/dim]")

    async def _fail_mission(self, reason: str):
        """Terminate mission with explicit failure reason."""
        self.failed = True
        self.failure_reason = reason
        console.print(f"[bold red][Frontier][/bold red] Mission terminated: {reason}")

        # Update mission status in DB
        try:
            await self.sm.adapter.update_mission_status(
                self.mission_id,
                status="failed",
                stop_reason=reason
            )
        except Exception as e:
            logger.error(f"[Frontier] Failed to update mission status: {e}")

    async def _save_node(self, node: FrontierNode, parent_node_id: Optional[str] = None):
        """Checkpoint a single node."""
        import uuid
        from src.research.domain_schema import MissionNode

        node_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{self.mission_id}:{node.concept}"))

        # Use passed parent_node_id, or the node's stored attribute, or None
        p_id = parent_node_id if parent_node_id is not None else getattr(node, 'parent_node_id', None)

        v3_node = MissionNode(
            node_id=node_id,
            mission_id=self.mission_id,
            parent_node_id=p_id,
            label=node.concept,
            concept_form=node.concept,
            status=node.status,
            exhausted_modes=list(node.exhausted_modes)
        )
        await self.sm.adapter.upsert_mission_node(v3_node.to_pg_row())

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
            
            if not resp or len(resp.strip()) < 10:
                raise ValueError(f"Empty or too short LLM response ({len(resp) if resp else 0} chars)")
            
            logger.debug(f"[Frontier] LLM response length: {len(resp)} chars")
            try:
                # Use JSONValidator's extraction first (better bracket matching)
                validator = JSONValidator()
                raw_json_str = validator._extract_json(resp)
                if raw_json_str:
                    # Try parsing directly first
                    try:
                        data = json.loads(raw_json_str)
                    except json.JSONDecodeError:
                        # If direct parse fails, try repair
                        data = repair_json(raw_json_str)
                else:
                    # No JSON found by bracket matching, try repair_json on full response
                    data = repair_json(resp)
            except Exception as e:
                logger.warning(f"[Frontier] JSON extraction failed: {e}, trying regex fallback")
                # Log first 500 chars for debugging
                logger.debug(f"[Frontier] Raw LLM response (first 500): {resp[:500]}")
                # Regex fallback: find "nodes": [...]
                node_match = re.search(r'"nodes"\s*:\s*\[(.*?)\]', resp, re.DOTALL)
                if node_match:
                    nodes_raw = re.findall(r'"([^"]*?)"', node_match.group(1))
                    data = {"nodes": nodes_raw, "policy": {"class": "technical"}}

            if not data or not data.get('nodes'):
                raise ValueError(f"No valid nodes extracted from LLM response (resp_len={len(resp) if resp else 0})")
            
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
                    node = FrontierNode(concept=clean_n, parent_node_id=None)
                    self.nodes[clean_n] = node
                    await self._save_node(node, parent_node_id=None)
                    node_count += 1
            
            if node_count > 0:
                console.print(f"[bold blue][Frontier][/bold blue] Initialized {node_count} research nodes. Depth locked.")
            else:
                raise ValueError("No valid nodes extracted")

        except Exception as e:
            logger.error(f"[Frontier] Policy generation failed: {e}. Activating Fallback Depth.")
            console.print(f"[yellow][Frontier][/yellow] Fallback: generating heuristic nodes for '{self.topic_name}'")
            fallbacks = [
                self.topic_name,
                f"{self.topic_name} technical architecture",
                f"{self.topic_name} implementation details",
                f"{self.topic_name} failure modes",
                f"{self.topic_name} best practices",
                f"{self.topic_name} performance optimization",
                f"{self.topic_name} security considerations",
                f"{self.topic_name} scalability patterns",
                f"{self.topic_name} testing and validation",
                f"{self.topic_name} deployment strategies",
                f"{self.topic_name} monitoring and observability",
                f"{self.topic_name} data management",
                f"{self.topic_name} integration patterns",
                f"{self.topic_name} error handling",
                f"{self.topic_name} versioning and compatibility"
            ]
            node_count = 0
            for fn in fallbacks:
                try:
                    node = FrontierNode(concept=fn)
                    self.nodes[fn] = node
                    await self._save_node(node)
                    node_count += 1
                except Exception as node_err:
                    logger.warning(f"[Frontier] Failed to save fallback node '{fn}': {node_err}")
            
            if node_count > 0:
                console.print(f"[bold green][Frontier][/bold green] Fallback initialized {node_count} research nodes.")
            else:
                console.print(f"[bold red][Frontier][/bold red] CRITICAL: Fallback node creation also failed!")

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

    async def _entity_based_discovery(self, entities: List[str]) -> int:
        """
        Secondary discovery channel: use extracted entities as search queries.
        This prevents thermal recovery from triggering when we have rich atom content
        but poor URL discovery (e.g., all found URLs are paywalled).

        Includes expansion limiter to prevent combinatorial explosion.
        """
        if not entities:
            return 0

        # Frontier expansion limiter: cap to prevent noise multiplication
        MAX_ENTITY_EXPANSION = 10
        capped = entities[:MAX_ENTITY_EXPANSION]

        if len(entities) > MAX_ENTITY_EXPANSION:
            console.print(f"[dim][Frontier] Capped entity expansion from {len(entities)} to {MAX_ENTITY_EXPANSION}[/dim]")

        round_yield = 0
        for entity in capped:
            # Build entity-focused queries
            entity_queries = [
                f"{entity} architecture implementation",
                f"{entity} performance benchmarks comparison",
                f"{entity} tutorial guide best practices",
            ]
            for q in entity_queries:
                enqueued = await self.sm.crawler.discover_and_enqueue(
                    topic_id=self.mission_id,
                    topic_name=self.topic_name,
                    query=q,
                    mission_id=self.mission_id,
                    visited_urls=self.visited_urls
                )
                round_yield += enqueued

        console.print(f"[bold cyan][Frontier][/bold cyan] Entity-based discovery: enqueued {round_yield} targets from {len(capped)} entities.")
        return round_yield

    async def _engineer_queries(self, node: FrontierNode, mode: str) -> List[str]:
        logger.debug(f"[Frontier] _engineer_queries START: node={node.concept}, mode={mode}")
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
        logger.debug("[Frontier] About to call ollama.complete")
        resp = await self.sm.ollama.complete(TaskType.QUERY_EXPANSION, prompt)
        logger.debug(f"[Frontier] ollama.complete returned, resp_len={len(resp) if resp else 0}")
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
        
        current_context = await self.sm.query(text=parent_concept, topic_filter=self.mission_id, max_results=10)
        
        prompt = f"""
Research Subject: {self.topic_name} | Area: {parent_concept}
Knowledge: {current_context[:2000]}
Identify 3-5 new, specific sub-topics MISSING from this context. No quotes. One per line.
"""
        resp = await self.sm.ollama.complete(TaskType.QUERY_EXPANSION, prompt)
        
        new_count = 0
        # Compute parent_node_id from parent_node (deterministic UUID5) if provided
        import uuid
        parent_node_id = None
        if parent_node is not None:
            parent_node_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{self.mission_id}:{parent_node.concept}"))
        for line in resp.split('\n'):
            clean = re.sub(r'^\d+[\.\)]\s*', '', line.strip()).replace('"', '').replace("'", "")
            if len(clean) > 10 and clean.lower() not in [n.lower() for n in self.nodes.keys()]:
                node = FrontierNode(concept=clean, parent_node_id=parent_node_id)
                self.nodes[clean] = node
                await self._save_node(node, parent_node_id=parent_node_id)
                new_count += 1
        
        if new_count > 0:
            console.print(f"[bold blue][Frontier][/bold blue] Expansion: Added {new_count} technical nodes to DB.")

    def _is_saturated(self) -> bool:
        return all(n.status == "saturated" for n in self.nodes.values())

    def _should_converge(self) -> bool:
        """
        Check if the frontier has converged.
        Stop conditions:
        1. Novelty rate < 5% over last N cycles
        2. Yield entropy is stable (no new information)
        3. All nodes are saturated
        """
        # Need enough data points
        if len(self._novelty_window) < self._novelty_window_size:
            return False

        # Check 1: All nodes saturated
        if self._is_saturated():
            return True

        # Check 2: Novelty rate (fraction of cycles with new discoveries)
        novelty = self._novelty_rate()
        if novelty < 0.05:
            return True

        # Check 3: Yield entropy stability
        if self._yield_entropy() < 0.3:
            return True

        return False

    def _novelty_rate(self) -> float:
        """
        Fraction of recent cycles that produced new discoveries.
        Low novelty rate = exploration is exhausted.
        """
        if not self._novelty_window:
            return 1.0
        productive_cycles = sum(1 for y in self._novelty_window if y > 0)
        return productive_cycles / len(self._novelty_window)

    def _yield_entropy(self) -> float:
        """
        Shannon entropy of yield distribution.
        Low entropy = yields are uniform (no new information patterns).
        Normalized to 0-1 range.
        """
        yields = self._novelty_window
        if len(yields) < 3:
            return 1.0  # Not enough data

        # Normalize yields to probabilities
        total = sum(yields)
        if total == 0:
            return 0.0  # All zeros = no information

        probs = [y / total for y in yields]
        entropy = -sum(p * math.log2(p + 1e-10) for p in probs if p > 1e-10)

        # Normalize by max possible entropy (uniform distribution)
        max_entropy = math.log2(len(yields))
        if max_entropy == 0:
            return 0.0

        return entropy / max_entropy

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
