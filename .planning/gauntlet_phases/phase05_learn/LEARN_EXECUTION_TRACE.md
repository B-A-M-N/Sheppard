# Phase 05 — `/learn` Execution Trace

**Date**: 2026-03-27
**Auditor**: Claude Code

Complete end-to-end trace of a `/learn` request from command parsing to atom indexing.

---

## 1. Command Parsing & Validation

| Step | File:Line | Action | Data Produced |
|------|-----------|--------|---------------|
| 1.1 | `src/core/commands.py:72` | `_handle_learn(*args)` invoked | `args = ["quantum computing", "--ceiling=10", "--academic"]` |
| 1.2 | `commands.py:76` | Join non-option args → `topic = "quantum computing"` | String |
| 1.3 | `commands.py:77-81` | Parse options: `ceiling=10.0`, `academic=True` | Floats, bools |
| 1.4 | `commands.py:83` | **Call** `system_manager.learn(topic_name=topic, query=topic, ceiling_gb=10, academic_only=True)` | Initiates mission |

---

## 2. Mission Creation & Database Setup

| Step | File:Line | Action | DB Table / Structure |
|------|-----------|--------|----------------------|
| 2.1 | `src/core/system.py:169` | `self._check_initialized()` — ensures system booted | — |
| 2.2 | `system.py:174` | Generate `mission_id = uuid.uuid4()` (canonical identifier) | UUID string |
| 2.3 | `system.py:177-187` | Create `DomainProfile` object | `profile_id = f"profile_{mission_id[:8]}"` |
| 2.4 | `system.py:187` | **Call** `self.adapter.upsert_domain_profile(profile.to_pg_row())` | `authority.domain_profiles` |
| 2.5 | `system.py:190-198` | Create `ResearchMission` object with `mission_id`, `topic_id=mission_id` | `mission_id`, `topic_id` unified |
| 2.6 | `system.py:198` | **Call** `self.adapter.create_mission(mission.to_pg_row())` | `mission.research_missions` row inserted |
| 2.7 | `system.py:201-205` | Register with BudgetMonitor: `self.budget.register_topic(topic_id=mission_id, topic_name=topic_name, ceiling_gb=10)` | In-memory `TopicBudget` in `BudgetMonitor._budgets[mission_id]` |

---

## 3. Background Task Launch

| Step | File:Line | Action | Result |
|------|-----------|--------|--------|
| 3.1 | `system.py:207` | Set `self.crawler.academic_only = True` | Configures crawler filter |
| 3.2 | `system.py:209` | **Create async task:** `asyncio.create_task(self._crawl_and_store(mission_id, topic_name, query))` | Background coroutine started |
| 3.3 | `system.py:210` | Store task ref: `self._crawl_tasks[mission_id] = task` | Trackable |
| 3.4 | `system.py:212` | Log mission start | `"Learning mission 'quantum computing' started (Mission ID: {mission_id})"` |
| 3.5 | `system.py:213` | **Return** `mission_id` to caller | Command prints Panel with mission_id |

---

## 4. Frontier Execution (Topic Decomposition → Discovery)

**Entry**: `SystemManager._crawl_and_store(mission_id, topic_name, query)`

| Step | File:Line | Action | Notes |
|------|-----------|--------|-------|
| 4.1 | `system.py:362` | Create `frontier = AdaptiveFrontier(self, mission_id, topic_name)` | Constructor: `frontier.py:65-74` |
| 4.2 | `system.py:363` | Store `self.active_frontiers[mission_id] = frontier` | Runtime tracking |
| 4.3 | `system.py:364` | **Call** `total_ingested = await frontier.run()` | Main loop |
| 4.4 | `frontier.py:78` | `await self._load_checkpoint()` | Load persisted frontier nodes from DB (if any) |
| 4.5 | `frontier.py:81` | `await self._frame_research_policy()` | Generate research policy (subject_class, authority indicators, evidence types) |
| 4.6 | `frontier.py:84-134` | **Main acquisition loop**:<br>• Budget check (line 85-88)<br>• Node selection `_select_next_action()` (line 91)<br>• Query engineering `_engineer_queries()` (line 101)<br>• For each query: `crawler.discover_and_enqueue()` (line 106)<br>• Checkpoint `_save_node()` (line 126)<br>• Sleep throttle (line 132) | Repeats until budget exhausted or frontier saturated |

