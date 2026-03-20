First and foremost, a special thanks to:

Dallan Loomis (https://github.com/DallanL): without your interactions and heads up, I would still somewhat be lost and trying to figure things out more some. 

My parents: without your support, I would be dead in the water.

and My son: without you, I would be dead period. 
______________________________________________________________
Benchmark Results Summary:
Research Effectiveness: 71.4/100
Memory Effectiveness: 100.0/100
System Integration: 73.3/100
Overall Score: 82.0/100

Results Interpretation:
----------------------
Research Effectiveness (71.4/100):
  - GOOD: Research system is performing well.

Memory Effectiveness (100.0/100):
  - GOOD: Memory system is performing well.
  - Consider optimizing recall speed for better performance.

System Integration (73.3/100):
  - GOOD: Systems are well integrated.
  - Consider optimizing multi-step reasoning capabilities.

Overall System Performance (82.0/100):
  - GOOD: System is performing well overall.
  - Focus on fine-tuning specific capabilities for optimal performance.
**THESE RESULTS ONLY REFLECT THE RESEARCH FUNCTION OF THE APPLICATION

*On an i9-12900k 32gb 6000mhz DDR5, a4000 16gb GPU, running PopOS! on 4tb gen 4 silicone power m2.
______________________________________________________________

# Sheppard Agency V3: Universal Domain Authority Foundry

## Overview
Sheppard Agency V3 is a **Universal Domain Authority Foundry**. It is an agentic research institute that recursively "eats" complex technical subjects, distilling vast amounts of distributed web data into high-fidelity, structured Knowledge Atoms. 

V3 introduces a **Distributed Triple-Engine Architecture** designed for non-blocking, asynchronous research at massive scales.

## Core Architecture (V3 Triad)

Sheppard V3 enforces a strict **Triad Memory Stack** to ensure canonical truth, semantic speed, and operational heat:
1.  **Postgres (The Truth):** The immutable system of record for all identity, structure, and lineage.
2.  **Chroma (The Proximity):** Semantic projections used exclusively for discovery and RAG.
3.  **Redis (The Motion):** Volatile state, distributed locks, and the global scraping queue.

### 1. The Adaptive Frontier (Intelligence)
- **Taxonomic Decomposition:** Generates deep technical research trees (15-50 nodes) to exhaustively map a subject.
- **Epistemic Modes:** Dynamically selects between **Grounding**, **Verification**, **Dialectic**, and **Expansion**.
- **Deep Mine Discovery:** Automatically scans multiple search pages (Page 1-5) via a **Parallel Discovery Race** to find obscure technical ore.

### 2. Distributed "Vampire" Metabolism (Acquisition)
Bypasses hardware bottlenecks and rate limits with a decentralized scraping swarm:
- **Global Redis Queue:** Discovered URLs are pushed to `queue:scraping` for distributed consumption.
- **Parallel Vampires:** 8-12 concurrent local workers on the main machine feast on the queue.
- **Scout Offloaders:** Passive nodes (Laptops, remote servers) pull from the same queue to "vampire" slow PDFs and static sites on separate IPs.

### 3. The Smelter (Refinery)
- **Atomic Distillation:** Sources are smelted sequentially into standalone **Knowledge Atoms** (Facts, Claims, Tradeoffs).
- **Native JSON Recovery:** Nuclear repair logic for malformed local LLM responses ensures zero-crash extraction.
- **Lineage First:** Every atom maintains an immutable link back to its source research mission and evidence.

## Distributed Topology

| Node | Role | Hardware Profile |
| :--- | :--- | :--- |
| **Main Brain** | Orchestrator / DBs | Ryzen 5900X, 64GB, RTX 3090 |
| **Reasoning Rig** | Heavy Inference / Extraction | Remote Node (.90) - Uncensored 8B Models |
| **Vampire Scout** | High-Core Scraper / Summarizer | 20-Core Node (.154) - Scraping Swarm |
| **Lazy Scout** | Stealth / Slow-Lane Offloader | i5 Laptop (.45) - PDF/Static Processing |

## Installation

### Requirements
- Python 3.10+
- PostgreSQL 14+ (with `btree_gin` extension)
- Redis 6.2+
- Ollama (Distributed or Local)
- Firecrawl-Local & SearXNG

### Quick Start
1.  **Start Services:** `./start_research_stack.sh`
2.  **Initialize V3 Memory:** `python3 src/memory/setup_v3.py` (Applies `schema_v3.sql`)
3.  **Launch Brain:** `python3 main.py`
4.  **Unleash Workers:** `python3 scout_worker.py` (On all auxiliary nodes)

## Commands
- `/learn <topic>` - Trigger a Deep Accretive Mission.
- `/status` - View the smelting backlog and vampire health.
- `/nudge <instruction>` - Steer the frontier in real-time.
- `/report <id>` - Generate a Tier 4 Master Brief from extracted atoms.

## Design Principle
> *Postgres is Truth. Chroma is a projection. Redis is motion. Lineage is permanent.*

## Licensing
Core functionality is licensed under the Mozilla Public License 2.0.
