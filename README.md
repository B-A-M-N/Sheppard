<p align="center">
  <img src="https://img.shields.io/github/stars/B-A-M-N/Sheppard?style=for-the-badge&color=gold" alt="Stars">
  <img src="https://img.shields.io/github/forks/B-A-M-N/Sheppard?style=for-the-badge&color=lightblue" alt="Forks">
  <img src="https://img.shields.io/github/license/B-A-M-N/Sheppard?style=for-the-badge&color=blue" alt="License">
  <img src="https://img.shields.io/badge/python-3.10+-blue?style=for-the-badge&logo=python" alt="Python">
  <img src="https://img.shields.io/badge/Ollama-Local%20LLM-green?style=for-the-badge" alt="Ollama">
</p>

<h1 align="center">Sheppard V3</h1>
<p align="center">
  <b>Local research, knowledge distillation, grounded retrieval, and applied reasoning</b><br>
  <i>Learn from the web. Build a reusable knowledge base. Use it to answer, analyze, and report.</i>
</p>

---

## What Sheppard Is

Sheppard is a self-hosted research and reasoning system that runs on local infrastructure.

It is not just a chatbot and not just a crawler. It is a full loop:

1. **Discover** topics and sources
2. **Acquire** pages and documents from the web
3. **Distill** them into structured knowledge atoms with lineage
4. **Store** them in a durable knowledge base
5. **Retrieve** evidence with trust-aware ranking
6. **Reason** over that evidence for chat, analysis, and report generation

The system is built to accumulate knowledge across missions instead of throwing context away every turn.

---

## What It Does

Sheppard currently supports four primary operating modes:

### 1. Learning Missions

`/learn <topic>` starts a background research mission.

That mission can:

- search via SearXNG
- crawl and scrape via Firecrawl (with internal browser automation via Playwright)
- queue sources through Redis-backed ingestion control
- extract structured atoms from source text
- attach provenance, confidence, importance, and trust signals
- persist results in Postgres and project them into Chroma
- expand breadth/depth through frontier node generation and follow-on topic discovery

The output is not a bag of raw text. It is a mission-scoped and corpus-wide knowledge substrate.

When a frontier cycle produces `round_yield >= 5`, the system may branch into follow-on frontier nodes to expand exploration breadth.

### 2. Retrieval-Augmented Chat

Normal chat is grounded in the stored knowledge base.

On each turn, Sheppard can:

- run canonical V3 retrieval against stored atoms
- build a context block from retrieved evidence
- add CMK reasoning overlays when available
- maintain session-scoped working state across turns
- escalate from ordinary chat to deeper analysis when cognitive pressure or user intent warrants it

### 3. Applied Analysis

`/analyze <problem>` runs a deliberate reasoning pipeline rather than just generating prose.

That path includes:

- problem framing
- targeted retrieval
- evidence assembly
- Analyst synthesis
- Adversarial Critic challenge pass

The goal is not “a nice answer.” The goal is a grounded diagnosis, recommendation, objections, and residual uncertainty.

### 4. Report Generation

`/report` produces a longer-form research artifact from accumulated evidence.

This path uses:

- deterministic derived claims
- evidence graph assembly
- section planning
- synthesis under citation and grounding constraints

---

## Core Capabilities

### Durable Knowledge Accumulation

Sheppard stores learned material in Postgres as the canonical source of truth.

- missions are durable
- sources are durable
- chunks are durable
- atoms are durable
- contradictions, authority state, and lineage are durable

Chroma is a projection for semantic lookup. Redis is used for runtime motion, queues, and volatile state.

### Trust-Aware Retrieval

Retrieval is not simple vector search.

The V3 retriever combines:

- semantic relevance
- lexical relevance
- authority/trust-state signals
- contradiction-aware handling
- gap-driven second-pass retrieval

This allows the system to retrieve not only “similar” content, but also contested or missing evidence that matters to the query.

### CMK: Cognitive Memory Kernel

The CMK layer adds corpus-level and session-level cognition on top of the base retrieval system.

It includes:

- concept clustering
- atom activation / recency-sensitive working memory
- contradiction detection
- belief graph structures
- meta-cognition hooks
- session runtime state for ongoing conversations

In practice, this means Sheppard can preserve short-term conversational context while still grounding answers in long-term stored knowledge.

### Session-Scoped Working Memory

Chat is not fully stateless anymore.

The session layer tracks things like:

- inferred user intent
- active concepts
- active contradictions
- soft hypotheses
- escalation pressure
- mission/topic scope

This state is session-scoped and intentionally volatile. It helps continuity without polluting the durable knowledge store.

### Automatic Local Startup

On launch, Sheppard can attempt to start local dependencies automatically when configured to do so.

That includes:

- PostgreSQL
- Redis
- Ollama
- the local research stack used for acquisition

The web app now exposes startup state through `/health`, and startup progress is reported stage-by-stage instead of silently hanging.

---

## High-Level Architecture

``` 
Discovery        Acquisition        Distillation         Storage             Retrieval/Reasoning
┌──────────┐    ┌──────────────┐   ┌───────────────┐   ┌───────────────┐   ┌──────────────────────┐
│ SearXNG  │───▶│ Firecrawl    │──▶│ Extraction +  │──▶│ Postgres      │──▶│ V3 Retriever         │
│ search   │    │ + Playwright │   │ consolidation │   │ Chroma        │   │ Analysis / Reports   │
└──────────┘    └──────────────┘   └───────────────┘   │ Redis runtime │   │ CMK session bridge   │
                          │                             └───────────────┘   └──────────────────────┘
                          │
                          ▼
                     Frontier logic
                 breadth/depth branching
```

