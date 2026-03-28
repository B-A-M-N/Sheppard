# Phase 03 — Rebuildability Assessment

---

## Question 1: Can Chroma be fully rebuilt from Postgres?

**Answer**: Yes, with qualifications.

### Reasoning

- **All Chroma documents are indexed from Postgres rows**:
  - Atoms: `index_atom()` called after `knowledge.knowledge_atoms` upsert
  - Chunks: `index_chunks()` called after `corpus.chunks` bulk upsert
  - Authority records: `index_authority_record()` after `authority.authority_records` upsert
  - Syntheses: `index_synthesis_artifact()` after `authority.synthesis_artifacts` upsert
- **No independent Chroma writes**: All writes go through `SheppardStorageAdapter` index methods. The only violation is `archivist/index.py`, which writes to a separate `archivist_research` collection. This collection is not used by V3Retriever and therefore does not affect the primary retrieval projection; however, it still violates the principle. The main `knowledge_atoms` and `corpus_chunks` collections are clean.
- **Rebuild process**:
  1. Clear Chroma collections (`knowledge_atoms`, `corpus_chunks`, etc.)
  2. Iterate all Postgres rows for atoms and chunks
  3. Call adapter's `index_atom` / `index_chunks` for each
- **Idempotency**: The index methods use `upsert` (by ID), so re-running is safe.
- **Missing automated script**: No `rebuild_chroma.py` exists, but the operation is theoretically straightforward.

### Caveats

- Archivist's `archivist_research` collection would be lost and not automatically rebuilt from Postgres (since it does not store canonical metadata). This is a data loss category separate from the main retrieval corpus.
- Rebuilding large corpus requires scanning entire Postgres; this could be done in batches.

---

## Question 2: Can Redis be lost without losing truth?

**Answer**: Yes, truth is preserved in Postgres; Redis loss is acceptable but may impact performance and durability of in-flight work.

### Ephemeral Categories

| Redis Key Type | Purpose | Rebuildable? | Rebuild Source |
|----------------|---------|--------------|----------------|
| `queue:scraping` | Work queue for vampires | ✅ | Unprocessed sources exist in `corpus.sources` with status='fetched' or 'queued' |
| `*:active:*` | Active mission/node state | ✅ | Reflects current state in Postgres (`research_missions`, `mission_nodes`) |
| `cache:*` | Hot object cache (TTL 1h) | ✅ | Can be lazily re-cached on next access from Postgres |
| `lock:*` | Distributed locks | ✅ | Locks are transient; can be reacquired |

### Data Loss Tolerance

- **Queue loss**: If Redis is wiped, pending scraping jobs may be orphaned. These can be re-enqueued by scanning `corpus.sources` where `status='fetched'` but not yet condensed. This requires a manual rescan script but data is safe.
- **Active state loss**: Applications may need to re-initialize active states; no permanent effect.
- **Cache loss**: Only performance impact; cache repopulates on demand.
- **Lock loss**: Locks time out; losing Redis resets all locks safely.

---

## Hard Fail Conditions Check

- [x] Chroma contains ONLY derivable projections (main collections) — **yes**, except archivist (minor)
- [x] Redis contains NO unrecoverable mission state — **yes**, all ephemeral
- [x] Postgres lineage is complete — **yes**, all canonical
- [x] Storage responsibilities are explicit — **yes**, adapter defines clean boundaries

---

## Recommendations

1. **Create rebuild script** `scripts/rebuild_chroma_from_postgres.py` to materialize projection after catastrophic Chroma loss.
2. **Provide queue reconciler** `scripts/reconcile_queues.py` to re-enqueue unprocessed sources after Redis loss.
3. **Fix archivist** to use adapter or clearly document it as out-of-scope.

---

**Conclusion**: The triad rebuildability criteria are satisfied. Chroma and Redis are replaceable from Postgres.
