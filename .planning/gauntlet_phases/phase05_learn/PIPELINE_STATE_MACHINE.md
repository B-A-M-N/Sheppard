# Phase 05 — Pipeline State Machine

**Date**: 2026-03-27
**Auditor**: Claude Code

Explicit state transition model for `/learn` pipeline.

---

## State Definitions

| State | Representation | Transition Triggers |
|-------|----------------|---------------------|
| `INPUT_RECEIVED` | Command parsed, arguments valid | User enters `/learn <topic>` |
| `MISSION_CREATED` | `mission.research_missions` row exists with status='discovering' | `adapter.create_mission()` called |
| `TOPIC_DECOMPOSED` | Frontier policy generated, initial research nodes created | `AdaptiveFrontier._frame_research_policy()` completes |
| `URL_DISCOVERED` | URLs yielded from search results | `crawler._search()` returns list of URLs |
| `URL_QUEUED` | Job payload in Redis `queue:scraping` | `adapter.enqueue_job()` called |
| `URL_FETCHED` | `corpus.sources` row with `status='fetched'` exists | Vampire completes scrape and `ingest_source()` finishes |
| `CONTENT_NORMALIZED` | `corpus.chunks` rows exist for the source, `corpus.text_refs` row exists | Chunking step in `ingest_source()` |
| `ATOMS_EXTRACTED` | Atoms produced from source by `DistillationPipeline` | `extract_technical_atoms()` returns atoms for a source |
| `ATOMS_STORED` | Rows in `knowledge.knowledge_atoms` and `knowledge.atom_evidence` | `store_atom_with_evidence()` commits transaction |
| `INDEX_UPDATED` | Atom document in Chroma `knowledge_atoms` collection | `index_atom()` completes |

---

## State Transition Table

| From | To | Conditions | File:Line | Notes |
|------|----|------------|-----------|-------|
| `INPUT_RECEIVED` | `MISSION_CREATED` | Mission record inserted successfully | `system.py:198` | `create_mission()` |
| `MISSION_CREATED` | `TOPIC_DECOMPOSED` | Frontier policy generated, nodes initialized | `frontier.py:81` | `_frame_research_policy()` |
| `TOPIC_DECOMPOSED` | `URL_DISCOVERED` | Search returns URLs | `crawler.py:295` | `_search()` result |
| `URL_DISCOVERED` | `URL_QUEUED` | URL enqueued to Redis | `crawler.py:313` | `adapter.enqueue_job("queue:scraping")` |
| `URL_QUEUED` | `URL_FETCHED` | Vampire dequeues, scrapes, ingests | `system.py:345` | `ingest_source()` returns source_id |
| `URL_FETCHED` | `CONTENT_NORMALIZED` | Chunks created | `storage_adapter.py:828` | `create_chunks()` |
| `CONTENT_NORMALIZED` | `ATOMS_EXTRACTED` | Source selected by condenser, atoms extracted | `pipeline.py:83` | `extract_technical_atoms()` |
| `ATOMS_EXTRACTED` | `ATOMS_STORED` | Transaction commits | `storage_adapter.py:616-656` | `store_atom_with_evidence()` |
| `ATOMS_STORED` | `INDEX_UPDATED` | Chroma indexing succeeds | `storage_adapter.py:659` | `index_atom()` |

---

## Additional State Changes (Parallel)

### Mission Status Updates
| State Change | File:Line | Trigger |
|--------------|-----------|---------|
| `discovering` → `active` | `system.py:367` (after frontier.run() completes) OR early update | Not explicitly set until completion |
| `active` → `completed` | `system.py:367` | `_crawl_and_store` success |
| `active` → `failed` | `system.py:372` | `_crawl_and_store` exception |
| `active` → `stopped` | `system.py:399` | `cancel_mission()` called |
| `active` → `condensing` | Not tracked | Budget monitor fires, condenser runs |

### Source Status Updates
| Status | Set At | File:Line |
|--------|--------|-----------|
| `fetched` | After ingestion | `storage_adapter.py:783` |
| `condensed` | After atoms extracted | `pipeline.py:124` |
| `error` | On extraction failure | `pipeline.py:128` |

