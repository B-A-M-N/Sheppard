# Sheppard V3 - External Integrations

## 1. API Clients

### 1.1 Ollama Client (`src/llm/client.py`)

**Purpose:** Multi-host LLM inference with task-specific routing

**Architecture:**
- Split-host routing based on task type (CHAT, EMBEDDING, DECOMPOSITION, etc.)
- Session pooling per host using `aiohttp.ClientSession`
- Both streaming and non-streaming responses
- Retry logic: 3 attempts with exponential backoff (configurable)
- Timeout: 900s total, 120s connect

**Host Configuration (from .env):**
```
OLLAMA_API_HOST=http://10.9.66.90        # Remote Brain
OLLAMA_EMBED_HOST=http://127.0.0.1      # Localhost embeddings
OLLAMA_API_PORT=11434
```

**Task Routing (inferred from ModelRouter):**
- **CHAT:** Remote Brain - `rnj-1:8b` or `mannix/llama3.1-8b-lexi:latest`
- **EMBEDDING:** Localhost - `mxbai-embed-large:latest` or `nomic-embed-text`
- **SUMMARIZATION:** Vampire Scout - `llama3.2:latest`
- **DECOMPOSITION/QUERY_EXPANSION:** Remote Brain - creative tasks
- **EXTRACTION/CONTRADICTION:** Remote Brain - precision tasks

**Key Methods:**
```python
async def chat_stream(model, messages, system_prompt=None) -> AsyncGenerator[str, None]
async def complete(task, prompt, system_prompt=None, max_tokens=None) -> str
async def generate_embedding(text) -> List[float]
async def embed(text) -> List[float]  # alias
```

**Errors:**
- `ModelNotFoundError` (HTTP 404)
- `TokenLimitError` (HTTP 413 or context length exceeded)
- `APIError` (other HTTP errors)
- `TimeoutError`
- `ServiceUnavailableError`

**Configuration:**
- `settings.REQUEST_TIMEOUT` (default 900)
- `settings.MAX_RETRIES` (default 3)
- `settings.CONNECTION_TIMEOUT` (default 120)

---

### 1.2 Firecrawl Client (`src/research/firecrawl_client.py`, `src/research/acquisition/crawler.py`)

**Purpose:** Robust web scraping with async job management

**Deployment:** `firecrawl-local` running locally

**Configuration:**
```
FIRECRAWL_BASE_URL=http://localhost:3002
FIRECRAWL_API_KEY=local  # For local instance; cloud uses real key
```

**Features:**
- Single URL scraping: `scrape_url(url)` → `{success, data: {markdown, html, metadata}}`
- Bulk scraping: `scrape_urls(urls)` with concurrency semaphore
- Async crawl jobs: `start_crawl(urls)` → job_id, `check_crawl_status(job_id)`, `get_crawl_results(job_id)`
- Rate limit tracking
- Metrics collection (success rate, timing)

**Integration Points:**
- Used by `FirecrawlLocalClient` in `crawler.py`
- Frontend sends URLs via "fast lane" or "slow lane" routing
- Returns `CrawlResult` dataclass with `url`, `title`, `markdown`, `raw_bytes`, `checksum`, `domain`

**Microservice Dependencies:**
- Playwright Service (`http://localhost:3003/scrape`) for JS-heavy pages
- Redis for rate limiting (`redis://localhost:6379`)

**Scraping Options:**
- `formats: ["markdown", "html"]`
- `exclude_paths` (regex patterns)
- `max_depth` (crawl depth)
- `page_limit` (max pages per crawl)

---

### 1.3 SearXNG Search (`src/research/archivist/search.py`, `src/research/acquisition/crawler.py`)

**Purpose:** Privacy-respecting meta-search across multiple search engines

**Interface:** Simple HTTP GET

```
GET /search?q={query}&format=json
```

**Configuration:**
- `SEARXNG_ENDPOINT` env var (default: `http://localhost:8080`)
- Multiple endpoints for load distribution in `CrawlerConfig.searxng_urls`

**Usage:**
- Frontier discovery: `crawler.discover_and_enqueue()` calls `search_web()` to find URLs
- Archivist system: `search.search_web()` for seed URLs

**Fallback Strategy:**
- Round-robin through configured endpoints
- Code shows commented-out DDG (DuckDuckGo) fallback

**Response Format:**
JSON with `results` array containing `url`, `title`, `snippet` for each result.

---

## 2. Message Queues & Distributed Coordination

### 2.1 Redis Queue System

