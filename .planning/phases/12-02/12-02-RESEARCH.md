# Phase 12-02: Retrieval Latency Optimization — Research

**Researched:** 2026-03-30
**Domain:** Async Python concurrency, ChromaDB, EvidenceAssembler orchestration
**Confidence:** HIGH

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **PERF-01 target = TOTAL retrieval across all sections**, not per-query
  - Current: ~1200ms total (8 sections × ~150ms/query)
  - First goal: ≤200–300ms total
  - Realistic via concurrency (parallelizing 8 queries)
- **Primary optimization target: `EvidenceAssembler`** — controls section loop, concurrency, ordering
- **V3Retriever: no changes** — keep simple and deterministic
- **Concurrency pattern (MANDATORY):** Index-preserving gather, NOT naive gather:
  ```python
  tasks = [
      (section.index, asyncio.create_task(retrieve_for_section(section)))
      for section in sections
  ]
  results = [(index, await task) for index, task in tasks]
  results.sort(key=lambda x: x[0])  # restore section order
  ```
- **Global re-sort before citation assignment (NON-NEGOTIABLE):**
  ```python
  all_atoms = sorted(all_atoms, key=lambda x: x.global_id)
  ```
  Citation keys ([A001], [A002]...) must be stable and reproducible.
- **`atom_ids_used` ordering:** Must remain deterministic post-concurrency; current per-section sort by `global_id` must be preserved.
- **Prefetch cache: DEFERRED** — only after concurrency confirms target hit.
- **Corpus tiers (MANDATORY before 12-03):**
  - SMALL: ~20 atoms (current synthetic baseline)
  - MEDIUM: ~200–500 atoms
  - LARGE: ~1000+ atoms
- **`src/retrieval/retriever.py` = likely dead/legacy** — confirm via import grep, mark deprecated, do NOT optimize.
- **Instrumentation to add:**
  ```json
  {
    "retrieval_queries": 8,
    "concurrency_level": 8,
    "retrieval_parallelism_efficiency": "<actual_ms vs sequential_estimate>"
  }
  ```
  Separate `embedding_ms` vs `query_ms` if possible.
- **Execution order:**
  1. Add per-section timing instrumentation
  2. Implement concurrent section retrieval (assembler layer)
  3. Re-run benchmark (small + medium corpus)
  4. Validate determinism + citation stability
  5. Only then consider prefetch cache
  6. Evaluate thread pool / embedding bottleneck

### Claude's Discretion
- Thread pool executor size tuning (if parallelism reveals thread contention)
- Whether to add an explicit asyncio.Semaphore to bound concurrency
- How to seed MEDIUM/LARGE corpus (synthetic injection extension of benchmark script)
- Whether to consolidate or just deprecate `src/retrieval/retriever.py`

### Deferred Ideas (OUT OF SCOPE)
- Prefetch cache (fetch all mission atoms once, filter in-memory per section)
- External Redis cache layer
- ChromaDB index configuration changes
- Re-ranking / scoring changes (Phase 12-07)
- Persistent metrics backend (Prometheus/Grafana) — Phase 12-04
</user_constraints>

---

## Summary

Phase 12-02 adds concurrent section retrieval to `EvidenceAssembler.build_evidence_packet` and extends the benchmark suite with MEDIUM/LARGE corpus tiers. The current bottleneck is a sequential `for` loop in `generate_master_brief` (in `SynthesisService`) that calls `build_evidence_packet` one section at a time — each call makes one `adapter.chroma.query()` call, which is wrapped in `asyncio.to_thread`. With 8 sections averaging ~150ms/query, the sequential total is ~1200ms.

The fix is to refactor `build_evidence_packet` into a parallel coroutine and drive it concurrently from `generate_master_brief` (or from a new method on `EvidenceAssembler`) using index-preserving `asyncio.gather`. After all concurrent results are collected, atoms must be merged and sorted by `global_id` before citation keys are assigned — this is the truth contract invariant that guarantees stable `[A001]`, `[A002]`, ... keys across runs.

The `src/retrieval/retriever.py` file is confirmed dead code (no imports in production paths). The active retriever is `src/research/reasoning/v3_retriever.py`. The test suite at `tests/retrieval/test_retriever.py` tests only the dead `src/retrieval/retriever.py` — those tests will continue to pass unchanged because we are not touching that file.

**Primary recommendation:** Parallelize the section loop in `SynthesisService.generate_master_brief` using index-preserving `asyncio.gather` over `build_evidence_packet` calls; apply global `sorted(all_atoms, key=lambda x: x['global_id'])` before citation assignment; extend benchmark seeding to 200–500 and 1000+ atom tiers.

---

