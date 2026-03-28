# Sheppard V3: Exhaustive Crawl + Knowledge Distillation Roadmap

**Vision**: Sheppard should take a topic, exhaustively crawl all possible sources (deduping and logging) until either:
- It reaches a configurable data ceiling (5-10GB), OR
- The frontier is truly exhausted (no new epistemic yield)
...and then distill that raw corpus into authoritative, contradiction-aware knowledge.

**CRITICAL REQUIREMENT**: The system must be **interactive while crawling**. Users can ask questions at any time, and Sheppard answers using:
- **Fresh crawled content** (uncondensed, raw) if relevant and recent
- **Condensed knowledge** (atoms, graph) for synthesized understanding
- **Clear disclosure** of confidence level and coverage state

**Current State**: The components exist but are **not integrated**. Two separate research systems:
1. **Archivist** (`src/research/archivist/loop.py`) - Currently used, limited
2. **Acquisition + Condensation** (`src/research/acquisition/`, `condensation/`) - Advanced but **unused**

---

## 1. The Two-System Problem

### System A: Archivist (Works But Limited)
```
Plan → Search → Fetch → Index → Summarize → Critique → Report
```
- ✅ Self-contained and functional
- ❌ No storage budget/ceiling
- ❌ No adaptive frontier (fixed query sets)
- ❌ No differential distillation (just summarization)

### System B: Acquisition + Condensation (Advanced But Unused)
Components:
- `AdaptiveFrontier` - 4 epistemic modes, saturation detection
- `BudgetMonitor` - 5-10GB ceiling, threshold-triggered condensation
- `DistillationPipeline` - Extracts "technical atoms" with contradiction awareness

- ✅ Sophisticated design
- ❌ Not wired into main research flow
- ❌ Standalone prototype state

### Integration Gap
No orchestrator coordinates: **Frontier → Crawler → Budget → Condensation → Index → Query**

---

## 2. Target Architecture: Unified Orchestrator

```
                    ┌────────────────────────┐
                    │  RESEARCH ORCHESTRATOR │
                    │  (New: src/research/   │
                    │   orchestrator.py)     │
                    └───────────┬────────────┘
                                │
        ┌───────────────────────┼───────────────────────┐
        │                       │                       │
        ▼                       ▼                       ▼
┌───────────────┐   ┌──────────────────┐   ┌─────────────────────┐
│  ADAPTIVE     │   │   CRAWLER        │   │   BUDGET MONITOR    │
│  FRONTIER     │──▶│   (acquisition/  │◀──│   (acquisition/     │
│  (acquisition/)│   │    crawler.py)   │   │    budget.py)       │
│               │   │                  │   │                     │
│ • Generates   │   │ • Fetches URLs   │   │ • Tracks raw/       │
│   concepts    │   │ • Extracts       │   │   condensed bytes   │
│ • 4 epistemic │   │   content        │   │ • Triggers          │
│   modes       │   │ • Deduplicates   │   │   condensation at   │
│ • Saturation  │   │   (URL+hash)     │   │   thresholds        │
│   detection   │   │                  │   │ • Enforces ceiling  │
└───────────────┘   └──────────────────┘   └─────────────────────┘
        │                       │                       │
        │                       │ Content                │ Triggers
        ▼                       ▼                         ▼
┌─────────────────────────────────────────────────────────────────┐
│               ARCHIVIST INDEX (archivist/)                     │
│  • Chunk storage (raw + atoms)                                 │
│  • Embeddings (FAISS)                                         │
│  • Metadata index                                             │
│  • Graph construction (SWOC)                                 │
│  • Search: vector + metadata + graph                          │
└───────────────────────────┬───────────────────────────────────┘
                            │
                            ▼
                  ┌──────────────────┐
                  │  QUERY INTERFACE │  ← Interactive queries while running
                  │  (orchestrator)  │    via CLI/API
                  └──────────────────┘
                            │
                            ▼
                  ┌──────────────────┐
                  │  FINAL REPORT    │  ← When mission complete
                  │  (archivist/     │    (exhausted or ceiling)
                  │   synth + critic)│
                  └──────────────────┘
```

### Two-Tier Knowledge Storage

**Raw Corpus Layer** (temporary, budgeted, queryable):
- Raw HTML/text blobs with embeddings
- Fetched timestamp, source reliability
- Queryable via vector search immediately

**Condensed Knowledge Layer** (permanent):
- Technical atoms: `{concept, claim, evidence, confidence, source_ids}`
- Contradiction records
- Knowledge graph nodes/edges

Both layers indexed for real-time queries.

