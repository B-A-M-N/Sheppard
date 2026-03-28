# Sheppard V3 - Code Structure & Module Breakdown

## 1. Repository Organization

```
/home/bamn/Sheppard/
├── src/                          # Main source code
│   ├── llm/                     # LLM integration layer
│   ├── shepherd/                # Core Shepherd V3 system
│   ├── swoc/                    # Semantic Web of Concepts
│   ├── metasystem/              # V2 Metasystem compatibility
│   ├── memory/                  # Memory interfaces
│   ├── interfaces/              # External API interfaces
│   ├── pipelines/               # Data processing pipelines
│   └── utils/                   # Shared utilities
├── tests/                       # Test suite
├── scripts/                     # Deployment and utility scripts
├── .planning/                   # GSD planning artifacts
│   ├── roadmap/                # Project roadmap
│   ├── phases/                 # Phase-specific planning
│   ├── research/               # Research phase outputs
│   └── codebase/               # Codebase mapping (this file)
├── data/                       # Data storage
├── logs/                       # Application logs
├── venv/                       # Python virtual environment
├── docker-compose.yml          # Service orchestration
├── .env                        # Configuration
├── .env.example                # Configuration template
└── main.py                     # Entry point

```

## 2. Core Module Breakdown

### 2.1 LLM Layer (`src/llm/`)

The LLM layer is the foundation of Sheppard V3, providing intelligent routing and inference capabilities.

#### `src/llm/client.py` - Multi-Host LLM Client
- **Purpose**: Unified interface to multiple LLM backends (Ollama, OpenRouter)
- **Key Classes**:
  - `LLMClient`: Main client with task-specific routing
  - `GenerationParams`: Configuration for model generation
  - Task routers: `CHAT`, `EMBEDDING`, `DECOMPOSITION`, `JUDGMENT`, `HYPER`
