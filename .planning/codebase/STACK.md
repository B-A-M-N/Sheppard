# Sheppard V3 Codebase - Technology Stack

## 1. Programming Languages

### Primary
- **Python 3.10+** - Core application language with heavy async/await usage
- **JavaScript/TypeScript** - Firecrawl and Playwright microservices

### Secondary/Supporting
- **SQL** - PostgreSQL schemas (V2 and V3)
- **Bash** - Service management scripts
- **YAML** - Configuration (SearXNG, Firecrawl)

## 2. Core Python Frameworks & Libraries

### Async & HTTP
```
aiohttp>=3.9.1           # Async HTTP client for Ollama, Redis
requests>=2.31.0        # Sync HTTP for SearXNG
```

### Configuration & Validation
```
python-dotenv>=1.0.0     # Environment loading
pydantic>=2.5.2         # Data validation and settings management
```

### Terminal UI
```
rich>=13.7.0            # Rich console formatting, progress bars, tables
```

### Databases & Storage
```
redis>=5.0.1            # Redis client (sync wrappers)
aioredis>=2.0.1         # Async Redis (legacy, should migrate to redis.asyncio)
chromadb>=0.4.18        # Vector database for embeddings
asyncpg                 # PostgreSQL async driver (used directly, not in requirements.txt)
```

### Browser Automation & Scraping
```
selenium>=4.15.2        # Browser automation (legacy fallback)
beautifulsoup4>=4.12.2  # HTML parsing
webdriver-manager>=4.0.1 # Chrome driver management
tldextract>=5.1.1       # Domain extraction
undetected-chromedriver>=3.5.4  # Anti-detection Chrome
fake-useragent>=1.2.1   # Rotating user agents
firecrawl-py>=0.2.0     # Firecrawl API client
```

### Testing & Development
```
pytest>=7.4.3           # Testing framework (not actively used)
pytest-asyncio>=0.23.2  # Async test support
pytest-cov>=4.1.0       # Coverage reporting
mypy>=1.7.1            # Static type checking
types-redis>=4.6.0.11  # Redis type stubs
types-aiofiles>=23.2.0 # aiofiles type stubs
```

### Documentation
```
sphinx>=7.2.6          # Documentation generator
sphinx-rtd-theme>=2.0.0 # Read the Docs theme
```

## 3. Database & Storage Systems

### PostgreSQL
- **Version:** 14+
- **Extension:** `btree_gin` required
- **Architecture:** V2 (single schema) + V3 (multi-schema)
  - V2: `public` schema with tables: `topics`, `sources`, `knowledge_atoms`, `frontier_nodes`, `contradictions`, etc.
  - V3: `config`, `mission`, `corpus`, `knowledge`, `authority`, `application` schemas
- **Connection:** asyncpg connection pool (configured: min=2, max=10)
- **Default Connection:**
  - V2: `postgresql://sheppard:1234@localhost:5432/semantic_memory` (from POSTGRES_DSN)
  - V3: `postgresql://sheppard:1234@10.9.66.198:5432/semantic_memory` (from DatabaseConfig)
- **Hardcoded Credentials:** `src/config/database.py` contains username `sheppard`, password `1234`, IP `10.9.66.198`

### ChromaDB
- **Version:** 0.4.18+
- **Mode:** Persistent client (file storage)
- **Path:** `./chroma_storage` or `./data/chroma_persistence`
- **Distance:** Cosine similarity
- **Collections:**
  - `corpus_chunks` - Document chunks
  - `knowledge_atoms` - Extracted facts (V2) + V3 atoms (with different metadata)
  - `thematic_syntheses` - Level C syntheses (V2)
  - `advisory_briefs` - Level D advisories (V2)
  - `authority_records` - Authority records (V3)
  - `synthesis_artifacts` - Synthesis artifacts (V3)
- **Embedding Dimension:** Depends on model (mxbai-embed-large: 1024, nomic-embed-text: 768)

### Redis
- **Version:** 6.2+
- **Instances:** Up to 6 separate Redis servers on different ports:
  - Port 6379: Main queue (`queue:scraping`, retry sets)
  - Port 6370: Ephemeral memory layer
  - Port 6371: Contextual memory layer
  - Port 6372: Episodic memory layer
  - Port 6373: Semantic memory layer
  - Port 6374: Abstracted memory layer
- **Use Cases:**
  - Global scraping queue (V3 distributed metabolism)
  - Distributed locks (frontier coordination)
  - Hot object caching (V3 adapter cache)
  - Active state storage (missions, nodes, bundles)
  - Memory layer caching (V2)
