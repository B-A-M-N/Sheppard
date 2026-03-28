# Sheppard V3 - System Architecture

## 1. High-Level Architecture Overview

Sheppard is a **distributed research automation system** that implements a **hybrid V2/V3 architecture** in transition. The V3 "Universal Domain Authority Foundry" is designed around a **Triad Memory Stack** but coexists with legacy V2 components.

### Architectural Vision (V3)

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          The Sheppard V3 Triad                           │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌─────────────────┐       ┌─────────────────┐       ┌─────────────┐ │
│  │   Postgres      │◄─────►│    ChromaDB     │◄─────►│    Redis     │ │
│  │   (The Truth)   │       │   (Proximity)   │       │   (Motion)  │ │
│  └─────────────────┘       └─────────────────┘       └─────────────┘ │
│         │  ▲                       │  ▲                      │  ▲      │
│         │  │ writes                │  │ writes               │  │      │
│         ▼  │                      ▼  │                      ▼  │      │
│  ┌──────────────┐         ┌──────────────┐         ┌───────────────┐│
│  │  Knowledge   │         │  Semantic    │         │  Job Queue    ││
│  │  Base        │         │  Index       │         │  Locks        ││
│  │  (Sources,   │         │  (Vectors)    │         │  Hot Cache    ││
│  │   Atoms,     │         │              │         │               ││
│  │   Authority) │         │              │         │               ││
│  └──────────────┘         └──────────────┘         └───────────────┘│
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
                              ▲
                              │ orchestrates
                              │
┌─────────────────────────────────────────────────────────────────────────┐
│                    System Manager (system.py)                          │
├─────────────────────────────────────────────────────────────────────────┤
│  BudgetMonitor │ Crawler │ Condenser │ Retriever │ Synthesis │ LLM     │
└─────────────────────────────────────────────────────────────────────────┘
```

### Actual Implementation: V2/V3 Hybrid

```
┌─────────────────────────────────────────────────────────────────────────┐
│                                                                         │
│  ┌────────────────────────────────────────────────────────────┐        │
│  │                  V2 Legacy MemoryManager                   │        │
│  │  - PostgreSQL (semantic_memory, localhost)                 │        │
│  │  - ChromaDB (knowledge_atoms, thematic_syntheses, ...)    │        │
│  │  - Redis (ephemeral contextual episodic semantic abstracted)│       │
│  └────────────────────────────────────────────────────────────┘        │
│                           │                                            │
│                           │ read (via HybridRetriever)                │
│                           ▼                                            │
│  ┌────────────────────────────────────────────────────────────┐        │
│  │                   Chat App (chat.py)                       │        │
│  │  - User input → memory.search() → LLM response            │        │
│  └────────────────────────────────────────────────────────────┘        │
│                                                                         │
│  ┌────────────────────────────────────────────────────────────┐        │
│  │                 V3 StorageAdapter (Triad)                 │        │
│  │  • Postgres (10.9.66.198) - config, mission, corpus,      │        │
│  │    knowledge, authority, application schemas               │        │
│  │  • ChromaDB (corpus_chunks, knowledge_atoms, ...)         │        │
│  │  • Redis (queue:scraping, locks, active state, cache)     │        │
│  └────────────────────────────────────────────────────────────┘        │
│                           ▲                                            │
│                           │ write                                      │
│  ┌────────────────────────────────────────────────────────────┐        │
│  │              Research Pipeline Components                 │        │
│  │  Frontier → Crawler → Vampires → Condenser → Synthesis    │        │
│  └────────────────────────────────────────────────────────────┘        │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

**Key Problem:** V2 and V3 are separate data silos. V3 writes to its databases, but V2 retriever queries only V2. Chat uses V2 → V3 research output is invisible.

---

## 2. Core System Components

### 2.1 SystemManager (`src/core/system.py`)

**Role:** Unified orchestrator for all V2/V3 subsystems

