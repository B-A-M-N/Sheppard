# Sheppard V3: Ambiguity Register — Master Catalog

**Purpose**: Master backlog of all system ambiguities, partitioned by priority and target phase.

**How to use**: Each ambiguity must be resolved via code inspection, testing, or decision before implementation begins. Do NOT treat this as a monolithic todo list — consult the relevant subset when planning each phase.

**Partitioning**:
- **Tier 0** — Critical, must resolve before Phase 05/06 PASS is valid
- **Tier 1** — Active in Phase 06 (discovery audit only — observe, classify, evidence; do NOT fix)
- **Tier 2** — Orchestration/Control Plane (Phases 07+)
- **Tier 3** — Product/Performance (later phases)
- **Tier 4** — Future Design / Nice-to-have

---

## Tier 0 — Must Already Be Resolved

If these remain open, Phase 05/06 PASS is invalid.

### A.2: What is `self.adapter` in `DistillationPipeline`?

**Ambiguity**: In `condensation/pipeline.py`:
```python
sources = await self.adapter.pg.fetch_many("corpus.sources", ...)
```
Where does `self.adapter` come from? What class is it? What other methods does it expose?
- `adapter.pg` - is this an asyncpg connection pool?
- `adapter.get_text_ref()` - what's that?
- `adapter.get_mission()` - where is mission data stored?

**Impact**: Need to know how to initialize `DistillationPipeline` properly.

**Resolution**: Find the adapter class definition. Likely in `src/research/` or `src/core/`. Could be `PostgresAdapter` or similar.

---

### A.3: What is the `KnowledgeAtom` Schema?

**Ambiguity**: The code mentions atoms but we need to confirm fields:
```python
from src.research.domain_schema import KnowledgeAtom, AtomLineage
```
What attributes does `KnowledgeAtom` have? At minimum:
- `concept` (str)
- `claim` (str)
- `evidence` (str or List[str])
- `confidence` (float 0-1)
- `source_ids` (List[str])
- `contradictions`? (List[OtherAtom])
- `extracted_at` (datetime)
- `mission_id` (str) - for scoping

**Impact**: Cannot implement storage or indexing without knowing schema.

**Resolution**: Read `domain_schema.py` to see exact definition. If incomplete, we must complete it.

---

### A.9: How Do We Scope Everything by `mission_id`?

**Ambiguity**: We're introducing a `mission_id` concept. All data (sources, atoms, frontier state) must be scoped to a mission.

But:
- Does `AdaptiveFrontier` currently support multiple missions? Probably not.
- `BudgetMonitor` seems to support multiple `TopicBudget` instances, but is `topic_id == mission_id`?
- `DistillationPipeline` queries `corpus.sources WHERE mission_id=$1` - so sources table must have `mission_id` column.
- `ArchivistIndex` currently seems single-mission (calls `index.clear_index()` in `run_research`). Need to make it multi-mission.

**Changes needed**:
- Every table: `sources`, `atoms`, `frontier_state`, `budget_metrics` needs `mission_id` column
- All queries must filter by `mission_id`

---

### A.14: What is the `CorpusAdapter` and Why Does Condensation Use It?

**Ambiguity**: `DistillationPipeline` takes an `adapter` parameter:
```python
def __init__(self, ollama, memory, budget, adapter=None):
    self.adapter = adapter
```
Then uses `self.adapter.pg`, `self.adapter.get_text_ref()`, `self.adapter.get_mission()`.

This suggests an abstraction over PostgreSQL and maybe other storage. Is this:
- A `PostgresAdapter` class somewhere?
- Part of a data access layer?

**Note**: This overlaps with A.2. Likely the same thing.

---

## Tier 1 — Phase 06 Active (Discovery Audit Only)

**Scope**: Only ambiguities directly affecting discovery layer behavior.
**Processing**: Observe, classify, produce evidence. Do NOT redesign or fix.

### A.4: How Does `AdaptiveFrontier.run()` Actually Work?

**Ambiguity**: We have the class but need to understand:
- **Input**: What parameters does it take? How is it initialized?
- **Output**: What API does it provide for the crawler to consume concepts?
- **Blocking vs async**: Is `run()` a long-running async task? Does it yield concepts?
- **State**: Does it maintain `nodes`, `visited_urls` in memory or DB?
- **Checkpointing**: `_load_checkpoint()` / `_save_checkpoint()` - what gets saved? To where?
- **Completion**: When does `run()` return? Does it ever return, or run forever until cancelled?
- **Concurrency**: If multiple missions, is each frontier independent?

**Audit focus**: Does frontier behavior match claims (4 modes, saturation detection, node generation)?

---

### A.6: What is the `Crawler` API?

**Ambiguity**: We have `acquisition/crawler.py` but need to know:
- Does it have a `fetch(url)` method? Or `crawl_concept(concept)`?
- How does frontier give it work? Queue? Callback? Shared data structure?
- What does it return? `Source` object? Just content?
- How does it deduplicate? Does it check `visited_urls` itself or does frontier do it?
- Is it async? Blocking?

**Audit focus**: Does crawler discovery match "deep mining" and "URL quality" claims?

