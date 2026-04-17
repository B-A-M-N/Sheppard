"""
cmk/belief_graph.py — Global Belief Graph layer.

Nodes = canonical claims (truth units)
Edges = reasoning links (supports, contradicts, implies, refines,
         depends_on, analogous_to, instantiates, causes)

This is NOT a storage graph. It's a reasoning constraint layer:
  - If no edge exists, the LLM cannot connect two ideas
  - Paths through the graph are verified reasoning chains
  - Authority propagates along edges
  - Contradictions propagate and suppress related beliefs

All knowledge is ONE connected graph. Topics are clustering artifacts.
"""

import logging
import uuid
import json
from typing import List, Dict, Any, Optional, Set, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────
# Relation types (keep this small — 8 max)
# ──────────────────────────────────────────────────────────────

class RelationType(str, Enum):
    SUPPORTS = "supports"           # strengthens another claim
    CONTRADICTS = "contradicts"     # conflicts with another claim
    IMPLIES = "implies"             # logically leads to
    REFINES = "refines"             # makes more specific
    DEPENDS_ON = "depends_on"       # prerequisite knowledge
    ANALOGOUS_TO = "analogous_to"   # structural similarity across domains
    INSTANTIATES = "instantiates"   # concrete example of abstract principle
    CAUSES = "causes"               # causal relationship


# All relation types
ALL_RELATIONS = [r.value for r in RelationType]

# Directed relations (asymmetric)
DIRECTED_RELATIONS = {
    RelationType.IMPLIES.value,
    RelationType.REFINES.value,
    RelationType.DEPENDS_ON.value,
    RelationType.CAUSES.value,
    RelationType.INSTANTIATES.value,
}

# Undirected/symmetric relations
SYMMETRIC_RELATIONS = {
    RelationType.SUPPORTS.value,
    RelationType.CONTRADICTS.value,
    RelationType.ANALOGOUS_TO.value,
}


@dataclass
class BeliefNode:
    """A node in the global belief graph — a canonical claim."""
    id: str
    claim: str
    domain: str = ""
    authority_score: float = 0.0
    stability_score: float = 0.0
    contradiction_pressure: float = 0.0
    revision_count: int = 0
    embedding: Optional[List[float]] = None
    canonical_id: Optional[str] = None  # Link to CKS
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    # Graph metadata
    neighbor_count: int = 0
    edge_types: Set[str] = field(default_factory=set)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "claim": self.claim,
            "domain": self.domain,
            "authority_score": self.authority_score,
            "stability_score": self.stability_score,
            "contradiction_pressure": self.contradiction_pressure,
            "revision_count": self.revision_count,
            "neighbor_count": self.neighbor_count,
            "edge_types": list(self.edge_types),
        }


@dataclass
class BeliefEdge:
    """A reasoning link between two belief nodes."""
    id: str
    from_node: str
    to_node: str
    relation_type: str
    strength: float  # 0-1 confidence in the relationship
    evidence_atom_ids: List[str] = field(default_factory=list)
    reason: str = ""  # LLM-generated explanation for the edge
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "from_node": self.from_node,
            "to_node": self.to_node,
            "relation_type": self.relation_type,
            "strength": self.strength,
            "evidence_atom_ids": self.evidence_atom_ids,
            "reason": self.reason,
        }


@dataclass
class BeliefPath:
    """A verified reasoning chain through the belief graph."""
    nodes: List[BeliefNode]
    edges: List[BeliefEdge]
    path_score: float  # Overall confidence in this chain

    @property
    def chain_text(self) -> str:
        if not self.nodes or not self.edges:
            return ""
        parts = [self.nodes[0].claim]
        for i, edge in enumerate(self.edges):
            if i + 1 < len(self.nodes):
                parts.append(f" --[{edge.relation_type}({edge.strength:.2f})]--> {self.nodes[i+1].claim}")
        return " → ".join(parts) if len(self.nodes) <= 3 else f"{self.nodes[0].claim} → ... → {self.nodes[-1].claim}"


