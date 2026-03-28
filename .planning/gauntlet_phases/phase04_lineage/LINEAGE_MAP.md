# Phase 04 — Data Lineage Map

**Purpose**: Visual/structured representation of entity relationships in V3

---

## High-Level Entity Relationship Diagram

```
┌─────────────────────────────────────────────────────────────────────────┐
│                                MISSION                                   │
│  ┌──────────────────────────────────────────────────────────────┐      │
│  │  mission.research_missions (mission_id PK)                  │      │
│  │  - topic_id, domain_profile_id FK, title, objective        │      │
│  └──────────────────────────────────────────────────────────────┘      │
│         │                               ▲                              │
│         │ 1:*                           │ CASCADE                      │
│         ▼                               │                              │
│  ┌─────────────────┐    ┌─────────────────────────────────────────┐   │
│  │    CORPUS       │    │           KNOWLEDGE                      │   │
│  │  sources        │    │  knowledge_atoms                         │   │
│  │  (source_id PK) │◄───┤  (atom_id PK)                            │   │
│  │  - mission_id FK│    │  - domain_profile_id FK, authority_id? │   │
│  └─────────────────┘    │  - topic_id, statement, confidence     │   │
│         │               └─────────────────────────────────────────┘   │
│         │ 1:*                           ▲                             │
│         ▼ CASCADE                      │ CASCADE?                     │
│  ┌─────────────────┐                   │                             │
│  │    chunks       │                   │ 1:*                         │
│  │  (chunk_id PK)  │                   │                             │
│  │  - source_id FK │◄──────────────────┤                             │
│  │  - mission_id FK│                   │                             │
│  └─────────────────┘                   │                             │
│         │                               │                             │
│         │ 1:*                           │                             │
│         ▼                               │                             │
│  ┌─────────────────────────────────────┼─────────────────────────┐   │
│  │         EVIDENCE (atom_evidence)    │                         │   │
│  │  PK: (atom_id, source_id, chunk_id)│                         │   │
│  │  - atom_id FK CASCADE              │                         │   │
│  │  - source_id FK CASCADE            │                         │   │
│  │  - chunk_id FK SET NULL            │                         │   │
│  └─────────────────────────────────────┼─────────────────────────┘   │
│                                        │                             │
│  ┌─────────────────────────────────────┼─────────────────────────┐   │
│  │          AUTHORITY                  │                             │
│  │  authority_records                  │                             │
│  │  (authority_record_id PK)          │                             │
│  │  - topic_id, domain_profile_id FK │                             │
│  │  - layer_json fields (cumulative) │                             │
│  └────────────────────────────────────┼─────────────────────────┘   │
│         │ CASCADE                      │                             │
│         ▼ 1:*                         │                             │
│  ┌─────────────────┐                  │                             │
│  │ synthesis_      │                  │                             │
│  │ artifacts       │                  │                             │
│  │ (artifact_id PK)│                  │                             │
│  └─────────────────┘                  │                             │
│         │ CASCADE                      │                             │
│         ▼ 1:*                         │                             │
│  ┌─────────────────┐                  │                             │
│  │ synthesis_      │                  │                             │
│  │ sections        │                  │                             │
│  └─────────────────┘                  │                             │
│         │ CASCADE                      │                             │
│         ▼ 1:*                         │                             │
│  ┌─────────────────┐                  │                             │
│  │ synthesis_      │                  │                             │
│  │ citations       │◄─────────────────┘                             │
│  │ (FK to atoms)  │                                                │
│  └─────────────────┘                                                │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │            APPLICATION LAYER                               │   │
│  │  application_queries → application_outputs → evidence     │   │
│  └─────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Core Lineage Chains

### 1. Ingestion Lineage (Bottom-Up)

```
mission.research_missions
    │ (mission_id)
    ▼
corpus.sources
    │ (source_id)
    ▼
corpus.chunks
    │ (chunk_id)
    ▼
knowledge.atom_evidence
    │ (atom_id)
    ▼
