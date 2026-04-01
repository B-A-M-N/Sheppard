"""
src/research/graph/claim_graph.py

Evidence Graph / Claim Graph — Phase 12-C.

Builds an ephemeral, deterministic graph connecting atoms, derived claims,
contradictions, and analytical bundles into a navigable knowledge structure.

Properties:
  - Ephemeral: constructed per EvidencePacket/section, never persisted
  - Deterministic: same inputs → same node/edge IDs
  - Navigable: connected component, supporting chain, contradiction queries
  - Lossless: every edge traceable to source atom IDs
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set

from src.retrieval.models import RetrievedItem

import logging
logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────
# Edge type enum
# ──────────────────────────────────────────────────────────────

class EdgeType(str, Enum):
    SUPPORTS      = "SUPPORTS"       # Evidence → Derived: atom contributes to derived claim
    DERIVED_FROM  = "DERIVED_FROM"   # Derived → Evidence: derived claim depends on atoms
    CONTRADICTS   = "CONTRADICTS"    # Evidence ↔ Evidence: conflicting claims
    RELATES_TO    = "RELATES_TO"     # Topic → Evidence: atom under topic branch
    SUPERSEDES    = "SUPERSEDES"     # Evidence → Evidence: newer replaces older
    ELABORATES    = "ELABORATES"     # Evidence → Evidence: adds detail, no conflict
    SAME_ENTITY   = "SAME_ENTITY"    # Analytical → Evidence: bundle references atom


# ──────────────────────────────────────────────────────────────
# Node and edge data models
# ──────────────────────────────────────────────────────────────

@dataclass
class GraphNode:
    """A single node in the evidence graph."""
    id: str                          # deterministic hash
    node_type: str                   # "evidence" | "derived" | "analytical" | "contradiction"
    content: str                     # human-readable summary
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class GraphEdge:
    """A directed edge between two graph nodes."""
    id: str                          # "{source_id}:{edge_type}:{target_id}"
    source_id: str
    target_id: str
    edge_type: EdgeType
    weight: float = 1.0
    metadata: Dict[str, Any] = field(default_factory=dict)


# ──────────────────────────────────────────────────────────────
# Graph
# ──────────────────────────────────────────────────────────────

@dataclass
class EvidenceGraph:
    """
    Ephemeral graph of knowledge atoms and their relationships.

    nodes: keyed by deterministic node ID
    edges: keyed by composite edge ID
    index_by_entity: entity name → list of node IDs with that entity
    index_by_topic: topic → list of node IDs
    """
    nodes: Dict[str, GraphNode] = field(default_factory=dict)
    edges: Dict[str, GraphEdge] = field(default_factory=dict)
    index_by_entity: Dict[str, List[str]] = field(default_factory=dict)
    index_by_topic: Dict[str, List[str]] = field(default_factory=dict)

    def _adjacency(self) -> Dict[str, List[str]]:
        """Build adjacency list (undirected) for traversal."""
        adj: Dict[str, List[str]] = {nid: [] for nid in self.nodes}
        for edge in self.edges.values():
            if edge.source_id in adj:
                adj[edge.source_id].append(edge.target_id)
            if edge.target_id in adj:
                adj[edge.target_id].append(edge.source_id)
        return adj

    def get_connected_component(self, node_id: str) -> Set[str]:
        """BFS from node_id; returns all reachable node IDs including start."""
        if node_id not in self.nodes:
            return set()
        adj = self._adjacency()
        visited: Set[str] = set()
        queue = [node_id]
        while queue:
            cur = queue.pop(0)
            if cur in visited:
                continue
            visited.add(cur)
            queue.extend(adj.get(cur, []))
        return visited

    def get_supporting_chain(self, derived_node_id: str) -> List[str]:
        """Return node IDs of all atoms reachable via DERIVED_FROM from a derived node."""
        chain: List[str] = []
        for edge in self.edges.values():
            if edge.source_id == derived_node_id and edge.edge_type == EdgeType.DERIVED_FROM:
                chain.append(edge.target_id)
        return chain

    def get_contradictions(self, entity: Optional[str] = None) -> List[str]:
        """Return node IDs of all ContradictionNodes (optionally filtered by entity)."""
        result = []
        for nid, node in self.nodes.items():
            if node.node_type == "contradiction":
                if entity is None or node.metadata.get("entity") == entity:
                    result.append(nid)
        return result


# ──────────────────────────────────────────────────────────────
# Internal helpers
# ──────────────────────────────────────────────────────────────

def _node_id(node_type: str, source_id: str) -> str:
    raw = f"{node_type}:{source_id}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _edge_id(source_id: str, edge_type: EdgeType, target_id: str) -> str:
    return f"{source_id}:{edge_type.value}:{target_id}"


_STOPWORDS = {
    "a", "an", "the", "and", "or", "is", "are", "was", "were", "be", "been",
    "it", "its", "this", "that", "as", "has", "have", "had", "not", "all",
    "in", "on", "to", "of", "at", "by", "for", "with", "from", "so", "do",
}


def _token_set(text: str) -> set:
    tokens = re.split(r'\W+', text.lower())
    return {t for t in tokens if t and t not in _STOPWORDS and len(t) > 1}


_ELABORATES_THRESHOLD = 0.4


# ──────────────────────────────────────────────────────────────
# Builder
# ──────────────────────────────────────────────────────────────

def build_evidence_graph(
    atoms: List[RetrievedItem],
    derived_claims: list,        # List[DerivedClaim] from 12-A
    analytical_bundles: list,    # List[AnalyticalBundle] from 12-B
    contradictions: list,        # List[dict] from packet.contradictions
) -> EvidenceGraph:
    """
    Construct an EvidenceGraph from all upstream intelligence artifacts.

    Deterministic: inputs are sorted by citation_key before processing.
    Silently skips on any per-item error (never raises).
    """
    graph = EvidenceGraph()

    # --- Sort for determinism ---
    sorted_atoms = sorted(atoms, key=lambda a: a.citation_key or '')

    # --- Build evidence nodes ---
    citation_to_node_id: Dict[str, str] = {}
    for atom in sorted_atoms:
        ck = atom.citation_key or ''
        nid = _node_id("evidence", ck)
        citation_to_node_id[ck] = nid
        graph.nodes[nid] = GraphNode(
            id=nid,
            node_type="evidence",
            content=atom.content[:200],
            metadata={
                "citation_key": ck,
                "item_type": atom.item_type,
                "source": atom.source,
                "recency_days": atom.recency_days,
                "trust_score": atom.trust_score,
            },
        )
        # Entity index
        meta = atom.metadata or {}
        entity = meta.get('entity_id') or meta.get('entity') or meta.get('concept_name')
        if entity:
            graph.index_by_entity.setdefault(entity, []).append(nid)

    # --- ELABORATES edges (high-overlap evidence pairs) ---
    atom_list = sorted_atoms
    token_sets = [_token_set(a.content) for a in atom_list]
    for i in range(len(atom_list)):
        for j in range(i + 1, len(atom_list)):
            union = token_sets[i] | token_sets[j]
            if not union:
                continue
            jaccard = len(token_sets[i] & token_sets[j]) / len(union)
            if jaccard >= _ELABORATES_THRESHOLD:
                try:
                    src_nid = citation_to_node_id[atom_list[i].citation_key or '']
                    tgt_nid = citation_to_node_id[atom_list[j].citation_key or '']
                    eid = _edge_id(src_nid, EdgeType.ELABORATES, tgt_nid)
                    graph.edges[eid] = GraphEdge(
                        id=eid, source_id=src_nid, target_id=tgt_nid,
                        edge_type=EdgeType.ELABORATES,
                        weight=round(jaccard, 4),
                    )
                except Exception as e:
                    logger.debug(f"[claim_graph] ELABORATES edge failed: {e}")

    # --- Derived claim nodes + DERIVED_FROM edges ---
    for claim in derived_claims:
        try:
            nid = _node_id("derived", claim.id)
            graph.nodes[nid] = GraphNode(
                id=nid,
                node_type="derived",
                content=f"{claim.rule}: {claim.output}",
                metadata={
                    "rule": claim.rule,
                    "claim_id": claim.id,
                    "output": claim.output,
                },
            )
            for atom_id in claim.source_atom_ids:
                target_nid = citation_to_node_id.get(atom_id)
                if target_nid:
                    eid = _edge_id(nid, EdgeType.DERIVED_FROM, target_nid)
                    graph.edges[eid] = GraphEdge(
                        id=eid, source_id=nid, target_id=target_nid,
                        edge_type=EdgeType.DERIVED_FROM,
                    )
        except Exception as e:
            logger.debug(f"[claim_graph] Derived node failed: {e}")

    # --- Analytical bundle nodes + SAME_ENTITY edges ---
    for bundle in analytical_bundles:
        try:
            bundle_source = f"{bundle.operator}:{','.join(sorted(bundle.atom_ids))}"
            nid = _node_id("analytical", bundle_source)
            graph.nodes[nid] = GraphNode(
                id=nid,
                node_type="analytical",
                content=f"{bundle.operator}",
                metadata={
                    "operator": bundle.operator,
                    "atom_count": len(bundle.atom_ids),
                },
            )
            for atom_id in bundle.atom_ids:
                target_nid = citation_to_node_id.get(atom_id)
                if target_nid:
                    eid = _edge_id(nid, EdgeType.SAME_ENTITY, target_nid)
                    graph.edges[eid] = GraphEdge(
                        id=eid, source_id=nid, target_id=target_nid,
                        edge_type=EdgeType.SAME_ENTITY,
                    )
        except Exception as e:
            logger.debug(f"[claim_graph] Analytical node failed: {e}")

    # --- Contradiction nodes + CONTRADICTS edges ---
    for c in contradictions:
        try:
            a_id = c.get('atom_a_id', '')
            b_id = c.get('atom_b_id', '')
            desc = c.get('description', '')
            nid = _node_id("contradiction", f"{a_id}:{b_id}:{desc}")
            graph.nodes[nid] = GraphNode(
                id=nid,
                node_type="contradiction",
                content=desc,
                metadata={"atom_a_id": a_id, "atom_b_id": b_id},
            )
            for atom_id in (a_id, b_id):
                target_nid = citation_to_node_id.get(atom_id)
                if target_nid:
                    eid = _edge_id(nid, EdgeType.CONTRADICTS, target_nid)
                    graph.edges[eid] = GraphEdge(
                        id=eid, source_id=nid, target_id=target_nid,
                        edge_type=EdgeType.CONTRADICTS,
                    )
        except Exception as e:
            logger.debug(f"[claim_graph] Contradiction node failed: {e}")

    return graph