class BeliefGraph:
    """
    Global Belief Graph — the reasoning substrate.

    All knowledge is ONE connected graph. Topics are clustering artifacts.
    Concept anchors serve as cross-domain hubs.

    In production: backed by Postgres (belief_nodes, belief_edges tables).
    For now: in-memory with persistence hooks.
    """

    def __init__(self, pg_pool=None):
        self.pg_pool = pg_pool
        self._nodes: Dict[str, BeliefNode] = {}
        self._edges: Dict[str, BeliefEdge] = {}  # edge_id → edge
        # Adjacency lists
        self._outgoing: Dict[str, List[str]] = {}  # node_id → [edge_ids]
        self._incoming: Dict[str, List[str]] = {}

    # ── Node operations ──

    def add_node(self, node: BeliefNode) -> str:
        """Add or update a belief node."""
        self._nodes[node.id] = node
        if node.id not in self._outgoing:
            self._outgoing[node.id] = []
            self._incoming[node.id] = []

        # Persist
        if self.pg_pool:
            self._persist_node(node)

        return node.id

    def get_node(self, node_id: str) -> Optional[BeliefNode]:
        """Get a belief node by ID."""
        return self._nodes.get(node_id)

    def remove_node(self, node_id: str):
        """Remove a node and all its edges."""
        # Remove edges
        for edge_id in list(self._outgoing.get(node_id, [])) + list(self._incoming.get(node_id, [])):
            self._edges.pop(edge_id, None)

        self._outgoing.pop(node_id, None)
        self._incoming.pop(node_id, None)
        self._nodes.pop(node_id, None)

    # ── Edge operations ──

    def add_edge(
        self,
        from_node: str,
        to_node: str,
        relation_type: str,
        strength: float,
        evidence_atom_ids: Optional[List[str]] = None,
        reason: str = "",
    ) -> Optional[BeliefEdge]:
        """
        Add a reasoning link between two belief nodes.

        Returns the edge if created, None if duplicate exists.
        """
        if from_node not in self._nodes or to_node not in self._nodes:
            logger.warning(f"[BeliefGraph] Cannot add edge: missing node(s) {from_node}/{to_node}")
            return None

        if relation_type not in ALL_RELATIONS:
            logger.warning(f"[BeliefGraph] Invalid relation type: {relation_type}")
            return None

        if not (0.0 <= strength <= 1.0):
            logger.warning(f"[BeliefGraph] Strength out of range: {strength}")
            return None

        # Check for duplicate
        for edge_id, edge in self._edges.items():
            if (edge.from_node == from_node and
                edge.to_node == to_node and
                edge.relation_type == relation_type):
                # Update existing
                edge.strength = strength
                edge.reason = reason
                return edge

        edge_id = str(uuid.uuid4())
        edge = BeliefEdge(
            id=edge_id,
            from_node=from_node,
            to_node=to_node,
            relation_type=relation_type,
            strength=strength,
            evidence_atom_ids=evidence_atom_ids or [],
            reason=reason,
        )

        self._edges[edge_id] = edge
        self._outgoing.setdefault(from_node, []).append(edge_id)
        self._incoming.setdefault(to_node, []).append(edge_id)

        # Update node metadata
        self._nodes[from_node].neighbor_count = len(self._outgoing.get(from_node, []))
        self._nodes[from_node].edge_types.add(relation_type)
        self._nodes[to_node].neighbor_count = len(self._incoming.get(to_node, []))
        self._nodes[to_node].edge_types.add(relation_type)

        # For symmetric relations, add reverse edge too
        if relation_type in SYMMETRIC_RELATIONS and from_node != to_node:
            # Check if reverse already exists
            reverse_exists = any(
                e.from_node == to_node and e.to_node == from_node and e.relation_type == relation_type
                for e in self._edges.values()
            )
            if not reverse_exists:
                rev_id = str(uuid.uuid4())
                rev_edge = BeliefEdge(
                    id=rev_id,
                    from_node=to_node,
                    to_node=from_node,
                    relation_type=relation_type,
                    strength=strength,
                    evidence_atom_ids=evidence_atom_ids or [],
                    reason=f"(symmetric of {edge_id})",
                )
                self._edges[rev_id] = rev_edge
                self._outgoing.setdefault(to_node, []).append(rev_id)
                self._incoming.setdefault(from_node, []).append(rev_id)

        # Persist
        if self.pg_pool:
            self._persist_edge(edge)

        return edge

    def get_neighbors(self, node_id: str, relation_type: Optional[str] = None) -> List[Tuple[BeliefNode, BeliefEdge]]:
        """
        Get all neighbors of a node, optionally filtered by relation type.

        Returns:
            List of (neighbor_node, connecting_edge) tuples
        """
        if node_id not in self._nodes:
            return []

        neighbors = []

        # Outgoing edges
        for edge_id in self._outgoing.get(node_id, []):
            edge = self._edges.get(edge_id)
            if edge and (relation_type is None or edge.relation_type == relation_type):
                neighbor = self._nodes.get(edge.to_node)
                if neighbor:
                    neighbors.append((neighbor, edge))

        # Incoming edges (for directed relations)
        for edge_id in self._incoming.get(node_id, []):
            edge = self._edges.get(edge_id)
            if edge and edge.from_node != node_id:  # Don't double-count symmetric
                if relation_type is None or edge.relation_type == relation_type:
                    neighbor = self._nodes.get(edge.from_node)
                    if neighbor:
                        neighbors.append((neighbor, edge))

        return neighbors

    # ── Path finding ──

    def find_paths(
        self,
        from_node: str,
        to_node: str,
        max_hops: int = 3,
        min_edge_strength: float = 0.5,
    ) -> List[BeliefPath]:
        """
        Find all reasoning paths between two nodes.

        Uses BFS with path tracking.

        Args:
            from_node: Start node ID
            to_node: End node ID
            max_hops: Maximum path length
            min_edge_strength: Minimum edge strength to traverse

        Returns:
            List of BeliefPath objects, sorted by path_score descending
        """
        if from_node not in self._nodes or to_node not in self._nodes:
            return []

        # BFS with path tracking
        paths: List[BeliefPath] = []
        # Queue: (current_node_id, visited_nodes, traversed_edges)
        queue = [(from_node, [from_node], [])]
        visited_paths = set()

        while queue:
            current, nodes_visited, edges_traversed = queue.pop(0)

            if current == to_node and len(nodes_visited) > 1:
                # Found a path
                path_nodes = [self._nodes[nid] for nid in nodes_visited]
                path_edges = [self._edges[eid] for eid in edges_traversed]

                # Compute path score (geometric mean of edge strengths, penalized by length)
                strengths = [e.strength for e in path_edges]
                if strengths:
                    import math
                    geo_mean = math.prod(strengths) ** (1 / len(strengths))
                    length_penalty = 1.0 / len(path_edges)
                    authority_boost = sum(n.authority_score for n in path_nodes) / len(path_nodes)

                    path_score = geo_mean * 0.5 + length_penalty * 0.2 + authority_boost * 0.3
                else:
                    path_score = 0.0

                path_key = tuple(nodes_visited)
                if path_key not in visited_paths:
                    visited_paths.add(path_key)
                    paths.append(BeliefPath(
                        nodes=path_nodes,
                        edges=path_edges,
                        path_score=path_score,
                    ))

                continue

            if len(nodes_visited) >= max_hops + 1:
                continue

            # Expand neighbors
            for neighbor, edge in self.get_neighbors(current):
                if neighbor.id not in nodes_visited and edge.strength >= min_edge_strength:
                    queue.append((
                        neighbor.id,
                        nodes_visited + [neighbor.id],
                        edges_traversed + [edge.id],
                    ))

        paths.sort(key=lambda p: p.path_score, reverse=True)
        return paths

    def find_best_path(self, from_node: str, to_node: str, **kwargs) -> Optional[BeliefPath]:
        """Find the single best path between two nodes."""
        paths = self.find_paths(from_node, to_node, **kwargs)
        return paths[0] if paths else None

    # ── Graph traversal ──

    def expand_from(
        self,
        node_id: str,
        max_hops: int = 2,
        min_strength: float = 0.5,
        relation_filter: Optional[Set[str]] = None,
    ) -> Set[str]:
        """
        Expand from a node, collecting all reachable node IDs within max_hops.

        Used for graph-based retrieval expansion.
        """
        if node_id not in self._nodes:
            return set()

        visited = {node_id}
        frontier = {node_id}

        for _ in range(max_hops):
            next_frontier = set()
            for nid in frontier:
                for neighbor, edge in self.get_neighbors(nid):
                    if neighbor.id not in visited and edge.strength >= min_strength:
                        if relation_filter is None or edge.relation_type in relation_filter:
                            visited.add(neighbor.id)
                            next_frontier.add(neighbor.id)
            frontier = next_frontier
            if not frontier:
                break

        return visited

    # ── Authority propagation ──

    def propagate_authority(self, iterations: int = 3, damping: float = 0.1):
        """
        Propagate authority scores across the graph.

        High-authority nodes boost their neighbors.
        Contradictions suppress related nodes.

        Similar to PageRank but with semantic relation awareness.
        """
        for _ in range(iterations):
            updates = {}

            for node_id, node in self._nodes.items():
                boost = 0.0
                suppression = 0.0

                for neighbor, edge in self.get_neighbors(node_id):
                    if edge.relation_type == RelationType.CONTRADICTS.value:
                        # High-authority contradictions suppress this node
                        if neighbor.authority_score > node.authority_score:
                            suppression += neighbor.authority_score * edge.strength * damping
                    elif edge.relation_type in (RelationType.SUPPORTS.value, RelationType.IMPLIES.value):
                        # High-authority supporters boost this node
                        boost += neighbor.authority_score * edge.strength * damping
                    elif edge.relation_type in (RelationType.REFINES.value, RelationType.DEPENDS_ON.value):
                        # Refinements and dependencies share authority
                        boost += neighbor.authority_score * edge.strength * damping * 0.5

                if boost > 0 or suppression > 0:
                    new_authority = max(0.0, min(1.0,
                        node.authority_score + boost - suppression
                    ))
                    updates[node_id] = new_authority

            # Apply all updates
            for node_id, new_authority in updates.items():
                self._nodes[node_id].authority_score = new_authority

    # ── Contradiction propagation ──

    def propagate_contradictions(self, threshold: float = 0.3) -> List[Dict[str, Any]]:
        """
        Propagate contradiction pressure through the graph.

        If a node has high contradiction pressure, related nodes
        via SUPPORTS/IMPLIES edges also receive pressure.

        Returns:
            List of affected node IDs with their new pressure scores
        """
        affected = []

        for node_id, node in self._nodes.items():
            if node.contradiction_pressure < threshold:
                continue

            # Propagate to supporters
            for neighbor, edge in self.get_neighbors(node_id):
                if edge.relation_type in (RelationType.SUPPORTS.value, RelationType.IMPLIES.value):
                    # If this claim is contradicted, claims that support it
                    # also get some pressure
                    propagated_pressure = node.contradiction_pressure * edge.strength * 0.3
                    old_pressure = neighbor.contradiction_pressure
                    neighbor.contradiction_pressure = min(1.0,
                        old_pressure + propagated_pressure
                    )

                    if abs(neighbor.contradiction_pressure - old_pressure) > 0.05:
                        affected.append({
                            "node_id": neighbor.id,
                            "contradiction_pressure": neighbor.contradiction_pressure,
                            "source": node_id,
                        })

        return affected

    # ── Stats ──

    def get_stats(self) -> Dict[str, Any]:
        relation_counts = {}
        for edge in self._edges.values():
            relation_counts[edge.relation_type] = relation_counts.get(edge.relation_type, 0) + 1

        return {
            "nodes": len(self._nodes),
            "edges": len(self._edges),
            "relation_types": relation_counts,
            "avg_neighbors": sum(n.neighbor_count for n in self._nodes.values()) / max(1, len(self._nodes)),
            "avg_authority": sum(n.authority_score for n in self._nodes.values()) / max(1, len(self._nodes)),
            "disconnected_nodes": sum(
                1 for n in self._nodes.values() if n.neighbor_count == 0
            ),
        }

    # ── Persistence ──

    async def load_from_db(self) -> int:
        """Load persisted belief nodes and edges into memory."""
        if self.pg_pool is None:
            return 0

        def _parse_embedding(value):
            if value is None:
                return None
            if isinstance(value, str):
                try:
                    return json.loads(value)
                except Exception:
                    return None
            try:
                return list(value)
            except TypeError:
                return None

        try:
            async with self.pg_pool.acquire() as conn:
                node_rows = await conn.fetch(
                    """
                    SELECT id, canonical_id, claim, domain, authority_score,
                           stability_score, contradiction_pressure, revision_count,
                           embedding, created_at, updated_at
                    FROM belief_nodes
                    """
                )
                edge_rows = await conn.fetch(
                    """
                    SELECT id, from_node, to_node, relation_type, strength,
                           evidence_atom_ids, reason, created_at
                    FROM belief_edges
                    """
                )
        except Exception as e:
            err = str(e).lower()
            if "does not exist" in err or "undefinedtable" in err or "relation" in err:
                logger.debug(f"[BeliefGraph] Load skipped — table missing: {e}")
                return 0
            raise

        self._nodes = {}
        self._edges = {}
        self._outgoing = {}
        self._incoming = {}

        for row in node_rows:
            node = BeliefNode(
                id=str(row["id"]),
                claim=row["claim"],
                domain=row["domain"] or "",
                authority_score=float(row["authority_score"] or 0.0),
                stability_score=float(row["stability_score"] or 0.0),
                contradiction_pressure=float(row["contradiction_pressure"] or 0.0),
                revision_count=int(row["revision_count"] or 0),
                embedding=_parse_embedding(row["embedding"]),
                canonical_id=str(row["canonical_id"]) if row["canonical_id"] is not None else None,
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )
            self._nodes[node.id] = node
            self._outgoing[node.id] = []
            self._incoming[node.id] = []

        for row in edge_rows:
            from_node = str(row["from_node"])
            to_node = str(row["to_node"])
            if from_node not in self._nodes or to_node not in self._nodes:
                continue

            edge = BeliefEdge(
                id=str(row["id"]),
                from_node=from_node,
                to_node=to_node,
                relation_type=row["relation_type"],
                strength=float(row["strength"] or 0.0),
                evidence_atom_ids=list(row["evidence_atom_ids"] or []),
                reason=row["reason"] or "",
                created_at=row["created_at"],
            )
            self._edges[edge.id] = edge
            self._outgoing[from_node].append(edge.id)
            self._incoming[to_node].append(edge.id)
            self._nodes[from_node].neighbor_count = len(self._outgoing[from_node])
            self._nodes[from_node].edge_types.add(edge.relation_type)
            self._nodes[to_node].neighbor_count = len(self._incoming[to_node])
            self._nodes[to_node].edge_types.add(edge.relation_type)

        return len(self._nodes)

    async def _persist_node(self, node: BeliefNode):
        """Persist a node to Postgres."""
        if not self.pg_pool:
            return
        try:
            import json as _json
            async with self.pg_pool.acquire() as conn:
                emb = _json.dumps(node.embedding) if node.embedding else None
                await conn.execute(
                    """
                    INSERT INTO belief_nodes
                        (id, canonical_id, claim, domain, authority_score,
                         stability_score, contradiction_pressure, revision_count,
                         embedding, updated_at)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, NOW())
                    ON CONFLICT (id) DO UPDATE SET
                        claim = EXCLUDED.claim,
                        domain = EXCLUDED.domain,
                        authority_score = EXCLUDED.authority_score,
                        stability_score = EXCLUDED.stability_score,
                        contradiction_pressure = EXCLUDED.contradiction_pressure,
                        revision_count = EXCLUDED.revision_count,
                        updated_at = NOW()
                    """,
                    node.id, node.canonical_id, node.claim, node.domain,
                    node.authority_score, node.stability_score,
                    node.contradiction_pressure, node.revision_count, emb,
                )
        except Exception as e:
            logger.debug(f"[BeliefGraph] Node persist failed for {node.id}: {e}")

    async def _persist_edge(self, edge: BeliefEdge):
        """Persist an edge to Postgres."""
        if not self.pg_pool:
            return
        try:
            async with self.pg_pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO belief_edges
                        (id, from_node, to_node, relation_type, strength,
                         evidence_atom_ids, reason)
                    VALUES ($1, $2, $3, $4, $5, $6, $7)
                    ON CONFLICT (from_node, to_node, relation_type) DO UPDATE SET
                        strength = EXCLUDED.strength,
                        evidence_atom_ids = EXCLUDED.evidence_atom_ids,
                        reason = EXCLUDED.reason
                    """,
                    edge.id, edge.from_node, edge.to_node,
                    edge.relation_type, edge.strength,
                    edge.evidence_atom_ids, edge.reason,
                )
        except Exception as e:
            logger.debug(f"[BeliefGraph] Edge persist failed for {edge.id}: {e}")