**Responsibilities:**
- Initialize all components (V2 + V3)
- Manage research missions (`learn()`)
- Coordinate vampire workers (8 concurrent)
- Provide chat and query interfaces
- Monitor budget and trigger condensation
- Clean shutdown

**Initialization Sequence:**
```python
async def initialize():
    # 0. V3 Triad adapters
    pg_pool = asyncpg.create_pool(DB_URLS['semantic_memory'])
    redis_client = redis.Redis.from_url("redis://localhost:6379")
    chroma_client = chromadb.PersistentClient(path)
    adapter = SheppardStorageAdapter(pg, redis_runtime, redis_cache, redis_queue, chroma)

    # 1. V2 Memory (legacy)
    memory = MemoryManager()
    await memory.initialize()

    # 2. LLM Client
    ollama = OllamaClient(model_router)
    await ollama.initialize()

    # 3. Budget monitor
    budget = BudgetMonitor(config, condensation_callback)

    # 4. Condensation pipeline
    condenser = DistillationPipeline(ollama, memory, budget, adapter)

    # 5. Crawler
    crawler = FirecrawlLocalClient(config, on_bytes_crawled=budget.record_bytes)
    await crawler.initialize()

    # 6. Retriever & Synthesis
    retriever = HybridRetriever(memory_manager=memory)  # Uses V2 memory!
    assembler = EvidenceAssembler(ollama, memory, retriever, adapter)
    synthesis_service = SynthesisService(ollama, memory, assembler, adapter)

    # 7. Background tasks
    monitor_task = asyncio.create_task(budget.run_monitor_loop())
    vampire_tasks = [asyncio.create_task(_vampire_loop(i)) for i in range(8)]

    _initialized = True
```

**State:**
- `self.memory` (V2)
- `self.adapter` (V3)
- `self.ollama`
- `self.budget`
- `self.crawler`
- `self.condenser`
- `self.retriever` (V2)
- `self.synthesis_service`
- `_crawl_tasks: Dict[topic_id, Task]`
- `active_frontiers: Dict[topic_id, AdaptiveFrontier]`

---

### 2.2 ChatApp (`src/core/chat.py`)

**Role:** Main user interface for chat interaction

**Flow:**
```python
async def process_input(user_input):
    # 1. Retrieve memories
    relevant_memories = await system_manager.memory.search(user_input, limit=5)

    # 2. Build context
    memory_context = "\n".join([f"- {m.content}" for m in relevant_memories])
    messages = [{"role": "system", "content": f"Use context: {memory_context}"}]
    messages += conversation_history
    messages.append({"role": "user", "content": user_input})

    # 3. Stream LLM response
    async for token in system_manager.chat(messages=messages):
        yield ChatResponse(content=token)

    # 4. Store interaction
    await system_manager.memory.store(interaction)
    await _extract_and_store_preferences(user_input)
```

**Key Methods:**
- `initialize(system_manager)` - attach system
- `process_input(user_input)` - main async generator
- `perform_research(topic)` - V2 research (uses `system_manager.query()`)
- `get_system_status()` - dashboard info

**Note:** Chat uses V2 `system_manager.memory` exclusively. V3 atoms never retrieved.

---

### 2.3 AdaptiveFrontier (`src/research/acquisition/frontier.py`)

**Role:** Intelligent research node generation and management

**Responsibilities:**
- Load/save checkpoint from DB (V3 `mission_nodes`)
- Generate domain-specific research policy (via LLM)
- Create 15 initial research nodes
- Select next node + epistemic mode for exploration
- Engineer queries for discovered nodes
- Respawn/fork nodes when yield is high
- Apply human nudges (steering)

**Main Loop (`run()`):**
```python
while True:
    if budget.usage_ratio >= 1.0:
        break  # Storage ceiling reached

    node, mode = _select_next_action()  # Find underexplored node + unused mode
    queries = await _engineer_queries(node, mode)  # LLM generates 3-4 queries

    for q in queries:
        enqueued = await crawler.discover_and_enqueue(
            topic_id, topic_name, query=q, mission_id=mission_id
        )
        total_ingested += enqued

    if round_yield == 0:
        await asyncio.sleep(10)  # thermal recovery

    node.yield_history.append(round_yield)
    node.exhausted_modes.add(mode)
    await _save_node(node)  # checkpoint

    if round_yield >= 5:
        await _respawn_nodes(node)  # generate sub-topics

    await asyncio.sleep(5)
```