---

### 4.1 Discovery & Enqueue Details

**`crawler.discover_and_enqueue(mission_id, topic_name, query, ...)`**

| Step | File:Line | Action | Output |
|------|-----------|--------|--------|
| 4.1.1 | `crawler.py:294-298` | Loop pages 1–5: `await self._search(query, pageno=page)` | Searches SearXNG for URLs |
| 4.1.2 | `crawler.py:300-318` | For each new URL:<br>• Skip if in `visited_urls`<br>• Determine lane (fast/slow)<br>• Build payload with `topic_id`, `mission_id`, `url`, `url_hash`, `lane`, `priority`<br>• **Call** `system_manager.adapter.enqueue_job("queue:scraping", payload)`<br>• Add to `visited_urls` | Payload enqueued to Redis queue `queue:scraping` |
| 4.1.3 | `crawler.py:323-329` | Break after first page with new URLs, else continue deeper | Returns `total_enqueued` count |

**Queue handoff**: URLs now sit in Redis list `queue:scraping` awaiting vampire workers.

---

## 5. Vampire Consumption (URL Fetch → Ingestion)

**Background workers**: `SystemManager._vampire_loop(vampire_id)` — 8 parallel tasks

| Step | File:Line | Action | Details |
|------|-----------|--------|---------|
| 5.1 | `system.py:310` | `job = await self.adapter.dequeue_job("queue:scraping", timeout_s=10)` | Blocks up to 10s waiting for job |
| 5.2 | `system.py:313-317` | Extract `url`, `mission_id` from job; skip if missing mission_id | Validation |
| 5.3 | `system.py:320-323` | **Dedupe check:** `existing = await self.adapter.get_source_by_url_hash(url_hash)`; if `status=='fetched'` skip | Avoid re-fetching |
| 5.4 | `system.py:326` | **Budget check:** `if not self.budget.can_crawl(mission_id):` → re-queue and sleep 30s | Backpressure |
| 5.5 | `system.py:332` | `result = await self.crawler._scrape_with_retry(url)` | Firecrawl scrape with 3 retries, exponential backoff |
| 5.6 | `system.py:335-345` | On success: build `source_meta` dict and **call** `await self.adapter.ingest_source(source_meta, result.markdown)` | Atomic ingestion |

---

## 6. Ingestion Pipeline (Atomic V3 Write)

**`SheppardStorageAdapter.ingest_source(source, text_content)`**

| Step | File:Line | Action | DB / Side-Effect |
|------|-----------|--------|------------------|
| 6.1 | `storage_adapter.py:772-777` | Create `text_refs` row (the blob) | `corpus.text_refs(blob_id, inline_text, byte_size)` |
| 6.2 | `storage_adapter.py:780-802` | Build `pg_row` for source with `status="fetched"`<br>• `source_id` (generate if absent)<br>• `mission_id`, `topic_id`<br>• `url`, `normalized_url`, `content_hash`<br>• `canonical_text_ref = blob_id`<br>**Call** `self.pg.upsert_row("corpus.sources", ["mission_id", "normalized_url_hash"], pg_row)` | `corpus.sources` row upserted |
| 6.3 | `storage_adapter.py:807-826` | Chunk the text:<br>• `chunk_text(text_content)` → list of strings<br>• For each chunk: create `chunk_row` with `chunk_id`, `source_id`, `mission_id`, `topic_id`, `chunk_index`, `chunk_hash`, `inline_text`, `text_ref` | Array of chunk dicts |
| 6.4 | `storage_adapter.py:828` | **Call** `await self.create_chunks(chunk_rows)` → inserts all chunks | `corpus.chunks` rows inserted |
| 6.5 | `storage_adapter.py:831` | **Cache** source in Redis: `self.redis_cache.cache_hot_object("source", source_id, pg_row, ttl_s=3600)` | Hot cache |
| 6.6 | `storage_adapter.py:833` | **Return** `source_id` | Vampire logs "Consumed" |

