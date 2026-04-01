# Phase 12-D Research: Section Planner

## Research Scope

Replace the LLM-generated section plan with a deterministic, evidence-driven planner that uses the claim graph from 12-C to produce structured report outlines. Each section specifies: title, purpose, required claim groups, allowed derivations, and contradiction handling policy.

---

## Current State Analysis

### LLM-Based Section Planning

`EvidenceAssembler.generate_section_plan()` in `assembler.py` (lines 51-98):

```python
async def generate_section_plan(self, topic_name: str) -> List[SectionPlan]:
    """Ask the LLM to architect the Master Brief."""
    prompt = f"""
You are the Chief Architect of a research institute...
Break the report down into 5 to 8 logical sections based on the nature of the subject...
Output ONLY valid JSON in this format: {"sections": [...]}
"""
    resp = await self.ollama.complete(task=TaskType.DECOMPOSITION, prompt=prompt)
    # Parse JSON, construct SectionPlan objects
    # Fallback: 3 generic sections if parsing fails
```

### SectionPlan Dataclass (assembler.py lines 27-32)

```python
@dataclass
class SectionPlan:
    order: int
    title: str
    purpose: str
    target_evidence_roles: List[str]  # e.g., ["definitions", "statistics", "contradictions"]
```

### Problems with LLM-Based Planning

| Problem | Impact |
|---------|--------|
| **Evidence-agnostic** | LLM may request sections for which no evidence exists |
| **Non-deterministic** | Same topic name → different section structure on different runs |
| **No contradiction awareness** | Never plans contradiction sections unless prompted |
| **No derivation awareness** | Cannot plan sections that require computed claims |
| **LLM cost** | Each planning call adds latency (~2-5 seconds for DECOMPOSITION task) |
| **Fallback degradation** | If JSON parsing fails, falls back to 3 generic sections |

### Usage in SynthesisService

`synthesis_service.py` line 52:
```python
plan = await self.assembler.generate_section_plan(topic_name)
```

Then line 88:
```python
all_packets = await self.assembler.assemble_all_sections(mission_id, topic_name, plan)
```

The planner produces `List[SectionPlan]`, which drives how many evidence packets are built and how many sections are written.

---

## Why Evidence-Driven Planning

### The Evidence-First Approach

Instead of starting from topic name and guessing what sections are needed, start from available evidence and discover what sections are justified:

1. **Graph traversal** → claim groups by entity/metric
2. **Claim group analysis** → which section does this group support?
3. **Section generation** → one section per sufficient evidence group + metadata sections

### Benefits

| Benefit | Description |
|---------|-------------|
| **No empty sections** | Only create sections with sufficient evidence |
| **Contradiction surfacing** | Always plan contradiction section if contradictions exist |
| **Derivation inclusion** | Plan sections that highlight computed insights |
| **Determinism** | Same evidence → same section structure |
| **Zero LLM cost** | No LLM call needed — pure deterministic logic |

---

## Deterministic Planning Algorithm

### ClaimGroup Structure

```python
@dataclass
class ClaimGroup:
    title: str                      # e.g., "Revenue Metrics"
    atoms: List[str]                # atom IDs in this group
    derived_claims: List[str]       # derived claim IDs in this group
    entity: str                     # canonical entity name
```

### SectionPlan Extension (from context)

```python
@dataclass
class SectionPlan:
    order: int
    title: str
    purpose: str
    target_evidence_roles: List[str]
    # NEW (12-D):
    claim_groups: List[ClaimGroup]     # clustered evidence from graph
    allowed_derivations: List[str]      # which rules apply to this section
    contradiction_policy: str           # "ignore" | "surface" | "resolve"
    min_evidence_count: int             # skip section if fewer than N atoms
    evidence_sufficient: bool           # computed during planning
```

### Clustering Strategy: Evidence Grouping

The claim graph from 12-C provides structured nodes. Clustering algorithm:

```python
def cluster_evidence(graph: ClaimGraph) -> List[ClaimGroup]:
    """Group atoms and derived claims by entity."""
    entity_groups = defaultdict(lambda: {"atoms": [], "derived_claims": []})

    # Walk REFERS_TO edges: atom → entity
    for edge in graph.edges:
        if edge.edge_type == EdgeType.REFERS_TO:
            atom_node = graph.nodes[edge.source]
            entity_name = graph.nodes[edge.target].content.get('name', '')
            entity_groups[entity_name]['atoms'].append(edge.source)

    # Walk DERIVED_FROM edges: derived_claim → atom
    for edge in graph.edges:
        if edge.edge_type == EdgeType.DERIVED_FROM:
            derived_node = graph.nodes[edge.source]
            derived_atom_ids = derived_node.content.get('source_atom_ids', [])
            for aid in derived_atom_ids:
                for eg in entity_groups.values():
                    if aid in eg['atoms']:
                        eg['derived_claims'].append(edge.source)
                        break

    # Create ClaimGroups from entity clusters
    groups = []
    for entity, data in sorted(entity_groups.items()):
        if len(data['atoms']) >= 1:  # At least one atom
            groups.append(ClaimGroup(
                title=f"{entity} Analysis",
                atoms=data['atoms'],
                derived_claims=list(set(data['derived_claims'])),
                entity=entity
            ))
    return groups
```

### Section Generation from Clusters