**Epistemic Modes:**
- `GROUNDING` - Facts, definitions
- `VERIFICATION` - Artifacts, proof
- `DIALECTIC` - Conflicts, disputes
- `EXPANSION` - Adjacent fields

**Checkpointing:**
- Nodes saved to V3 `mission.mission_nodes`
- Visited URLs saved to V2 `frontier_nodes` (legacy fallback)
- Domain profile saved to V3 `config.domain_profiles`

**Policy Content:**
```json
{
  "policy": {
    "class": "scientific|technical|investigative|...",
    "authority": ["edu domains", "gov", "arxiv", ...],
    "evidence": ["empirical data", "peer-reviewed", ...]
  },
  "nodes": ["node1", "node2", ..., "node15"]
}
```

---

### 2.4 FirecrawlLocalClient (`src/research/acquisition/crawler.py`)

**Role:** Distributed URL scraping with dual-lane metabolism

**Features:**
- URL deduplication via checksums
- Fast lane (main PC) vs slow lane (auxiliary nodes) routing
- Academic whitelist filtering for scholarly content
- Rate limit awareness
- Retry logic with exponential backoff
- Metrics: `queue_size`, `total_scraped`

**Dual-Lane Routing (`_route_url`):**
```python
def _route_url(url):
    if url.endswith(".pdf"): return "slow"
    generic_domains = ["wikipedia.org", "arxiv.org", "stackoverflow.com", ...]
    if any(d in domain for d in generic_domains):
        return "slow"  # Offload to Lazy Scout
    return "fast"  # Main PC handles
```

**Discovery (`discover_and_enqueue`):**
1. Build query from topic + node concept
2. Call SearXNG for each configured endpoint (parallel)
3. Filter URLs (academic whitelist if enabled, junk filter)
4. Check `visited_urls` to avoid duplicates
5. Create job payload: `{url, topic_id, mission_id, url_hash}`
6. `adapter.enqueue_job("queue:scraping", job)` - push to Redis queue
7. Return count of enqueued URLs

**Scraping (`_scrape_with_retry`):**
- Retries (default 3) with exponential delays
- Calls Firecrawl `/v1/scrape`
- Returns `CrawlResult` or None

---

### 2.5 Vampire Workers (`_vampire_loop` in `system.py`)

**Role:** Consume URLs from Redis queue and ingest sources

**Architecture:** 8 concurrent tasks running on main PC (`num_vampires = 8`)

**Loop:**
```python
while True:
    job = await adapter.dequeue_job("queue:scraping", timeout_s=10)
    if not job: continue

    url = job['url']
    topic_id = job['topic_id']
    mission_id = job.get('mission_id') or topic_id

    # Dedup check: already fetched?
    existing = await adapter.get_source_by_url_hash(job['url_hash'])
    if existing and existing['status'] == 'fetched':
        continue

    # Budget check
    if not budget.can_crawl(topic_id):
        await adapter.enqueue_job("queue:scraping", job)  # re-queue
        await asyncio.sleep(30)
        continue

    # Scrape
    result = await crawler._scrape_with_retry(url)
    if result:
        source_meta = {url, checksum, title, source_type, ...}
        await adapter.ingest_source(source_meta, result.markdown)  # V3
        await memory.store_source(  # V2 legacy
            topic_id=topic_id, url=url, content=result.markdown, ...
        )
```

**Note:** Writes to BOTH V3 and V2 → data divergence risk if one fails and other succeeds.

---

### 2.6 DistillationPipeline (`src/research/condensation/pipeline.py`)

**Role:** Atomic distillation of raw sources into Knowledge Atoms