---

### A.8: What Does "Exhaustion" Mean for the Frontier?

**Ambiguity**: `AdaptiveFrontier` has `exhausted_modes` per node. But when is the **entire mission** considered exhausted?

Options:
1. **All nodes have all 4 modes exhausted** → `frontier.is_exhausted = True`
2. **No new sources in X minutes** → timeout-based
3. **Yield below threshold for N iterations** → "nothing new found"
4. **Frontier run() returns** → maybe it exits when nothing to do?

**Problem**: Modes might be exhausted for a node, but there might be **new nodes** (new concepts) still being discovered. When do we stop?

**Audit focus**: Is exhaustion detection implemented? Does it work as claimed?

---

### A.10: What is the Archivist Index Currently Storing?

**Ambiguity**: `archivist/loop.py:run_research()` uses:
- `index.add_chunks(chunks, embs, metadatas)`
- Later retrieval via `retriever.retrieve(...)`

But what is the storage backend? The code uses:
- `from . import index, embeddings, retriever, ...`
- `index.clear_index()` (what does this clear? ChromaDB? FAISS?)

**Questions**:
- Is it using `chromadb`? Or custom FAISS?
- What's the schema for stored items? Do they have `mission_id` field?

**Audit focus**: Only insofar as discovery output is indexed and searchable. Not a deep dive into archivist internals.

---

### A.13: How Does Multi-Mission Coordination Work?

**Ambiguity**: The plan says `BudgetMonitor` already supports multiple `TopicBudget` instances. But:
- Is each mission its own topic? `topic_id == mission_id`?
- Does `AdaptiveFrontier` support multiple instances? (Yes, if we create one per mission)
- Does `ArchivistIndex` support multiple missions? Likely not currently.
- How do we prevent cross-mission data leakage? (must always filter by `mission_id`)
- What about LLM client? Is it shared? Thread-safe?

**Audit focus**: Does discovery layer properly isolate concurrent missions? Or is there bleed?

---

## Tier 2 — Orchestration / Control Plane (Phases 07+)

### A.5: How Does `BudgetMonitor` Actually Measure Storage Usage?

**Ambiguity**: Currently `BudgetMonitor` tracks bytes **in-memory**:
```python
self._budgets[topic_id].raw_bytes += len(content)
```
But this is **NOT persistent** and can diverge from actual DB size if:
- Sources are inserted outside the budget monitor
- Condensation prunes raw but doesn't update counter
- System crashes (memory lost)

We need a `StorageBackend` that queries the **actual database size**.

---

### A.7: How Does Condensation Triggering Work?

**Ambiguity**: `BudgetMonitor` calls `condensation_callback` when threshold crossed.

But:
- Does it call it **once** when threshold crossed, or **repeatedly** while above threshold?
- What happens if condensation is already running? Should it queue? Skip?
- What does the callback do? Likely: `await condensation.run(mission_id, priority)`
- Does condensation run in the same task or separate? Probably separate to not block budget monitor.
- What if condensation fails? Error handling?

---

### A.11: How Does the Current `run_research` Generate the Final Report?

**Ambiguity**: `archivist/loop.py` has `finalize_report()` that assembles sections.

But we need to understand:
- Does it use LLM to synthesize? Or just concatenate?
- How does it handle contradictions? Does it include them?
- What's the format? Markdown? JSON?
- Can we reuse this for our final report, or do we need new synthesis?

---

### A.12: What are the Configuration Options Currently?

**Ambiguity**: `ResearchSystem.__init__` takes `config`. What config options exist?
- `config.research.*`?
- `config.browser.*`?
- `config.firecrawl.*`?
- `config.chunk_size`, `chunk_overlap`?

We need to add new configs:
- `RESEARCH_CEILING_GB`
- `RESEARCH_EXHAUSTION_ENABLED`
- Threshold percentages
- Condensation priority mapping

---

### A.15: How Do We Handle LLM Errors During Interactive Queries?

**Ambiguity**: `query_knowledge()` calls LLM to generate answer. What if:
- LLM times out? Return partial results? Error?
- LLM returns malformed response? Retry?
- LLM is rate-limited? Cache?

---

### A.16: What is the Expected Query Latency and How Do We Achieve <2s?

**Ambiguity**: Success criteria says query latency <2 seconds for 10k+ atoms.

But:
- Embedding generation for question: ~200-500ms (Ollama)
- Vector search over raw corpus: how many chunks? 10k chunks → ~500ms?
- Vector search over atoms: 10k atoms → ~500ms?
- LLM synthesis: ~1000-3000ms (depending on context size)
- Total could easily exceed 2 seconds.

---

### A.17: How Do We Estimate "Coverage" for a Query?

**Ambiguity**: Query response should include `coverage_estimate` - what percentage of relevant knowledge we've gathered.

But how to compute this?

---

### A.18: How Do We Score "Confidence" Based on Source Agreement?

**Ambiguity**: Want confidence level (high/medium/low) for query answers.

Approach: Use source consensus. But how?

---

### A.19: How Does "Freshness" Indicator Work?