```python
from research.graph.claim_graph import ClaimGraph
from typing import List

@dataclass
class SectionPlan:
    order: int
    title: str
    purpose: str
    target_evidence_roles: List[str]
    claim_groups: List[ClaimGroup]
    allowed_derivations: List[str]
    contradiction_policy: str
    min_evidence_count: int
    evidence_sufficient: bool

def plan_sections(graph: ClaimGraph, claim_groups: List[ClaimGroup]) -> List[SectionPlan]:
    """Generate deterministic section plan from claim graph."""
    sections = []
    order = 1

    # 1. Executive Summary section (always present)
    all_atoms = [nid for nid, node in graph.nodes.items()
                  if node.node_type == NodeType.ATOM]
    sections.append(SectionPlan(
        order=order,
        title="Executive Summary",
        purpose="Overview of key findings and insights",
        target_evidence_roles=["core_concepts", "definitions"],
        claim_groups=[],
        allowed_derivations=[],
        contradiction_policy="surface",
        min_evidence_count=1,
        evidence_sufficient=len(all_atoms) >= 1
    ))
    order += 1

    # 2. Entity-based sections (one per claim group with sufficient evidence)
    for group in claim_groups:
        sections.append(SectionPlan(
            order=order,
            title=group.title,
            purpose=f"Detailed analysis of {group.entity}",
            target_evidence_roles=["statistics", "methodologies"],
            claim_groups=[group],
            allowed_derivations=["delta", "percent_change"] if group.derived_claims else [],
            contradiction_policy="resolve" if _has_contradictions_for_entities(graph, [group.entity]) else "ignore",
            min_evidence_count=2,
            evidence_sufficient=len(group.atoms) >= 2
        ))
        order += 1

    # 3. Contradictions section (always added if contradictions exist)
    contradiction_nodes = [nid for nid, node in graph.nodes.items()
                           if node.node_type == NodeType.CONTRADICTION]
    if contradiction_nodes:
        sections.append(SectionPlan(
            order=order,
            title="Contradictions & Disputes",
            purpose="Surface and resolve conflicting evidence",
            target_evidence_roles=["contradictions", "disputes"],
            claim_groups=[],
            allowed_derivations=[],
            contradiction_policy="surface",
            min_evidence_count=1,
            evidence_sufficient=True  # always sufficient if we have contradictions
        ))
        order += 1

    return sections
```

### Where to Integrate

Two options:

| Option | Location | Description |
|--------|----------|-------------|
| **Replace** `generate_section_plan()` | `assembler.py` lines 51-98 | Replace the entire method with graph-based planning |
| **Add new method** `generate_evidence_plan()` | `assembler.py` next to `generate_section_plan()` | New method, keep fallback |

**Recommendation**: Replace. The LLM-based planner has no advantages over evidence-driven planning once the claim graph exists. If needed, fallback can simply be a 3-section plan (same as current fallback).

```python
# assembler.py
def generate_section_plan(self, topic_name: str) -> List[SectionPlan]:
    """Ask the LLM to architect the Master Brief."""
    # NOTE: For 12-D, replaced by evidence-driven planning below
    raise NotImplementedError("Use generate_evidence_plan() instead")

def generate_evidence_plan(self, graph: Optional[ClaimGraph] = None) -> List[SectionPlan]:
    """Deterministic section planning from claim graph."""
    if graph is None:
        return [  # Fallback: generic sections
            SectionPlan(order=1, title="Executive Summary", purpose="Overview", target_evidence_roles=["definitions"])
        ]
    claim_groups = cluster_evidence(graph)
    return plan_sections(graph, claim_groups)
```

---

## Contradiction Handling Policy

The `contradiction_policy` field in `SectionPlan` determines behavior:

| Policy | Meaning | When Used |
|--------|---------|-----------|
| `"ignore"` | Do not surface contradictions in this section | Sections with no related contradictions |
| `"surface"` | List contradictions as-is, do not attempt resolution | Summary sections, executive overview |
| `"resolve"` | Attempt synthesis between conflicting atoms | Detailed analysis sections with strong evidence on both sides |

Contradiction detection: A contradiction is "related to this section" if either of its referenced atoms is in a claim group used by the section.

---

## Determinism Guarantees

### Sorted Traversal

Every data structure that could vary in order must use sorted keys:

```python
# Entity names sorted → sections in alphabetical (not hash-map) order
for entity in sorted(entity_groups.keys()):
    ...
```

### Deterministic Section Titles

Section titles can be derived from entity names. To avoid LLM-generated titles (which vary), use a deterministic format:

| Evidence Group | Section Title |
|---------------|---------------|
| Atoms about "Company A revenue" | "Company A: Revenue Analysis" |
| Atoms about "Python performance" | "Python: Performance Characteristics" |
| Contradictions present | "Contradictions & Disputes" |

### Same Atoms → Same Plan, Guaranteed

The algorithm is a pure function:
- Input: `ClaimGraph` (itself deterministic from EvidencePacket)
- Output: `List[SectionPlan]`
- No state mutation, no LLM calls, no randomness

---

## Dependencies on 12-C

| Dependency | From | Used For |
|-----------|------|---------|
| `ClaimGraph` dataclass | 12-C | Input to clustering |
| `GraphNode.node_type` | 12-C | Filtering by type (ATOM, ENTITY, DERIVED_CLAIM, CONTRADICTION) |
| `GraphEdge.edge_type` | 12-C | Finding relationships between nodes |
| `GraphEdge.source` / `GraphEdge.target` | 12-C | Mapping atoms to entities |
| `ClaimGraph.nodes` dict | 12-C | Iterating all nodes of a type |
| `ClaimGraph.edges` list | 12-C | Traversing relationships |