---

## 3. Interactive Query While Crawling

**User Experience**:
```
User: "Tell me about quantum computing"
Sheppard: "I'm actively researching quantum computing. So far I've analyzed
          342 sources covering hardware, algorithms, and applications.
          Here's what I know:

          • Hardware: IBM's 433-qubit processor (2024) leads... [confidence: high]
          • Algorithms: Shor's algorithm remains theoretical... [confidence: medium]
          • Contradiction: 37% of sources claim quantum advantage achieved,
            63% say no.

          I'm still gathering data on quantum error correction.
          Sources: [342] | Fresh data: last 12 minutes | Coverage: 68%"
```

**Implementation**: `ResearchOrchestrator.query_knowledge(mission_id, question)`
1. Embed the question
2. Search both raw chunks and condensed atoms (vector search)
3. Merge & deduplicate by source
4. Generate answer with LLM, include:
   - Confidence level (source agreement)
   - Coverage estimate
   - Freshness indicator
   - Gap disclosure

---

## 4. Gap Analysis

### Critical Missing Pieces (Blocking)

#### 4.1.1 Unified Orchestrator
**Problem**: No component coordinates the pipeline.

**Solution**: Create `src/research/orchestrator.py` with:
- Component initialization (frontier, crawler, budget, condensation, index)
- `run_mission()` main loop
- `query_knowledge()` real-time queries
- `get_mission_stats()` progress reporting

**Effort**: 2-3 days

#### 4.1.2 Storage Backend for Budget
**Problem**: `BudgetMonitor` tracks bytes in-memory, not real DB size.

**Solution**: Implement `StorageBackend` abstraction:
```python
class StorageBackend(ABC):
    async def get_raw_size(self, mission_id) -> int: ...
    async def get_condensed_size(self, mission_id) -> int: ...
    async def prune_raw(self, mission_id, target_bytes): ...
```

**Effort**: 1 day

#### 4.1.3 Distillation Pipeline Contract
**Problem**: `DistillationPipeline` output schema undefined.

**Solution**: Define `KnowledgeAtom` schema, implement storage in `corpus.atoms` table, wire to index.

**Effort**: 2 days

### High-Priority Enhancements

- **Exhaustion detection** (1d) - `AdaptiveFrontier.is_exhausted` property
- **Deduplication** (2d) - URL, content hash, semantic atom dedup
- **Archivist index integration** (2d) - `index_atoms()` method
- **Research type unification** (1d) - Add `EXHAUSTIVE_DISTILLATION`
- **Progress reporting** (1d) - Callbacks for stats updates

### Medium-Priority
- **Quality metrics** (2d) - Coverage ratio, contradiction density, confidence distribution
- **Persistence & checkpointing** (2-3d) - Resume after crash
- **Multi-mission coordination** (2d) - Concurrent missions with separate budgets

### Interactive Query Layer (CRITICAL)
- Extend `ArchivistIndex.search_raw_chunks()` (1d)
- Implement `query_knowledge()` in orchestrator (2d)
- Confidence scoring and coverage estimation (1d)
- REST endpoint: `POST /api/v1/missions/{id}/query` (1d)
- CLI command: `sheppard mission query` (1d)

**Total**: 3-4 days

### CLI Enhancements (2-3 days)
- `sheppard research start` → returns `mission_id` immediately
- `sheppard mission query <id> "question"`
- `sheppard mission status <id>`
- `sheppard mission list`
- `sheppard mission stop <id>`
- `sheppard mission report <id>`

---

## 5. Implementation Plan (Phased)

### Phase 0: Preparation (Day 1-2)
**Goal**: Understand codebase, set up tests, validate assumptions

**Tasks**:
- [ ] Read full implementations: `AdaptiveFrontier`, `BudgetMonitor`, `DistillationPipeline`, `ArchivistIndex`
- [ ] Understand data model: PostgreSQL schema (`corpus.sources`, `corpus.atoms`)
- [ ] Create test fixtures: sample corpus (100 sources), sample atoms
- [ ] Set up test database (PostgreSQL with Docker)
- [ ] Create mocks: `MockFrontier`, `MockCrawler`, `MockBudget`, `MockCondensation`
- [ ] Write analysis docs and ADRs

**Deliverable**: Integration test harness + analysis docs

### Phase 1: Core Integration (Day 3-5)
**Build `ResearchOrchestrator`** and wire:
```
Frontier → Crawler → Budget → Condensation (triggered)
```
- Async task coordination
- Mission state management
- Budget monitoring loop

**Deliverable**: `src/research/orchestrator.py` + smoke test