- **Pattern**: Split-host routing based on task type to optimize cost/performance
- **Integration Points**:
  - Connects to V2/Swarm through `SWARM_CLIENT_*
  - Reports telemetry to `METRICS_CLIENT`
  - Handles long-running tasks via `MAX_WAIT` and checkpoint/reload

#### `src/llm/embedding.py` - Embedding Management
- `EmbeddingMatcher`: Vector similarity with FAISS backend
- Caches embeddings to avoid recomputation
- Supports both local (Ollama) and remote (OpenRouter) embedding models

#### `src/llm/context.py` - Context Window Management
- `ContextBuffer`: Token-aware context management
- `ContextWriter`: Thread-safe context persistence
- Handles long conversations with intelligent truncation

### 2.2 Core Shepherd System (`src/shepherd/`)

The heart of the V3 Universal Domain Authority Foundry.

#### `src/shepherd/core.py` - Main Shepherd Engine
- `Shepherd`: Main orchestrator class
- Implements the **Triad Memory Stack**:
  - **Elastic Context Buffer (ECB)**: Working memory
  - **Long-term Memory (LTM)**: Persistent context storage
  - **Remote Provenance Store (RPS)**: External evidence tracking
- Coordinates between:
  - Pipelines (`DiscoveryPipeline`, `ValidationPipeline`, `ConsolidationPipeline`)
  - Memory systems (`SQLiteMemory`, `RedisCache`)
  - External services (Firecrawl, SearXNG, Playwright)

#### `src/shepherd/pipelines/` - Processing Pipelines
Three main pipelines provide the research automation workflow:

1. **DiscoveryPipeline**: Automated web research at scale
   - Multi-strategy search (search APIs, scraping, API ingestion)
   - Relevance filtering and deduplication
   - Extracts searchable content with Playwright for JS-heavy sites

2. **ValidationPipeline**: Quality assurance
   - Cross-validation against multiple sources
   - Credibility scoring using domain whitelists/blacklists
   - Relevancy scoring (0-100) using LLM judgment

3. **ConsolidationPipeline**: Knowledge synthesis
   - Contradiction detection and resolution
   - Confidence-weighted consolidation
   - Hyper-context generation for deep research

#### `src/shepherd/memory/` - Memory Systems
- `SQLiteMemory`: Structured memory with JSON metadata
  - Enforces schema on insert
  - Supports filtering by tags, timestamps, predicates
- `RedisCache`: High-performance cache layer
  - Stores both context buffers and parsed content
  - Auto-serialization with TTL support

#### `src/shepherd/io/` - Input/Output Handlers
- `ShepherdWriter`: Output formatting and routing
- `ShepherdPlotter`: Visualization generation
- `ShepherdDB`: Direct database access and queries

### 2.3 Semantic Web of Concepts (`src/swoc/`)

Graph-based semantic reasoning engine.

#### `src/swoc/core.py` - SWOC Main Engine
- `SWOC`: Central graph management
- `Concept`: Graph nodes with semantic tags
- `Edge`: Relationships with weights
- `Graph`: Directed graph with algorithms (PageRank, Dijkstra)
- Implements **Query→Graph→Refine** loop for semantic processing

#### `src/swoc/llm_bridge.py` - LLM Integration
- LLM-assisted graph operations:
  - Extraction from text
  - Schema validation
  - Query expansion
- Dynamic schema adaptation

#### `src/swoc/parsers.py` - Content Parsers
- `SimpleParser`: Basic text extraction
- `ReadabilityParser`: Article content extraction
- `PDFParser`: PDF document parsing
- Registry-based parser selection

#### `src/swoc/graph_viz.py` - Visualization
- Graph rendering with networkx/matplotlib
- Export to JSON for frontend consumption
- Interactive HTML output with D3.js

### 2.4 Metasystem (`src/metasystem/`)

V2 compatibility layer providing unified access to V2 capabilities.

#### `src/metasystem/core.py` - Metasystem Orchestrator
- `Metasystem`: V2/V3 bridge
- Enables V3 code to use V2 features:
  - `v2_context()`: Access context engine
  - `script()`: Execute V2 scripts
  - `run_pipeline()`: V2 pipeline execution
  - `spec()`: Schema operations
- Provides migration pathway from V2 → V3

#### `src/metasystem/debug.py` - Debugging Tools
- `Shell`: Interactive shell for V2/V3 exploration
- `InfoNode`: Structured introspection
- Trace logging for V2 compatibility issues

#### `src/metasystem/replay.py` - Replay System
- `Replayer`: Event replay for debugging
- Record/replay of V2 operations in V3 environment

### 2.5 Memory Interfaces (`src/memory/`)

Unified memory abstraction layer.

- `base.py`: Abstract interfaces
- `sqlite.py`: SQLite implementation with schema
- `redis_cache.py`: Redis cache layer
- `context_buffer.py`: ECB implementation
- `ltm.py`: Long-term memory persistence
- `rps.py`: Remote provenance store client

### 2.6 Interfaces (`src/interfaces/`)

External API endpoints and integrations.

#### `src/interfaces/api.py` - REST API
- FastAPI application
- Endpoints:
  - `/shepherd/research`: Trigger research
  - `/shepherd/status`: Pipeline status
  - `/swoc/graph`: Graph operations
  - `/memory/*`: Memory access
  - `/metrics`: System metrics

#### `src/interfaces/cli.py` - Command Line Interface
- `main()`: CLI entry point
- Commands: `research`, `query`, `graph`, `memory`
- Uses Typer for argument parsing

#### `src/interfaces/web_ui/` - Web Interface
- Minimal UI for interaction
- Uses Jinja templates
- Auto-generated forms from schemas

### 2.7 Utilities (`src/utils/`)

Shared helper functions and infrastructure.

- `logging_config.py`: Structured logging setup
- `config.py`: Configuration management
- `validation.py`: Pydantic models and validators
- `file_io.py`: Safe file operations
- `decorators.py`: Retry, circuit breaker, rate limiting
- `async_utils.py`: Async helper functions

## 3. Module Interactions & Dependencies

### 3.1 High-Level Dependency Graph

```
                    ┌─────────────────────┐
                    │   CLI / API Layer   │
                    │ (interfaces/)       │
                    └──────────┬──────────┘
                               │
                    ┌──────────▼──────────┐
                    │   Shepherd Core     │
                    │   (shepherd/)       │
                    └──────────┬──────────┘
                               │
           ┌───────────────────┼───────────────────┐
           │                   │                   │
    ┌──────▼──────┐   ┌──────▼──────┐   ┌──────▼──────┐
    │  Pipelines  │   │   Memory    │   │   LLM       │
    │  (3x)       │   │  (SQLite/   │   │  (client/   │
    │             │   │   Redis)    │   │   embed)    │
    └──────┬──────┘   └──────┬──────┘   └──────┬──────┘
           │                   │                   │
           └───────────────────┼───────────────────┘
                               │
                    ┌──────────▼──────────┐
                    │   External          │
                    │   Services          │
                    │ (Firecrawl, etc.)   │
                    └─────────────────────┘

                    ┌─────────────────────┐
                    │     SWOC            │
                    │ (Graph Engine)      │
                    └──────────┬──────────┘
                               │
                    ┌──────────▼──────────┐
                    │   Metasystem        │
                    │ (V2 Bridge)         │
                    └─────────────────────┘
```

### 3.2 Interface Contracts

**Shepherd ↔ LLM**:
- `LLMClient.generate()` returns `GenerationResult`
- `GenerationResult` includes tokens, model, stop_reason
- Shepherd provides context via prompt templates
- LLM returns JSON for structured outputs

**Shepherd ↔ Memory**:
- `Memory.store(item, metadata)`
- `Memory.query(filter) → List[Item]`
- `Memory.update(id, updates)`
- Memory backends transparently interchangeable

**Shepherd ↔ Pipelines**:
- Pipelines receive `ContextBuffer` as input
- Return enriched `ContextBuffer` as output
- Pipeline stages are async generators
- Inter-stage communication via message queues

**SWOC ↔ LLM**:
- `LLMBridge.extract_concepts(text) → List[Concept]`
- `LLMBridge.validate_schema(graph) → ValidationReport`
- `LLMBridge.expand_query(query) → ExpandedQuery`
- All bridge calls are cached

**Metasystem ↔ V2**:
- `Metasystem.v2_context()` returns context proxy
- Proxies forward calls to V2 runtime
- Maintains compatibility with V2 API signatures

## 4. Critical Infrastructure Components

### 4.1 Service Integration Points

**Firecrawl Integration** (`src/shepherd/pipelines/discovery.py`):
```python
# Multi-strategy approach:
firecrawl_results = await self.firecrawl.scrape(url)
api_ingestion = await self.api_client.fetch(endpoint)
playwright_content = await self.playwright_renderer.render(js_page)
```

**SearXNG Integration**:
- Privacy-respecting search aggregation
- Multiple instance fallback
- Result deduplication

**Redis Caching**:
- Context buffers: `redis://localhost:6379/0`
- Embeddings: `redis://localhost:6379/1`
- TTL: 1 hour for context, 24 hours for embeddings

**SQLite Memory**:
- Path: `data/memory.db`
- Schema: `items(id, content, metadata, created_at, updated_at)`
- Indices: `metadata`, `created_at` for query performance

### 4.2 Configuration System

Configuration hierarchy:
1. `config.py` defaults
2. Environment variables (`.env`)
3. Runtime overrides (function parameters)

Key settings:
- `OLLAMA_HOST` / `OPENROUTER_API_KEY`
- `DATABASE_URL` / `REDIS_URL`
- `FIRECRAWL_API_KEY` / `SEARXNG_ENDPOINT`
- `MAX_TOKENS` / `BATCH_SIZE`
- `LOG_LEVEL` / `METRICS_ENABLED`

## 5. Startup & Initialization Flow

```
1. Load configuration from .env
2. Initialize Redis connection
3. Initialize SQLite database
4. Create LLMClient with routing rules
5. Instantiate Memory backends
6. Build Pipeline objects
7. Initialize SWOC graph
8. Start FastAPI server or CLI
9. Background tasks: metrics collection, cache cleanup
```

## 6. Data Flow Examples

### 6.1 Research Request Flow

```
User → API / CLI
  ↓
Shepherd.research(topic)
  ↓
DiscoveryPipeline (search + scrape)
  ↓ store in SQLiteMemory
ValidationPipeline (cross-check + score)
  ↓ update memory items
ConsolidationPipeline (synthesize)
  ↓ generate final report
Output to user / file
```

### 6.2 Graph Query Flow

```
Query → LLMBridge.expand_query()
  ↓
SWOC.graph.query(expanded)
  ↓
Graph algorithms (PageRank, Dijkstra)
  ↓
Ranked results with confidence scores
  ↓
User receives structured response
```

## 7. Testing Structure

Tests mirror source structure:
```
tests/
├── llm/              # Client and embedding tests
├── shepherd/         # Core and pipeline tests
├── swoc/             # Graph engine tests
├── metasystem/       # V2 bridge tests
├── integration/      # End-to-end tests
└── fixtures/        # Test data and mocks
```

Test types:
- Unit tests with mock LLM responses
- Integration tests with test containers
- Pipeline tests with sample datasets
- Performance benchmarks

## 8. Deployment Considerations

- Dockerfile provided for containerized deployment
- docker-compose.yml for local development with all services
- Production: systemd service or Kubernetes deployment
- Monitoring: Prometheus metrics endpoint
- Logging: Structured JSON to stdout for log aggregation

## 9. Development Workflow

1. Clone repository and create virtualenv
2. Copy `.env.example` to `.env` and configure
3. Run `docker-compose up -d` for dependencies
4. Install dependencies: `pip install -e .`
5. Run tests: `pytest tests/`
6. Start development server: `python -m interfaces.api`
7. Make changes and iterate

## 10. Future Structure Evolution

Planned architectural changes:
- Separate microservices for each pipeline
- Message queue (RabbitMQ/Kafka) for async coordination
- Separate read/write database replicas
- Distributed tracing with OpenTelemetry
- Plugin system for custom pipelines