**Architecture:**
- Runs as background callback triggered by budget monitor
- Semaphore-limited concurrency (2 simultaneous distillations)
- Sequential batch processing (5 sources at a time)

**Workflow (`run(mission_id, priority)`):**
1. Fetch sources: `adapter.pg.fetch_many("corpus.sources", where={"mission_id": status="fetched"}, limit=5)`
2. For each source:
   - Get `canonical_text_ref` → `adapter.get_text_ref(blob_id)` to retrieve content
   - Call `extract_technical_atoms(ollama, content, topic_name)` → JSON validation
   - For each atom:
     - Create `KnowledgeAtom` with `AtomLineage(mission_id, extraction_mode="atomic_distillation")`
     - `adapter.upsert_atom(atom)` → V3 `knowledge.knowledge_atoms` + Chroma index
     - `adapter.bind_atom_evidence(atom_id, [{source_id, evidence_strength, supports_statement}])`
   - Mark source status = "condensed"
3. Log summary
4. If priority HIGH/CRITICAL: `await resolve_contradictions(mission_id)` (STUB)

**Critical Issues:**
- `_cluster_sources()` returns ONE batch cluster (no clustering)
- `resolve_contradictions()` is stub (TODO: V3 migration)
- `consolidate_atoms()` is stub (TODO: V3 migration)

**Atom Extraction (`extract_technical_atoms()`):**
- Prompt: "Analyze this technical document... extract Knowledge Atoms"
- Schema: `{"atoms": [{"type": "claim|evidence|event|procedure|contradiction", "content": "...", "confidence": 0.9}]}`
- Uses `JSONValidator` with iterative repair (max 2 attempts)
- Filters out fallback atoms

---

### 2.7 HybridRetriever (`src/research/reasoning/retriever.py`)

**Role:** 4-stage retrieval for RAG context assembly

**Stages:**

1. **Lexical Prefilter** (`_stage1_lexical`):
   - Extracts exact terms (tech names, error codes, libraries) via regex
   - `memory.lexical_search_atoms(terms)` → V2 PostgreSQL full-text search
   - Catches exact matches that vector search might miss

2. **Semantic Retrieval** (`_stage2_semantic`):
   - Queries ChromaDB collections: `knowledge_atoms` (Level B), `thematic_syntheses` (C), `advisory_briefs` (D)
   - `memory.chroma_query(collection, query_text, n_results=8, where={"topic_id": ...})`
   - Expects V2 metadata format (source_url, captured_at, tech_density, citation_key)

3. **Structural Retrieval** (`_stage3_structural`):
   - Concept graph traversal (`find_concepts_by_text` + `traverse_concept_graph`) - V2 only
   - Contradiction retrieval (`search_contradictions`) - V2 only
   - Citation lookup (`search_citations`) - V2 only
   - Project artifact search if `project_filter` set

4. **Re-ranking** (`_stage4_rerank`):
   - Composite score = `relevance * 0.35 + trust * 0.20 + recency_factor * 0.10 + tech_density * 0.15 + project_proximity * 0.20`
   - Recency factor: `max(0.2, 1.0 - (recency_days / 365))`
   - `tech_density` pulled from metadata (defaults 0.5 if missing)

**Role-Based Assembly** (`_assemble_by_role`):
- Fills slots: definitions (max 3), evidence (max 5), contradictions (max 2), project artifacts (max 2), unresolved (max 2)
- Selects top-N per role by composite score

**Critical Issue:** `lexical_search_atoms`, concept graph, contradictions all query V2 Postgres tables. V3 atoms invisible to these stages. Only semantic stage may find V3 atoms but with degraded metadata (missing source_url, captured_at, tech_density → defaults lower scores).

---

### 2.8 EvidenceAssembler (`src/research/reasoning/assembler.py`)

**Role:** Build evidence packets for synthesis engine

**Tasks:**
- Generate section plan for master brief (LLM: DECOMPOSITION)
- For each section: gather atoms via `HybridRetriever.retrieve()`
- Deduplicate atoms by ID
- If section targets contradictions: also fetch via `memory.get_unresolved_contradictions(topic_id)` (V2 query)
- Build `EvidencePacket` with atoms and contradictions

