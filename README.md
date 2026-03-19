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

# Sheppard Agency V2

## Overview
Sheppard Agency is a **Recursive Knowledge Distillery** and agentic research engine. It is designed to act as a permanent, local-only research institute that "eats" subjects by recursively searching, ingesting, and distilling vast amounts of web data into high-fidelity technical memory.

Unlike thin search agents, Sheppard V2 uses an **Adaptive Research Metabolism** to saturate its understanding of a domain until it reaches a state of expertise.

## Core Architecture

### 1. The Adaptive Frontier (Intelligence)
The system no longer follows a fixed search pattern. At the start of every mission, it asks itself: *"What counts as Authority and Evidence for this specific subject?"*
- **Taxonomic Decomposition:** Generates 20-30 granular technical nodes per mission.
- **Epistemic Modes:** Dynamically selects between **Grounding** (facts), **Verification** (proof), **Dialectic** (disputes), and **Expansion** (context).
- **Agentic Growth:** Spawns new research nodes automatically when it detects high-density information pockets.

### 2. Local Research Stack (Acquisition)
Bypasses cloud latencies and rate limits with a fully local acquisition pipeline:
- **SearXNG:** Private discovery at `http://localhost:8080`.
- **Firecrawl-Local:** Precision extraction at `http://localhost:3002`.
- **Playwright Stealth:** High-evasion browsing at `http://localhost:3003`.
- **Recursive Depth:** Follows links up to 5 levels deep into technical documentation and bibliographies.

### 3. The 5-Layer Cognitive Stack (Memory)
Data is refined through five distinct layers, each with its own **Redis (6370-6374)** and **PostgreSQL** instance:
- **Ephemeral:** Working memory for the current task.
- **Contextual:** Session-based conversational memory.
- **Episodic:** Chronological history of research cycles.
- **Semantic:** Knowledge Atoms, technical facts, and cited claims.
- **Abstracted:** The "10% Signal"—Master reports and high-level syntheses.

### 4. Differential Distillery (Condensation)
- **10% Rule:** Designed to ingest 10GB of raw data and distill it into ~1GB of Knowledge Atoms.
- **Differential Mining:** Compares similar sources to extract unique technical claims rather than just summarizing.
- **Conflict First:** Explicitly identifies and preserves contradictions between sources.

## Installation

### Requirements
- Python 3.10+
- PostgreSQL 14+
- Redis 6.2+
- Ollama (Local)
- Firecrawl-Local & SearXNG (Local)

### Local Services Setup
Run the unified research stack:
```bash
./start_research_stack.sh
```

### Sheppard Setup
1. Install dependencies: `pip install -r requirements.txt`
2. Initialize memory stores: `sudo python3 server_setup.py`
3. Configure `.env` (Default model: `rnj-1:8b-cloud`)

## Commands

### Accretive Research
- `/learn <topic> [--ceiling=GB] [--academic]` - Start a recursive background mission to exhaust a subject.
- `/status` - View the full dashboard, mission quotas, and **Scout Queue**.
- `/distill <id>` - Manually trigger a distillation pass on ingested data.

### Interaction & Query
- `/query <text>` - Search the 4-tier knowledge stack with hybrid Lexical/Semantic retrieval.
- `/r <topic> --deep` - Perform a single-shot agentic research dive (Archivist-style).
- `/memory search <query>` - Direct search into your persistent life-history.

### System Control
- `/settings` - Configure models, temperatures, and timeouts.
- `/clear` - Wipe current conversation context.
- `/exit` - Graceful shutdown of all background tasks.

## Design Principle
> *Coverage before compression, diversity before certainty, contradiction before consensus, and lineage before deletion.*

## Licensing
Core functionality is licensed under the Mozilla Public License 2.0. Enterprise features require a commercial license. Contact benevolentjoker@gmail.com for inquiries.