---

## State Machine Characteristics

### Determinism
- ✅ Most transitions are deterministic: one code path per state change
- ⚠️ `URL_DISCOVERED` → `URL_QUEUED` may produce duplicate URLs if frontier re-discovers (dedupe protects at vampire)
- ⚠️ `ATOMS_EXTRACTED` timing non-deterministic: condenser runs on budget thresholds, processes up to 5 sources per batch; order depends on when thresholds crossed

### Observability
- Mission state: `mission.research_missions.status`
- Source state: `corpus.sources.status`
- Atoms: `knowledge.knowledge_atoms` (no status field)
- Frontier nodes: **in-memory only**, not persisted as explicit state (nodes saved as `ops.mission_nodes` but not a state machine)

### Missing/Implicit States
- `TOPIC_DECOMPOSED` is not persisted as a state; it's an in-memory frontier initialization step
- No global pipeline orchestrator that tracks overall mission progress from state to state
- Budget condensation is fire-and-forget; no `condensation_status` tracked at mission level

---

## State Transition Diagram (Textual)

```
INPUT_RECEIVED
    ↓
MISSION_CREATED (DB: research_missions)
    ↓
TOPIC_DECOMPOSED (frontier policy + nodes)
    ↓ loop ──────────────────────────────────────────────────────────┐
    │                                                                │
    ▼                                                                │
URL_DISCOVERED (search yields)                                      │
    ↓                                                               │
URL_QUEUED (Redis queue) ──→ (vampire consumes) ──→ URL_FETCHED ──┘
    │                                                                ↓
    └──────────────────────────────────────────────────────────────┘ (repeats)
                                                                    ↓
                                                            CONTENT_NORMALIZED (chunks)
                                                                    ↓
                                                            ATOMS_EXTRACTED (condenser)
                                                                    ↓
                                                            ATOMS_STORED (atom+evidence)
                                                                    ↓
                                                            INDEX_UPDATED (Chroma)
```

**Notes**:
- Discovery loop (URL_DISCOVERED → URL_QUEUED) runs repeatedly until budget exhausted
- Each URL_FETCHED triggers chunking immediately (inline)
- Distillation runs in **separate async task**, triggered when `raw_bytes / ceiling_bytes` crosses thresholds
- No direct coupling between ingestion completion and distillation start; condenser polls `corpus.sources` for `status='fetched'`

---

## Gaps vs. Mandatory State Chain

From Phase 05 requirements:

| Required State | Present? | Evidence |
|----------------|----------|----------|
| `INPUT_RECEIVED` | ✅ | Command parsing exists |
| `MISSION_CREATED` | ✅ | `create_mission()` inserts row |
| `TOPIC_DECOMPOSED` | ⚠️ Implicit | Frontier policy generated but not stored as explicit state |
| `URL_DISCOVERED` | ✅ | URLs returned from `_search()` |
| `URL_QUEUED` | ✅ | `enqueue_job()` writes to Redis |
| `URL_FETCHED` | ✅ | `ingest_source()` sets `status='fetched'` |
| `CONTENT_NORMALIZED` | ✅ | Chunk rows created with `text_ref` linkage |
| `ATOMS_EXTRACTED` | ✅ | Atoms produced in `pipeline.run()` |
| `ATOMS_STORED` | ✅ | `store_atom_with_evidence()` commits |
| `INDEX_UPDATED` | ✅ | `index_atom()` called post-commit |

**Gaps**:
- `TOPIC_DECOMPOSED` not explicitly recorded as a persistent state
- No central state machine registry; states distributed across DB tables and in-memory structures
- No formal state transition **event log** (audit trail of state changes)

---

## Conclusion

The pipeline exhibits **de facto** state progression, but lacks a formal state machine with explicit state tracking. Transitions are implicit in function call order and database status values. This is sufficient for operation but not easily auditable without code tracing.

**Recommendation**: Document the as-is state model (as done here) and consider adding a mission-phase table if explicit observability needed later.