**Contradiction Handling:**
```python
if "contradictions" in section.target_evidence_roles:
    conflicts = await memory.get_unresolved_contradictions(topic_id, limit=5)
    for c in conflicts:
        packet.contradictions.append({
            "description": c['description'],
            "claim_a": c['atom_a_content'],
            "claim_b": c['atom_b_content']
        })
```

**Problem:** `get_unresolved_contradictions` uses V2 schema (JOIN with `knowledge_atoms` on `id`). V3 atom IDs are TEXT not UUID, and V3 contradictions stored in `knowledge.contradiction_sets` with members table. Query will fail or return nothing for V3.

---

### 2.9 SynthesisService (`src/research/reasoning/synthesis_service.py`)

**Role:** Orchestrate Tier 4 Master Brief generation

**Workflow:**
1. `generate_master_brief(topic_id)`
2. Generate section plan via `assembler.generate_section_plan(topic_name)`
3. For each section:
   - `build_evidence_packet(topic_id, topic_name, section)` → uses HybridRetriever
   - `archivist.write_section(packet, previous_context)` → LLM generates prose
   - `adapter.store_synthesis_section()` to database
   - Accumulate into `full_report`
4. Store `SynthesisArtifact` in V3 `authority.synthesis_artifacts`
5. Return report

**Note:** Uses `ArchivistSynthAdapter` (from `research/archivist/synth_adapter.py`) which has its own LLM client and prompts.

---

## 3. Data Flow: Research Mission End-to-End

```
User: /learn quantum computing
  │
  ├─► SystemManager.learn()
  │   ├─► V2: create_topic(name, desc)
  │   ├─► V3: upsert_domain_profile(DomainProfile)
  │   ├─► V3: create_mission(ResearchMission)
  │   └─► launch _crawl_and_store() task
  │
  └─► returns topic_id

_crawl_and_store() creates AdaptiveFrontier
  │
  ├─► frontier._load_checkpoint()
  │   ├─► V3: list_mission_nodes(mission_id)
  │   └─► V2: get_frontier_nodes(topic_id) [fallback]
  │
  ├─► frontier._frame_research_policy()
  │   ├─► LLM: generate 15 nodes + policy
  │   └─► V3: upsert_domain_profile()
  │
  └─► frontier.run() loop:
      │
      ├─► For each node+mode:
      │   ├─► _engineer_queries() → LLM generates 3 queries
      │   ├─► crawler.discover_and_enqueue(query)
      │   │   ├─► SearXNG search (parallel)
      │   │   ├─► Filter URLs
      │   │   └─► adapter.enqueue_job("queue:scraping", payload)
      │   └─► Queue size increases
      │
      └─► Vampire workers (parallel):
          ├─► adapter.dequeue_job("queue:scraping")
          ├─► crawler._scrape_with_retry(url) → Firecrawl
          ├─► adapter.ingest_source(source_meta, markdown)
          │   ├─► INSERT text_ref (corpus.text_refs)
          │   ├─► INSERT source (corpus.sources)
          │   └─► index_chunks (Chroma)
          └─► memory.store_source() [V2 legacy ALSO]

BudgetMonitor triggers condenser when thresholds crossed
  │
  └─► condenser.run(mission_id, priority)
      ├─► SELECT sources WHERE status='fetched'
      ├─► For each source:
      │   ├─► Get text_ref content
      │   ├─► extract_technical_atoms(ollama, content) → JSON
      │   ├─► Create KnowledgeAtom + lineage
      │   ├─► adapter.upsert_atom(atom)
      │   │   ├─► INSERT knowledge.knowledge_atoms
      │   │   ├─► index_atom(Chroma)
      │   │   └─► cache_hot_object(Redis)
      │   ├─► adapter.bind_atom_evidence()
      │   └─► Update source status='condensed'
      └─► (TODO) resolve_contradictions() - STUB
          (TODO) consolidate_atoms() - STUB

User: /report <topic_id>
  │
  └─► system_manager.generate_report()
      └─► synthesis_service.generate_master_brief(topic_id)
          ├─► assembler.generate_section_plan()
          ├─► For each section:
          │   ├─► build_evidence_packet()
          │   │   └─► retriever.retrieve()  ← V2 memory only!
          │   │   └─► get_unresolved_contradictions() ← V2 only!
          │   ├─► archivist.write_section(packet)
          │   └─► adapter.store_synthesis_section()
          └─► Store SynthesisArtifact

Result: Report generated but may lack V3-distilled atoms!
```

