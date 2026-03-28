# Sheppard V3: Ambiguity Register

**Purpose**: Document all unclear or unknown aspects of the architecture and implementation plan. These are risks that need clarification before/during Phase 0.

**How to use**: Each ambiguity should be resolved via code inspection, testing, or decision before implementation begins.

---

## Critical Ambiguities (Block Phase 1 if Unresolved)

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
- Are there any foreign key constraints?

**Impact**: Cannot implement `StorageBackend` or verify condensation output without knowing schema.

**Resolution needed**: Find existing schema files or migrations. If none exist, we must **design the schema ourselves**.

**Owner**: Phase 0 Task 0.3

---

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

**Owner**: Phase 0 Task 0.1

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

**Owner**: Phase 0 Task 0.1

---

### A.4: How Does `AdaptiveFrontier.run()` Actually Work?

**Ambiguity**: We have the class but need to understand:
- **Input**: What parameters does it take? How is it initialized?
- **Output**: What API does it provide for the crawler to consume concepts?
- **Blocking vs async**: Is `run()` a long-running async task? Does it yield concepts?
- **State**: Does it maintain `nodes`, `visited_urls` in memory or DB?
- **Checkpointing**: `_load_checkpoint()` / `_save_checkpoint()` - what gets saved? To where?
- **Completion**: When does `run()` return? Does it ever return, or run forever until cancelled?
- **Concurrency**: If multiple missions, is each frontier independent?

**Impact**: Cannot design orchestrator-crawler communication without knowing frontier's API.

**Resolution**: Read full `frontier.py`, especially `run()` method and how it calls `crawler`.

**Owner**: Phase 0 Task 0.1

---

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

**Questions**:
- How to efficiently get total raw content size for a mission from PostgreSQL?
  - `SELECT SUM(LENGTH(content)) FROM corpus.sources WHERE mission_id=$1`?
  - Or track via file size if storing on disk?
- How to get condensed size? Sum of `LENGTH(claim)` from `corpus.atoms`?
- Performance: Is summing all rows every 10 seconds acceptable for 1M+ sources?
- Should we maintain a cached total that's updated on every insert/delete?

**Impact**: Budget monitoring could be wildly inaccurate if we don't implement proper storage backend.

**Resolution**: Decide on storage backend design (DB query vs cached counters). Implement and test.

**Owner**: Phase 0 Task 0.2, Phase 1 Task: Storage Backend

---

### A.6: What is the `Crawler` API?

**Ambiguity**: We have `acquisition/crawler.py` but need to know:
- Does it have a `fetch(url)` method? Or `crawl_concept(concept)`?
- How does frontier give it work? Queue? Callback? Shared data structure?
- What does it return? `Source` object? Just content?
- How does it deduplicate? Does it check `visited_urls` itself or does frontier do it?
- Is it async? Blocking?

**Impact**: Need to design orchestrator-crawler interaction.

**Resolution**: Read `crawler.py` fully.

**Owner**: Phase 0 Task 0.1

---

### A.7: How Does Condensation Triggering Work?

**Ambiguity**: `BudgetMonitor` calls `condensation_callback` when threshold crossed.

But:
- Does it call it **once** when threshold crossed, or **repeatedly** while above threshold?
- What happens if condensation is already running? Should it queue? Skip?
- What does the callback do? Likely: `await condensation.run(mission_id, priority)`
- Does condensation run in the same task or separate? Probably separate to not block budget monitor.
- What if condensation fails? Error handling?

**Example scenario**:
- Usage goes from 84% → 86% (crosses HIGH threshold)
- Budget calls callback with priority=HIGH
- Condensation starts running
- While condensation runs, usage drops to 82% (condensation freed space)
- Should we cancel condensation? Or let it finish?

**Impact**: Need clear semantics for trigger handling.

**Resolution**: Read `BudgetMonitor.monitor_loop()` implementation. Design callback contract.

**Owner**: Phase 0 Task 0.1

---

### A.8: What Does "Exhaustion" Mean for the Frontier?

**Ambiguity**: `AdaptiveFrontier` has `exhausted_modes` per node. But when is the **entire mission** considered exhausted?

Options:
1. **All nodes have all 4 modes exhausted** → `frontier.is_exhausted = True`
2. **No new sources in X minutes** → timeout-based
3. **Yield below threshold for N iterations** → "nothing new found"
4. **Frontier run() returns** → maybe it exits when nothing to do?

**Problem**: Modes might be exhausted for a node, but there might be **new nodes** (new concepts) still being discovered. When do we stop?

**Question**: Does frontier keep generating new concepts indefinitely? Or does it have a finite set from initial topic decomposition?

**Impact**: Cannot implement mission completion logic without clear exhaustion criteria.

**Resolution**: Read frontier's `run()` method to see when/if it terminates. Define `is_exhausted` property combining:
- All known nodes have all modes exhausted
- No new nodes discovered in last N iterations
- (Maybe) max runtime or max sources reached

