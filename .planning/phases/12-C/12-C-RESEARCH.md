# Phase 12-C Research: Claim Graph Builder

## Research Scope

Build a structured graph of evidence (atoms + derived claims from 12-A) to enable deterministic section planning. The graph transforms the current "bag of atoms" into an organized network of entities, relationships, and derivations.

---

## Current State Analysis

### Evidence Packet — "Bag of Atoms" Model

`EvidencePacket` in `assembler.py` (lines 34-43) carries evidence:

```python
@dataclass
class EvidencePacket:
    topic_name: str
    section_title: str
    section_objective: str
    atoms: List[Dict] = field(default_factory=list)
    contradictions: List[Dict] = field(default_factory=list)
    atom_ids_used: List[str] = field(default_factory=list)
    retrieval_profile: Optional[Dict[str, float]] = None
```

After Phase 12-A, this also includes:
- `derived_claims: List[DerivedClaim]`

### How Evidence Currently Flows

1. `EvidenceAssembler._build_from_context()` (lines 127-181) deduplicates retrieved `RetrievedItem` objects, packs them into `atom_dict` entries in `atoms` list
2. RetrievedItem objects (from `src/research/reasoning/retriever.py`) carry: content, source, strategy, relevance_score, trust_score, recency_days, citation_key, metadata, is_contradiction, concept_name
3. Contradictions are fetched separately via `_get_unresolved_contradictions()` (lines 183-220) from PostgreSQL `contradictions` table, attached as dict entries
4. The packet goes to `SynthesisService` where each section receives this packet and writes prose

### The Structure Problem

Currently, evidence is **flat**:
- `atoms` is a list of dicts with no relationship information
- `contradictions` is a separate list with no link back to specific atoms in the atoms list
- `derived_claims` (added in 12-A) references atom IDs but has no graph structure

The LLM writer receives this flat packet and must figure out: which atoms support which claims, which atoms contradict each other, which entities are mentioned across multiple atoms.

---

## The Graph Need vs Bag of Atoms

### Why a Structured Graph

| Current Model (Bag) | Graph Model |
|--------------------|-------------|
| Atoms listed, no relationships | Nodes for atoms, edges for relationships |
| Contradictions separate from atoms | Contradictions are edge types between atoms |
| Derived claims reference atom IDs by list | Derived claims are nodes with DERIVED_FROM edges |
| Writer must organize evidence from flat list | Writer receives pre-clustered evidence groups |
| No entity-level reasoning | Entity nodes aggregate all mentions across atoms |

### What the Graph Enables (for 12-D Section Planner)

The section planner uses the graph to:
1. **Cluster evidence** by entity/metric — all atoms about "Company A's revenue" go together
2. **Identify contradictions** as structural conflict — two nodes with CONTRADICTS edges
3. **Surface derivations** — DERIVED_CLAIM nodes point to their source atoms
4. **Plan structure deterministically** — same graph structure → same section plan

---

## Graph Design Based on Context Document

### Node Types

```python
class NodeType(Enum):
    ATOM = "atom"              # Original knowledge atom (from retrieval)
    ENTITY = "entity"          # Canonicalized entity (Company A, Product B)
    DERIVED_CLAIM = "derived"  # Computed relationship (from 12-A engine)
    CONTRADICTION = "contradiction"  # Opposing claim pair
```

### Edge Types

```python
class EdgeType(Enum):
    SUPPORTS = "supports"        # Atom supports entity's claim
    CONTRADICTS = "contradicts"  # Atom opposes another
    DERIVED_FROM = "derived"     # Derived claim from source atoms
    REFERS_TO = "refers"         # Atom mentions entity
```

### Construction Flow

1. **Input**: `EvidencePacket.atoms`, `EvidencePacket.derived_claims`, `EvidencePacket.contradictions`
2. **Create nodes**:
   - One ATOM node per atom (from atoms list)
   - One ENTITY node per unique entity detected (via Named Entity Recognition heuristic — capitalized proper nouns in atom content)
   - One DERIVED_CLAIM node per DerivedClaim object
   - One CONTRADICTION node per contradiction entry
3. **Create edges**:
   - REFERS_TO: atom → entity (if atom content mentions entity name)
   - SUPPORTS: atom → entity (if atom content supports the entity positively)
   - CONTRADICTS: atom ↔ atom (from contradictions list or derived contradictions)
   - DERIVED_FROM: derived_claim → atom_a, derived_claim → atom_b (from DerivedClaim.source_atom_ids)

### Data Structures

```python
@dataclass
class GraphNode:
    id: str                    # "atom_A001", "entity_Company_A", "derived_abc123", "contr_xyz456"
    node_type: NodeType
    content: Dict[str, Any]    # Atom dict, entity name, derived claim fields, etc.

@dataclass
class GraphEdge:
    source: str                # Node ID
    target: str                # Node ID
    edge_type: EdgeType
    metadata: Dict[str, Any]   # Optional: strength, confidence

@dataclass
class ClaimGraph:
    nodes: Dict[str, GraphNode]    # ID → node
    edges: List[GraphEdge]          # List of edges
```

