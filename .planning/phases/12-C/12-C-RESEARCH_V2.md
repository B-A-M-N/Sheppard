# Phase 12-C: Claim Graph Builder - Research

**Researched:** 2024-05-24
**Domain:** Graph Theory, Evidence Assembly, Knowledge Representation
**Confidence:** HIGH

## Summary

Phase 12-C focuses on building a **Claim Graph** (also known as an Evidence Graph), which transforms a flat "bag of atoms" into a structured, navigable network of entities, relationships, and derivations. This graph is ephemeral (constructed per section/packet) and deterministic, ensuring that the Section Planner (Phase 12-D) can reason about the logic of the assembled evidence before synthesis.

**Primary recommendation:** Use a lightweight custom graph implementation using Python dataclasses and Pydantic for serialization, ensuring all nodes and edges are traceable to source atom IDs via deterministic hashing.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **12-C = Structure**: Relational intelligence made navigable.
- **Ephemeral**: Constructed per EvidencePacket/section, NOT persisted to Postgres.
- **Deterministic**: Same input atoms → same graph structure.
- **Navigable**: Query neighbors, find paths, detect clusters.
- **Lossless**: Every edge traceable to source atom IDs.

### the agent's Discretion
- **Implementation**: The exact internal data structure (though a dataclass-based approach is suggested).
- **Navigation Algorithms**: BFS/DFS implementation details.
- **ID Generation**: Specific hashing algorithm (though SHA-256 is standard in the project).

### Deferred Ideas (OUT OF SCOPE)
- **Postgres Persistence**: Graph is strictly in-memory/ephemeral.
- **Global Knowledge Graph**: This is a local claim graph for a specific research context.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| GRAPH-01 | Deterministic node generation from Atoms/DerivedClaims | Verified SHA-256 pattern in 12-A as the standard. |
| GRAPH-02 | Edge creation for SUPPORTS, CONTRADICTS, DERIVED_FROM | Adjacency list pattern identified as optimal for small graphs. |
| GRAPH-03 | Navigation (connected components, supporting chains) | BFS/DFS algorithms documented for custom implementation. |
| GRAPH-04 | Lossless traceability to source atoms | Node/Edge metadata structure ensures back-references. |
| GRAPH-05 | Integration with EvidencePacket and EvidenceAssembler | Modification points in `assembler.py` identified. |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `dataclasses` | Stdlib | Data Modeling | Provides type-safe, concise node/edge structures. |
| `enum` | Stdlib | Type Safety | Ensures valid edge and node types. |
| `pydantic` | 2.x | Serialization | Project standard for data exchange and JSON output. |
| `hashlib` | Stdlib | Determinism | Used for generating stable IDs from content. |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `uuid` | Stdlib | ID Generation | Use `uuid5` for namespace-based deterministic IDs. |
| `networkx` | 3.x | Advanced Graph Ops | *Optional*: Use if complex pathfinding or cycle detection is needed. |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Custom Graph | NetworkX | NetworkX is robust but adds a dependency and may be slower for small ephemeral graphs. |
| SHA-256 | UUID4 | UUID4 is not deterministic; SHA-256 or UUID5 is required for 12-C invariants. |

**Installation:**
```bash
# No new packages required if using custom implementation.
# If using NetworkX:
pip install networkx
```

## Architecture Patterns

### Recommended Project Structure
```
src/
└── research/
    ├── graph/
    │   ├── __init__.py
    │   ├── claim_graph.py   # EvidenceGraph class & Builder
    │   ├── node_types.py    # Node and Edge type definitions
    │   └── query_engine.py  # Navigation (BFS/DFS) logic
    └── reasoning/
        └── assembler.py     # Integrates graph builder into pipeline
```

### Pattern 1: Deterministic Node ID Generation
**What:** Generate stable IDs by hashing the node type and its primary content (atom ID or claim ID).
**When to use:** Always, to satisfy the "Deterministic" invariant.
**Example:**
```python
import hashlib

def make_node_id(node_type: str, content_id: str) -> str:
    """Source: src/research/derivation/engine.py pattern"""
    raw = f"{node_type}:{content_id}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]
```

### Anti-Patterns to Avoid
- **Global ID Collision:** Ensure different node types (e.g., EvidenceNode vs TopicNode) have distinct ID prefixes to avoid collisions if they share a source ID.
- **Reference Mutation:** Graph nodes should be frozen/immutable once added to ensure the "Lossless" invariant.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Deterministic Hashing | Custom salt/logic | `hashlib.sha256` | Proven, secure, and matches 12-A implementation. |
| Serialization | Manual `to_dict` | `Pydantic` | Handles nested objects and types automatically. |
| Graph Traversal | Complex recursions | BFS/DFS (Standard) | Simple, non-recursive BFS/DFS is safer for deep chains. |