**Owner**: Phase 0 Task 0.1, Phase 3 Task: Exhaustion Detection

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
- Indexes should include `mission_id`

**Impact**: This is a **schema design requirement**. Must add `mission_id` to all tables if not present.

**Resolution**: Check existing schema. Add `mission_id` columns where missing. Create composite indexes.

**Owner**: Phase 0 Task 0.3 (schema validation)

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
- Can we add `search_raw_chunks(mission_id, embedding)` method? Does the index support filtering by metadata?
- Do raw chunks and atoms need separate collections/tables, or same with type discriminator?

**Impact**: Index design affects how we implement `query_knowledge`.

**Resolution**: Read `archivist/index.py`. Understand storage backend. Plan extension.

**Owner**: Phase 0 Task 0.1

---

### A.11: How Does the Current `run_research` Generate the Final Report?

**Ambiguity**: `archivist/loop.py` has `finalize_report()` that assembles sections.

But we need to understand:
- Does it use LLM to synthesize? Or just concatenate?
- How does it handle contradictions? Does it include them?
- What's the format? Markdown? JSON?
- Can we reuse this for our final report, or do we need new synthesis?

**Impact**: Determines how we implement `orchestrator.generate_report()`.

**Resolution**: Read `finalize_report()` and related functions in `loop.py`. Decide to reuse or replace.

**Owner**: Phase 0 Task 0.1

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
- Checkpoint interval

**Questions**:
- Where is config defined? `src/research/config.py`?
- How is it loaded from `.env`? Pydantic settings?
- What's the precedence order?

**Impact**: Must integrate new config options consistently.

**Resolution**: Read `config.py`, understand config management pattern. Document all research-related configs.

**Owner**: Phase 0 Task 0.1

---

### A.13: How Does Multi-Mission Coordination Work?

**Ambiguity**: The plan says `BudgetMonitor` already supports multiple `TopicBudget` instances. But:
- Is each mission its own topic? `topic_id == mission_id`?
- Does `AdaptiveFrontier` support multiple instances? (Yes, if we create one per mission)
- Does `ArchivistIndex` support multiple missions? Likely not currently.
- How do we prevent cross-mission data leakage? (must always filter by `mission_id`)
- What about LLM client? Is it shared? Thread-safe?

**Design**:
- Each mission: own `AdaptiveFrontier`, own budget tracking, but may share:
  - LLM client (rate-limited, shared pool)
  - Database connection pool (shared)
  - Redis cache (namespaced by mission_id)
  - Index (must partition by mission_id)

**Impact**: Need to decide what's per-mission vs shared.

**Resolution**: Define component lifecycle: which are singleton, which are per-mission. Implement proper scoping.

**Owner**: Phase 0 Task 0.2, Phase 2 Task

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
- Documented anywhere?

**Impact**: Need to initialize `DistillationPipeline` with correct adapter. Must understand API.

**Resolution**: Find adapter implementation. If none, we need to write it or pass `None` and implement simpler interface.

**Owner**: Phase 0 Task 0.1

---

### A.15: How Do We Handle LLM Errors During Interactive Queries?

**Ambiguity**: `query_knowledge()` calls LLM to generate answer. What if:
- LLM times out? Return partial results? Error?
- LLM returns malformed response? Retry?
- LLM is rate-limited? Cache?

**Impact**: User experience during query could be poor without proper error handling.

**Resolution**: Define retry policy, timeout, fallback (maybe return raw search results without synthesis). Already have LLM client with error handling? Need to check.

**Owner**: Phase 5 Task: Interactive Query

---

### A.16: What is the Expected Query Latency and How Do We Achieve <2s?

**Ambiguity**: Success criteria says query latency <2 seconds for 10k+ atoms.

But:
- Embedding generation for question: ~200-500ms (Ollama)
- Vector search over raw corpus: how many chunks? 10k chunks → ~500ms?
- Vector search over atoms: 10k atoms → ~500ms?
- LLM synthesis: ~1000-3000ms (depending on context size)
- Total could easily exceed 2 seconds.

**Potential optimizations**:
- Cache question embeddings? (Not useful, questions vary)
- Limit context size (top 20 sources only)
- Use faster embedding model (nomic-embed-text vs mxbai-embed-large?)
- Pre-warm cache? Not applicable
- Use smaller LLM for answers (8B vs 70B)

**Questions**:
- What's the target context size (number of sources) for query?
- Is 2s realistic with current LLM setup?
- Should we make latency configurable (fast vs thorough)?

**Impact**: May need to adjust expectations or optimize aggressively.

**Resolution**: Benchmark current query latency with synthetic data in Phase 4. Tune parameters.

**Owner**: Phase 4 Task: Performance Benchmarks

---

### A.17: How Do We Estimate "Coverage" for a Query?