### Phase 2: Condensation Bridge (Day 6-7)
Connect distillation to index:
- Implement atom storage (`corpus.atoms`)
- Bridge: `DistillationPipeline` → `ArchivistIndex.index_atoms()`
- Graph construction from atoms
- Deduplication logic

**Deliverable**: Atoms indexed and retrievable

### Phase 3: Exhaustion & Completion (Day 8-9)
- `AdaptiveFrontier.is_exhausted` detection
- Budget ceiling enforcement
- Mission completion logic
- Final distillation pass
- Report generation (using archivist synthesis)

**Deliverable**: `orchestrator.run_mission()` completes and returns report

### Phase 4: Testing & Quality (Day 10-12)
- End-to-end integration test (mock corpus → final report)
- Property tests (budget calc, exhaustion logic)
- Performance benchmarks (crawl rate, query latency)
- Real test on sample topic (if Firecrawl available)
- Coverage ≥80% for new code

**Deliverable**: All tests passing, benchmark suite

### Phase 5: Interactive Query Layer (Day 13-16)
**CRITICAL FOR UX**:
- `ArchivistIndex.search_raw_chunks(mission_id, embedding)`
- `ResearchOrchestrator.query_knowledge(mission_id, question)`
- Confidence scoring, coverage estimation, freshness
- REST API: `POST /api/v1/missions/{id}/query`
- CLI: `sheppard mission query <id> "question"`
- WebSocket (optional: can be Phase 8)

**Deliverable**: Can query running mission via CLI/API

### Phase 6: Migration (Day 17-19)
- Deprecate `archivist/loop.run_research` (keep as fallback)
- Update `ResearchSystem.research_topic()` → `orchestrator.run_mission()`
- Add config: `RESEARCH_CEILING_GB`, `RESEARCH_EXHAUSTION_ENABLED`
- Update API endpoint: `POST /api/v1/research?type=exhaustive_distillation`
- Update CLI: `sheppard research start --type exhaustive --ceiling 10GB`
- Documentation updates

**Deliverable**: All research uses new pipeline

### Phase 7: Validation & Documentation (Day 20-21)
- Manual test: Research "blockchain" with 5GB ceiling
- Evaluate report quality, tune prompts
- Write comprehensive docs:
  - `docs/research/exhaustive.md`
  - `docs/research/budgeting.md`
  - `docs/research/frontier.md`
  - `docs/research/querying.md`
  - Update `ARCHITECTURE.md`
- Add monitoring metrics
- Create demo video or tutorial

**Deliverable**: Production-ready system with complete documentation

---

## 6. Success Criteria

**Functional**:
- ✅ Run mission with configurable ceiling (5-10GB)
- ✅ Completes on exhaustion or ceiling hit
- ✅ Raw content stored, then condensed to atoms
- ✅ Final report synthesizes, preserves contradictions
- ✅ Deduplication (URL + content hash + atom similarity)
- ✅ Progress reporting (callbacks, stats API)
- ✅ **Real-time queries while crawling** (CLI + API)
- ✅ Query responses include confidence, coverage, freshness

**Quality**:
- ✅ Report reads as authoritative narrative
- ✅ Contradictions explicitly flagged
- ✅ Confidence levels per claim
- ✅ Complete source bibliography

**Performance**:
- ✅ Crawling: ≥10 sources/minute sustained
- ✅ Condensation: ≤2x crawl time (parallel)
- ✅ Query latency: <2 seconds (10k+ atoms)
- ✅ Memory: bounded by batch sizes

**Observability**:
- ✅ Metrics: raw_bytes, condensed_bytes, atoms, frontier_saturation, query_latency
- ✅ Structured logging with mission_id
- ✅ Can trace source: fetch → atom → report
- ✅ Stats API for real-time monitoring

**CLI/API**:
- ✅ `sheppard mission start/status/query/stop/list`
- ✅ REST API: `/missions`, `/missions/{id}/query`, `/missions/{id}/stats`
- ✅ WebSocket for live updates (optional)

---

## 7. Risks & Mitigations

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Budget tracking inaccurate | Medium | High | Storage backend abstraction; cross-check actual DB size |
| Frontier stuck (no yield) | Medium | High | Timeout, min yield thresholds, manual stop |
| Condensation too slow | Medium | Medium | Batch tuning, parallelization, GPU acceleration |
| Atom dedup misses | Medium | Medium | Content hash + embedding similarity |
| Report quality poor | High | High | Iterate prompts, human validation |
| Memory leaks | Medium | High | Profiling, batch processing, explicit cleanup |
| Query latency high | Medium | High | Index optimization, benchmark, cache |
| Interactive query slow | Medium | High | Dual-layer indexing, pre-warm embeddings |