**Summary**: After ingestion completes:
- `corpus.sources` row with `status='fetched'`
- `corpus.chunks` rows linked to source
- Text blob stored in `corpus.text_refs`
- Source is now eligible for distillation (budget monitor will pick it up)

---

## 7. Distillation Trigger & Atom Extraction

**Trigger mechanism**: Budget monitor fires when storage thresholds crossed.

| Step | File:Line | Action |
|------|-----------|--------|
| 7.1 | `system.py:126` (initialize) | `BudgetMonitor` instantiated with `condensation_callback=self._condensation_callback` |
| 7.2 | `crawler.py:202` (or vampire via callback injection) | After each page, `on_bytes_crawled(topic_id, raw_bytes)` invoked |
| 7.3 | `budget.py:126-142` | `record_bytes()` updates `raw_bytes`, calls `_check_thresholds()` |
| 7.4 | `budget.py:170-208` | `_check_thresholds()` evaluates `usage_ratio`; if threshold crossed and not already condensing, sets `condensation_running=True` and fires callback |
| 7.5 | `budget.py:204-208` | `asyncio.create_task(self.condensation_callback(topic_id, priority))` |
| 7.6 | `system.py:430` | `_condensation_callback(topic_id, priority)` → `await self.condenser.run(topic_id, priority)` |

---

### 7.1 Distillation Pipeline (`DistillationPipeline.run`)

| Step | File:Line | Action |
|------|-----------|--------|
| 7.1.1 | `pipeline.py:43` | `run(mission_id, priority)` — `topic_id = mission_id` bridge |
| 7.1.2 | `pipeline.py:49-54` | Fetch batch of sources: `self.adapter.pg.fetch_many("corpus.sources", where={"mission_id": mission_id, "status": "fetched"}, limit=5)` |
| 7.1.3 | `pipeline.py:60-128` | For each source:<br>• Get `text_ref` blob (line 68)<br>• Extract atoms via `extract_technical_atoms(ollama, content, topic_name)` (line 83)<br>• Build `KnowledgeAtom` object with `atom_id`, `statement`, `confidence`, etc. (line 92-107)<br>• Build `evidence_rows` with `source_id` (line 111-115)<br>• **Call** `await self.adapter.store_atom_with_evidence(atom_row, evidence_rows)` (line 116)<br>• Mark source `status='condensed'` (line 121-125) |
| 7.1.4 | `pipeline.py:130-142` | After batch:<br>• If HIGH/CRITICAL priority, call `resolve_contradictions()` (pending)<br>• Call `budget.record_condensation_result()` to free raw bytes |

---

## 8. Atomic Atom + Evidence Storage

**`SheppardStorageAdapter.store_atom_with_evidence(atom, evidence_rows)`**

| Step | File:Line | Action |
|------|-----------|--------|
| 8.1 | `storage_adapter.py:610-611` | Validate `evidence_rows` non-empty; raise if empty (V3 integrity invariant) |
| 8.2 | `storage_adapter.py:616-660` | **Single transaction**:<br>• INSERT `knowledge.knowledge_atoms` (ON CONFLICT atom_id DO UPDATE) (line 626-632)<br>• INSERT `knowledge.atom_evidence` (ON CONFLICT DO NOTHING/UPDATE) (line 647-656)<br>• `async with conn.transaction()` ensures atomicity |
| 8.3 | `storage_adapter.py:659-660` | After commit:<br>• `await self.index_atom(atom)` → indexes in Chroma<br>• `await self.redis_cache.cache_hot_object("atom", atom_id, atom, ttl_s=3600)` |

**Result**:
- `knowledge.knowledge_atoms` row present
- One or more `knowledge.atom_evidence` rows linking atom → source + chunk
- Atom indexed in Chroma collection `knowledge_atoms` for retrieval
- Atom cached in Redis