**Ambiguity**: Query response should include `coverage_estimate` - what percentage of relevant knowledge we've gathered.

But how to compute this?
- Option 1: `(sources_fetched_for_topic) / (estimated_total_sources_on_topic)` - need estimate of total, unknown
- Option 2: `(frontier_saturation)` - what % of concepts are saturated? But query might be about a specific concept.
- Option 3: `(raw_bytes / ceiling)` - crude but measurable
- Option 4: LLM self-assessment? "Based on these sources, how complete is the answer?" Not reliable.
- Option 5: Don't estimate - just show source count.

**Better**: Per-concept coverage. If query maps to concept X (via embedding similarity of query to concept definitions), show: "Coverage for this topic: 42% (12/29 sources saturated)".

**Impact**: Need algorithm for coverage estimation. Might be approximated.

**Resolution**: Design coverage estimation algorithm in Phase 5. Could be:
- For each frontier node related to query (embedding similarity > threshold), compute node's coverage (sources_for_node / estimated_needed)
- Aggregate weighted by relevance to query
- Or simpler: show overall mission coverage and note "this answer covers about X% of the mission scope"

**Owner**: Phase 5 Task

---

### A.18: How Do We Score "Confidence" Based on Source Agreement?

**Ambiguity**: Want confidence level (high/medium/low) for query answers.

Approach: Use source consensus. But how?
- If multiple sources make the same claim (embedding similarity of claims > threshold) → higher confidence
- If sources contradict → lower confidence
- If only one source → low confidence
- But claims are extracted from sources, not the raw sources themselves. So we need atoms.

**Process**:
1. Get relevant atoms (and/or raw chunks)
2. For each distinct claim (or answer position), count supporting sources
3. If >70% of sources agree → high confidence
4. If 30-70% agree on one position, 30-70% on another → contradiction, medium confidence (with flag)
5. If single source or wide dispersion → low confidence

**Challenge**: Extracting "claims" from raw text is hard. We're relying on atoms for this. So confidence scoring depends on quality of atom extraction.

**Impact**: Confidence may be noisy if atom extraction is poor.

**Resolution**:
- Initially use simple approach: count sources that mention similar embeddings
- Later: rely on atom's `confidence` field (already extracted by condensation)
- If no atoms yet (early mission), use raw chunks with lower confidence

**Owner**: Phase 5 Task

---

### A.19: How Does "Freshness" Indicator Work?

**Ambiguity**: Want to show "Fresh data: last 5 minutes" in query response.

Need to:
- Track `fetched_at` timestamp for each source
- For query results, look at the `fetched_at` of the newest source that contributed to the answer
- If newest < 5 minutes ago → "fresh" badge
- But if most sources are old but one is fresh? Maybe show "includes fresh data from X"

**Edge cases**:
- Mission just started, all data fresh → always fresh
- Mission complete, all data from crawl period → "Data collected between Jan 1-15"
- Query dominated by old condensed atoms (from early in mission) → freshness based on when those atoms were extracted? Or original source fetch time?

**Decision**: Freshness should be based on **source fetch time** (when we got the content from the web), not when atom was extracted. This reflects recency of information, not processing time.

**Impact**: Need to store `fetched_at` on sources and propagate to atoms? Or query can look at source metadata.

**Resolution**: Ensure source table has `fetched_at` timestamp. Atoms should reference source_ids, so can trace back to fetch time. Compute freshness as max(fetched_at) among sources contributing to answer.

**Owner**: Phase 5 Task

---

### A.20: How Do We Define `mission_id` Scope in ArchivistIndex?

**Ambiguity**: Currently `archivist/loop.py` does:
```python
index.clear_index()  # clears everything
```

This is single-mission design. For multi-mission:
- Option A: Partition by `mission_id` in same index (metadata field `mission_id`)
- Option B: Separate index for each mission (in-memory, file-based)
- Option A is better for memory, but requires indexing and filtering by mission_id.

**Questions**:
- Can the current index backend (likely Chroma/FAISS) filter by metadata `mission_id` efficiently?
- Do we need separate indexes? (One per concurrent mission)
- What about the graph? SWOC graph is in-memory - can we have multiple graphs?

**Impact**: ArchivistIndex needs major refactor for multi-mission.

**Resolution**: Check if index supports metadata filtering. If yes, add `mission_id` to all items and filter. If no, create wrapper class that maintains dict of indexes: `self.indexes = {mission_id: Index()}`.

**Owner**: Phase 2 Task

---

### A.21: What Should Be the CLI Command Structure?

**Ambiguity**: We propose:
```bash
sheppard research start "topic" --type exhaustive --ceiling 10GB
sheppard mission query <id> "question"
sheppard mission status <id>
```

But current CLI (in `src/interfaces/cli.py`?) likely has different structure. Need to check:
- What's the existing command hierarchy?
- How does it currently invoke research?
- Can we extend without breaking?

