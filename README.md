<p align="center">
  <img src="https://img.shields.io/github/stars/B-A-M-N/Sheppard?style=for-the-badge&color=gold" alt="Stars">
  <img src="https://img.shields.io/github/forks/B-A-M-N/Sheppard?style=for-the-badge&color=lightblue" alt="Forks">
  <img src="https://img.shields.io/github/license/B-A-M-N/Sheppard?style=for-the-badge&color=blue" alt="License">
  <img src="https://img.shields.io/badge/python-3.10+-blue?style=for-the-badge&logo=python" alt="Python">
  <img src="https://img.shields.io/badge/Ollama-Local%20LLM-green?style=for-the-badge" alt="Ollama">
</p>

<h1 align="center">Sheppard Agency V3</h1>
<p align="center">
  <b>AI research agent for Ollama</b><br>
  <i>Search, scrape, extract, and synthesize knowledge — all on local hardware.</i>
</p>

---

## What It Is

Sheppard is an async Python chat agent backed by Ollama that can do two things:

1. **Chat** — normal conversation with persistent memory across sessions
2. **Research** — give it `/learn <topic>` and it will search, scrape, extract, and synthesize knowledge on that topic, storing everything in a structured memory system

The research pipeline works like this:

- **Searches** via SearXNG to find relevant sources
- **Scrapes** them via Firecrawl (local) with Playwright
- **Distills** content into structured knowledge atoms — facts, claims, contradictions
- **Stores** everything in Postgres + ChromaDB + Redis
- **Generates** citable reports on demand

> Benchmarked at **82.0/100** on research and memory tasks — i9-12900K, 32GB DDR5, RTX A4000.

## Tech Stack

| Component | Role |
|-----------|------|
| [Ollama](https://ollama.com) | Local LLM inference (rnj-1:8b default, configurable) |
| [PostgreSQL](https://www.postgresql.org) | Structured storage — topics, sources, atoms, lineage |
| [ChromaDB](https://www.trychroma.com) | Semantic vector search for RAG retrieval |
| [Redis](https://redis.io) | Scraping queue, distributed locks, volatile state |
| [Firecrawl](https://github.com/mendableai/firecrawl) (local) | Web scraper with built-in Playwright |
| [SearXNG](https://docs.searxng.org) | Self-hosted search engine for discovery |

## Memory Design

```
Postgres  →  Canonical truth. Topics, sources, atoms, lineage.
ChromaDB  →  Semantic projections. Fast similarity search for RAG.
Redis     →  Operational state. Scraping queue, locks, caching.
```

ChromaDB is treated as a projection — it can be wiped and rebuilt from Postgres at any time.

## Quick Start

### Requirements

- Python 3.10+
- PostgreSQL 14+ (with `btree_gin` extension)
- Redis 6.2+
- Ollama (local or remote)
- Firecrawl-Local
- SearXNG

### Setup

```bash
# 1. Clone and install
git clone https://github.com/B-A-M-N/Sheppard.git
cd Sheppard
pip install -r requirements.txt

# 2. Start supporting services
./start_research_stack.sh

# 3. Initialize database schema
python3 src/memory/setup_v3.py

# 4. Run the agent
python3 main.py
```

### Commands

| Command | Description |
|---------|-------------|
| `/learn <topic>` | Start a background research mission |
| `/stop` | Stop an active mission |
| `/missions` | View mission status |
| `/nudge <instruction>` | Adjust research direction mid-mission |
| `/query <topic>` | Ask questions about previously learned topics |
| `/report <id>` | Generate a synthesis report from stored knowledge |
| `/status` | View system health and backlog |

## Architecture

### Research Pipeline

```
  Discovery          Acquisition          Condensation         Storage            Synthesis
┌─────────────┐    ┌───────────────┐    ┌───────────────┐    ┌──────────┐    ┌───────────────┐
│  SearXNG    │───▶│  Firecrawl    │───▶│  LLM Extract  │───▶│  Postgres│───▶│  Report Gen   │
│  search     │    │  + Playwright │    │  atoms        │    │  Chroma  │    │  w/ citations │
└─────────────┘    └───────────────┘    └───────────────┘    └──────────┘    └───────────────┘
                                                                  ▲
                                                                  │
                                                              Redis (queue)
```

1. **Discovery** — SearXNG returns results across multiple pages
2. **Acquisition** — Firecrawl scrapes pages via Playwright; PDFs offloaded to slower workers
3. **Condensation** — LLM extracts structured atoms (facts, claims, tradeoffs) from raw content
4. **Storage** — Atoms stored in Postgres with full source lineage; embeddings indexed in ChromaDB
5. **Synthesis** — Evidence assembler pulls relevant atoms and generates citable reports

### Project Structure

```
Sheppard/
├── main.py                    # Entry point — interactive chat loop
├── scout_worker.py            # Auxiliary scraping worker
├── start_research_stack.sh    # Service bootstrap
├── requirements.txt
├── src/
│   ├── core/
│   │   ├── sheppard/          # Chat agent, response generation, tool usage
│   │   ├── commands.py        # Slash command handler
│   │   ├── memory/            # Storage adapters (Postgres, Chroma, Redis)
│   │   └── system.py          # System initialization and lifecycle
│   ├── research/
│   │   ├── acquisition/       # Firecrawl client, search, crawling
│   │   ├── condensation/      # Knowledge distillation pipeline
│   │   ├── reasoning/         # Evidence assembly and report synthesis
│   │   ├── archivist/         # Research loop, chunking, indexing
│   │   └── config.py          # Research system configuration
│   ├── memory/
│   │   ├── manager.py         # Memory coordination (PG + Chroma)
│   │   ├── stores/            # Individual store adapters
│   │   └── schema_v3.sql      # Database schema
│   ├── llm/                   # Ollama client, model routing
│   └── config/                # Application settings
└── tests/
```

## Design Principle

> *Postgres is Truth. Chroma is a projection. Redis is motion. Lineage is permanent.*

## Acknowledgments

- **[Dallan Loomis](https://github.com/DallanL)** — for the interactions and guidance that kept this project on track
- **My parents** — for the support that made all of this possible
- **My son** — the reason I build

## License

[MPL-2.0](LICENSE)