---

## Tech Stack

| Component | Role |
|-----------|------|
| [Ollama](https://ollama.com) | Local LLM inference, embeddings, and task-specific generation |
| [PostgreSQL](https://www.postgresql.org) | Canonical knowledge store |
| [ChromaDB](https://www.trychroma.com) | Vector projection for semantic retrieval |
| [Redis](https://redis.io) | Runtime queues, locks, state, ingestion flow |
| [Firecrawl](https://github.com/mendableai/firecrawl) | Local scraping and page extraction |
| [Playwright](https://playwright.dev) | Internal browser automation used by the local acquisition stack |
| [SearXNG](https://docs.searxng.org) | Self-hosted search and discovery |
| FastAPI + WebSockets | Web UI, streaming chat/analyze/logs endpoints |

> Postgres is truth. Chroma is projection. Redis is motion.

---

## Reasoning Model

### Retrieval

The canonical path is the V3 retriever.

It:

- pulls evidence from the stored corpus
- reranks by trust and authority
- surfaces contradictions
- assembles an evidence packet
- can perform a bounded follow-up pass to fill missing evidence gaps in `EvidenceAssembler._build_from_context()`

### Analysis

The analysis path is for decisions and problem-solving, not just Q&A.

It uses:

1. problem framing
2. evidence retrieval
3. evidence assembly
4. Analyst output
5. Adversarial Critic output

### Derived Claims

Some claims are produced deterministically rather than by the LLM.

The derivation engine currently supports seven rule families:

- `delta`
- `percent_change`
- `rank`
- `ratio`
- `chronology`
- `simple_support_rollup`
- `simple_conflict_rollup`

These are traceable back to source atoms.

---

## Interfaces

### Terminal / TUI Commands

| Command | Description |
|---------|-------------|
| `/help` | Show available commands |
| `/health` | Show startup/backend health |
| `/learn <topic>` | Start a background research mission |
| `/stop <mission_id>` | Stop or cancel a mission |
| `/missions` | View mission status |
| `/knowledge` | View stored knowledge topics |
| `/query <text>` | Query the knowledge base |
| `/analyze <problem>` | Run the analysis pipeline |
| `/report <mission>` | Generate a report from stored evidence |
| `/status` | Show runtime system status |

### Web UI

The web UI provides:

- streaming chat
- streaming analysis
- mission dashboard
- knowledge graph and atom browser
- log streaming
- health endpoint at `/health`

Key routes:

- `/` - SPA
- `/health` - startup and backend health
- `/api/missions`
- `/api/knowledge/stats`
- `/api/ws/chat`
- `/api/ws/analyze`
- `/api/ws/logs`

---

## Startup Behavior

Running:

```bash
python web.py
```

starts the FastAPI server and schedules backend initialization in the background.

During startup:

- the app can serve immediately
- `/health` reports readiness and current startup stage
- local dependencies may be auto-started
- backend routes become fully functional once `ok: true`

If startup is still in progress, `/health` will show the current stage, such as migration application or subsystem initialization.

---

## Quick Start

### Requirements

- Python 3.10+
- PostgreSQL
- Redis
- Ollama
- local research stack for acquisition (`Firecrawl`, `Playwright`, `SearXNG`)

### Setup

```bash
git clone https://github.com/B-A-M-N/Sheppard.git
cd Sheppard
pip install -r requirements.txt
python3 src/memory/setup_v3.py
python web.py
```

### Health Check

After launch:

```bash
curl http://127.0.0.1:8000/health
```

or use:

```text
/health
```

in the terminal or web command layer.

---

## Project Structure

```
Sheppard/
├── main.py
├── web.py
├── src/
│   ├── core/
│   │   ├── system.py
│   │   ├── chat.py
│   │   ├── commands.py
│   │   └── memory/
│   │       └── cmk/
│   │           ├── runtime.py
│   │           ├── session_runtime.py
│   │           ├── chat_bridge.py
│   │           ├── belief_graph.py
│   │           ├── contradiction_detector.py
│   │           └── meta_cognition.py
│   ├── research/
│   │   ├── acquisition/
│   │   ├── condensation/
│   │   ├── derivation/
│   │   ├── graph/
│   │   ├── reasoning/
│   │   └── archivist/
│   ├── memory/
│   │   ├── storage_adapter.py
│   │   └── adapters/
│   ├── web/
│   │   ├── server.py
│   │   ├── routes/
│   │   └── static/
│   └── llm/
└── tests/
```

---

## What Sheppard Is Capable Of

Today, the system is capable of:

- running long-lived research missions
- extracting and storing structured knowledge from crawled sources
- maintaining a growing local knowledge base
- grounding chat responses in retrieved evidence
- producing analysis with recommendation and critique
- generating longer-form evidence-based reports
- tracking mission state and knowledge statistics through the web UI
- preserving session-scoped conversational state
- surfacing startup health and runtime status

What it is not trying to be:

- a generic cloud SaaS assistant
- a pure vector-search wrapper
- a stateless prompt shell

It is an accumulative local research system with applied reasoning on top.

---

## Notes

- Postgres is the canonical store.
- Chroma can be rebuilt from canonical data.
- Redis-backed runtime state is intentionally volatile.
- Some parts of the cognitive architecture are still heavier scaffolding than always-on runtime logic; the system keeps those paths bounded to avoid making every chat turn expensive.

---

## Acknowledgments

- **[Dallan Loomis](https://github.com/DallanL)** — for the interactions and guidance that kept this project on track
- **My parents** — for the support that made all of this possible
- **My son** — the reason I build

## License

[MPL-2.0](LICENSE)