**Primary Queue:**
- **Name:** `queue:scraping`
- **Type:** Redis List (LPUSH/RPUSH for enqueue, BLPOP for dequeue)
- **Payload:** JSON with keys:
  ```json
  {
    "url": "https://example.com/page",
    "topic_id": "uuid",
    "mission_id": "uuid",
    "url_hash": "md5checksum"
  }
  ```
- **Consumers:** Vampire workers (`_vampire_loop`) block with 10s timeout

**Retry Mechanism:**
- Sorted set: `retry:queue:scraping`
- Score: epoch timestamp when retry should be released
- `schedule_retry()`: ZADD with timestamp
- `move_due_retries()`: ZRANGEBYSCORE 0..now, then RPUSH back to main queue
- Run periodically by budget monitor or on dequeue miss

**Distributed Locks:**
- Redis SET with NX and EX for lock acquisition
- Lock handle contains: `{key, token, expires_at}`
- Refresh via EXPIRE, release checks token matches before DEL
- Used for frontier node checkpointing (prevent concurrent updates)

**Hot Caching:**
- Key format: `{kind}:hot:{object_id}` (e.g., `source:hot:abc123`)
- TTL typically 3600s (1 hour)
- Used by `SheppardStorageAdapter` for frequently accessed objects

**Active State:**
- Key pattern: `mission:active:{mission_id}`, `source:hot:{source_id}`, etc.
- Volatile state that doesn't need persistence
- TTL varies: missions 86400s (1 day), others 3600s

**Multiple Instances:**
- Ports 6370-6374 for different memory layers (V2 architecture)
- Port 6379 for main queue and V3 runtime/cache
- Different Redis databases (db 0-4) for isolation

---

## 3. Databases

### 3.1 PostgreSQL Adapter (`src/memory/adapters/postgres.py`)

**Implementation:** `PostgresStoreImpl` with `asyncpg` connection pool

**Connection:**
- From `DatabaseConfig.DB_URLS['semantic_memory']`
- Default (hardcoded): `postgresql://sheppard:1234@10.9.66.198:5432/semantic_memory`
- Pool size: min=2, max=10 (from system.py) or 5-20 (from database.py - inconsistent)

**Core Methods (Async):**
```python
async def upsert_row(table, key_fields, row)   # INSERT ... ON CONFLICT DO UPDATE
async def insert_row(table, row)              # Simple INSERT
async def update_row(table, key_field, row)   # UPDATE WHERE key_field = $n
async def bulk_insert(table, rows)            # Batch INSERT
async def bulk_upsert(table, key_fields, rows) # Batch upsert
async def fetch_one(table, where) → dict | None
async def fetch_many(table, where, order_by, limit) → list[dict]
async def delete_where(table, where)
```

**Data Type Conversions:**
- `dict`/`list` → JSON string (via `json.dumps()`)
- ISO datetime strings → `datetime` objects (parsed with `fromisoformat()`)
- UUID strings passed directly (asyncpg handles UUID type)

**Schemas Supported:**
- V2: `public` schema (legacy from `schema.sql`)
- V3: `config`, `mission`, `corpus`, `knowledge`, `authority`, `application` (from `schema_v3.sql`)

**Tables Used (V3 examples):**
- `config.domain_profiles`
- `mission.research_missions`, `mission.mission_nodes`, `mission.mission_events`
- `corpus.sources`, `corpus.text_refs`, `corpus.chunks`, `corpus.clusters`
- `knowledge.knowledge_atoms`, `knowledge.atom_evidence`, `knowledge.contradiction_sets`
- `authority.authority_records`, `authority.synthesis_artifacts`
- `application.application_queries`

---

### 3.2 Redis Adapters (`src/memory/adapters/redis.py`)

**Implementation:** `RedisStoresImpl` implements three protocols:
1. `RedisRuntimeStore` - volatile state & locks
2. `RedisCacheStore` - hot object cache
3. `RedisQueueStore` - job queuing

**Serialization:** JSON via `json.dumps(payload, default=lambda obj: obj.isoformat() if datetime else raise TypeError)`

**Methods:**

**Runtime:**
- `acquire_lock(key, ttl_s)` → `LockHandle | None` (SET NX)
- `refresh_lock(handle, ttl_s)` → extends TTL if token matches
- `release_lock(handle)` → DEL if token matches
- `set_active_state(key, payload, ttl_s)` → SET with/without EX
- `get_active_state(key)` → GET + json.loads
- `delete_active_state(key)` → DEL

**Cache:**
- `cache_hot_object(kind, object_id, payload, ttl_s)` → key=f"{kind}:hot:{object_id}"
- `get_hot_object(kind, object_id)` → returns cached object or None
- `invalidate_hot_object(kind, object_id)` → DEL