---

## 4. Design Patterns Observed

### 4.1 Adapter Pattern
- `SheppardStorageAdapter` adapts V3 backend stores (Postgres, Redis, Chroma) to unified protocol interfaces
- Separate adapters: `PostgresStoreImpl`, `RedisStoresImpl`, `ChromaSemanticStoreImpl`

### 4.2 Manager Pattern
- `MemoryManager` - coordinates V2 memory backends
- `BrowserManager` - manages browser instances
- `TaskManager` - manages research tasks
- `SystemManager` - orchestrates all subsystems

### 4.3 Factory Pattern
- `ResearchComponentFactory` (mentioned in docs, location varies) - lazy singleton creation
- `ModelRouter` - factory for model names based on task type

### 4.4 Dataclass Pattern
Extensive use of `@dataclass` for data models:
- `ResearchMission`, `MissionNode`, `Source`, `Chunk`, `KnowledgeAtom` (V3)
- `CrawlResult`, `CrawlerConfig`
- `TopicBudget`, `BudgetConfig`
- `RetrievalQuery`, `RetrievedItem`, `RoleBasedContext`
- `Preference`, `PreferenceValue`, etc.

### 4.5 Protocol/Interface Pattern
- `StorageAdapter` protocols in `storage_adapter.py` (ConfigStore, MissionStore, CorpusStore, etc.)
- Defines async interface; concrete adapters implement
- Enables dependency injection

### 4.6 Singleton/Global Instance
- Global `settings` object
- Global `console` (Rich console)
- `system_manager = SystemManager()` global singleton

### 4.7 Initialize/Cleanup Lifecycle
Many components implement:
```python
async def initialize(self) -> bool:
    # Acquire resources
    return True

async def cleanup(self) -> None:
    # Release resources
```

### 4.8 Strategy Pattern
- `ResearchType` strategies (WEB_SEARCH, ACADEMIC_SEARCH, etc.)
- Multiple embedding models (switchable)
- Validation levels (NONE, LOW, MEDIUM, HIGH, FULL)

---

## 5. Module Responsibilities

### Core (`src/core/`)
| File | Responsibility |
|------|----------------|
| `chat.py` | ChatApp - main user interface, message processing |
| `commands.py` | Command parsing and routing (/research, /memory, etc.) |
| `system.py` | SystemManager - orchestrator, V2+V3 coordinator |
| `constants.py` | Constants, command definitions, error messages |
| `exceptions.py` | Core exception hierarchy |
| `trust_call.py` | Trust/safety validation layer |

### Research (`src/research/`)
| Subdir | Files | Responsibility |
|--------|-------|----------------|
| `acquisition/` | `frontier.py`, `crawler.py`, `budget.py` | Research planning, URL discovery, scraping coordination |
| `condensation/` | `pipeline.py` | Knowledge atom extraction (distillation) |
| `reasoning/` | `retriever.py`, `assembler.py`, `synthesis_service.py` | Multi-stage retrieval, evidence gathering, synthesis |
| `archivist/` | `loop.py`, `planner.py`, `crawler.py`, `synth.py`, ... | Standalone research engine (legacy/parallel) |
| `system.py` | ResearchSystem - separate from core system |
| `pipeline.py` | ResearchPipeline - 5-stage processing |
| `task_manager.py` | ResearchTaskManager |
| `models.py` | Research data models (ResearchTask, ResearchFinding, etc.) |