## Architecture Patterns

### Q1: How does `build_evidence_packet` call `retrieve()`? Where is citation assignment?

**Answer (HIGH confidence — direct code read):**

`build_evidence_packet` (in `assembler.py`) does the following per call:
1. Calls `await self.retriever.retrieve(q)` — returns a `RoleBasedContext`
2. Iterates `retrieved_context.all_items`
3. For each item with `metadata['atom_id']`, constructs `atom_dict` with:
   ```python
   "global_id": f"[{item.citation_key}]" if item.citation_key else f"[A{len(seen_ids)}]"
   ```
4. Collects into `collected: List[(atom_dict, atom_id)]`
5. Sorts: `collected.sort(key=lambda pair: pair[0]['global_id'])`
6. Unpacks into `packet.atoms` and `packet.atom_ids_used`

**Critical finding:** Citation keys (`[A001]` etc.) are NOT assigned inside `build_evidence_packet`. The `citation_key` on `RetrievedItem` objects comes from metadata stored in ChromaDB at index time — it is a property of the stored atom, not dynamically assigned here. What `build_evidence_packet` does is: **wrap** that stored citation_key in brackets for `global_id`, using the fallback `[A{n}]` only when no citation_key is present in metadata.

This means that with concurrent retrieval, as long as we:
1. Collect all atoms from all concurrent results
2. Apply `sorted(all_atoms, key=lambda x: x['global_id'])` globally

...the citation stability invariant holds. The `global_id` values are derived from stored metadata, not from insertion order.

**The concurrent boundary:** The safe model is to fan out `build_evidence_packet` calls concurrently (one coroutine per section), collect all resulting `EvidencePacket` objects, then extract atoms and re-sort globally. However, the current design assigns `global_id` within each section packet independently. For a concurrent approach there are two implementation options:

- **Option A (recommended):** Move concurrency to `generate_master_brief` in `SynthesisService`, parallelizing the `build_evidence_packet` calls. Each packet is self-contained. Post-gather, merge all `packet.atoms` lists and sort globally, then rebuild the per-section atom assignment. This requires a small architectural change: either a new assembler method `build_all_evidence_packets(sections)` that does the global sort, or the merger happens in `generate_master_brief`.

- **Option B:** Introduce a new method `assemble_all_sections(mission_id, topic_name, sections)` on `EvidenceAssembler` that fans out concurrently and returns a dict of `{section_order: EvidencePacket}` after applying global sort. This keeps concurrency logic in the assembler layer where it belongs per CONTEXT.md.

**CONTEXT.md mandates:** Primary optimization lives in `EvidenceAssembler`. Option B is preferred.

### Q2: What does `generate_master_brief` look like? Is there already async structure?

**Answer (HIGH confidence — direct code read):**

`generate_master_brief` in `SynthesisService` (synthesis_service.py:85–157):
- Is a single `async def` method
- Contains a **sequential** `for section in sorted(plan, key=lambda x: x.order)` loop
- Each iteration: `packet = await self.assembler.build_evidence_packet(...)` — this is the bottleneck
- No existing concurrency; all sections run one at a time

The benchmark script (benchmark_suite.py:239–271) mirrors this same sequential loop, explicitly timing each `build_evidence_packet` call and summing them as `retrieval_ms_total`. This confirms the bottleneck measurement methodology is correct.

The `SynthesisService` loop also does LLM synthesis per section sequentially (Archivist calls), which we are NOT parallelizing in this phase. Only the retrieval gather is in scope.

### Q3: Is `asyncio.to_thread` in ChromaDB adapter thread-safe for concurrent calls?

**Answer (HIGH confidence — code inspection + asyncio semantics):**

`ChromaSemanticStoreImpl.query()` in `chroma.py` uses:
```python
results = await asyncio.to_thread(coll.query, **kwargs)
```

Two concerns:

**Concern 1: `_collections` dict cache race condition.**
The `_get_collection` method:
```python
async def _get_collection(self, name: str):
    if name not in self._collections:
        self._collections[name] = await asyncio.to_thread(
            self.client.get_or_create_collection, name=name
        )
    return self._collections[name]
```
This has a TOCTOU (Time-Of-Check-Time-Of-Use) race: if 8 coroutines all call `_get_collection("knowledge_atoms")` concurrently while the key is not yet in `_collections`, they will all issue `asyncio.to_thread(get_or_create_collection, ...)` concurrently. However:
- All 8 calls use the same collection name `"knowledge_atoms"`
- ChromaDB's `get_or_create_collection` is idempotent (it creates if absent, returns existing otherwise)
- The last write to `self._collections[name]` wins in Python's GIL-protected dict assignment
- In practice, all 8 coroutines will get a valid collection object back (pointing to the same underlying collection)

