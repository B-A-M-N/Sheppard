# Phase 12-C — Context: Evidence Graph / Claim Graph

## Position in Stack

**12-C = Structure** — relational intelligence made navigable.

Builds an ephemeral graph connecting atoms, derived claims, contradictions, and analytical bundles into a navigable knowledge structure. Without this, long reports are flat fact-dumps. With it, the planner can reason about what belongs together, what supports what, and what conflicts.

**Master Invariant:** The writer never invents intelligence; it renders intelligence already mechanically assembled upstream.

---

## Current State

**Nothing built.** 12-C is pure plan, no implementation.

---

## What Must Be Built

### Node Types

| Type | Purpose | Input |
|------|---------|-------|
| `EvidenceNode` | Raw knowledge atom reference | RetrievedItem (citation_key, content, source) |
| `DerivedNode` | Computed relationship | DerivedClaim (rule, source_atoms, output) |
| `ContradictionNode` | Explicit conflict | Pair of conflicting atoms |
| `AnalyticalNode` | Structured comparison | AnalyticalBundle from 12-B |
| `TopicNode` | Conceptual clustering (from frontier) | FrontierNode.concept, subtopics |

### Edge Types

| Type | A → B | Meaning |
|------|-------|----------|
| SUPPORTS | Evidence → Derived | Atom contributes atomic data to derived claim |
| CONTRADICTS | Evidence → Evidence | Two atoms make conflicting claims |
| DERIVED_FROM | Derived → Evidence | Derived claim depends on source atoms |
| RELATES_TO | Topic → Evidence | Atom discovered under topic branch |
| SUPERSEDES | Evidence → Evidence | Newer atom replaces/updates older |
| ELABORATES | Evidence → Evidence | Atom adds detail to another without conflict |
| SAME_ENTITY | Analytical → Evidence | Bundle references same entity |

### Graph Properties

- **Ephemeral** — constructed per EvidencePacket/section, NOT persisted to Postgres
- **Deterministic** — same input atoms → same graph structure
- **Navigable** — query neighbors, find paths, detect clusters
- **Lossless** — every edge traceable to source atom IDs

### Implementation

```python
@dataclass
class EvidenceGraph:
    nodes: Dict[str, GraphNode]       # keyed by deterministic ID
    edges: Dict[str, GraphEdge]       # keyed by composite ID
    index_by_entity: Dict[str, List[str]]  # entity name → node IDs
    index_by_topic: Dict[str, List[str]]   # topic → node IDs
    
    def get_connected_component(self, node_id: str) -> Set[str]
    def get_contradictions(self, entity: str) -> List[str]
    def get_supporting_chain(self, derived_node_id: str) -> List[str]

@dataclass
class GraphEdge:
    source_id: str
    target_id: str
    edge_type: EdgeType  # ENUM
    weight: float = 1.0  # confidence/support strength
    metadata: Dict = field(default_factory=dict)
```

### Integration Points

- **Input**: Output from 12-A (derived claims) + 12-B (analytical bundles) + existing EvidencePacket
- **Construction**: Called in Assembly phase before Section Planning (12-D)
- **Output**: Queryable graph consumed by 12-D planner

### Files That Will Change

| File | Change |
|------|--------|
| `src/research/graph/claim_graph.py` | NEW — EvidenceGraph, GraphNode, GraphEdge, builder |
| `src/research/reasoning/assembler.py` | Call graph builder after analytical operators |
| `EvidencePacket` | Add `evidence_graph` field |
| `tests/research/graph/test_claim_graph.py` | NEW — graph construction, navigation, determinism tests |
| `.planning/phases/12-C/EVIDENCE_GRAPH_SCHEMA.md` | NEW — schema doc |
| `.planning/phases/12-C/CLAIM_GRAPH_RULES.md` | NEW — edge rules, determinism guarantees |