### Memory (`src/memory/`)
| File | Responsibility |
|------|----------------|
| `manager.py` | V2 MemoryManager - coordinates V2 storage backends |
| `storage_adapter.py` | V3 StorageAdapter - triad adapter with protocols |
| `adapters/postgres.py` | PostgreSQL backend for V3 |
| `adapters/redis.py` | Redis backend for V3 (3 roles: runtime, cache, queue) |
| `adapters/chroma.py` | ChromaDB backend for V3 |
| `models.py` | V2 memory models (Memory, MemorySearchResult, etc.) |
| `processor.py` | MemoryProcessor - processes content before storage |
| `interactions.py` | InteractionEmbeddingManager - context summarization |
| `schema.sql` | V2 database schema |
| `schema_v3.sql` | V3 database schema |

### LLM (`src/llm/`)
| File | Responsibility |
|------|----------------|
| `client.py` | OllamaClient - async wrapper for Ollama API (chat, embeddings) |
| `model_router.py` | ModelRouter - task → model + host routing |
| `models.py` | ChatMessage, ChatResponse, SystemMessage, etc. |

### Config (`src/config/`)
| File | Responsibility |
|------|----------------|
| `settings.py` | Global settings object with typed attributes |
| `database.py` | DatabaseConfig - **HAS HARDCODED CREDENTIALS - SECURITY ISSUE** |
| `logging.py` | Logging configuration (RichHandler for dev) |

### Preferences (`src/preferences/`)
| File | Responsibility |
|------|----------------|
| `models.py` | Preference, PreferenceValue, PreferenceCategory dataclasses |
| `store.py` | PreferenceStore - persistence layer |
| `validator.py` | PreferenceValidator - validates preference values |
| `schemas.py` | Pydantic schemas for validation |

### Schemas (`src/schemas/`)
| File | Responsibility |
|------|----------------|
| `validator.py` | Schema validation utilities |
| Various `.py` files | Domain schema definitions? |

### Utils (`src/utils/`)
| File | Responsibility |
|------|----------------|
| `console.py` | Rich console singleton |
| `validation.py` | Input validation functions |
| `text_processing.py` | Text utilities (repair_json, cleaning, etc.) |
| `constants.py` | Utility constants |
| `exceptions.py` | Utility exceptions |

### Stable (`src/stable/`)
| File | Responsibility |
|------|----------------|
| `stable.py` | Stable/verified components? (purpose unclear) |

---

## 6. Configuration Management

### Central Configuration

**Primary:** `src/config/settings.py`
```python
class Settings:
    OLLAMA_MODEL: str = os.getenv('OLLAMA_MODEL', 'rnj-1:8b')
    OLLAMA_EMBED_MODEL: str = os.getenv('OLLAMA_EMBED_MODEL', 'mxbai-embed-large:latest')
    REDIS_HOST: str = os.getenv('REDIS_HOST', 'localhost')
    REDIS_PORT: int = int(os.getenv('REDIS_PORT', 6379))
    # ... many more
```

**Global instance:** `settings = Settings()` imported everywhere.

**Problem:** Not all code uses `settings`. For example, `database.py` hardcodes DB URLs, `system.py` hardcodes `num_vampires = 8`.

---

## 7. Entry Points

### `main.py`
**Primary CLI entry point.**
```python
async def async_main():
    nest_asyncio.apply()
    base_dir = Path(__file__).parent
    chat_app = await initialize_components(base_dir)
    await run_chat(chat_app)  # Infinite input loop

if __name__ == "__main__":
    asyncio.run(async_main())
```

**Commands:** Parsed by `CommandHandler` (starts with `/`).

### `scout_worker.py`
**Distributed worker for auxiliary nodes.**
Runs `_vampire_loop` without the full system. Can be deployed on laptops/servers to contribute scraping capacity.

### `bench_test.py`
**Benchmark suite** - runs integration tests and outputs metrics.

### `server_setup.py`
**System setup** - initial PostgreSQL/Redis configuration.