---

## Determinism Requirements

### Why Determinism Matters

The graph is consumed by the section planner (12-D), which must produce deterministic output. If the graph structure varies between runs with the same evidence, sections will be inconsistent.

### Guarantee Mechanisms

| Requirement | Implementation |
|------------|---------------|
| Same atoms → same nodes | Node IDs are derived from atom global_ids (deterministic) |
| Same entities detected | Entity detection uses regex on lowercase text, order-independent |
| Same edges | Edges are functions of node content, not of processing order |
| Deterministic traversal | Iteration over edges/nodes uses sorted keys |

```python
def build_graph(packet: EvidencePacket) -> ClaimGraph:
    graph = ClaimGraph()
    # Add nodes in sorted order
    for atom in sorted(packet.atoms, key=lambda a: a['global_id']):
        graph.add_atom_node(atom)
    # Add derived claims (already deterministic from 12-A)
    for claim in sorted(packet.derived_claims, key=lambda c: c.id):
        graph.add_derived_claim_node(claim)
    # Add contradictions
    for c in sorted(packet.contradictions, key=lambda c: c.get('description', '')):
        graph.add_contradiction_node(c)
    # Add entities after atoms (so we know which atoms refer to them)
    graph.extract_and_add_entities()
    # Create all edges
    graph.build_all_edges()
    return graph
```

---

## Integration Points

### Where to Build the Graph

In `assembler.py`, `_build_from_context()`, after atoms are unpacked and derived claims are added (by the derivation engine from 12-A):

```python
# After line 165 (atom unpacking)
# Graph construction:
from research.graph.claim_graph import build_claim_graph
graph = build_claim_graph(packet)
packet.claim_graph = graph  # Optional field added to EvidencePacket
```

### EvidencePacket Modification

```python
from research.graph.claim_graph import ClaimGraph, Optional
@dataclass
class EvidencePacket:
    ...
    claim_graph: Optional["ClaimGraph"] = None  # NEW: from 12-C
```

### How 12-D Uses It

Section planner receives `EvidencePacket.claim_graph` and:
1. Traverses graph to find entity clusters
2. Groups atoms by entity/metric clusters
3. Creates ClaimGroup objects for each cluster
4. Generates section plans from groups

---

## Provenance Preservation

Every graph element must maintain traceability back to its source:

| Graph Element | Provenance Field | Source |
|--------------|-----------------|--------|
| ATOM node | `node.content['global_id']` | Original atom ID from retrieval |
| ENTITY node | `node.content['source_atom_ids']` | All atoms that mention this entity |
| DERIVED_CLAIM node | `node.content['derived_claim'].source_atom_ids` | DerivedClaim.source_atom_ids (from 12-A) |
| CONTRADICTION node | `node.content['atom_a_id']`, `node.content['atom_b_id']` | Contradiction table FKs |
| SUPPORTS edge | `edge.metadata['atom_id']`, `edge.metadata['entity_id']` | Both endpoint node IDs |
| DERIVED_FROM edge | `edge.metadata['rule']` | DerivedClaim.rule from 12-A |

---

## Risk Analysis

### False Entity Detection

| Risk | Scenario | Mitigation |
|------|----------|------------|
| Common non-entities detected as entities | "The System" detected as entity | Filter: require entity mentioned in ≥2 atoms or ≥3 uppercase chars |
| Different spellings of same entity | "Company A" vs "Company-A" | Normalize: strip punctuation, lowercase, deduplicate |
| Over-clustering | All atoms grouped under one giant entity | Split entities: "Company A revenue" vs "Company A team" |

### Graph Construction Overhead

- Per-atom NER (Named Entity Recognition): regex-based, not ML, O(n) on text length. For 20 atoms × 200 chars = 4KB of text — negligible.
- Edge construction: O(n²) worst case (every atom connected to every entity), but n is typically <50 atoms — trivial.

### Circular Dependencies

The graph should NOT cycle. Edges flow in one direction: DERIVED_CLAIM → ATOM → ENTITY or CONTRADICTION ↔ ATOM. No entity → atom reverse edges. The only potential cycle is CONTRADICTS between atoms (undirected), but this does not affect traversals that use directed edges.

---

## Dependencies

| Dependency | Provided By | Needed For |
|-----------|-------------|-----------|
| `DerivedClaim` dataclass | 12-A | Creating DERIVED_CLAIM nodes |
| `DerivedClaim.source_atom_ids` | 12-A | Creating DERIVED_FROM edges |
| `EvidencePacket.derived_claims` | 12-A (assembler modification) | Input to graph construction |
| Contradiction table schema | Existing (assembler._get_unresolved_contradictions) | Creating CONTRADICTION nodes |
| RetrievedItem.citation_key | Existing | Creating ATOM node IDs |