- **Configuration:** Each instance with maxmemory 100MB, LRU eviction, AOF persistence (inferred)

### File Storage
```
./data/
├── raw_docs/           # Raw scraped content (text/markdown)
├── embeddings/         # Cached embedding vectors
├── stats/              # System statistics (JSON)
├── tools/              # Tool-specific storage
├── memory/             # V2 layered memory directories
│   ├── episodic/
│   ├── semantic/
│   ├── contextual/
│   ├── general/
│   └── abstracted/
├── chroma_persistence/ # V2 Chroma storage (alternative location)
└── conversations/      # Chat history JSON files

./screenshots/          # Browser screenshots
./logs/                 # Application logs
./chat_history/         # Exported chat history
```

## 4. External Services & APIs

### Ollama (LLM Inference)
- **Purpose:** Local LLM hosting for chat, extraction, decomposition, query expansion
- **Deployment:** Multi-host topology (distributed nodes)
- **Hosts Configured:**
  - Main Brain: `http://10.9.66.90:11434`
  - Localhost: `http://127.0.0.1:11434`
  - Vampire Scout: `http://10.9.66.154:11434` (inferred)
  - Lazy Scout: `http://10.9.66.45:11434` (inferred)
- **Models:**
  - Chat: `rnj-1:8b` or `mannix/llama3.1-8b-lexi:latest`
  - Embeddings: `mxbai-embed-large:latest` or `nomic-embed-text`
  - Summarization: `llama3.2:latest`
- **Features:** Streaming chat, embeddings, configurable temperature/top_p
- **Timeout:** 900 seconds (15 min)
- **Retries:** 3 attempts with exponential backoff
- **Task Routing:** `ModelRouter` directs different task types to appropriate hosts

### Firecrawl (Web Scraping)
- **Purpose:** Primary web scraping engine
- **Deployment:** Local firecrawl-local instance
- **Base URL:** `http://localhost:3002`
- **Auth:** Bearer token (default "local" for local instance)
- **Features:**
  - Single URL scraping (`/v1/scrape`)
  - Async crawl jobs (`/v1/crawl`)
  - Rate limit tracking
  - Concurrent request limiting
  - WebSocket support (unused)
- **Microservice Dependencies:**
  - Playwright Service: `http://localhost:3003/scrape`
  - Redis for rate limiting: `redis://localhost:6379`
