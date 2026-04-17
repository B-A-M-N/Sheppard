"""
src/research/graph/gap_scorer.py — Identify retrieval gaps from an evidence graph.

Given an EvidenceGraph built from a first retrieval pass, score_gaps() returns
a prioritised list of RetrievalGap objects.  Each gap carries a query string
that can drive a targeted second retrieval pass.

Gap types (highest → lowest priority):
  contradiction     (0.9) — unresolved contradiction nodes need arbitrating evidence
  unsupported_derived (0.7) — derived claim has no DERIVED_FROM link to any atom
  isolated          (0.6) — evidence node has no edges at all
  sparse_cluster    (0.5) — evidence node is in a singleton connected component

Design constraints:
  - Deterministic: same graph → same gaps (sorted by nid for tiebreaking)
  - Bounded: caller controls max_gaps to prevent query explosion
  - Never raises: silently skips per-node errors
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Set

from src.research.graph.claim_graph import EdgeType, EvidenceGraph

logger = logging.getLogger(__name__)

_MAX_QUERY_CHARS = 120


@dataclass
class RetrievalGap:
    """A single retrieval gap derived from graph analysis."""
    query: str
    priority: float           # 0.0 – 1.0; higher = more urgent to fill
    gap_type: str             # contradiction | unsupported_derived | isolated | sparse_cluster
    source_node_ids: List[str] = field(default_factory=list)


def score_gaps(graph: EvidenceGraph, max_gaps: int = 4) -> List[RetrievalGap]:
    """Return up to *max_gaps* RetrievalGaps from *graph*, sorted by priority desc.

    Called after the initial evidence graph is built.  The returned gaps drive a
    bounded second retrieval pass in EvidenceAssembler._build_from_context().
    """
    if not graph.nodes:
        return []

    gaps: List[RetrievalGap] = []

    # ── Degree map (undirected) ─────────────────────────────────────────────
    degree: Dict[str, int] = {nid: 0 for nid in graph.nodes}
    for edge in graph.edges.values():
        degree[edge.source_id] = degree.get(edge.source_id, 0) + 1
        degree[edge.target_id] = degree.get(edge.target_id, 0) + 1

    # ── Gap 1: Contradiction nodes (priority 0.9) ───────────────────────────
    for nid in sorted(graph.nodes):
        node = graph.nodes[nid]
        if node.node_type != "contradiction":
            continue
        try:
            query = node.content[:_MAX_QUERY_CHARS] or "unresolved contradiction"
            gaps.append(RetrievalGap(
                query=query,
                priority=0.9,
                gap_type="contradiction",
                source_node_ids=[nid],
            ))
        except Exception as e:
            logger.debug(f"[gap_scorer] contradiction gap failed for {nid}: {e}")

    # ── Gap 2: Unsupported derived claims (priority 0.7) ────────────────────
    derived_with_support: Set[str] = set()
    for edge in graph.edges.values():
        if edge.edge_type == EdgeType.DERIVED_FROM:
            derived_with_support.add(edge.source_id)

    for nid in sorted(graph.nodes):
        node = graph.nodes[nid]
        if node.node_type != "derived" or nid in derived_with_support:
            continue
        try:
            query = node.content[:_MAX_QUERY_CHARS] or "derived claim"
            gaps.append(RetrievalGap(
                query=query,
                priority=0.7,
                gap_type="unsupported_derived",
                source_node_ids=[nid],
            ))
        except Exception as e:
            logger.debug(f"[gap_scorer] unsupported_derived gap failed for {nid}: {e}")

    # ── Gap 3: Isolated evidence nodes — degree 0 (priority 0.6) ───────────
    for nid in sorted(graph.nodes):
        node = graph.nodes[nid]
        if node.node_type != "evidence" or degree.get(nid, 0) != 0:
            continue
        try:
            query = node.content[:_MAX_QUERY_CHARS]
            if query:
                gaps.append(RetrievalGap(
                    query=query,
                    priority=0.6,
                    gap_type="isolated",
                    source_node_ids=[nid],
                ))
        except Exception as e:
            logger.debug(f"[gap_scorer] isolated gap failed for {nid}: {e}")

    # ── Gap 4: Singleton connected components among connected evidence (0.5) ─
    # Only nodes that have at least one edge but form a size-1 evidence cluster.
    connected_evidence = {
        nid for nid, n in graph.nodes.items()
        if n.node_type == "evidence" and degree.get(nid, 0) > 0
    }
    visited: Set[str] = set()
    for start in sorted(connected_evidence):
        if start in visited:
            continue
        component = graph.get_connected_component(start) & connected_evidence
        visited |= component
        if len(component) != 1:
            continue
        node = graph.nodes[start]
        try:
            query = node.content[:_MAX_QUERY_CHARS]
            if query:
                gaps.append(RetrievalGap(
                    query=query,
                    priority=0.5,
                    gap_type="sparse_cluster",
                    source_node_ids=[start],
                ))
        except Exception as e:
            logger.debug(f"[gap_scorer] sparse_cluster gap failed for {start}: {e}")

    # ── Deduplicate by query string, sort by priority desc, cap ─────────────
    seen_queries: Set[str] = set()
    result: List[RetrievalGap] = []
    for gap in sorted(gaps, key=lambda g: g.priority, reverse=True):
        if len(result) >= max_gaps:
            break
        if gap.query not in seen_queries:
            seen_queries.add(gap.query)
            result.append(gap)

    return result