**Queue:**
- `enqueue_job(queue_name, payload)` → RPUSH
- `dequeue_job(queue_name, timeout_s)` → BLPOP timeout or None
- `schedule_retry(queue_name, payload, when_epoch_s)` → ZADD to sorted set
- `move_due_retries(queue_name, now_epoch_s)` → ZRANGEBYSCORE 0..now, count moved items

---

### 3.3 ChromaDB Adapter (`src/memory/adapters/chroma.py`)

**Implementation:** `ChromaSemanticStoreImpl`

**Client:** `chromadb.PersistentClient(path=persist_dir)`

**Collections:**
- `corpus_chunks` - Document chunks
- `knowledge_atoms` - Knowledge atoms (V2 and V3 both use this collection but with different metadata schemas)
- `authority_records` - Authority records (V3)
- `synthesis_artifacts` - Synthesis artifacts (V3) (maybe separate collection?)

**Operations (all async, run in thread pool):**
```python
async def index_document(collection, object_id, document, metadata)
async def index_documents(collection, rows)  # rows = [(id, doc, meta), ...]
async def search(collection, query_text, where=None, limit=20) → list[SearchHit]
async def delete_document(collection, object_id)
```

**Search Output:** `SearchHit` dataclass:
```python
@dataclass
class SearchHit:
    object_id: str
    score: float           # 1.0 - distance (cosine)
    metadata: dict
```

**Where Clauses:** Supports Chroma `where` filtering on metadata (e.g., `{"topic_id": "uuid"}`)

**Distance Metric:** Cosine (configured in collection creation: `{"hnsw:space": "cosine"}`)

---

## 4. Browser Automation

### 4.1 Selenium-Based (`src/research/browser_manager.py`, `src/research/browser_control.py`)

**Status:** Legacy/fallback; primary scraping uses Firecrawl

**Features:**
- Chrome/Chromium driver via `webdriver-manager`
- `undetected-chromedriver` for anti-bot evasion
- URL filtering: removes tracking params (utm_*, fbclid, gclid)
- Screenshot capture
- Cookie handling
- Headless mode
- Stealth mode with user-agent rotation

**Configuration (`BrowserConfig` dataclass):**
- `headless: bool = True`
- `user_agent`: Rotating via `fake-useragent`
- `window_size: str = "1920,1080"`
- `page_load_timeout: int = 60`
- `implicit_wait: int = 10`
- `stealth_mode: bool = True`

**Classes:**
- `BrowserManager` - singleton manager for browser instances
- `AutonomousBrowser` - high-level browsing with self-healing

**Note:** Being phased out in favor of Firecrawl+Playwright.

---

### 4.2 Playwright Microservice (External)

**Purpose:** Render JavaScript-heavy pages for Firecrawl

**Deployment:** Node.js TypeScript service in `firecrawl-local/apps/playwright-service-ts`

**Interface:**
```
POST http://localhost:3003/scrape
Content-Type: application/json

{
  "url": "https://example.com",
  "options": { "waitForSelector": "...", "screenshot": false }
}

→ { success, html, screenshot?, error? }
```

**Firecrawl Integration:** Firecrawl calls this internally when page detection indicates JS is needed.

---

## 5. Webhooks & Callbacks

**None detected.** The system is fully pull-based with message queues and polling.

---

## 6. Configuration via Environment Variables

### Complete Reference

**Ollama:**
```
OLLAMA_MODEL                    # Chat model name
OLLAMA_EMBED_MODEL              # Embedding model name
OLLAMA_API_HOST                 # Chat API host (default: localhost)
OLLAMA_EMBED_HOST               # Embedding API host (default: same as API host)
OLLAMA_API_PORT                 # Port (default: 11434)
```

**Redis:**
```
REDIS_HOST                      # Main Redis host (default: localhost)
REDIS_PORT                      # Main Redis port (default: 6379)
REDIS_DB                        # Database number (default: 0)
```

**ChromaDB:**
```
CHROMADB_PERSIST_DIRECTORY      # Path to storage (default: ./chroma_storage)
CHROMADB_TELEMETRY_ENABLED      # 0 to disable
```

**Firecrawl:**
```
FIRECRAWL_API_KEY               # API key (default: 'local' for local instance)
FIRECRAWL_BASE_URL              # API base URL (default: http://localhost:3002)
PORT                            # Firecrawl port (default: 3002)
HOST                            # Firecrawl bind address (default: 0.0.0.0)
REDIS_URL                       # Firecrawl's Redis (default: redis://localhost:6379)
REDIS_RATE_LIMIT_URL            # Rate limit Redis (default: same as REDIS_URL)
PLAYWRIGHT_MICROSERVICE_URL     # Playwright endpoint (default: http://localhost:3003/scrape)
USE_DB_AUTHENTICATION           # false for local
NUM_WORKERS_PER_QUEUE           # Firecrawl's internal workers (default: 12)
SEARXNG_ENDPOINT                # Search endpoint (default: http://localhost:8080)
```