- **Configuration:**
  - `NUM_WORKERS_PER_QUEUE=12` (Firecrawl's own workers)
  - `max_depth=5` default crawl depth
  - `exclude_paths` for filtering

### SearXNG (Privacy-Respecting Meta-Search)
- **Purpose:** Distributed search for discovery phase
- **Deployment:** Multiple instances for load distribution
- **Endpoints (from code):**
  - `http://localhost:8080`
  - `http://10.9.66.45:8080`
  - `http://10.9.66.154:8080`
- **Interface:** REST GET `/search?q={query}&format=json`
- **Usage:** Frontier discovers URLs via parallel SearXNG queries

### Playwright Microservice
- **Purpose:** JavaScript-heavy page rendering for Firecrawl
- **Deployment:** Node.js TypeScript service in `firecrawl-local/apps/playwright-service-ts`
- **Port:** 3003
- **Endpoint:** `POST /scrape` with URL, returns rendered HTML

### PostgreSQL
- **Version:** 14+
- **Extensions:** `btree_gin`, `pgcrypto`
- **Authentication:** Password-based (hardcoded `sheppard:1234`)
- **Network:** Internal (10.9.66.198) and localhost
- **Connection Pooling:** asyncpg with configurable pool size

### Redis
- **Version:** 6.2+
- **Authentication:** None configured (uses localhost without AUTH)
- **Persistence:** AOF (Append-Only File)
- **Eviction:** LRU with maxmemory 100MB per instance

## 5. Build Tools & Deployment

### Systemd Services
Multiple Redis instances, PostgreSQL managed via systemd. No unit files in repo.

### Bash Scripts
- `start_research_stack.sh` - Comprehensive startup: SearXNG, Playwright, Firecrawl, workers
- `server_setup.py` - Initial system setup (PostgreSQL, Redis instances, databases)
- `postgreswipe.sh` - Database cleanup
- `server_wipe.py` - Full system reset
- `schemafix.py` - Schema management
- `setup.py` - Package installation

### Process Management
- `setsid`/`nohup` for background services
- Manual process oversight (no Supervisor config found)
- Worker processes:
  - Firecrawl workers (configurable, default 12)
  - Vampire workers (8 on main PC, from system.py:140)
  - Scout worker (`scout_worker.py`) for auxiliary nodes

### No Containerization
No Docker or Docker Compose. Deploys directly to system with dependencies installed via pip and system packages.

## 6. Configuration Management

### Environment Variables (.env)

**Core Application:**
```
OLLAMA_MODEL=rnj-1:8b
OLLAMA_EMBED_MODEL=mxbai-embed-large:latest
OLLAMA_API_HOST=http://localhost
OLLAMA_EMBED_HOST=http://127.0.0.1
OLLAMA_API_PORT=11434
REDIS_HOST=localhost
REDIS_PORT=6379
CHROMADB_PERSIST_DIRECTORY=./chroma_storage
CHROMADB_TELEMETRY_ENABLED=0
LOG_LEVEL=INFO
```

**Firecrawl/SearXNG Stack:**
```
FIRECRAWL_API_KEY=fc-a434f4156e824c1898cfefa92b76c392  # Example from .env
FIRECRAWL_BASE_URL=http://localhost:3002
PORT=3002
HOST=0.0.0.0
REDIS_URL=redis://localhost:6379
REDIS_RATE_LIMIT_URL=redis://localhost:6379
PLAYWRIGHT_MICROSERVICE_URL=http://localhost:3003/scrape
USE_DB_AUTHENTICATION=false
NUM_WORKERS_PER_QUEUE=12
SEARXNG_ENDPOINT=http://localhost:8080
```

### Configuration Classes

- `src/config/settings.py` - Application settings (global `settings` instance)
- `src/config/database.py` - Database configurations (unfortunately hardcoded)
- `src/config/logging.py` - Logging setup

### Settings Pattern
Uses `os.getenv()` with defaults. Some classes use `@property` for computed values. No centralized schema validation for all settings.

## 7. Runtime Requirements

### Main Brain (Reference Hardware)
- **CPU:** AMD Ryzen 5900X (20+ cores)
- **RAM:** 64GB DDR5
- **GPU:** NVIDIA RTX 3090 (16GB) or A4000
- **Storage:** Fast NVMe SSD
- **OS:** Linux (PopOS! 22.04+, Ubuntu 20.04+)

### Distributed Workers
- **Vampire Scout:** High-core count (20-core) for parallel scraping
- **Lazy Scout:** Lower-power laptop (i5) for PDF/static processing
- **Reasoning Rig:** Remote server for heavy LLM inference

### Python
- **Version:** 3.10+
- **Virtual Environment:** Recommended but not enforced
- **Install:** `pip install -r requirements.txt`

### System Services
- PostgreSQL 14+ with `btree_gin` extension: `CREATE EXTENSION btree_gin;`
- Redis 6.2+ instances
- Ollama with models pulled: `ollama pull rnj-1:8b`, `ollama pull mxbai-embed-large:latest`

### Network Ports
```
11434 - Ollama API
3002  - Firecrawl API
3003  - Playwright service
8080  - SearXNG
6370-6374 - Redis instances
5432  - PostgreSQL
```

## 8. Notable Implementation Details

### Async Architecture
Heavy use of `asyncio` with async generators, `asyncio.Queue`, `asyncio.Semaphore`, and `asyncio.create_task()`. Most I/O operations are async.

### Connection Pooling
- PostgreSQL: `asyncpg.create_pool(min_size=2, max_size=10)` in system.py (hardcoded)
- aiohttp: `ClientSession` reused for Ollama and Firecrawl

### Model Routing
`ModelRouter` class maps `TaskType` (CHAT, EMBEDDING, DECOMPOSITION, etc.) to specific model names and hosts. Supports task-specific model selection.

### Triad Storage Pattern (V3)
`SheppardStorageAdapter` enforces write consistency:
1. Write to Postgres (canonical)
2. Index to Chroma (semantic)
3. Update Redis (hot cache/queue)

Read path checks Redis cache first, then Chroma, then Postgres.

---

## Summary

Sheppard V3 is a **highly distributed, multi-database, multi-service research automation system** with:

- **6 database systems** (PostgreSQL with 2 schemas, ChromaDB, 4+ Redis instances)
- **3+ external services** (Ollama multi-host, Firecrawl, SearXNG, Playwright)
- **3 hardware tiers** (Main Brain, Vampire Scout, Lazy Scout)
- **Task-specific model routing** across distributed Ollama nodes
- **Queue-based distributed processing** with 8-12 concurrent workers
- **No webhooks** - fully asynchronous pull-based architecture

The stack is **ambitious but incomplete**, with V2/V3 coexistence creating significant architectural debt. Security is weak due to hardcoded credentials and bare exception handlers. Testing coverage is minimal.