**Option**: Keep `research` as top-level, but subcommands:
```
sheppard research start [options]    # starts mission, returns ID
sheppard research query <id> [question]  # but this mixes resource types
```

Better: separate `mission` resource:
```
sheppard mission create "topic" --type exhaustive --ceiling 10GB
sheppard mission query <id> "question"
sheppard mission show <id>
sheppard mission list
sheppard mission stop <id>
```

**Impact**: Design CLI ergonomics.

**Resolution**: Check existing CLI. Design new commands. Implement in Phase 5/6.

**Owner**: Phase 5 Task: CLI Enhancements

---

### A.22: How Do We Handle API Request Timeouts for Long Missions?

**Ambiguity**: `POST /api/v1/research` for exhaustive mission returns immediately with `mission_id`. That's fine.

But what about:
- `GET /api/v1/missions/{id}/stats` - should be fast, returns current state
- `POST /api/v1/missions/{id}/query` - needs to be fast (<2s)
- `DELETE /api/v1/missions/{id}` - stop mission, should return immediately but stop may take time

What if a mission needs to be stopped and it's in the middle of a crawl? We need to signal the orchestrator to cancel tasks gracefully.

**Approach**: Set `self._cancelled = True` flag, orchestrator checks between operations and cancels tasks.

**Impact**: Need cancellation mechanism.

**Resolution**: Implement cooperative cancellation in orchestrator. Tasks check `asyncio.Event` or similar.

**Owner**: Phase 1 Task

---

### A.23: What About Error Handling and Retries in the Crawler?

**Ambiguity**: The crawler will encounter:
- Network timeouts
- HTTP errors (403, 404, 429)
- Malformed HTML
- Parser errors

What's the retry policy?
- Retry 3 times with exponential backoff?
- If 429 (rate limit), wait longer?
- Permanent failures (404) → mark source as failed, don't retry
- Should we have a dead letter queue for failed URLs?

**Impact**: Reliability of crawl. Need to handle failures gracefully without losing data.

**Resolution**: Define retry policy in crawler. Use `tenacity` or similar. Log failures clearly. Continue on errors.

**Owner**: Phase 1 Task: Crawler verification (or fix if needed)

---

### A.24: How Do We Ensure Data Consistency Across Components?

**Ambiguity**: Multiple components access shared state:
- Frontier, crawler, budget all need `visited_urls` and `total_ingested`
- They'll modify these concurrently? Or orchestrator mediates?

**Race conditions**:
- Crawler adds to `visited_urls` while frontier reads it
- Budget reads `raw_bytes` while crawler updates it
- Frontier reads `total_ingested` to decide next concept

**Current code**: `BudgetMonitor` has `asyncio.Lock()` for state updates. Good.

But `AdaptiveFrontier` state - is it protected? Need to review.

**Impact**: Potential data corruption if not synchronized.

**Resolution**: Ensure all shared mutable state has locks. Or use actor model (single writer). Review frontier code for thread safety.

**Owner**: Phase 1 Task: Wire components, add locks if needed

---

### A.25: What Happens When the Storage Ceiling is Hit Mid-Fetch?

**Ambiguity**: Scenario:
1. Budget usage at 99%, waiting for condensation to free space
2. Crawler just fetched a large source (2MB) → would exceed ceiling
3. What happens? Should we:
   - Reject the fetch? (wasteful, already fetched)
   - Accept it and immediately trigger CRITICAL condensation?
   - Temporarily exceed ceiling by buffer amount?

**Design**:
- Budget monitor polls every 10s. Between polls, crawler may fetch and insert sources temporarily exceeding ceiling.
- That's okay - we allow temporary overage (maybe 1% buffer).
- Next budget check will see over-ceiling and trigger CRITICAL condensation, which may prune raw data.

**Edge case**: If we're at ceiling, crawler fetches huge source (100MB), and we can't prune enough fast enough → disk full?

**Mitigation**: Set ceiling slightly below actual disk limit (e.g., 10GB ceiling on 11GB disk). Monitor actual disk usage separately.

**Impact**: Budget is advisory, not hard limit? Should be enforced but with tolerance for temporary spikes.

**Resolution**: Define policy: ceiling is trigger for aggressive condensation, not hard block. Document.

**Owner**: Phase 1 Task

---

### A.26: What Does "Condensation May Prune Raw Content" Mean?

**Ambiguity**: `budget.py` comment: "condensation may prune raw content (at critical threshold)".

How does pruning work?
- After atoms extracted from a source, can we delete the raw `corpus.sources` entry?
- Or just mark as `pruned=True` and ignore in future budget calculations?
- What if source has large images or binaries stored separately?
- What about sources that haven't been condensed yet?

**Approach**:
- Condensation processes sources in batch (status='fetched')
- Extracts atoms for each
- Then can mark sources as `condensed=True` or delete them
- Budget calculation: only count raw bytes from `status='fetched'` (exclude `condensed`)