**Application:**
```
LOG_LEVEL                       # Logging level (default: INFO)
GPU_ENABLED                     # Use GPU for Ollama (true/false)
GPU_LAYERS                      # Number of GPU layers (default: 32)
NUM_GPU                         # Number of GPUs (default: 1)
F16                             # Use half-precision (true/false)
REQUEST_TIMEOUT                 # LLM timeout in seconds (default: 900)
CONNECTION_TIMEOUT              # Connection timeout in seconds (default: 120)
MAX_RETRIES                     # Max retry attempts (default: 5)
RETRY_DELAY                     # Retry delay in seconds (default: 5.0)
```

**Distributed:**
```
MAIN_PC_IP                       # Central server IP (e.g., 10.9.66.198)
VAMPIRE_WORKERS                  # Number of local vampire workers (default: 4)
```

**Database (Legacy V2):**
```
POSTGRES_DSN                     # Full connection string for V2 MemoryManager
                                 # Default: postgresql://sheppard:1234@localhost:5432/semantic_memory
```

**CRITICAL:** `POSTGRES_DSN` is the only var used by `MemoryManager`; all other DB URLs are hardcoded in `database.py`. This creates configuration inconsistency.

---

## 7. Integration Flow: End-to-End Data Pipeline

### Research Mission Flow (V3)

1. **User** runs `/learn quantum computing`
2. **ChatApp** → `system_manager.learn(topic_name, query)`
3. **SystemManager.learn:**
   - Creates topic in V2 memory (legacy)
   - Creates `DomainProfile` in V3 via `adapter.upsert_domain_profile()`
   - Creates `ResearchMission` in V3 via `adapter.create_mission()`
   - Registers topic with `BudgetMonitor`
   - Starts background task `_crawl_and_store()`

4. **_crawl_and_store** creates `AdaptiveFrontier`:
   - `_load_checkpoint()` - loads state from DB
   - `_frame_research_policy()` - generates domain-specific policy + 15 nodes (or loads existing)
   - Main loop:
     - `_select_next_action()` - picks node & epistemic mode
     - `_engineer_queries()` - generates 3 search queries via LLM
     - `crawler.discover_and_enqueue()` - SearXNG search → enqueues URLs to Redis `queue:scraping`
     - Repeats for next node

5. **Vampire Workers** (`_vampire_loop` running in parallel):
   - `adapter.dequeue_job("queue:scraping")` - blocks waiting for URLs
   - `crawler._scrape_with_retry(url)` - Firecrawl call
   - `adapter.ingest_source()` - writes to V3 `corpus.sources` + `corpus.text_refs`
   - `memory.store_source()` - ALSO writes to V2 `sources` table (legacy)

6. **Condensation** (triggered by budget monitor):
   - `DistillationPipeline.run(mission_id, priority)`
   - Queries V3: `adapter.pg.fetch_many("corpus.sources", where={"mission_id": mission_id, "status": "fetched"})`
   - For each source:
     - Get `text_ref` from DB
     - Call `extract_technical_atoms(ollama, content, topic_name)`
     - Create `KnowledgeAtom` + `AtomLineage`
     - `adapter.upsert_atom()` → writes to V3 `knowledge.knowledge_atoms`
     - `adapter.index_atom()` → indexes in Chroma with metadata
     - Bind evidence: `adapter.bind_atom_evidence()`
     - Mark source status = "condensed"
   - If priority HIGH/CRITICAL: calls `resolve_contradictions()` (STUB)

7. **Retrieval for Chat** (`system_manager.chat()`):
   - `ChatApp.process_input(user_input)`
   - `system_manager.memory.search(user_input)` → V2 `MemoryManager.search()`
     - Chroma query `knowledge_atoms` collection
     - Expected V2 metadata format (source_url, captured_at, tech_density, citation_key)
     - V3 atoms have different metadata → degraded scoring
   - V2 lexical search: `memory.lexical_search_atoms()` → queries V2 `knowledge_atoms` table (UUID, content)
     - V3 atoms in different table → NOT FOUND
   - Returns top N results

8. **Response Generation:**
   - System prompt includes retrieved context
   - `system_manager.ollama.chat_stream()` with chat model
   - Stream to user