knowledge.knowledge_atoms
```

**Guarantee**: Every atom can be traced to its source chunks, which trace to the original source URL and mission.

### 2. Synthesis Lineage (Top-Down)

```
authority.authority_records
    │ (authority_record_id)
    ▼
authority.synthesis_artifacts (reports)
    │ (artifact_id)
    ▼
authority.synthesis_sections (report sections)
    │ (citations to)
    ▼
knowledge.knowledge_atoms + corpus.sources
```

**Guarantee**: Every report cites its evidence via `synthesis_citations` and `bundle_atoms`.

### 3. Evidence Bundles (Mid-Tier)

```
evidence_bundles (bundle_id)
    ├─ bundle_atoms (atom_id)
    ├─ bundle_sources (source_id)
    └─ bundle_excerpts (chunk_id / inline_text)
```

Bundles assemble evidence for specific objectives (e.g., report sections).

---

## Key Foreign Key Constraints

| Table | Column | References | On Delete |
|-------|--------|------------|-----------|
| `mission.research_missions` | `domain_profile_id` | `config.domain_profiles` | RESTRICT |
| `corpus.sources` | `mission_id` | `mission.research_missions` | CASCADE |
| `corpus.chunks` | `source_id` | `corpus.sources` | CASCADE |
| `corpus.chunks` | `mission_id` | `mission.research_missions` | CASCADE |
| `knowledge.atom_evidence` | `atom_id` | `knowledge.knowledge_atoms` | CASCADE |
| `knowledge.atom_evidence` | `source_id` | `corpus.sources` | CASCADE |
| `knowledge.atom_evidence` | `chunk_id` | `corpus.chunks` | SET NULL |
| `authority.synthesis_artifacts` | `authority_record_id` | `authority.authority_records` | CASCADE |
| `authority.synthesis_sections` | `artifact_id` | `authority.synthesis_artifacts` | CASCADE |
| `authority.synthesis_citations` | `atom_id` | `knowledge.knowledge_atoms` | SET NULL |
| `authority.synthesis_citations` | `source_id` | `corpus.sources` | SET NULL |

---

## Orphan Prevention

- **Source → Mission**: FK ensures no source exists without mission (mission deletion cascades)
- **Chunk → Source**: FK ensures no chunk exists without source (source deletion cascades)
- **Atom Evidence → Atom/Source/Chunk**: Composite PK/FK ensures evidence always points to valid entities
- **Synthesis → Authority**: FK ensures reports are tied to authority records

**Potential Gap**: `knowledge_atoms.authority_record_id` is **not** a foreign key (schema has no constraint). This is acceptable if authority linkage is optional (atoms can exist before authority synthesis).

---

## Immutability Notes

- **Chunks**: Immutable once created (derived from source text)
- **Atoms**: May be updated (confidence adjustments) but evidence lineage persists
- **Sources**: Fixed at ingestion time
- **Synthesis artifacts**: Versioned; old versions retained

---

## Queryability

Can reconstruct full provenance for any atom:

```sql
SELECT
    a.atom_id,
    a.statement,
    e.source_id,
    s.url,
    s.mission_id,
    m.title AS mission_title
FROM knowledge.knowledge_atoms a
JOIN knowledge.atom_evidence e ON a.atom_id = e.atom_id
JOIN corpus.sources s ON e.source_id = s.source_id
JOIN mission.research_missions m ON s.mission_id = m.mission_id
WHERE a.atom_id = '...';
```

Can reconstruct full report provenance:

```sql
SELECT
    sa.artifact_id,
    sa.title,
    sc.section_name,
    sc.content_ref,
    ci.atom_id,
    k.statement
FROM authority.synthesis_artifacts sa
JOIN authority.synthesis_sections sc ON sa.artifact_id = sc.artifact_id
LEFT JOIN authority.synthesis_citations ci ON sa.artifact_id = ci.artifact_id
LEFT JOIN knowledge.knewledge_atoms k ON ci.atom_id = k.atom_id
WHERE sa.artifact_id = '...';
```

---

**Conclusion**: Lineage is **structurally enforced** via foreign keys. The data model ensures traceability from atoms → chunks → sources → missions, and from reports → atoms. No orphan risks for core entities.