## Common Pitfalls

### Pitfall 1: Entity Fragmentation
**What goes wrong:** Same entity (e.g., "Apple Inc." vs "Apple") represented as multiple `TopicNode`s.
**Why it happens:** Lack of entity normalization upstream in 12-B.
**How to avoid:** The Graph Builder should use a normalization helper or rely on normalized entity IDs from Analytical Bundles.

### Pitfall 2: Memory Bloat
**What goes wrong:** Creating large graphs for massive sections.
**Why it happens:** Per-section packets are usually small, but if retrieval is unfiltered, the graph grows.
**How to avoid:** Enforce a maximum atom count (e.g., 30-50) per section as defined in `v3_retriever`.

## Code Examples

### EvidenceGraph Structure (Pydantic-based)
```python
from pydantic import BaseModel, Field
from typing import Dict, List, Set, Any
from enum import Enum

class NodeType(str, Enum):
    EVIDENCE = "evidence"
    DERIVED = "derived"
    CONTRADICTION = "contradiction"
    ANALYTICAL = "analytical"
    TOPIC = "topic"

class EdgeType(str, Enum):
    SUPPORTS = "supports"
    CONTRADICTS = "contradicts"
    DERIVED_FROM = "derived_from"
    RELATES_TO = "relates_to"
    SAME_ENTITY = "same_entity"

class GraphNode(BaseModel):
    id: str
    type: NodeType
    content_ref: str  # ID of atom, claim, or bundle
    metadata: Dict[str, Any] = Field(default_factory=dict)

class GraphEdge(BaseModel):
    source_id: str
    target_id: str
    type: EdgeType
    weight: float = 1.0

class EvidenceGraph(BaseModel):
    nodes: Dict[str, GraphNode] = Field(default_factory=dict)
    edges: List[GraphEdge] = Field(default_factory=list)
    
    # Adjacency lists for fast navigation
    adj: Dict[str, List[str]] = Field(default_factory=dict)
    rev_adj: Dict[str, List[str]] = Field(default_factory=dict)

    def add_node(self, node: GraphNode):
        self.nodes[node.id] = node
        if node.id not in self.adj:
            self.adj[node.id] = []
        if node.id not in self.rev_adj:
            self.rev_adj[node.id] = []

    def add_edge(self, source_id: str, target_id: str, edge_type: EdgeType):
        edge = GraphEdge(source_id=source_id, target_id=target_id, type=edge_type)
        self.edges.append(edge)
        self.adj[source_id].append(target_id)
        self.rev_adj[target_id].append(source_id)
```

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest |
| Config file | `pytest.ini` |
| Quick run command | `pytest tests/research/graph/ -n auto` |
| Full suite command | `pytest tests/research/ -v` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| GRAPH-01 | Nodes generated deterministically | unit | `pytest tests/research/graph/test_claim_graph.py::test_determinism` | ❌ Wave 0 |
| GRAPH-02 | Edges correctly link atoms/claims | unit | `pytest tests/research/graph/test_claim_graph.py::test_edge_linkage` | ❌ Wave 0 |
| GRAPH-03 | Component navigation returns full set | unit | `pytest tests/research/graph/test_claim_graph.py::test_navigation` | ❌ Wave 0 |
| GRAPH-04 | Metadata contains source atom IDs | unit | `pytest tests/research/graph/test_claim_graph.py::test_traceability` | ❌ Wave 0 |

### Wave 0 Gaps
- [ ] `src/research/graph/claim_graph.py` — Core implementation.
- [ ] `tests/research/graph/test_claim_graph.py` — New test suite.
- [ ] `tests/research/graph/conftest.py` — Graph-specific fixtures.

## Sources

### Primary (HIGH confidence)
- `12-C-CONTEXT.md` - Phase objectives and data structures.
- `src/research/derivation/engine.py` - Standard for ID generation and `DerivedClaim` structure.
- `src/research/reasoning/assembler.py` - Integration point for `EvidencePacket`.

### Secondary (MEDIUM confidence)
- Google Web Search - "Claim Graph vs Knowledge Graph" - Verified industry terminology and patterns.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - Built-in Python tools and project standards.
- Architecture: HIGH - Matches requirements and existing patterns.
- Pitfalls: MEDIUM - Entity resolution is a known hard problem in NLP.

**Research date:** 2024-05-24
**Valid until:** 2024-06-24