**Ambiguity**: Want to show "Fresh data: last 5 minutes" in query response.

Need to:
- Track `fetched_at` timestamp for each source
- For query results, look at the `fetched_at` of the newest source that contributed to the answer

---

### A.20: How Do We Define `mission_id` Scope in ArchivistIndex?

**Ambiguity**: Currently `archivist/loop.py` does:
```python
index.clear_index()  # clears everything
```
This is single-mission design. For multi-mission:
- Option A: Partition by `mission_id` in same index (metadata field `mission_id`)
- Option B: Separate index for each mission (in-memory, file-based)

---

### A.21: What Should Be the CLI Command Structure?

**Ambiguity**: We propose:
```bash
sheppard research start "topic" --type exhaustive --ceiling 10GB
sheppard mission query <id> "question"
sheppard mission status <id>
```
But current CLI likely has different structure. Need to check compatibility.

---

### A.22: How Do We Handle API Request Timeouts for Long Missions?

**Ambiguity**: `POST /api/v1/research` for exhaustive mission returns immediately with `mission_id`. That's fine.

But what about:
- `GET /api/v1/missions/{id}/stats` - should be fast
- `POST /api/v1/missions/{id}/query` - needs to be fast (<2s)
- `DELETE /api/v1/missions/{id}` - stop mission, should return immediately but stop may take time

---

### A.23: What About Error Handling and Retries in the Crawler?

**Ambiguity**: The crawler will encounter:
- Network timeouts
- HTTP errors (403, 404, 429)
- Malformed HTML
- Parser errors

What's the retry policy?

---

### A.24: How Do We Ensure Data Consistency Across Components?

**Ambiguity**: Multiple components access shared state:
- Frontier, crawler, budget all need `visited_urls` and `total_ingested`
- They'll modify these concurrently? Or orchestrator mediates?

**Race conditions**:
- Crawler adds to `visited_urls` while frontier reads it
- Budget reads `raw_bytes` while crawler updates it
- Frontier reads `total_ingested` to decide next concept

---

## Tier 3 — Product / Performance (Ignore for Now)

### A.16: Query Latency <2s (duplicate entry)
### A.17: Coverage Estimation (duplicate)
### A.18: Confidence Scoring (duplicate)
### A.19: Freshness Indicator (duplicate)

(Already in Tier 2)

### A.29: Should the Orchestrator Expose a Subscription Model for Real-Time Updates?

**Ambiguity**: Polling vs WebSocket? MVP: polling. WebSocket Phase 8.

---

## Tier 4 — Future Design / Nice-to-Have

### A.25: What Happens When the Storage Ceiling is Hit Mid-Fetch?

**Ambiguity**: Allow temporary overage? Reject fetch? Trigger CRITICAL immediately?

---

### A.26: What Does "Condensation May Prune Raw Content" Mean?

**Ambiguity**: After atoms extracted from a source, can we delete the raw `corpus.sources` entry? Or mark as `pruned=True`?

---

### A.27: How Do We Test With Real Firecrawl Without Spending Money?

**Ambiguity**: Use mock Firecrawl for most tests? Small real URL set? Local file corpus?

---

### A.28: What is the Relationship Between `ResearchSystem` and the New Orchestrator?

**Ambiguity**: Does `ResearchOrchestrator` take system deps? Instantiate in `ResearchSystem.__init__` or `research_topic()`?

---

### A.30: How Do We Ensure Summary Quality Before and After Condensation?

**Ambiguity**: Old `archivist/loop.py` uses `synth.summarize_source()`. Keep summaries or replace with atoms?

---

## Phase 02/03 Residual (Should Already Be Done)

⚠️ These affect Phase 05/06 PASS validity if unresolved.

### A.1: Does PostgreSQL Schema `corpus.sources` and `corpus.atoms` Actually Exist?

**Ambiguity**: The `DistillationPipeline` code references:
```python
await self.adapter.pg.fetch_many("corpus.sources", ...)
await self.adapter.pg.update_row("corpus.sources", ...)
```
But we haven't verified:
- Does the `corpus` schema exist?
- Do `sources` and `atoms` tables exist?
- What are the exact columns and types?
- Are there indexes for performance?

**Impact**: Cannot implement `StorageBackend` or verify condensation output without knowing schema.

---

**Total ambiguities**: 30 (some duplicated across tiers; deduplicated count = 28 unique)

**Partitioning summary**:
- **Tier 0**: 4 items (A.2, A.3, A.9, A.14) — MUST resolve before PASS
- **Tier 1**: 5 items (A.4, A.6, A.8, A.10, A.13) — Phase 06 audit scope
- **Tier 2**: 12 items (A.5, A.7, A.11, A.12, A.15–A.24) — Phases 07+
- **Tier 3**: 1 item (A.29) — later
- **Tier 4**: 5 items (A.25, A.26, A.27, A.28, A.30) — future/nice-to-have
- **Phase 02/03 Residual**: 1 item (A.1) — urgent blockers

**Note**: A.16–A.19 appear in both Tier 2 and Tier 3 due to duplication in source document — Phase 06 should not touch them.