---

## 9. State Machine Summary

```
INPUT_RECEIVED
    ↓ (command parsed)
MISSION_CREATED (research_missions row inserted)
    ↓ (background task launched)
TOPIC_DECOMPOSED (frontier policy generated, nodes initialized)
    ↓ (query engineering)
URL_DISCOVERED (search returns URLs)
    ↓ (enqueue)
URL_QUEUED (Redis queue:scraping)
    ↓ (vampire dequeue)
URL_FETCHED (crawl successful)
    ↓ (ingest_source)
CONTENT_NORMALIZED (chunks created, text_ref stored)
    ↓ (budget threshold crossed)
ATOMS_EXTRACTED (condenser distills atoms from fetched sources)
    ↓ (store_atom_with_evidence)
ATOMS_STORED (knowledge_atoms + atom_evidence rows)
    ↓ (index_atom)
INDEX_UPDATED (Chroma index refreshed)
```

**Notes**:
- States are **implicit**: represented by DB row status fields and in-memory flags
- Frontier node states (`underexplored`, `active`, `saturated`) are in-memory only
- Source progression: `fetched` → `condensed` (status field in `corpus.sources`)
- Mission status: stored in `mission.research_missions.status` (via `update_mission_status`)

---

## 10. Queue Handoff & Async Boundaries

| Boundary | Producer | Queue | Consumer | Concurrency |
|----------|----------|-------|----------|-------------|
| Discovery → Scraping | Frontier (`crawler.discover_and_enqueue`) | Redis `queue:scraping` | Vampire `_vampire_loop` (x8 tasks) | Multiple vampires compete via `dequeue_job` |
| — | Each vampire runs infinite loop | — | Scrapes, ingests | 8 concurrent consumers |
| Ingestion → Distillation | `ingest_source` (status='fetched') | Postgres `corpus.sources` rows | Budget-triggered `condenser.run()` | Sequential batch (semaphore=2) |

**Handoff semantics**:
- Frontier pushes URLs to Redis; returns immediately (fire-and-forget)
- Vampires block on `dequeue_job` with 10s timeout; process one job at a time
- No explicit acknowledgment; dedupe via `url_hash` check before scrape
- Distillation triggered asynchronously by budget monitor loop; may overlap with ongoing crawling

---

## 11. Deduplication & Retry Policies

### Deduplication
- **URL level**: `visited_urls` set in frontier (in-memory, lost on restart) + `url_hash` check in vampire (`get_source_by_url_hash`)
- **Content level**: `corpus.sources` unique constraint `(mission_id, normalized_url_hash)` prevents duplicate source ingestion
- **Atom level**: `knowledge_atoms` primary key `atom_id` is UUID; no content-hash dedup (potential duplicate atoms)

### Retries
- **Scrape retry**: `_scrape_with_retry` (crawler.py:335-358) — 3 attempts with exponential backoff (`retry_base_delay * 2^attempt`)
- **Queue dequeue**: vampire retries every 10s on timeout/crash (infinite loop)
- **Distillation errors**: caught per-source; failed sources marked `status='error'`, batch continues

---

## 12. Critical Code References (Index)

| Component | File:Key Lines |
|-----------|----------------|
| Command handler | `src/core/commands.py:72-84` |
| Mission creation | `src/core/system.py:161-213` |
| Frontier main loop | `src/research/acquisition/frontier.py:76-134` |
| Discovery + enqueue | `src/research/acquisition/crawler.py:280-331` |
| Vampire worker | `src/core/system.py:305-353` |
| Ingestion | `src/memory/storage_adapter.py:767-833` |
| Chunking | `src/memory/storage_adapter.py:807-828` |
| Distillation trigger | `src/research/acquisition/budget.py:170-208` |
| Distillation run | `src/research/condensation/pipeline.py:43-142` |
| Atom + evidence storage | `src/memory/storage_adapter.py:604-660` |
| Indexing | `src/memory/storage_adapter.py:914-917` |

---

**Status**: Trace complete. Ready for state machine validation and verification.