---

## 8. Error Handling Strategy

**Fragmented.** Multiple approaches coexist:

1. **Raise exceptions** - for critical failures (initialization, config errors)
2. **Return tuples** `(bool, Optional[str])` for validation (e.g., `validate_data()`)
3. **Bare except:** `except:` traps all exceptions including KeyboardInterrupt ⚠️
4. **Log and continue** - non-critical failures (e.g., one URL fails, keep going)
5. **Graceful degradation** - if Redis down, may continue without caching

**Critical Issue:** Bare `except:` blocks in ~30 locations suppress all errors including system interrupts. Must be replaced with `except Exception:` at minimum.

---

## 9. Concurrency Model

**Async I/O** throughout using `asyncio`.

**Key concurrent structures:**
- `asyncio.Queue` - for frontier discovery (in-memory)
- Redis Lists - for distributed URL queue
- `asyncio.Semaphore` - to limit parallel distillation (2) and Firecrawl bulk scrapes
- `asyncio.Task` - background tasks (`_monitor_task`, `_vampire_tasks`, `_crawl_tasks`)

**Task Management:**
- SystemManager tracks `_crawl_tasks: Dict[topic_id, Task]`
- Tasks cancelled in `cleanup()`
- No watchdog for orphaned tasks if cleanup skipped

---

## 10. Critical Architectural Concerns

### 10.1 V2/V3 Hybrid Is Broken

The system attempts to run two memory architectures simultaneously:

- **V2:** `MemoryManager` → Postgres (localhost) + Chroma (V2 metadata) + Redis (5 instances)
- **V3:** `SheppardStorageAdapter` → Postgres (10.9.66.198, different DBs/schemas) + Chroma (V3 metadata) + Redis (1 instance)

**Consequences:**
- V3 writes (atoms, sources) are not visible to V2 retrievers
- Chat queries (`ChatApp`) use V2 → V3 research output effectively lost
- V2 and V3 connect to different PostgreSQL databases → no data sharing
- Condensation runs on V3, but synthesis queries V2 → empty results

**Resolution Path:**
- Option A: Complete V3 migration - remove `MemoryManager`, migrate all consumers to V3 adapter
- Option B: Revert to V2 - remove V3 adapter and all V3-specific components

Half-implemented hybrid renders V3 features non-functional.

---

### 10.2 Data Inconsistency from Dual Writes

`_vampire_loop` writes to both systems:
```python
await self.adapter.ingest_source(source_meta, result.markdown)  # V3
await self.memory.store_source(...)  # V2
```

If one succeeds and the other fails, data diverges. No two-phase commit.

---

### 10.3 Metadata Incompatibility

Same Chroma collection `knowledge_atoms` used by both V2 and V3 but with different metadata schemas:

- V2: `{source_url, captured_at, tech_density, citation_key, ...}`
- V3: `{atom_id, authority_record_id, confidence, importance, stability, ...}`

Retriever expects V2 metadata, so V3 atoms get:
- `source_url = "chromadb"`
- `captured_at = None` → `recency_days = 9999`
- `tech_density = 0.5` (default)
- `citation_key = None`

V3 atoms severely disadvantaged in re-ranking.

---

## Summary

Sheppard's architecture is **ambitious but incomplete**. The V3 Triad design is sound (Postgres truth, Chroma proximity, Redis motion), but:

1. **Dual architecture** causes data silos and broken retrieval
2. **Core features** (contradiction resolution, consolidation) are stubs
3. **Metadata mismatch** degrades V3 atom retrieval quality
4. **Configuration** is inconsistent and insecure
5. **Error handling** includes dangerous bare excepts
6. **Testing** virtually nonexistent

The codebase represents a **mid-migration snapshot** where V3 infrastructure exists but critical components were never finished, and the V2/V3 hybrid creates systemic breakage.

For the system to function as intended, a **hard decision must be made**: either complete V3 migration (finish stubs, fix metadata, remove V2) or abandon V3 and refine V2. Continuing with both is unsustainable.