9. **Synthesis/Tier 4** (`/report` command):
   - `synthesis_service.generate_master_brief(topic_id)`
   - `assembler.generate_section_plan()` - LLM generates 5-8 section plan
   - For each section:
     - `assembler.build_evidence_packet()` - uses `HybridRetriever` (V2 memory)
     - `archivist.write_section()` - ArchivistLLM generates prose
     - `adapter.store_synthesis_section()` - V3 storage
   - Stores `SynthesisArtifact` in V3 `authority.synthesis_artifacts`

**Critical Gap:** Step 6 writes to V3, Step 7 reads from V2 → V3 atoms invisible to chat unless they were also written to V2 (they're not).

---

## 8. Configuration Files

### `.env`
Primary source for runtime configuration. Should be gitignored (it is). Contains secrets in development.

### `src/config/settings.py`
Global `settings` object with typed attributes. Uses `os.getenv()` with defaults.

### `src/config/database.py`
**PROBLEM:** Hardcoded database URLs and credentials. Should use environment variables.

```python
DB_URLS = {
    "episodic_memory": "postgresql://sheppard:1234@10.9.66.198:5432/episodic_memory",
    # ... all hardcoded
}
```

### `src/config/logging.py`
Logging configuration (RichHandler for development).

---

## 9. Service Dependencies & Startup Order

### Required Services (for full V3 operation):

1. **PostgreSQL** (with btree_gin extension, databases created)
2. **Redis** (main instance on port 6379, optionally 5 more for memory layers)
3. **Ollama** (with required models pulled)
4. **Firecrawl-Local** (`firecrawl-local` process)
5. **SearXNG** (for URL discovery)
6. **Playwright Service** (for JS rendering)

### Startup Script: `start_research_stack.sh`

Sequence:
- Start SearXNG (background)
- Start Firecrawl (background, waits for port 3002)
- Start Playwright service
- Launch workers (multiple `python scout_worker.py &`)
- Wait and check status

### Manual: `main.py`

After services running:
```bash
python3 main.py
```

Initialization order (in `initialize_components`):
1. Create directories
2. `system_manager.initialize()`:
   - Create Postgres pool (V3 triad)
   - Create Redis client
   - Create Chroma client
   - Initialize V2 `MemoryManager` (separate connection)
   - Initialize `OllamaClient`
   - Initialize `BudgetMonitor`
   - Initialize `DistillationPipeline`
   - Initialize `FirecrawlLocalClient`
   - Initialize `HybridRetriever`
   - Initialize `EvidenceAssembler` and `SynthesisService`
   - Start budget monitor task
   - Spawn 8 vampire workers
3. Create `ChatApp` and attach system_manager
4. Return chat_app

---

## 10. Cross-Version Compatibility Issues

### V2 vs V3 Memory Incompatibility

| Aspect | V2 (MemoryManager) | V3 (StorageAdapter) |
|--------|-------------------|---------------------|
| Postgres DB | `POSTGRES_DSN` (localhost) | `DB_URLS['semantic_memory']` (10.9.66.198) |
| Chroma Collection | Same name `knowledge_atoms` | Same collection `knowledge_atoms` |
| Chroma Metadata | `source_url, captured_at, tech_density, citation_key` | `atom_id, authority_record_id, confidence, importance` |
| Atom Table | `public.knowledge_atoms` (UUID id) | `knowledge.knowledge_atoms` (TEXT id) |
| Contradictions | `public.contradictions` (atom_a_id, atom_b_id) | `knowledge.contradiction_sets` + `knowledge.contradiction_members` |
| Source Table | `sources` (V2 schema) | `corpus.sources` (V3 schema with text_refs) |
| Source Mark | `condensed` boolean field | `status` enum ('fetched', 'condensed', 'error') |

**Result:** V3 writes are invisible to V2 retrievers. System fundamentally broken due to data silos.

---

## Summary

Sheppard integrates **9 external systems** (PostgreSQL, Redis, ChromaDB, Ollama, Firecrawl, SearXNG, Playwright, Selenium, Chrome) across **multiple network endpoints** and **3+ hardware nodes**. The integration topology is complex and ambitious but suffers from:

1. **Dual architecture:** V2 and V3 systems run in parallel without data sharing
2. **Configuration fragility:** Hardcoded credentials and IPs, inconsistent env var usage
3. **Security gaps:** No authentication on Redis or PostgreSQL beyond trivial passwords
4. **Incomplete migration:** V3 features stubbed, V2 still primary but untested with V3 data
5. **Minimal testing:** No integration tests verify these integrations work correctly together

The system is **technically impressive but production-risky**. It works in a trusted lab environment but would fail under real-world constraints (security audits, scaling, monitoring, observability).
