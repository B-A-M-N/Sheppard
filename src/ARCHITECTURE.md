# Sheppard V3 — Architectural Blueprint

Sheppard V3 is a **Universal Domain Authority Foundry**. It is designed to transform raw, unstructured web data into verified technical authority records through a strict multi-layer processing pipeline.

## 1. The V3 Triad (Memory Hierarchy)

V3 abandons monolithic memory in favor of a **Responsibility-Driven Triad**. Every piece of data has a canonical owner and a projected purpose.

### **Layer 1: Postgres (Canonical Truth)**
- **Schema Namespaces:** `config`, `mission`, `corpus`, `knowledge`, `authority`, `application`.
- **Role:** Owns identity (UUIDs), structural relationships (Foreign Keys), temporal lineage (`created_at`), and the "Gold Record."
- **Constraint:** If it's not in Postgres, it doesn't exist.

### **Layer 2: Chroma (Semantic Discovery)**
- **Collections:** `corpus_chunks`, `knowledge_atoms`, `authority_records`.
- **Role:** Purely for high-speed semantic proximity. Used for RAG retrieval and deduplication.
- **Invariant:** Chroma is a **Projection** of Postgres. It can be wiped and reconstructed from Postgres rows at any time.

### **Layer 3: Redis (Operational Heat)**
- **Role:** Owns volatile state, the **Global Scraping Queue**, distributed locks, and hot-caching of active research nodes.
- **Distributed:** Nodes (.45, .90, .154) all communicate via the Main PC's Redis instances.

---

## 2. Distributed "Vampire" Metabolism

Acquisition is decoupled from orchestration to allow for massive parallel ingestion.

1.  **The Producer (Frontier):**
    - Runs on the Main PC.
    - Designs the research tree (15-50 nodes).
    - Performs **Discovery Races** (hitting all SearXNG nodes in parallel).
    - Pushes unique URLs to Redis `queue:scraping`.
2.  **The Consumers (Vampire Swarm):**
    - Workers run on any available hardware.
    - Each node runs its own local **Firecrawl** instance to bypass IP rate limits.
    - Workers "vampire" URLs from the Redis queue and push finished Markdown back to the Main PC's Postgres.

---

## 3. The Sequential Smelter (Refinery)

Distillation is performed via a sequential-atomic smelting process to ensure the highest possible extraction quality from 8B models.

- **Atomic Extraction:** Documents are processed one-by-one to minimize context window noise.
- **Validated Smelting:** Every extracted fact is passed through the `JSONValidator` for schema compliance and iterative repair.
- **Lineage Binding:** Every **Knowledge Atom** is permanently linked to its `source_id` and `mission_id` in the relational tables.

---

## 4. Multi-Model Hardware Topology

Tasks are routed based on hardware suitability:

| Task | Model | Hardware |
| :--- | :--- | :--- |
| **Reasoning / Chat** | `llama3.1-8b-lexi` | Remote Brain (.90) - Uncensored |
| **Smelting (Extraction)** | `llama3.1-8b-lexi` | Remote Brain (.90) - High Precision |
| **Summarization** | `llama3.2:latest` | Scouter Node (.154) - Parallel Muscle |
| **Embeddings** | `mxbai-embed-large` | Main PC - Local Vector Math |

---

## 5. Development Philosophy

- **Conflict over Consensus:** Preserve contradictory technical claims as first-class objects rather than averaging them out.
- **Depth over Breadth:** Dig up to 5 pages deep into search results to find technical "Long Tail" content.
- **Auditability:** Every claim made by the LLM in chat must be back-traceable to a Knowledge Atom, which must be back-traceable to a Source PDF/Doc.