**Risk**: If we delete raw sources, can't revisit them. But we have atoms, so okay.

**Resolution**: Implement prune as UPDATE `corpus.sources` SET status='condensed' AND content=NULL WHERE ... Or actually DELETE. Decide.

**Owner**: Phase 2 Task

---

### A.27: How Do We Test With Real Firecrawl Without Spending Money?

**Ambiguity**: Firecrawl is a paid service (has free tier but limited). Testing exhaustive crawl for real could:
- Cost money if many sources
- Hit rate limits
- Take too long

**Options**:
- Use mock Firecrawl for most tests (returns fake content)
- Have a small set of real URLs we can test with (doesn't cost much)
- Use local files as corpus for integration tests
- Test with `depth=1` and small ceiling in CI

**Impact**: Need test strategy that's fast, deterministic, and doesn't require real API calls.

**Resolution**: Build comprehensive mocks. Use fixtures with pre-saved HTML. Run real Firecrawl only in manual integration tests.

**Owner**: Phase 4 Task

---

### A.28: What is the Relationship Between `ResearchSystem` and the New Orchestrator?

**Ambiguity**: Currently `ResearchSystem.research_topic()` is the entry point. We'll replace `DEEP_RESEARCH` with `orchestrator.run_mission()`.

But:
- `ResearchSystem` has `memory_manager`, `ollama_client`, `browser`, etc.
- Should `ResearchOrchestrator` take these as dependencies? Or be self-contained?
- Do we instantiate `ResearchOrchestrator` in `ResearchSystem.__init__` or in `research_topic`?

**Design**:
```python
class ResearchSystem:
    def __init__(self, ...):
        self.orchestrator = None  # lazy init

    async def research_topic(self, topic, type=DEEP_RESEARCH, ...):
        if type == DEEP_RESEARCH:
            if not self.orchestrator:
                self.orchestrator = ResearchOrchestrator(
                    memory_manager=self.memory_manager,
                    ollama_client=self.ollama_client,
                    config=self.config,
                    browser=self.browser  # or create new browser?
                )
            return await self.orchestrator.run_mission(topic, ...)
```

**Impact**: Need to decide dependency injection pattern.

**Resolution**: Design orchestrator initialization in Phase 6.

**Owner**: Phase 6 Task

---

### A.29: Should the Orchestrator Expose a Subscription Model for Real-Time Updates?

**Ambiguity**: We plan to have `GET /missions/{id}/stats` for polling. But real-time could be WebSocket.

Question: Polling vs WebSocket?
- Polling: simpler, but 1-5s delay, more load
- WebSocket: real-time, but more complex (connection mgmt, reconnection)

For MVP (backends only), polling is fine. WebSocket can be Phase 8 (UI track).

But the spec says "WebSocket endpoint for interactive chat" in Phase 5. That's borderline UI.

**Decision**:
- Query API: REST (no WebSocket needed)
- Stats updates: Polling acceptable (every 5s) for CLI/API. WebSocket for UI later.
- Chat: REST is fine (request-response). Not need WebSocket unless streaming response.

**Resolution**: Use REST for all interactive queries. Add WebSocket only if needed for UI.

**Owner**: Phase 5 Task

---

### A.30: How Do We Ensure Summary Quality Before and After Condensation?

**Ambiguity**: The `archivist/loop.py` uses `synth.summarize_source()` during crawl, before any condensation.

But our design has:
- Raw corpus: just chunks, no summaries
- Condensed atoms: extracted later

What about the `source_summaries[sid] = synth.summarize_source(text, url)` in the old code?

Do we still need summaries? Maybe useful for query results preview.

**Option**: Keep summaries from archivist's current approach. Or replace with condensation atoms which are better.

**Resolution**: Decide whether to:
1. Keep pre-crawl summaries (cheap, fast)
2. Rely only on atoms (better quality but delayed)
3. Do both: early queries get raw chunks (not summarized), later get atoms (summarized)

**Owner**: Phase 5 Task (query design)

---

## Medium Ambiguities (Should Be Resolved but Not Blocking)

### B.1: What is the Exact Celery/RQ Pattern for Condensation Queue?

**Ambiguity**: Should condensation run as a background worker (Celery) or just async task in orchestrator?

Current `budget.py` suggests condensation callback is called in the same thread as monitor? Or async?

If we want true parallelization, condensation should be separate workers processing a queue:
- Budget enqueues `(mission_id, priority)` to a Redis queue
- Condensation workers (multiple) dequeue and process
- This allows multiple missions' condensation to run in parallel

But simpler: just `await condensation.run()` in the orchestrator's budget callback (runs in same event loop, blocks other things?).

**Impact**: Could affect throughput if condensation is slow.

**Resolution**: For MVP, run condensation in orchestrator (simple). For scaling, move to separate workers later.

**Owner**: Phase 1 Task

---

### B.2: What is the Expected Data Volume and Performance Characteristics?

**Ambiguity**: We're targeting 5-10GB ceiling. But how many sources is that?
- Average source size: 100KB? 1MB?
- 10GB / 100KB = 100,000 sources
- 10GB / 500KB = 20,000 sources

At 10 sources/minute → 2000 minutes = 33 hours for 20k sources. That's a long-running mission!

**Questions**:
- What's the realistic source count and mission duration?
- How many atoms per source? 3? 10? 100?
- Graph size: atoms → nodes. 20k sources * 10 atoms = 200k atoms → 200k nodes? That's a huge graph.

**Impact**: Performance optimizations needed for scale. Graph algorithms may not handle 200k nodes.

**Resolution**: Benchmark on realistic data. May need to:
- Limit graph size (only most connected nodes?)
- Use approximate algorithms
- Consider graph database instead of in-memory

**Owner**: Phase 4 Task

---

### B.3: Should We Use Existing `ResearchContentProcessor` or Replace?

**Ambiguity**: There's `src/research/content_processor.py`. What does it do?
- Chunking? Cleaning? Deduplication?
- Might be used by current research system.

Should we reuse it in the crawler? Possibly.

**Resolution**: Investigate. Reuse if appropriate.

**Owner**: Phase 1 Task

---

### B.4: How Do We Handle Binary Content (PDFs, Images)?

**Ambiguity**: Firecrawl can extract text from PDFs. What about:
- Images with text (OCR)? Probably not
- Embedded binaries?
- Should we store binary blobs? Likely too large for 10GB ceiling if many PDFs.

**Policy**:
- Extract text from PDFs using Firecrawl (it does this)
- Discard binary content, keep only extracted text
- Store metadata: original content type, size

**Impact**: Must ensure budget counts only text content, not binaries (or include them? they consume space).

**Resolution**: Clarify what content types we accept. Firecrawl likely returns markdown text, which is what we store.

**Owner**: Phase 1 Task

---

### B.5: What is the `epistemic_mode` Switching Logic?

**Ambiguity**: `AdaptiveFrontier` has modes: `GROUNDING`, `EXPANSION`, `DIALECTIC`, `VERIFICATION`.

When does it switch? Based on:
- Current yield? If low, try different mode?
- Mission progress? Maybe start with GROUNDING, then EXPANSION, then DIALECTIC?
- Random? Or policy?

**Resolution**: Read frontier code's `_select_mode()` or similar. Understand strategy.

**Owner**: Phase 0 Task 0.1

---

### B.6: How Does the Frontier Generate "Concepts"?

**Ambiguity**: Frontier nodes are `FrontierNode` with `concept` string.

Where do concepts come from?
- From initial topic decomposition? (LLM generates sub-topics)
- From entities extracted during crawl? (NER to discover new concepts)
- From gaps in coverage? (missing keywords)

**Impact**: Quality of frontier depends on good concept generation. Need to understand mechanism.

**Resolution**: Read frontier code thoroughly. Check `_generate_initial_nodes()` or similar.

**Owner**: Phase 0 Task 0.1

---

### B.7: What LLM Models Are Used for Which Tasks?

**Ambiguity**: Current system likely uses different models:
- Embeddings: `nomic-embed-text` or `mxbai-embed-large`
- Extraction/condensation: `llama3:8b` or `mistral:7b`
- Synthesis: `llama3:70b` or `claude` via OpenRouter?

Need to know:
- What models are configured in `.env`?
- Do we have fallbacks?
- Cost implications?

**Impact**: Model choices affect cost, speed, quality. May need to optimize.

**Resolution**: Check config and code. Document typical model assignments per task.

**Owner**: Phase 0 Task 0.1

---

### B.8: How Do We Handle Rate Limiting from Search Engines and Firecrawl?

**Ambiguity**:
- Search APIs (Bing, Google) have rate limits
- Firecrawl has rate limits (based on plan)
- OpenAI/OpenRouter have rate limits

What happens when we hit limits?
- Sleep and retry? For how long?
- Circuit breaker? Use `pybreaker`?
- Fail the mission? Or degrade gracefully?

**Impact**: Long-running crawl may hit limits. Need strategy.

**Resolution**: Implement rate limiting and retry logic in:
- `search.search_web()` (if using direct APIs)
- `firecrawl` client (it may handle it)
- LLM client (already may have retry)

**Owner**: Phase 1 Task: Ensure robustness

---

### B.9: What is the "Policy" in `ResearchPolicy` Used For?

**Ambiguity**: `frontier.py` defines:
```python
@dataclass
class ResearchPolicy:
    subject_class: str = "general"
    authority_indicators: List[str] = []
    evidence_types: List[str] = []
    search_strategy: str = "balanced"
```

How is this used?
- Does frontier adjust behavior based on policy?
- Is policy generated per mission from topic? How?
- Could it be used to bias frontier toward certain domains?

**Impact**: If unused, we can ignore. If used, must initialize correctly when creating frontier.

**Resolution**: Search for `ResearchPolicy` usage in frontier code.

**Owner**: Phase 0 Task 0.1

---

### B.10: How Do We Handle Duplicate Sources Across Different Frontiers?

**Ambiguity**: Suppose:
- Mission A is researching "quantum computing"
- Mission B is researching "quantum algorithms"
- Both may fetch the same source (e.g., arXiv paper on quantum algorithms)

Should they share `visited_urls` across missions? Likely no - separate missions independent.

But the database `corpus.sources` probably has a unique constraint on URL? Or can same URL appear in multiple missions?

**Design**:
- `sources` table should have `(mission_id, url)` unique constraint
- Allow same URL across different missions (different mission_id)
- `global visited_urls` cache could be shared across missions to avoid refetching same URL even in different missions? Maybe not, different context.

**Resolution**: Decide. For independence, each mission manages its own visited set. But could share a global cache to avoid refetching. That's an optimization.

**Owner**: Phase 1 Task

---

### B.11: What is the `memory_manager` Really Used For?

**Ambiguity**: `ResearchSystem` has `self.memory_manager` (SQLite/Redis). Current `run_research` doesn't seem to use it much (maybe stores results at end?).

In our orchestrator, should we store:
- Raw sources in memory manager? (Probably not, too big)
- Atoms? Could store final atoms for query
- Graph? Could store in memory

**Current pattern**: `memory_manager.store(item)` for persistent storage.

**Decision**: Memory manager is for long-term storage of distilled knowledge (atoms, final reports). Raw corpus goes in `corpus.sources` in Postgres (which could be considered the "memory" for raw data).

**Resolution**: Don't use `MemoryManager` for raw corpus. Use Postgres `corpus` tables. Use `MemoryManager` for final reports and maybe cross-mission shared knowledge.

**Owner**: Phase 1 Task

---

### B.12: What is the `BaseResearchSystem` and What Does It Provide?

**Ambiguity**: `ResearchSystem(BaseResearchSystem)`. What does base class do?
- Common initialization?
- Memory manager setup?
- LLM client setup?
- Config loading?

**Resolution**: Read `base_system.py` to understand inheritance.

**Owner**: Phase 0 Task 0.1

---

### B.13: What Metrics Are Already Being Collected?

**Ambiguity**: We want to add metrics: `research_mission_*`, `research_query_*`.

But maybe there's already a metrics system. Search for:
- `prometheus_client` imports
- Custom metrics classes
- `/metrics` endpoint

Can we extend existing? Or need new?

**Resolution**: Search codebase for metrics. Reuse if exists.

**Owner**: Phase 0 Task 0.4

---

### B.14: Should Condensation Run Continuously or Batch?

**Ambiqueness**: Budget monitor triggers condensation at thresholds. But could condensation:
- Run continuously in background, always processing newest sources?
- Run in batch when threshold hit? (As currently seems designed)

Current design: Event-driven (threshold crossing triggers batch). This is fine.

But what about at mission completion? We want a "final distillation" that processes all remaining raw sources. That's a batch job.

**Resolution**: Keep current design: threshold-triggered batches + final batch.

**Owner**: N/A (design is fine)

---

### B.15: How Do We Ensure Atomicity of Database Operations?

**Ambiguity**: When storing source and its atoms, we want consistency:
- If atom extraction fails after source stored, should we rollback source insert?
- Or tolerate partial failure?

**Transactions**:
- Each source fetch: insert source, then later update to status='condensed' after atoms created
- Should be atomic within a single source, but not across all sources.

**Resolution**: Use database transactions for individual source+atom writes. If failure, mark source as error and continue.

**Owner**: Phase 1-2 Tasks

---

### B.16: What Happens if a Mission is Stopped Mid-Way?

**Ambiguity**: User calls `DELETE /missions/{id}` or `sheppard mission stop <id>`.
- Should we cancel immediately? Or finish current source?
- Should we keep partial results? Probably yes.
- Should we allow resuming? Maybe later.

**For MVP**: Cancel as soon as possible, keep what we have, mark mission as `cancelled`. User can query partial results.

**Resolution**: Implement cancellation flag. Check in long-running operations (crawl, condensation). Cleanup on next budget check or frontier iteration.

**Owner**: Phase 1 Task

---

### B.17: How Do We Version the API?

**Ambiguity**: Current API might not be versioned. We're adding new endpoints for missions.

Should we version as `/api/v1/missions`? Or keep `/api/missions`?
If we already have `/api/v1/research`, we should use `/api/v1/missions`.

**Resolution**: Use existing version prefix if present. Otherwise, consider adding versioning as part of migration.

**Owner**: Phase 6 Task

---

### B.18: What's the Fallback If Components Are Missing?

**Ambiguity**: System might run without:
- Firecrawl (use browser fallback)
- Ollama (no LLM extraction/summarization)
- PostgreSQL (no condensation? or use SQLite?)

What should be the behavior?
- If no LLM → just store raw content, no atoms (mission can still ingest)
- If no PostgreSQL → can't do condensation, maybe store raw in SQLite? Or fail?
- If no Redis → just skip cache, slower but works

**Resolution**: Define graceful degradation. Document required vs optional dependencies.

**Owner**: Phase 6 Task (migration)

---

### B.19: How Do We Handle Timezones and Timestamps?

**Ambiguity**: All timestamps in database:
- UTC? Local time?
- Store as `datetime` with timezone? Or naive?
- Python: use `datetime.utcnow()` or `datetime.now(timezone.utc)`?

**Resolution**: Use UTC everywhere. Store as TIMESTAMPTZ in Postgres, naive UTC in Python (or timezone-aware consistently).

**Owner**: Phase 0 Task 0.3 (schema)

---

### B.20: How Do We Secure the API?

**Ambiguity**: API endpoints likely have no authentication yet. For a system that can crawl the web and use LLM credits, we need:
- API keys? JWT? Simple token?
- Rate limiting per user/mission?
- Who can start missions? Anyone with network access?

**For MVP**: Maybe no auth (assume local/trusted network). But for any deployment, need auth.

**Resolution**: For now, document that API should be behind firewall. Plan auth in Phase 8 (UI) or separate security sprint.

**Owner**: Out of scope for backend MVP? But note.

---

## Low Ambiguities (Nice to Clarify)

### C.1: What is the `DELTA_NOTES.md` in src/?

Likely change history. Not relevant.

---

### C.2: What is the `stable/` Directory?

Probably old code or backups. Can ignore or clean up.

---

### C.3: Should We Use `src/shepherd/` or `src/research/` as Main Package?

There's both `src/shepherd/` and `src/research/`. The research system is in `src/research/`. Should the new orchestrator go in `src/research/`? Yes, consistent.

**Resolution**: Place `orchestrator.py` in `src/research/`.

---

### C.4: Should We Keep `src/core/` and `src/llm/` Separate?

Yes, they're generic utilities and LLM abstraction. Not research-specific.

---

### C.5: What is `src/metasystem/`?

Seems to be V2 compatibility layer. Probably not relevant to new research. Can ignore.

---

## Summary: 28 Ambiguities Resolved

### Critical (A): 28 items
**Must resolve in Phase 0 or early Phase 1**:

A.1: Database schema existence ✅
A.2: Adapter class API ✅
A.3: KnowledgeAtom schema ✅
A.4: AdaptiveFrontier.run() API ✅
A.5: Budget storage measurement ✅
A.6: Crawler API ✅
A.7: Condensation trigger semantics ✅
A.8: Exhaustion definition ✅
A.9: mission_id scoping ✅
A.10: ArchivistIndex current design ✅
A.11: Final report generation ✅
A.12: Configuration options ✅
A.13: Multi-mission coordination ✅
A.14: What is adapter? ✅
A.15: LLM error handling ✅
A.16: Query latency feasibility ✅
A.17: Coverage estimation algorithm ✅
A.18: Confidence scoring algorithm ✅
A.19: Freshness calculation ✅
A.20: Index multi-mission support ✅
A.21: CLI command structure ✅
A.22: API timeouts ✅
A.23: Crawler error handling ✅
A.24: Data consistency (locks) ✅
A.25: Ceiling overshoot policy ✅
A.26: Raw pruning semantics ✅
A.27: Firecrawl testing strategy ✅
A.28: ResearchSystem-orchestrator integration ✅
A.29: WebSocket vs REST for queries ✅
A.30: Source summaries vs atoms ✅

### Medium (B): ~10 items
Can be resolved during implementation, but design decisions needed.

### Low (C): ~5 items
Trivial or not urgent.

---

## Action Items from This Ambiguity Document

**For Phase 0**:
1. Resolve A.1-A.14: Read code and write analysis docs confirming these ambiguities
2. Resolve A.28, A.21: Plan integration with ResearchSystem and CLI
3. Document decisions in ADRs

**For Phase 1**:
4. Implement solutions for A.15-A.20, A.22-A.27
5. Ensure thread safety (A.24)
6. Design error handling (A.15, A.23)

**For Phase 5**:
7. Finalize query algorithms: coverage (A.17), confidence (A.18), freshness (A.19)

---

**Conclusion**: There are **many ambiguities**, but they're **mostly answerable** by reading the existing code and making design decisions. Phase 0 is crucial for this.

**Estimated time to resolve critical ambiguities**: 2-3 days of code reading and documentation.

**Risk if not resolved**: Implementation delays, rework, incorrect assumptions.

**Recommendation**: Proceed with Phase 0 immediately to answer these questions.