---

## 8. Web UI (Post-MVP, After Backend Complete)

**Timeline**: After Phase 7, separate track (~3-4 weeks)

**Rationale**: System must be **fully functional via CLI/API** first. UI later.

### Phases:
- **Phase 8**: Dashboard (monitoring, stats, real-time updates)
- **Phase 9**: Interactive chat (replace CLI query)
- **Phase 10**: Advanced views (frontier graph, sources browser, knowledge graph)
- **Phase 11**: Final report viewer + polish

**Tech**: React/TypeScript, Tailwind, Socket.IO, D3.js, Zustand
**Effort**: 4 weeks (1 person)

---

## 9. Dependencies

Assumes:
- ✅ PostgreSQL adapter exists (used by condensation)
- ✅ LLM client (Ollama/OpenRouter) functional
- ✅ Firecrawl/SearXNG working for search/scraping
- ✅ Memory manager (SQLite/Redis) operational
- 🔍 **Needs verification**: `corpus.sources` and `corpus.atoms` schema

Coordinate with:
- **Database**: Ensure `corpus` schema with indexes for performance
- **LLM**: Tune condensation prompts for quality atom extraction
- **Infra**: PostgreSQL must handle 10GB+ tables

---

## 10. Configuration Reference

Once implemented:

```bash
# .env
RESEARCH_CEILING_GB=10
RESEARCH_EXHAUSTION_ENABLED=true
RESEARCH_CONDENSATION_THRESHOLD_LOW=0.70
RESEARCH_CONDENSATION_THRESHOLD_HIGH=0.85
RESEARCH_CONDENSATION_THRESHOLD_CRITICAL=0.95
RESEARCH_PRUNE_RAW_AT=critical  # low|high|critical|never
```

**CLI**:
```bash
sheppard research start "topic" --type exhaustive --ceiling 10GB
sheppard mission list
sheppard mission status <id>
sheppard mission query <id> "question"
sheppard mission stop <id>
sheppard mission report <id> > report.md
```

**API**:
```json
POST /api/v1/research
{
  "topic": "quantum computing",
  "type": "exhaustive_distillation",
  "ceiling_gb": 10
}
# Returns: {"mission_id": "abc123", "status": "running"}

GET /api/v1/missions/abc123/stats
# Returns: {"stage": "crawling", "sources": 342, "raw_bytes": 4.2e9, ...}

POST /api/v1/missions/abc123/query
{"question": "latest qubit count"}
# Returns: {"answer": "...", "coverage": 0.42, "confidence": "high", ...}
```

---

## 11. Quick Reference: File Map

**Existing components to reuse**:
- `src/research/acquisition/frontier.py` - AdaptiveFrontier ✅
- `src/research/acquisition/budget.py` - BudgetMonitor ✅ (needs storage backend)
- `src/research/acquisition/crawler.py` - Crawler (verify)
- `src/research/condensation/pipeline.py` - DistillationPipeline ✅ (needs output contract)
- `src/research/archivist/index.py` - Index (needs raw search extension)
- `src/research/archivist/embeddings.py` - Embeddings ✅
- `src/research/archivist/retriever.py` - Retrieval (use for query)
- `src/research/archivist/synth.py` - Synthesis (use for report)
- `src/research/archivist/critic.py` - Critique (use for quality check)

**New components to create**:
- `src/research/orchestrator.py` - **Main coordination** (core)
- `src/research/storage_backend.py` - Abstract storage interface
- `src/research/storage_postgres.py` - PostgreSQL implementation
- (Optional: `src/research/tui.py` - Text UI for monitoring)

**Components to deprecate**:
- `src/research/archivist/loop.py:run_research` → Replace with orchestrator

---

## 12. Next Step: Phase 0 Preparation

**Start here**: Deep dive into existing code to validate assumptions.

**Tasks**:
1. Read `AdaptiveFrontier`, `BudgetMonitor`, `DistillationPipeline` fully
2. Verify PostgreSQL schema (corpus tables)
3. Set up test database and fixtures
4. Write analysis docs
5. Create ADRs

**See**: `.planning/phases/phase0_preparation.md` for detailed checklist

---

**Document Version**: 1.0
**Last Updated**: 2025-03-27
**Status**: Ready for Implementation
**Estimated Backend Timeline**: 21 days (3 weeks)
**Estimated Total Timeline (including UI)**: 7-8 weeks