**Risk level: LOW.** After the first real run, the collection is cached and subsequent concurrent calls hit the `if name not in self._collections` fast path safely (dict read is atomic in CPython).

**Concern 2: Thread safety of `coll.query` itself.**
ChromaDB's PersistentClient uses SQLite3 internally via `chromadb.PersistentClient`. `asyncio.to_thread` runs each call in Python's default thread pool. SQLite3 in WAL mode supports concurrent readers. ChromaDB's Python client uses a per-request approach that does not share connection state between threads.

**Answer:** Concurrent `asyncio.to_thread(coll.query, ...)` calls are safe. Each call gets its own thread-local context. The collection object is read-only during query operations.

**Semaphore consideration (Claude's discretion):** 8 concurrent queries (one per section) is fine. The thread pool default size is `min(32, (os.cpu_count() or 1) + 4)` in Python 3.10 — on a Ryzen 9 that is at least 16 threads. 8 concurrent ChromaDB queries fit comfortably. An `asyncio.Semaphore(8)` would add overhead without benefit for 8 sections. If sections ever exceed 16, consider `Semaphore(12)`.

### Q4: What tests exist for retrieval? Which would break if ordering changes?

**Answer (HIGH confidence — direct code read):**

| Test File | What it Tests | Ordering Sensitivity |
|-----------|--------------|----------------------|
| `tests/retrieval/test_retriever.py` | `src/retrieval/retriever.py` (DEAD CODE) | Tests sequential citation key assignment `[A001]`, `[A002]`, `[A003]` — but this is for the dead retriever, not the active one |
| `tests/retrieval/test_validator.py` | `src/retrieval/validator.py` | No ordering dependency |
| `tests/research/reasoning/test_phase11_invariants.py` | `EvidenceAssembler`, `SynthesisService`, `V3Retriever` (active path) | **ORDERING-SENSITIVE** |

**Critical invariant tests in `test_phase11_invariants.py`:**
- `test_evidence_packet_captures_atom_ids`: Asserts `[a['global_id'] for a in packet.atoms] == ['[A1]', '[A2]']` (sorted order)
- `test_atom_order_sorted`: Asserts `gids == ['[A]', '[B]']` and `packet.atom_ids_used == ['atom1', 'atom2']` (items in items-sorted-by-global_id order)

These tests call `build_evidence_packet` directly and check deterministic sort order. They will continue to pass if we preserve per-section `collected.sort(key=lambda pair: pair[0]['global_id'])` within `build_evidence_packet`.

**If we add a `assemble_all_sections` method** (Option B above): the new method must apply global sort before returning, but individual packet atoms must still be sorted (for the single-section test path to remain valid). The existing tests mock `build_evidence_packet` directly in the `SynthesisService` tests, so SynthesisService refactors do not affect those.

**No test file will break** from concurrent retrieval if per-section sort is preserved and global sort is applied before citation assignment.

### Q5: Is `src/retrieval/retriever.py` dead code?

**Answer (HIGH confidence — grep confirmed):**

Grep of all `*.py` under `src/` for `from retrieval` or `import retrieval` returned **zero matches**.

Active production imports checked:
- `src/core/system.py` imports: `from research.reasoning.retriever import RetrievalQuery` (the reasoning/ version)  and `from research.reasoning.v3_retriever import V3Retriever`
- `src/research/reasoning/assembler.py` imports: `from research.reasoning.retriever import RetrievalQuery` and `from research.reasoning.v3_retriever import V3Retriever`

The only files importing from `src/retrieval/`:
- `tests/retrieval/test_retriever.py` imports `from retrieval.retriever import V3Retriever, RoleBasedContext, RetrievedItem`
- `tests/retrieval/test_validator.py` imports `from retrieval.validator import ...` and `from retrieval.models import RetrievedItem`
- `tests/test_chat_integration.py` imports `from retrieval.retriever import RoleBasedContext, RetrievedItem` (this test is in the exclude list)

**Conclusion:** `src/retrieval/retriever.py` is dead production code. It has its own `V3Retriever` class (different API — takes `query_text: str` not a `RetrievalQuery` object), `RoleBasedContext`, and `RetrievedItem` — these duplicate the types in `src/research/reasoning/`. The dead retriever tests at `tests/retrieval/test_retriever.py` will continue passing unchanged because we touch neither file.

**Action:** Add a deprecation docstring comment at the top of `src/retrieval/retriever.py`. Do not delete (tests reference it).

### Q6: How are atoms sorted/deduplicated in `build_evidence_packet`? What invariants must be preserved?

**Answer (HIGH confidence — direct code read):**

Current algorithm in `build_evidence_packet`:
1. `seen_ids: set()` — deduplication by `atom_id` from metadata
2. `collected: List[(atom_dict, atom_id)]` — built in retrieval order
3. `global_id` = `f"[{item.citation_key}]"` if citation_key else `f"[A{len(seen_ids)}]"` — fallback counter
4. `collected.sort(key=lambda pair: pair[0]['global_id'])` — lexicographic sort on global_id string
5. Unpack: `packet.atoms` and `packet.atom_ids_used` in sorted order

**Invariants that MUST be preserved:**
1. **Deduplication:** No atom_id appears twice across any section (already per-section; cross-section dedup is currently absent but atoms can repeat across sections)
2. **Per-section sort by global_id:** `packet.atoms` must be sorted by `global_id` lexicographically
3. **atom_ids_used mirrors atom order:** `packet.atom_ids_used[i]` is the atom_id of `packet.atoms[i]`
4. **global_id derived from stored citation_key:** The fallback `[A{n}]` counter uses `len(seen_ids)` as n — after concurrency, if per-section dedup is preserved independently, this fallback remains deterministic within each section

**Critical cross-section concern:** The CONTEXT.md mandates a global re-sort of all atoms before citation assignment. However, looking at the code more carefully:

The `global_id` is derived from ChromaDB-stored `citation_key` metadata — not dynamically assigned sequential IDs. So global sort in `EvidenceAssembler` would sort by the stored citation_key values (e.g., `[A001]`, `[A002]`...) — these are pre-assigned at index time, not at retrieval time. The sort ensures a canonical ordering but does NOT change the citation keys themselves.

**Where citation keys are stored:** In ChromaDB metadata field `citation_key` on each atom. This is assigned at ingestion/condensation time. V3Retriever reads it from `meta.get("citation_key")` and sets `item.citation_key`.

**Implication for concurrent gather:** Each concurrent `build_evidence_packet` call returns a self-contained `EvidencePacket` with correctly sorted atoms. If `generate_master_brief` needs to present a globally consistent atom set (e.g., for cross-section reporting), a global merge-and-sort is needed. But `generate_master_brief` currently does NOT merge atoms across sections — it stores each section's `atom_ids_used` independently. The global re-sort mandate in CONTEXT.md is therefore a **pre-storage validation step**, not a requirement that changes individual packet content.

**Implementation note:** CONTEXT.md's non-negotiable global re-sort is most naturally applied in a new `assemble_all_sections` method that returns pre-sorted, globally-deduplicated atoms, or it can be applied in `generate_master_brief` after gathering all packets.

### Q7: Benchmark script structure — how hard to extend for MEDIUM/LARGE tiers?

**Answer (HIGH confidence — direct code read):**

The existing `seed_high_evidence_atoms(adapter, mission_id, topic, count=20)` function (benchmark_suite.py:111–153) already does all the work:
1. Fetches mission to get `domain_profile_id`
2. Creates `count` synthetic atoms with structured content
3. Inserts each into PostgreSQL via `adapter.pg.insert_row("knowledge.knowledge_atoms", atom)`
4. Indexes each into ChromaDB via `adapter.chroma.index_document("knowledge_atoms", atom_id, doc, meta)`

**Extension pattern is trivial:** Change the call from `count=20` to `count=500` or `count=1000`. The function already accepts `count` as a parameter.

**What needs adding for corpus tiers:**
1. A `--corpus-tier` CLI argument: `small` (20), `medium` (500), `large` (1000)
2. Map tier names to counts: `CORPUS_TIERS = {"small": 20, "medium": 500, "large": 1000}`
3. Pass the count into `seed_high_evidence_atoms(adapter, mission_id, topic, count=tier_count)`
4. Include tier name in benchmark output JSON

**MEDIUM/LARGE seeding performance:** At 500–1000 atoms, the seeding loop makes 500–1000 sequential insert + index calls. This will be slow (potentially 30–60 seconds). Consider batching: `index_documents()` (plural) already exists in `ChromaSemanticStoreImpl` and accepts batches. PostgreSQL batch insert can use `insert_rows` if that method exists, or a single `executemany`.

**Check `adapter.pg` for batch insert:** The `PostgresStoreImpl` `insert_row` method works one row at a time. For LARGE tier seeding, a batched approach or a direct `COPY` statement will reduce seeding time significantly.

### Q8: Is asyncio.Semaphore needed? Is 8 concurrent queries fine?

**Answer (HIGH confidence — environment + code analysis):**

Factors:
- **Thread pool size:** Python 3.10 default `ThreadPoolExecutor` max workers = `min(32, os.cpu_count() + 4)`. On a Ryzen 9 (16 cores), that is `min(32, 20)` = 20 threads. 8 concurrent ChromaDB queries fit within this pool.
- **ChromaDB SQLite WAL:** SQLite in WAL mode allows concurrent readers; no mutex contention for read queries.
- **ChromaDB embedding:** With `query_texts` (not pre-computed embeddings), ChromaDB computes the embedding inline. This is CPU-bound and happens inside `asyncio.to_thread` — so 8 concurrent embeddings would use 8 threads simultaneously. This is fine on Ryzen 9.
- **Memory:** 8 concurrent result sets of 15 atoms each = 120 atoms in flight. Negligible.

**Recommendation (Claude's discretion):** No `asyncio.Semaphore` needed for baseline. If profiling reveals thread contention, add `Semaphore(6)` as a tunable. Use a module-level constant `RETRIEVAL_CONCURRENCY_LIMIT = 8` so it can be adjusted.

---

## Standard Stack

### Core (no new dependencies)
| Library | Current Version | Purpose | Notes |
|---------|----------------|---------|-------|
| `asyncio` | stdlib (3.10) | Concurrency primitives | `asyncio.gather`, `asyncio.create_task` |
| `chromadb` | 1.5.5 (verified) | Vector store queries | Already in use |
| `asyncio.to_thread` | stdlib (3.9+) | Offload blocking calls | Already used in `ChromaSemanticStoreImpl` |

**No new pip dependencies required for this phase.**

---

## Architecture Patterns

### Pattern 1: Index-Preserving gather (MANDATORY from CONTEXT.md)

The CONTEXT.md mandates this exact pattern. Verified it aligns with Python's `asyncio.gather` semantics — `asyncio.gather` already preserves input order in its return values (Python docs: "results in the list in the order of the original sequence"). However, because we are using `asyncio.create_task` which may schedule in any order, using explicit index tagging is the safer approach and is explicitly required.

```python
# In EvidenceAssembler.assemble_all_sections (new method)
import asyncio

async def assemble_all_sections(
    self, mission_id: str, topic_name: str, sections: List[SectionPlan]
) -> Dict[int, EvidencePacket]:
    """
    Retrieve evidence for all sections concurrently.
    Returns dict keyed by section.order, with atoms sorted per-section.
    """
    # Fan out: create (order, task) pairs — preserves index for result matching
    indexed_tasks = [
        (section.order, asyncio.create_task(
            self.build_evidence_packet(mission_id, topic_name, section)
        ))
        for section in sections
    ]
    # Gather all — return_exceptions=True prevents one failure from killing all
    results_raw = await asyncio.gather(
        *[task for _, task in indexed_tasks],
        return_exceptions=True
    )
    # Map results back to section order
    packets: Dict[int, EvidencePacket] = {}
    for (order, _), result in zip(indexed_tasks, results_raw):
        if isinstance(result, Exception):
            # Log and fall back to empty packet
            logger.error(f"[Assembler] Section {order} retrieval failed: {result}")
            packets[order] = EvidencePacket(
                topic_name=topic_name,
                section_title=f"Section {order}",
                section_objective=""
            )
        else:
            packets[order] = result
    return packets
```

### Pattern 2: SynthesisService integration

`generate_master_brief` calls `assemble_all_sections` instead of the per-section loop for retrieval:

```python
# Replace:
for section in sorted(plan, key=lambda x: x.order):
    packet = await self.assembler.build_evidence_packet(mission_id, topic_name, section)

# With:
all_packets = await self.assembler.assemble_all_sections(mission_id, topic_name, plan)

for section in sorted(plan, key=lambda x: x.order):
    packet = all_packets[section.order]
    # ... rest of synthesis loop unchanged ...
```

This keeps the LLM synthesis calls sequential (as required — they depend on `previous_context`) but parallelizes only retrieval.

### Pattern 3: Global re-sort invariant

The CONTEXT.md global re-sort is most clearly implemented inside `assemble_all_sections` or as a validation step. Since individual `build_evidence_packet` calls already sort their own atoms, and since `generate_master_brief` processes sections independently (not merging atoms across sections), the global re-sort applies at the **per-packet** level and is already implemented. The CONTEXT.md mandate is satisfied by preserving the existing `collected.sort(key=lambda pair: pair[0]['global_id'])` within `build_evidence_packet`.

If a cross-section global sort is ever needed (e.g., for a global atom registry), add it in `assemble_all_sections` after collecting all packets.

### Pattern 4: Per-section timing instrumentation

Add timing inside `build_evidence_packet` to separate:
- `embedding_ms`: Time ChromaDB spends computing embedding (hard to separate without ChromaDB internals)
- `query_ms`: Full `adapter.chroma.query()` call time

Practical approach — time the `retrieve()` call itself:
```python
import time

t0 = time.perf_counter()
retrieved_context = await self.retriever.retrieve(q)
retrieve_ms = (time.perf_counter() - t0) * 1000
logger.debug(f"[Assembler] Section '{section.title}' retrieval: {retrieve_ms:.1f}ms")
```

Return timing data via a side channel (e.g., a `_last_timing` attribute or by enriching `EvidencePacket` with optional timing metadata).

### Pattern 5: Corpus tier extension for benchmark

```python
CORPUS_TIERS = {
    "small": 20,
    "medium": 500,
    "large": 1000
}

# In seed_high_evidence_atoms: use batch indexing for medium/large
async def seed_high_evidence_atoms(adapter, mission_id, topic, count=20):
    ...
    # Batch Chroma indexing for speed
    rows = [(atom_id, doc, meta), ...]
    await adapter.chroma.index_documents("knowledge_atoms", rows)
```

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Result order after gather | Custom ordering logic | Zip indexed_tasks with gather results | asyncio.gather already preserves order by index; zip is O(n) and correct |
| Thread-safe collection cache | Locking/double-checked locking | Accept chromadb idempotency | `get_or_create_collection` is idempotent; GIL protects dict writes |
| Embedding separation timing | Hook into chromadb internals | Time full `retrieve()` call | Embedding is inside chromadb.to_thread; not separable without chromadb source changes |
| LARGE corpus batch insert | Write custom SQL COPY | Use `index_documents()` for Chroma batch + PostgreSQL row-by-row with chunking | `index_documents()` already batches Chroma upsert |

---

## Common Pitfalls

### Pitfall 1: Naive `asyncio.gather` loses section ordering
**What goes wrong:** Using `results = await asyncio.gather(*tasks)` and mapping results back to sections by position assumes tasks were created and completed in the same order as `sections`. While Python's `asyncio.gather` does preserve return-value order relative to input order, the explicit index-tagging pattern required by CONTEXT.md provides a safety net and self-documents intent.
**Why it happens:** Developer assumes gather result index == section order.
**How to avoid:** Always use `(section.order, task)` tuples and zip them with results.
**Warning signs:** Citation keys shifting across runs; sections containing wrong evidence.

### Pitfall 2: `global_id` fallback counter is non-deterministic in concurrent context
**What goes wrong:** The fallback `f"[A{len(seen_ids)}]"` in `build_evidence_packet` uses a counter that increments per atom within a single packet call. In concurrent execution, two sections might independently assign `[A1]`, `[A2]` etc. When these atoms are later merged for cross-section reporting, duplicate global_ids appear.
**Why it happens:** The fallback was designed for single-section use.
**How to avoid:** The current design does NOT merge atoms across sections in storage — each section stores its own `atom_ids_used` independently. The problem only arises if you add cross-section merging. If you do, replace the counter-based fallback with a mission-scoped global counter or use the atom_id directly.
**Warning signs:** `[A3]` appears in two different sections' stored evidence.

### Pitfall 3: `_collections` cache race under concurrent cold start
**What goes wrong:** 8 concurrent coroutines all call `_get_collection("knowledge_atoms")` on a fresh `ChromaSemanticStoreImpl` before any collection is cached. All 8 see `name not in self._collections` and all 8 issue `asyncio.to_thread(get_or_create_collection, ...)`. This results in 8 thread pool tasks running concurrently, each calling ChromaDB's `get_or_create_collection`. Because ChromaDB's operation is idempotent, this is safe but wastes 7 unnecessary thread-pool round trips.
**Why it happens:** No locking in `_get_collection`.
**How to avoid:** After warm-up (second call onward), the collection is cached and only one `to_thread` call happens. Cold-start inefficiency is a one-time cost per process lifetime. No fix needed for this phase.
**Warning signs:** First benchmark iteration slightly slower than subsequent ones (already the case per BASELINE_METRICS.md warm-up note).

### Pitfall 4: Seeding LARGE corpus via per-atom sequential inserts times out
**What goes wrong:** `seed_high_evidence_atoms` with `count=1000` makes 1000 sequential Chroma `index_document` calls. Each call is `asyncio.to_thread(coll.upsert, ...)`. At ~5ms per upsert, that's ~5 seconds just for Chroma indexing. PostgreSQL `insert_row` similarly calls one at a time.
**Why it happens:** Existing seeding function was written for `count=20`.
**How to avoid:** Use `adapter.chroma.index_documents()` (batch upsert) and PostgreSQL `executemany` or chunked inserts.
**Warning signs:** Benchmark seeding phase taking > 10 seconds before first measurement.

### Pitfall 5: SynthesisService LLM loop must remain sequential
**What goes wrong:** Attempting to parallelize LLM section synthesis alongside retrieval. The Archivist `write_section` uses `previous_context` (accumulated from all prior sections) — parallelizing it would produce incoherent sections.
**Why it happens:** Developer conflates "parallelize retrieval" with "parallelize everything."
**How to avoid:** Only retrieval (ChromaDB queries) is parallelized. LLM synthesis loop remains sequential with `previous_context` accumulation.
**Warning signs:** Section 2 prose not referencing Section 1 context; sections with repetitive content.

---

## Code Examples

### Current sequential loop (the bottleneck)
```python
# synthesis_service.py:85-91 — confirmed by direct read
for section in sorted(plan, key=lambda x: x.order):
    console.print(f"\n[bold blue][Section {section.order}][/bold blue] {section.title}")
    console.print(f"[dim]  - Gathering Evidence ({', '.join(section.target_evidence_roles)})...[/dim]")
    # Assemble Evidence with mission_id — SEQUENTIAL BOTTLENECK
    packet = await self.assembler.build_evidence_packet(mission_id, topic_name, section)
```

### The single retrieve call inside build_evidence_packet
```python
# assembler.py:107 — confirmed by direct read
retrieved_context = await self.retriever.retrieve(q)
```

### ChromaDB's asyncio.to_thread wrapping
```python
# chroma.py:97 — confirmed by direct read
results = await asyncio.to_thread(coll.query, **kwargs)
```

### Existing sort invariant in build_evidence_packet
```python
# assembler.py:127-128 — MUST be preserved
collected.sort(key=lambda pair: pair[0]['global_id'])
for atom_dict, atom_id in collected:
    packet.atoms.append(atom_dict)
    packet.atom_ids_used.append(atom_id)
```

### Existing seeding function signature (for extension)
```python
# benchmark_suite.py:111
async def seed_high_evidence_atoms(adapter, mission_id, topic, count=20):
    # Inserts count atoms into PostgreSQL + Chroma
    # Already accepts count param — just needs MEDIUM/LARGE values
```

---

## Dead Code Confirmation

**`src/retrieval/retriever.py`** is dead. Evidence:

1. Zero production imports found via grep of `src/**/*.py` for `from retrieval` or `import retrieval`
2. Active production path uses `src/research/reasoning/v3_retriever.py` (different module, different API signature: takes `RetrievalQuery` object; dead code takes `query_text: str`)
3. Active production path also uses `src/research/reasoning/retriever.py` for `RetrievalQuery`, `RoleBasedContext`, `RetrievedItem` **types only** (the class itself has no implementation beyond line 122)
4. Only test files import from `src/retrieval/`: `tests/retrieval/test_retriever.py`, `tests/retrieval/test_validator.py`
5. `tests/test_chat_integration.py` imports from `retrieval.retriever` but is excluded from the guardrail pytest run

**Action:** Add deprecation comment header to `src/retrieval/retriever.py`. Do not delete — it would break `tests/retrieval/test_retriever.py` and `tests/retrieval/test_validator.py` which are in the guardrail suite.

**`src/retrieval/validator.py`** and **`src/retrieval/models.py`** are also dead production code; only referenced by tests.

---

## Validation Architecture

`nyquist_validation` key is absent from `.planning/config.json` — treating as enabled.

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest |
| Config file | none (pytest.ini not found; uses default discovery) |
| Quick run command | `pytest tests/research/reasoning/test_phase11_invariants.py -q` |
| Full suite command | `pytest tests/ -q --ignore=tests/test_archivist_resilience.py --ignore=tests/test_chat_integration.py --ignore=tests/test_smelter_status_transition.py` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| PERF-01 | Total retrieval P95 < 200ms with concurrent gather | benchmark | `python3 scripts/benchmark_suite.py --scenario high_evidence --iterations 3` | ✅ (extends existing) |
| PERF-01 | Citation key stability across concurrent runs | unit | `pytest tests/research/reasoning/test_phase11_invariants.py::test_atom_order_sorted -x` | ✅ |
| PERF-01 | atom_ids_used ordering preserved after concurrency | unit | `pytest tests/research/reasoning/test_phase11_invariants.py::test_evidence_packet_captures_atom_ids -x` | ✅ |
| PERF-01 | Section order preserved after concurrent gather | unit | new test needed — Wave 0 gap | ❌ Wave 0 |
| PERF-01 | return_exceptions=True handles section failure gracefully | unit | new test needed — Wave 0 gap | ❌ Wave 0 |
| PERF-04 | Concurrency level documented and configurable | code | grep `RETRIEVAL_CONCURRENCY_LIMIT` in assembler.py | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `pytest tests/research/reasoning/test_phase11_invariants.py -q`
- **Per wave merge:** Full suite command above
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/research/reasoning/test_concurrent_assembly.py` — covers concurrent section ordering and error fallback (REQ: PERF-01 concurrency correctness)
- [ ] `RETRIEVAL_CONCURRENCY_LIMIT` constant in `assembler.py` — covers PERF-04 configurability
- [ ] No framework install needed (pytest already present, 94 tests passing per BASELINE_METRICS.md)

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python asyncio | Concurrent gather | ✓ | 3.10 stdlib | — |
| chromadb | Vector queries | ✓ | 1.5.5 | — |
| PostgreSQL | Atom seeding | ✓ | localhost:5432 per BASELINE_METRICS | — |
| Redis | System init | ✓ | localhost:6379 per system.py | — |
| pytest | Test guardrail | ✓ | Used in benchmark | — |

No missing dependencies.

---

## Project Constraints (from CLAUDE.md)

`CLAUDE.md` does not exist in the working directory. No additional project-specific constraints beyond those in CONTEXT.md.

---

## Open Questions

1. **Cross-section atom deduplication post-concurrency**
   - What we know: `build_evidence_packet` deduplicates within a single section call (via `seen_ids`). Currently, the same atom can appear in multiple sections.
   - What's unclear: CONTEXT.md says "global re-sort before citation assignment" — is this mandating cross-section dedup, or just ordering within what's collected?
   - Recommendation: Read CONTEXT.md as requiring per-section atom sort (already done) plus section-order preservation after gather. Do NOT add cross-section dedup in this phase — it would change atom_ids_used semantics and is not mentioned as a correctness requirement.

2. **Embedding timing separation**
   - What we know: ChromaDB computes embeddings inside `asyncio.to_thread(coll.query, ...)` — no external hook available.
   - What's unclear: Can we use ChromaDB's `query_embeddings` param with a pre-computed embedding to separate embedding cost from search cost?
   - Recommendation: For PERF-01, time the full `retrieve()` call. CONTEXT.md says "if possible" for embedding vs query separation — mark as optional in plan.

3. **Seeding LARGE corpus: PostgreSQL batch method**
   - What we know: `adapter.pg.insert_row()` exists. No `insert_rows()` plural was confirmed in the portion of storage_adapter.py read.
   - What's unclear: Does `PostgresStoreImpl` have a batch insert method, or does seeding LARGE tier require 1000 sequential calls?
   - Recommendation: Check `src/memory/adapters/postgres.py` during implementation (Wave 1 task). If no batch method, implement seeding with chunked asyncio gather over insert_row calls, or add `executemany` directly.

---

## Sources

### Primary (HIGH confidence)
- Direct read: `src/research/reasoning/assembler.py` — full `build_evidence_packet` implementation
- Direct read: `src/research/reasoning/synthesis_service.py` — full `generate_master_brief` sequential loop
- Direct read: `src/research/reasoning/v3_retriever.py` — single `retrieve()` call via `adapter.chroma.query`
- Direct read: `src/memory/adapters/chroma.py` — `asyncio.to_thread` wrapping, `_collections` cache
- Direct read: `src/core/system.py` — assembler/retriever wiring
- Direct read: `scripts/benchmark_suite.py` — seeding function, timing methodology
- Direct read: `tests/research/reasoning/test_phase11_invariants.py` — ordering invariant tests
- Direct read: `tests/retrieval/test_retriever.py` — dead-code retriever tests
- Direct read: `BASELINE_METRICS.md` — confirmed retrieval_ms mean=1209ms, 8 sections, 20 atoms
- Direct read: `src/retrieval/retriever.py` — dead code confirmed (different API, no production imports)
- Grep: zero production imports of `src/retrieval/` confirmed
- Python docs / asyncio.gather help: verified return order preservation

### Secondary (MEDIUM confidence)
- ChromaDB 1.5.5 SQLite WAL thread safety: verified via `python3 -c "import chromadb; print(chromadb.__version__)"` + general SQLite WAL documentation

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — no new dependencies; asyncio and chromadb are already in use
- Architecture: HIGH — code read confirmed exact call sites; no inference needed
- Pitfalls: HIGH — derived directly from code inspection of race conditions and invariants
- Dead code status: HIGH — grep confirmed zero production imports
- Test impact: HIGH — all test files read directly

**Research date:** 2026-03-30
**Valid until:** 2026-04-30 (stable domain; asyncio and chromadb APIs are not changing)
