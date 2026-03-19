# Sheppard V2 — Architecture & Implementation Roadmap

## What's Built (Scaffolded)

```
sheppard_v2/
├── main.py                        ✅ CLI entry point + command handler
├── core/
│   └── system.py                  ✅ System orchestrator (ties everything together)
├── acquisition/
│   ├── budget.py                  ✅ Pressure-valve budget monitor
│   └── crawler.py                 ✅ Firecrawl-local async wrapper
├── condensation/
│   └── pipeline.py                ✅ 4-phase on-the-fly condensation
├── reasoning/
│   └── retriever.py               ✅ Multi-strategy hybrid retriever
├── llm/
│   └── model_router.py            ✅ Task → model mapping
└── memory/
    └── schema.sql                 ✅ Full Postgres schema (concepts, graph, citations)
```

## What Needs to Be Built Next (Priority Order)

### 1. `memory/manager.py`  ← BUILD THIS FIRST
The MemoryManager is the most-depended-on component.
Everything calls into it.

Methods needed:
- `initialize()` — connect ChromaDB + Postgres
- `create_topic(name, description)` → topic_id
- `update_topic_status(topic_id, status)`
- `store_source(topic_id, url, title, content, raw_bytes, checksum, domain, source_type, raw_file_path)`
- `get_uncondensed_sources(topic_id, limit)` → list of source dicts
- `mark_sources_condensed(source_ids)`
- `store_chunk(topic_id, source_id, source_url, chunk_index, summary, embedding, metadata)` → chunk_id
- `store_synthesis(topic_id, content, embedding, source_chunk_ids)`
- `upsert_concept(topic_id, name, concept_type, definition, importance)` → concept_id
- `upsert_relationship(topic_id, source_concept_name, target_concept_name, relationship, weight)`
- `find_concepts_by_text(query_text, topic_id, limit)` → list of concept dicts
- `traverse_concept_graph(concept_id, max_depth)` → list (uses recursive CTE from schema.sql)
- `search_citations(query_text, topic_id, limit)` → list
- `get_project_concept_applications(project_name, query_text, limit)` → list
- `create_project(name, local_path, repo_url)` → project_id
- `index_project_files(project_id, project_name, local_path)` — walks dir, chunks, embeds
- `log_condensation(report)`
- `chroma_query(collection, query_text, n_results, where)` → ChromaDB result dict
- `cleanup()`

### 2. `llm/client.py`
Async Ollama wrapper.

Methods needed:
- `initialize()` — verify Ollama running + models available
- `embed(text)` → List[float]
- `complete(model, prompt, max_tokens)` → str
- `chat_stream(model, messages, system_prompt)` → AsyncGenerator[str]

Note: model name is passed in from model_router, client is model-agnostic.

### 3. `core/commands.py` (optional enhancement)
Richer command parsing, history, autocompletion.
Can use `prompt_toolkit` for this.

### 4. `acquisition/scheduler.py`
Job queue for multiple concurrent topic crawls.
Useful once you're running 3-4 topics simultaneously.

---

## Key Design Decisions Already Made

| Decision | Choice | Reason |
|---|---|---|
| Storage budget | Condense on-the-fly | Never stop crawling |
| Condensation trigger | 3 thresholds (70/85/95%) | Graduated response |
| Graph database | Postgres recursive CTEs | No Neo4j dependency |
| Vector store | ChromaDB | Already in Sheppard |
| Hot cache | Redis (existing) | Sheppard already uses it |
| Academic filter | Ivory Tower whitelist | From Archivist |
| Project context | Separate ChromaDB collection per project | Clean isolation |

---

## Condensation Compression Targets

| Phase | What it does | Typical reduction |
|---|---|---|
| Phase 1: Dedup | Removes near-identical content | 30-40% |
| Phase 2: Chunk summarize | 2000-word chunks → 200-word summaries | 85-90% of remainder |
| Phase 3: Synthesis | Cross-source integration | Minor additional reduction |
| Phase 4: Concept extract | Structured knowledge to Postgres | Supplementary |

Combined target: **~10% of original raw size** stored as condensed knowledge.

---

## Model Assignment

| Task | Default Model | Env Var |
|---|---|---|
| Embedding | mxbai-embed-large | OLLAMA_EMBED_MODEL |
| Chunk summarization | llama3.2:1b | OLLAMA_SUMMARIZE_MODEL |
| Synthesis + concept extraction | llama3.1:8b | OLLAMA_SYNTHESIS_MODEL |
| Chat (main) | mannix/dolphin-2.9-llama3-8b | OLLAMA_MODEL |

---

## Retrieval Strategy Weights

When retrieving for a reasoning conversation, results are scored as:

```
project_context × 1.1   ← highest (most actionable)
semantic_search × 1.0
citation_lookup × 0.9
concept_graph   × 0.85  ← weighted lower, useful for discovery
```

---

## Environment Variables

```env
# Ollama
OLLAMA_MODEL=mannix/dolphin-2.9-llama3-8b:latest
OLLAMA_EMBED_MODEL=mxbai-embed-large
OLLAMA_SUMMARIZE_MODEL=llama3.2:1b
OLLAMA_SYNTHESIS_MODEL=llama3.1:8b
OLLAMA_API_BASE=http://localhost:11434

# Firecrawl-local
FIRECRAWL_LOCAL_URL=http://localhost:3002
FIRECRAWL_API_KEY=local

# Postgres
POSTGRES_DSN=postgresql://user:password@localhost:5432/sheppard_v2

# ChromaDB
CHROMADB_PERSIST_DIRECTORY=./data/chromadb
CHROMADB_DISTANCE_FUNC=cosine

# Redis
REDIS_HOST=localhost
REDIS_PORT=6379

# Budget
BUDGET_CEILING_GB=5
BUDGET_THRESHOLD_LOW=0.70
BUDGET_THRESHOLD_HIGH=0.85
BUDGET_THRESHOLD_CRITICAL=0.95
BUDGET_POLL_SECS=10

# Storage
RAW_DATA_DIR=./data/raw
DATA_DIR=./data
LOG_DIR=./logs
```

---

## Project Indexing (Future DB Connection)

When you're ready to connect SOLLOL, FlockParser, etc.:

```
/project index SOLLOL /path/to/sollol
/project index FlockParser /path/to/flockparser
```

This will:
1. Walk the directory tree for .py, .md, .txt, .json files
2. Chunk each file by function/class boundaries
3. Embed chunks into `project_sollol` ChromaDB collection
4. Create a Postgres project record for cross-referencing

Then in chat:
```
How does consistent hashing apply to SOLLOL's routing? --project=SOLLOL
```

Sheppard will retrieve both generic knowledge about consistent hashing
AND SOLLOL-specific code context, synthesizing across both.
