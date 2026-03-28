# Phase 03 — Storage Read Matrix

---

## Read Operations by Component

### V3Retriever

| Source Store | Collection/Table | Purpose | Canonical or Projection? |
|--------------|------------------|---------|--------------------------|
| Chroma | `knowledge_atoms` | Semantic retrieval for `/query` | Projection (derived from `knowledge.knowledge_atoms`) |

**Note**: Does not read Postgres directly; relies on Chroma projection.

---

### DistillationPipeline

| Source Store | Table | Purpose | Canonical or Projection? |
|--------------|-------|---------|--------------------------|
| Postgres | `corpus.sources` (where status='fetched') | Fetch source content for distillation | Canonical |

---

### SystemManager (learn, crawl, etc.)

| Source Store | Table/Key | Purpose | Canonical or Projection? |
|--------------|-----------|---------|--------------------------|
| Postgres | `corpus.sources` (by url hash) | Check deduplication in `_vampire_loop` | Canonical |
| Postgres | `mission.research_missions` | Mission state checks | Canonical |
| Redis | `queue:scraping` | Dequeue URLs for scraping | Ephemeral (queue) |
| Redis | `active:*` | Optional hot caches (if used) | Ephemeral |
| Chroma | N/A (尚无) | — | — |

---

### AdaptiveFrontier

| Source Store | Table/Key | Purpose | Canonical or Projection? |
|--------------|-----------|---------|--------------------------|
| Postgres | `mission.mission_nodes` | Load current frontier nodes | Canonical |
| Redis | `frontier:*` | Cached states (if any) | Ephemeral |

---

### EvidenceAssembler / SynthesisService

Currently disabled; not in use. If re-enabled:
- Would read from `knowledge.knowledge_atoms` and `atom_evidence` via Postgres or Chroma.

---

## Read Summary

- **Primary canonical reads**: Postgres tables (`corpus.sources`, `mission.*`, `knowledge.*`)
- **Projection reads**: Chroma (`knowledge_atoms`) for retrieval
- **Ephemeral reads**: Redis queues and caches
- **V2 reads**: None (Phase 03.0 lock confirmed)

---

## Observations

- Retrieval path (`/query`) reads only from Chroma projection. This is correct provided Chroma is up-to-date.
- Distillation reads from Postgres directly; writes go via adapter (canonical then projection). Good.
- No code reads directly from Redis truth; only queues/caches. Acceptable.

---

## Potential Issues

- **Stale projection risk**: If Chroma indexing fails after Postgres commit, retrieval will not see the data. This is an eventual consistency gap, not a read violation. See Atomicity Gap in Phase 02.
- **Queue durability**: `queue:scraping` is ephemeral; pending jobs may be lost if Redis restarts. However, source records remain in Postgres with status='fetched' and could be re-queued. Not a triad violation, but operational concern.

---

## Conclusion

Read patterns are clean: canonical reads from Postgres, semantic reads from Chroma projection, transient reads from Redis. No V2 contamination.
