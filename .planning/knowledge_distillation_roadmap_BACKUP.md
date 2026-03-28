# Sheppard V3: Exhaustive Crawl + Knowledge Distillation Roadmap

**Vision**: Sheppard should be able to take a topic, exhaustively crawl all possible sources (deduping and logging as it goes) until either:
- It reaches a configurable data ceiling (5-10GB), OR
- The frontier is truly exhausted (no new epistemic yield)
...and then distill that raw corpus into authoritative, contradiction-aware knowledge.

**CRITICAL REQUIREMENT**: The system must be **interactive while crawling**. Users can ask questions at any time, and Sheppard should answer using:
- **Fresh crawled content** (uncondensed, raw) if it's relevant and recent
- **Condensed knowledge** (atoms, graph) for synthesized understanding
- **Clear disclosure** of confidence level and coverage state

**Current State**: The components exist but are **not integrated**. There are *two separate research systems*:
1. **Archivist** (`src/research/archivist/loop.py`) - The currently used system
2. **Acquisition + Condensation** (`src/research/acquisition/`, `src/research/condensation/`) - A more advanced but **unused** system

---

## 1. Current Architecture Assessment

### 1.1 What Exists Today

#### System A: Archivist (Currently Active)
**Entry point**: `src/research/archivist/loop.py:run_research()`

**Flow**:
```
1. Plan outline (planner.plan_outline)
2. For each section:
   - Generate queries (planner.generate_section_queries)
   - Search web (search.search_web, top 12 results)
   - Fetch URLs (crawler.fetch_url with browser)
   - Chunk text (chunker.chunk_text)
   - Generate embeddings (embeddings.get_embeddings_batch)
   - Index chunks (index.add_chunks)
   - Summarize source (synth.summarize_source)
3. Active Adversarial Audit:
   - Critique report (critic.critique_answer)
   - Identify missing topics
   - Patch sections via execute_section_cycle
4. Final Polish (finalize_report)
```

**Characteristics**:
- ✅ Self-contained and working
- ✅ Has critic loop for gap detection
- ✅ Stores in memory + index
- ❌ No storage budget/ceiling
- ❌ No exhaustive frontier (fixed query sets)
- ❌ No differential distillation (just summarization)
- ❌ No condensation-triggered pruning

#### System B: Acquisition + Condensation (Incomplete)
**Components**:
- `acquisition/frontier.py` - AdaptiveFrontier with 4 epistemic modes
- `acquisition/budget.py` - BudgetMonitor with thresholds and condensation triggers
- `acquisition/crawler.py` - Advanced crawler (details not fully examined)
- `condensation/pipeline.py` - DistillationPipeline that extracts "technical atoms"

**Design** (as described in code comments):
- **Adaptive Control Loop**: Policy-driven exploration per concept
- **Budget Pressure-Valve**: Monitor storage usage, trigger condensation at 70/85/95% thresholds
- **Metabolic Distillation**: Coverage before compression, diversity before certainty, contradiction before consensus

**Characteristics**:
- ✅ Has sophisticated frontier with saturation detection
- ✅ Has configurable storage ceiling (default 5GB)
- ✅ Has condensation pipeline with differential extraction
- ❌ Not wired into main research flow
- ❌ No integration with archivist index
- ❌ Standalone prototype-like state

### 1.2 Integration Gaps

| Gap | Archivist | Acquisition+Condensation | Integration Issue |
|-----|----------|--------------------------|-------------------|
| Entry point | `run_research()` | `AdaptiveFrontier.run()` | Two separate entry points |
| Storage tracking | None (unbounded) | `BudgetMonitor` with ceiling | Budget not used by archivist |
| Frontier logic | Fixed query sets | Adaptive with modes | Archivist doesn't use frontier |
| Condensation | Simple summarization | Differential atom extraction | Different distillation approaches |
| Data store | Local index (chromadb?) | PostgreSQL corpus | Different storage backends |
| Orchestration | Linear section cycle | Metabolic loop | No coordination |

**Conclusion**: We have a **schism** - two parallel research systems that should be one.

---

## 2. Target Architecture: Unified Knowledge Distillation Pipeline

### 2.1 High-Level Design

```
┌─────────────────────────────────────────────────────────────┐
│                    RESEARCH MISSION                         │
│  Topic: "Quantum Computing" + Depth/Ceiling Config         │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│              ORCHESTRATOR (New/Existing)                   │
│  • Initialize components                                   │
│  • Create mission record in DB                             │
│  • Coordinate Frontier ↔ Crawler ↔ Condensation ↔ Index   │
│  • Monitor budget, trigger actions                        │
│  • Report status/telemetry                                 │
└────────────────────────┬────────────────────────────────────┘
                         │
        ┌────────────────┴────────────────┐
        │                                 │
        ▼                                 ▼
┌─────────────────┐           ┌─────────────────────────────┐
│  ADAPTIVE       │           │   CONSOLIDATION /          │
│  FRONTIER       │◄─────────►│   DISTILLATION             │
│  (acquisition/) │  Triggers │  (condensation/)           │
│                 │           │                             │
│ • Adaptive      │  At       │ • Differential atom        │
│   exploration   │  budget   │   extraction               │
│ • Epistemic     │  thresholds│ • Contradiction           │
│   mode tracking │           │   resolution               │
│ • Saturation    │           │ • Knowledge synthesis      │
│   detection     │           │ • Source consolidation     │
└─────────────────┘           └─────────────┬───────────────┘
        │                                      │
        │ Raw content                         │ Technical atoms
        ▼                                      ▼
┌─────────────────┐           ┌─────────────────────────────┐
│  CRAWLER        │           │   ARCHIVIST INDEX           │
│  (acquisition/) │──────────►│   (archivist/)              │
│                 │           │                             │
│ • Multi-strategy│           │ • Chunk storage             │
│   search        │           │ • Embeddings (FAISS)       │
│ • Content       │           │ • Metadata index           │
│   extraction    │           │ • Retrieval engine         │
│ • Deduplication │           │ • Graph construction       │
│   (URL/content) │           │                             │
└─────────────────┘           └─────────────────────────────┘
                                          │
                                          ▼
                                  ┌─────────────────────┐
                                  │  SYNTHESIS &        │
                                  │  REPORTING          │
                                  │  (archivist/loop)   │
                                  │                     │
                                  │ • Final narrative   │
                                  │   generation        │
                                  │ • Contradiction     │
                                  │   presentation      │
                                  │ • Source            │
                                  │   bibliography       │
                                  └─────────────────────┘
```

### 2.2 Key Data Flows

**1. Ingestion Loop**:
```
Frontier identifies next concept → Crawler fetches URLs → Store raw content
→ Update frontier yield stats → Check budget → Repeat until saturation or ceiling
```

**2. Condensation Trigger**:
```
BudgetMonitor polls storage → usage_ratio >= threshold → Call condensation_callback
→ DistillationPipeline.run(mission_id, priority) → Extract atoms → Update corpus
→ Condensation may prune raw content (at critical threshold)
```

**3. Final Synthesis**:
```
Mission complete (exhausted or ceiling hit) → Run full_distillation()
→ Build knowledge graph → Generate final authoritative report
→ Store in memory with metadata (objective: true)
```

### 2.3 Storage Model (Two-Tier Knowledge)

**Raw Corpus Layer** (temporary, budgeted, but queryable):
- Raw HTML/text blobs with embeddings
- Metadata: URL, fetch timestamp, source reliability, `fetched_at`
- **Queryable via vector search** even before condensation
- May be pruned after condensation (but keep summary + embedding)

**Condensed Knowledge Layer** (permanent):
- Technical atoms: `{concept, claim, evidence, confidence, source_ids}`
- Contradiction records: `{atom_a, atom_b, conflict_type, resolution}`
- Graph nodes/edges for semantic relationships
- This is the "objective authority" distilled form

**Index Layer** (unified:
- Embeddings for both raw chunks and atoms
- Inverted index for text metadata
- Graph index for SWOC integration
- **Must support hybrid queries**: raw + condensed together

### 2.4 Interactive Query Architecture

```
User Query: "What's the current state of quantum computing?"

        │
        ▼
┌─────────────────────────────────────────────┐
│  QUERY ROUTER                               │
│  • Is this about the active mission topic? │
│  • Freshness requirement?                  │
│  • Confidence needed?                      │
└─────────────┬───────────────────────────────┘
              │
      ┌───────┴────────┐
      │                │
      ▼                ▼
┌──────────┐  ┌──────────────────────┐
│  RAW     │  │  CONDENSED (ATOMS)  │
│  CORPUS  │  │                      │
│          │  │ • Graph search       │
│ • Vector │  │ • Contradiction      │
│   search │  │   resolution         │
│ • Recent │  │ • High confidence    │
│   content│  │ • Synthesized        │
│ • Low    │  │   narratives         │
│   confidence│ │                     │
└──────────┘  └──────────────────────┘
      │                │
      └────────┬───────┘
               ▼
      ┌─────────────────────┐
      │  MERGE & RANK       │
      │  • Dedup results    │
      │  • Weight by layer │
      │    (condensed > raw)│
      │  • Attach confidence│
      │  • Flag as "incomplete"│
      └──────────┬──────────┘
                 ▼
          ┌─────────────┐
          │  RESPONSE   │
          │  • Answer   │
          │  • Sources  │
          │  • Coverage │
          │    metrics  │
          │  • Caveats  │
          └─────────────┘
```

**Key Interactive Features**:
- **Real-time**: As soon as a source is fetched and embedded, it's queryable (within seconds)
- **Transparent**: Response includes:
  - "Based on 234 sources so far" (coverage)
  - "Fresh content from last 5 minutes included" (temporal)
  - Confidence level: "high/medium/low" based on source consensus
  - Contradiction flagging: "Sources disagree on X"
- **Progressive**: Early queries have limited coverage → system says "still gathering data on Y"
- **Topic-bound**: Unless explicitly general, queries outside mission topic get: "I'm focused on X, but I can answer questions about that"

**Example Interaction**:
```
User: "Tell me about quantum computing"
Sheppard: "I'm actively researching quantum computing. So far I've analyzed
          342 sources covering hardware, algorithms, and applications.
          Here's what I know:

          • **Hardware**: IBM's 433-qubit processor (2024) leads... [confidence: high]
          • **Algorithms**: Shor's algorithm remains theoretical... [confidence: medium]
          • **Contradiction**: Some sources claim quantum advantage achieved,
            others say no - I'm seeing 37% of sources say yes, 63% say no.

          I'm still gathering data on quantum error correction and recent
          breakthroughs in 2025. Would you like me to prioritize those areas?

          Sources: [342] | Fresh data: last 12 minutes | Coverage: 68%"
```

---

## 3. Gap Analysis: What Needs to Be Built/Fixed

### 3.1 Critical Missing Pieces (Blocking)

#### 3.1.1 Unified Orchestrator
**Problem**: No component coordinates Frontier → Crawler → Budget → Condensation → Index

**Solution**: Create `src/research/orchestrator.py`:
```python
class ResearchOrchestrator:
    def __init__(
        self,
        memory_manager,
        ollama_client,
        config
    ):
        self.frontier = AdaptiveFrontier(...)
        self.crawler = Crawler(...)
        self.budget = BudgetMonitor(config, self.trigger_condensation)
        self.condensation = DistillationPipeline(...)
        self.index = ArchivistIndex(...)
        self.memory = memory_manager

    async def run_mission(self, topic: str, ceiling_gb: float = 5.0):
        # 1. Initialize mission in DB
        mission_id = await self.create_mission_record(topic, ceiling_gb)

        # 2. Start frontier and crawler loops
        frontier_task = asyncio.create_task(self.frontier.run())
        crawler_task = asyncio.create_task(self.crawler_loop(mission_id))

        # 3. Start budget monitor
        budget_task = asyncio.create_task(self.budget.monitor_loop())

        # 4. Wait for completion (exhaustion or ceiling)
        done, pending = await asyncio.wait(
            [frontier_task, crawler_task],
            return_when=asyncio.FIRST_COMPLETED
        )

        # 5. Cancel remaining tasks
        for task in pending:
            task.cancel()

        # 6. Final distillation
        await self.final_distillation(mission_id)

        # 7. Generate report
        report = await self.generate_report(mission_id)

        return report
```

**Effort**: 2-3 days

#### 3.1.2 Budget ↔ Storage Backend Integration
**Problem**: `BudgetMonitor` tracks `raw_bytes` and `condensed_bytes` but doesn't actually query the filesystem or database to measure real usage.

**Solution**: Implement `StorageBackend` abstraction:
```python
class StorageBackend(ABC):
    @abstractmethod
    async def get_raw_size(self, mission_id: str) -> int: ...
    @abstractmethod
    async def get_condensed_size(self, mission_id: str) -> int: ...
    @abstractmethod
    async def prune_raw(self, mission_id: str, target_bytes: int): ...

class PostgresStorageBackend(StorageBackend):
    async def get_raw_size(self, mission_id):
        row = await self.db.fetchval(
            "SELECT SUM(LENGTH(content)) FROM corpus.sources "
            "WHERE mission_id=$1 AND status='fetched'",
            mission_id
        )
        return row or 0
```

Then wire `BudgetMonitor` to call these methods instead of tracking in-memory counters.

**Effort**: 1 day

#### 3.1.3 Distillation Pipeline Input/Output Contract
**Problem**: `DistillationPipeline.run()` expects sources from `corpus.sources` table and writes atoms, but the schema is undefined and integration unclear.

**Solution**:
- Define `KnowledgeAtom` schema in `src/research/domain_schema.py` (may already exist)
- Implement `DistillationPipeline` output: store atoms in `corpus.atoms` table
- Implement atom → index: feed atoms to archivist for graph construction
- Implement deduplication: detect duplicate atoms across sources

**Effort**: 2 days

### 3.2 High-Priority Enhancements

#### 3.2.1 Exhaustion Detection
**Problem**: `AdaptiveFrontier` has `exhausted_modes` per node but doesn't have global "mission complete" detection.

**Solution**: Add to `AdaptiveFrontier`:
```python
@property
def is_exhausted(self) -> bool:
    if not self.nodes:
        return True
    # All nodes have all 4 modes exhausted?
    for node in self.nodes.values():
        if len(node.exhausted_modes) < len(EpistemicMode.__members__):
            return False
    return True

# Also: yield-based exhaustion
# If last N frontier updates yielded 0 new sources, consider exhausted
```

**Effort**: 1 day

#### 3.2.2 Deduplication Strategy
**Problem**: Need to deduplicate at multiple levels:
- URLs (already in frontier's `visited_urls`)
- Content (near-duplicate detection)
- Knowledge atoms (semantic deduplication)

**Solution**:
- URL dedup: already exists (frontier.visited_urls)
- Content dedup: add content hash (SHA256) check before indexing
- Atom dedup: LLM-based similarity check or embedding similarity threshold

**Effort**: 2 days

#### 3.2.3 Archivist Index Integration
**Problem**: Condensation produces atoms but they need to be indexed for retrieval.

**Solution**: Bridge condensation → archivist:
```python
class ArchivistIndex:
    async def index_atoms(self, atoms: List[KnowledgeAtom]):
        for atom in atoms:
            # Create graph node
            graph_id = self.graph.add_concept(atom.concept, {
                'claim': atom.claim,
                'confidence': atom.confidence,
                'source_ids': atom.source_ids
            })
            # Add embedding for concept+claim
            embedding = await self.ollama.generate_embedding(
                f"{atom.concept}: {atom.claim}"
            )
            self.vector_store.add(graph_id, embedding)
```

**Effort**: 2 days

### 3.3 Medium-Priority Improvements

#### 3.3.1 Research Types Unification
**Problem**: System currently has `ResearchType.WEB_SEARCH` (simple) and `ResearchType.DEEP_RESEARCH` (archivist). Need a third type: `EXHAUSTIVE_DISTILLATION` that uses the new pipeline.

**Solution**: Add to `ResearchType` enum and `research_topic()`:
```python
if research_type == ResearchType.EXHAUSTIVE_DISTILLATION:
    return await orchestrator.run_mission(topic, ceiling_gb=depth*5)
```

**Effort**: 1 day

#### 3.3.2 Progress Reporting
**Problem**: Budget-driven condensation runs in background; need to expose progress to user.

**Solution**: Add callback system to `ResearchOrchestrator`:
```python
async def run_mission(self, topic, progress_callback=None):
    # Yield progress events:
    # {'stage': 'crawling', 'raw_bytes': 1.2e9, 'sources': 342}
    # {'stage': 'condensing', 'priority': 'high', 'atoms': 1203}
    # {'stage': 'complete', 'report': ...}
```

**Effort**: 1 day

#### 3.3.3 Quality Metrics
**Problem**: Need to measure "objective authority" - how thorough and confident the distillation is.

**Solution**: Add metrics:
- Coverage ratio: `sources_condensed / sources_total`
- Contradiction density: `contradictions / atoms`
- Source diversity: unique domains / total sources
- Confidence distribution histogram
- Epistemic mode distribution (how much grounding vs verification, etc.)

Expose in final report and via `/metrics` endpoint.

**Effort**: 2 days

### 3.4 Interactive Query Layer (CRITICAL - Move to High Priority)
**Problem**: Need to query knowledge while mission is running. Raw corpus and condensed atoms must be searchable in real-time.

**Solution**: Implement `ResearchOrchestrator.query_knowledge()`:
- Vector search across both raw chunks and condensed atoms
- Merge results with ranking (condensed > raw)
- Generate answer with confidence and coverage metrics
- Expose via API and WebSocket

**Effort**: 3-4 days

**Key sub-tasks**:
1. Extend `ArchivistIndex` with `search_raw_chunks(mission_id, embedding)` method
2. Implement confidence scoring (source agreement via embedding similarity)
3. Add contradiction detection in query results
4. Implement coverage estimation (what % of relevant corpus covered?)
5. Add freshness indicator (how recent is the data?)
6. Expose via REST: `POST /api/v1/missions/{mission_id}/query`
7. Add WebSocket for interactive chat: `ws://.../missions/{id}/chat`

### 3.5 Persistence & Checkpointing
**Problem**: If system crashes, mission state lost.

**Solution**: Checkpoint frontier and budget state to DB every N minutes or after each source. On restart, can resume.

**Effort**: 2-3 days

### 3.6 Multi-Mission Coordination
**Problem**: Budget and crawler are single-mission currently. Need to support concurrent missions with separate budgets.

**Solution**: Make `BudgetMonitor` track multiple `TopicBudget` instances (already partially there). Ensure `AdaptiveFrontier` is per-mission.

**Effort**: 2 days

---

## 4. Implementation Plan (Phased)

### Phase 0: Preparation (Day 1-2)
**Goal**: Understand codebase, set up testing environment, create integration test harness

Tasks:
- [ ] Read full `AdaptiveFrontier` implementation
- [ ] Read full `DistillationPipeline` implementation
- [ ] Read full `BudgetMonitor` implementation
- [ ] Understand archivist data model (index, embeddings, graph)
- [ ] Create test fixtures with mock data for integration tests
- [ ] Set up test database (PostgreSQL) with schema

Deliverable: `tests/integration/test_exhaustive_distillation.py` with mock end-to-end tests

### Phase 1: Core Integration (Day 3-5)
**Goal**: Wire Frontier → Crawler → Budget → Condensation into a working loop

Tasks:
- [ ] Implement `ResearchOrchestrator` skeleton with component initialization
- [ ] Implement `run_mission()` main loop with async tasks
- [ ] Wire frontier's `run()` to produce concepts → crawler consumes
- [ ] Wire crawler to update frontier's `visited_urls` and `total_ingested`
- [ ] ImplementStorageBackend for budget to measure real DB size
- [ ] Wire budget monitor to call `condensation_callback`
- [ ] Implement `condensation_priority` mapping from budget thresholds

Deliverable: `src/research/orchestrator.py` + integration tests showing data flow

### Phase 2: Condensation Bridge (Day 6-7)
**Goal**: Connect DistillationPipeline output to Archivist index and graph

Tasks:
- [ ] Define/confirm `KnowledgeAtom` schema (fields: concept, claim, evidence, confidence, source_ids, contradictions)
- [ ] Implement storing atoms in `corpus.atoms` table (or existing equivalent)
- [ ] Implement `ArchivistIndex.index_atoms()` method
- [ ] Wire condensation output → index.input
- [ ] Add duplicate atom detection (semantic similarity)
- [ ] Update condensation to handle `mission_id` scoping

Deliverable: Condensed atoms appear in index and are retrievable

### Phase 3: Exhaustion & Completion (Day 8-9)
**Goal**: Detect when mission is done (exhausted or ceiling hit) and trigger final report

Tasks:
- [ ] Implement `AdaptiveFrontier.is_exhausted` property
- [ ] Implement `BudgetMonitor.would_exceed_ceiling()` predictor
- [ ] Add mission completion logic in orchestrator:
  - If frontier.exhausted → complete
  - If budget.usage_ratio >= 0.99 → complete
- [ ] Implement `final_distillation()`: run full corpus through condensation at CRITICAL priority
- [ ] Implement `generate_report()` using archivist's synthesis (hook into archivist/loop.finalize_report pattern)
- [ ] Store final report in memory with full metadata

Deliverable: `orchestrator.run_mission()` completes and returns authoritative report

### Phase 4: Testing & Quality (Day 10-12)
**Goal**: End-to-end validation with realistic data

Tasks:
- [ ] Write comprehensive integration test:
  - Mock small corpus (100 sources across 5 concepts)
  - Run orchestrator
  - Verify: all sources fetched, atoms extracted, graph built, report generated
- [ ] Add property tests for budget calculations
- [ ] Test exhaustion detection with synthetic frontier
- [ ] Test condensation priority triggers
- [ ] Test ceiling enforcement
- [ ] Run full pipeline on sample topic ("machine learning basics") with real Firecrawl (if available)

Deliverable: All tests passing, coverage ≥80% for new code

### Phase 5: Interactive Query Layer (Day 13-16)
**Goal**: Enable real-time queries while mission is running (CLI/API only, no UI)

Tasks:
- [ ] Extend `ArchivistIndex` with `search_raw_chunks(mission_id, embedding, limit)` method
- [ ] Implement `ResearchOrchestrator.query_knowledge(mission_id, question, include_raw=True)`
- [ ] Implement confidence scoring based on source agreement
- [ ] Implement coverage estimation and freshness indicators
- [ ] Add contradiction detection in query results
- [ ] Expose via REST endpoint: `POST /api/v1/missions/{mission_id}/query`
- [ ] Add WebSocket endpoint for interactive chat (optional, can be Phase 8)
- [ ] Add `get_mission_stats(mission_id)` and `get_mission_progress(mission_id)` methods
- [ ] CLI command: `sheppard mission query <mission_id> "question"`
- [ ] CLI command: `sheppard mission status <mission_id>`
- [ ] CLI command: `sheppard mission list`

Deliverable: Can query ongoing mission via CLI/API with confidence, coverage, and freshness metrics

### Phase 6: Migration & Polish (Day 17-19)
**Goal**: Replace `ResearchSystem.research_topic(DEEP_RESEARCH)` with new orchestrator

Tasks:
- [ ] Deprecate `archivist/loop.run_research` (keep for backward compatibility but mark deprecated)
- [ ] Update `ResearchSystem.research_topic()`:
  - `ResearchType.DEEP_RESEARCH` → calls new `orchestrator.run_mission()`
  - Pass `ceiling_gb` from `depth` parameter (depth=3 → 15GB? Or config)
- [ ] Add configuration options:
  - `RESEARCH_CEILING_GB` (default 5)
  - `RESEARCH_EXHAUSTION_ENABLED` (bool)
  - `RESEARCH_CONDENSATION_PRIORITY` thresholds
- [ ] Update API endpoint to support new research type
- [ ] Update CLI to expose new options
- [ ] Document new behavior in README

Deliverable: Deep research now uses exhaustive+distillation pipeline

### Phase 7: Validation & Documentation (Day 20-21)
**Goal**: Ensure system produces objective authority, document usage

Tasks:
- [ ] Manual test: Research "blockchain technology" with 5GB ceiling
- [ ] Evaluate report quality: is it comprehensive? contradictory? authoritative?
- [ ] Tune condensation prompts for better atom extraction
- [ ] Document:
  - `docs/research/exhaustive.md` - how to run exhaustive missions
  - `docs/research/budgeting.md` - storage budget configuration
  - `docs/research/frontier.md` - how frontier adapts
  - `docs/research/querying.md` - how to query while mission runs
  - Update `ARCHITECTURE.md` with new unified design
- [ ] Add monitoring metrics:
  - `research_mission_raw_bytes_total`
  - `research_mission_atoms_total`
  - `research_mission_exhaustion_detected`
  - `research_mission_ceiling_hit`
  - `research_query_latency_seconds`
  - `research_query_confidence_score`

Deliverable: Complete documentation and validated end-to-end workflow

---

## 8. Web UI (Post-MVP, After Backend Complete)

**Timeline**: After Phase 7, separate development track (~3-4 weeks)

**Rationale**: The system should be **fully functional via CLI and API** before any UI work begins. This ensures:
- Core logic validated independently
- API contracts stable before frontend depends on them
- Can demo and test without UI
- UI development can parallelize with any late backend tweaks

### 8.1 UI Components (Priority Order)

**Phase 8: Core Dashboard (Week 1)**
- Mission list page
- Mission detail dashboard (stats, activity feed, storage gauge)
- Real-time updates via WebSocket
- **Goal**: Monitor missions without CLI

**Phase 9: Interactive Query (Week 2)**
- Chat interface for querying running missions
- Answer display with confidence, coverage, sources
- Suggestion chips (based on frontier gaps)
- **Goal**: Replace CLI `mission query` with visual chat

**Phase 10: Advanced Views (Week 3)**
- Frontier explorer (graph visualization of concepts)
- Sources browser (table with filters)
- Knowledge graph viewer (SWOC visualization)
- **Goal**: Exploratory analysis tools

**Phase 11: Final Report & Polish (Week 4)**
- Final report viewer with PDF export
- Mission comparison
- User settings, theme (dark mode)
- **Goal**: Complete user experience

**Tech Stack Recommendation**:
- React + TypeScript (or Vue 3 if you prefer)
- Vite for fast development
- Tailwind CSS for styling
- Socket.IO client for real-time
- Recharts for charts
- D3.js or Cytoscape.js for graph viz
- Zustand for state management

**Estimated Effort**: 4 weeks (1 person) or 2-3 weeks with 2 people

**Integration**: Backend API must be complete and stable before UI starts. All endpoints documented in OpenAPI/Swagger.

---

## 9. Success Criteria

---

## 4. User Experience & UI Requirements

### 4.1 Web UI (Essential for Interactive Use)

While streaming CLI output is fine for initial use, **a proper web UI is essential** for:
- Real-time monitoring of crawling progress
- Interactive chat with the research agent
- Visualizing the frontier and knowledge graph
- Inspecting sources and atoms

**Recommended Approach**: Extend existing web UI or create new React/Vue app.

**Core Pages**:

#### 4.1.1 Mission Dashboard
**URL**: `/missions/{mission_id}`

**Features**:
- **Status panel**: Mission running/completed, elapsed time, ETA
- **Storage gauge**: Raw bytes vs condensed bytes vs ceiling (progress bar)
- **Coverage heatmap**: Frontier concepts with saturation levels (color-coded)
- **Activity feed**: Recent sources fetched, atoms extracted, condensation runs
- **Quick stats**:
  - Sources fetched: 342
  - Atoms extracted: 1,203
  - Contradictions found: 17
  - Current epistemic mode: "dialectic"
  - Crawling rate: 12 sources/min

**Real-time updates**: WebSocket pushes stats every 10 seconds

#### 4.1.2 Interactive Chat Console
**URL**: `/missions/{mission_id}/chat`

**Features**:
- Chat interface (like ChatGPT)
- Input: Ask any question about the research topic
- Response includes:
  - Answer with markdown formatting
  - Source citations (with links)
  - Confidence indicator (color: green/yellow/red)
  - "Based on 234 sources (coverage: 68%)"
  - "Fresh data: last 5 min" badge if recent
  - Gap disclosure: "I'm still gathering data on X"
- Suggestions: "You could ask about: X, Y, Z" (based on under-saturated frontier nodes)
- Option to "prioritize this area" → increases frontier weight for that concept

#### 4.1.3 Frontier Explorer
**URL**: `/missions/{mission_id}/frontier`

**Visualization**:
- Graph view of concepts (nodes) with edges showing relationships
- Node color by saturation (red=underexplored, green=saturated)
- Node size by source count
- Click node → see details:
  - Which epistemic modes tried?
  - Yield per mode
  - Sources covering this concept
  - Atoms extracted
- Ability to manually add concept to frontier (priority boost)

#### 4.1.4 Sources Browser
**URL**: `/missions/{mission_id}/sources`

**Features**:
- Table of all fetched sources (URL, title, date, reliability)
- Filter by domain, date, reliability
- Preview text snippet
- Tag as "high quality"/"low quality"
- See which atoms cite this source
- Raw content viewer

#### 4.1.5 Knowledge Graph
**URL**: `/missions/{mission_id}/graph`

**Features**:
- SWOC graph visualization (network graph)
- Nodes: concepts from atoms
- Edges: relationships (extracted by LLM or shared sources)
- Color by confidence, size by source count
- Search/filter nodes
- Explore: click node → see related atoms

**Implementation Options**:
- D3.js for interactive force-directed graph
- Cytoscape.js for complex graphs
- vis.js for simpler network visualizations

#### 4.1.6 Final Report Viewer
**URL**: `/missions/{mission_id}/report`

**Features**:
- Generated final report (markdown → HTML)
- Collapsible sections
- Hover on claim → see source tooltips
- Click source → open in new tab
- Export options: PDF, Markdown, JSON
- Compare drafts: show evolution through condensation

**Technology Stack**:
- **Frontend**: React or Vue.js with TypeScript
- **State management**: Zustand or Pinia (lightweight)
- **Real-time**: Socket.IO or WebSocket API
- **Charts**: Recharts or Chart.js
- **Graph visualization**: D3.js or Cytoscape.js
- **Styling**: Tailwind CSS or Chakra UI
- **Components**: Shadcn/ui or Element Plus (pre-built accessible components)

**Estimated Effort**: 5-7 days for MVP (dashboard + chat), 10-12 days for full suite

**Integration Points**:
- GET `/api/v1/missions` - list missions
- GET `/api/v1/missions/{id}` - mission metadata
- GET `/api/v1/missions/{id}/stats` - real-time stats (or WebSocket)
- POST `/api/v1/missions/{id}/query` - chat question
- WebSocket `/ws/missions/{id}/updates` - push updates
- GET `/api/v1/missions/{id}/sources` - list sources
- GET `/api/v1/missions/{id}/atoms` - list atoms
- GET `/api/v1/missions/{id}/graph` - graph data (JSON)

**Success Criteria**:
- ✅ Can monitor a 10-minute mission in real-time without refreshing
- ✅ Chat response < 3 seconds
- ✅ Frontier graph renders 1000+ nodes smoothly
- ✅ Works on mobile (responsive)
- ✅ Dark mode support (optional but nice)

**Effort**: 5-10 days depending on complexity

---

### 4.2 CLI Enhancements

Keep CLI for power users and automation:

```bash
# Start mission and get mission ID
sheppard research start "quantum computing" --ceiling 10GB --output mission.json
# → {"mission_id": "abc123", "status": "running"}

# Query while running
sheppard research query abc123 "latest qubit count"
# → Answer with sources, coverage: 42%, confidence: high

# Check status
sheppard research status abc123
# → {"stage": "crawling", "sources": 342, "raw_bytes": "4.2GB", "atoms": 1203}

# Stream logs
sheppard research logs abc123 --follow
# → [2024-01-15 10:30:12] Fetched: https://arxiv.org/abs/2401.12345
# → [2024-01-15 10:30:15] Extracted 3 atoms

# Stop mission
sheppard research stop abc123

# Get final report
sheppard research report abc123 > report.md
```

**Effort**: 2-3 days

---

### 4.3 API Design (Backend)

Already partially exists in `src/interfaces/api.py`. Need to add:

**New endpoints**:

```
GET    /api/v1/missions                    # List all missions
POST   /api/v1/missions                    # Create new mission
GET    /api/v1/missions/{id}               # Get mission metadata
DELETE /api/v1/missions/{id}               # Cancel mission
GET    /api/v1/missions/{id}/stats         # Real-time stats
WS      /ws/missions/{id}/updates          # WebSocket for live updates
POST   /api/v1/missions/{id}/query         # Interactive query
POST   /api/v1/missions/{id}/prioritize    # Boost concept priority
GET    /api/v1/missions/{id}/sources       # List sources (filterable)
GET    /api/v1/missions/{id}/atoms         # List atoms
GET    /api/v1/missions/{id}/graph         # Knowledge graph JSON
GET    /api/v1/missions/{id}/report        # Final report (when complete)
POST   /api/v1/missions/{id}/condense      # Trigger manual condensation
```

**Existing endpoints to update**:
- `POST /api/v1/research` - accept `type: "exhaustive_distillation"` and `ceiling_gb`
- Should return `mission_id` immediately (not block), then client polls `/missions/{id}/stats`

**Response format**:
```json
{
  "success": true,
  "data": { ... },
  "error": null,
  "request_id": "abc123"
}
```

**WebSocket message format**:
```json
{
  "type": "stats_update",
  "data": {
    "mission_id": "abc123",
    "timestamp": "2024-01-15T10:30:00Z",
    "stats": {
      "stage": "crawling",
      "sources_fetched": 342,
      "raw_bytes": 4231934872,
      "atoms_extracted": 1203,
      "condensation_queue": 0,
      "frontier_nodes": 47,
      "saturated_nodes": 12
    }
  }
}
```

**Effort**: 2-3 days (FastAPI already supports WebSocket)

---

### 4.4 Summary: UI Effort Breakdown

| Component | Effort | Dependencies |
|-----------|--------|--------------|
| API extensions (endpoints + WebSocket) | 3 days | Orchestrator must expose stats |
| Dashboard page (React + real-time) | 4 days | API ready, UI components |
| Interactive chat console | 3 days | Query API ready |
| Frontier explorer (graph viz) | 4 days | Graph data API, D3.js |
| Sources browser | 2 days | Sources API |
| Knowledge graph viewer | 3 days | Graph API |
| Final report viewer | 2 days | Report generation |
| CLI enhancements | 2 days | API ready |
| Testing (UI unit + e2e) | 3 days | All components |
| **Total** | **~23 days** (~5 weeks) | Can parallelize with backend |

**UI can be developed in parallel** with backend (Phases 1-6) if API contracts are defined early. Recommend:

- Week 3-4: Design API contracts, create mock API server
- Week 4-5: Build UI with mocks, backend implements real APIs
- Week 6: Integration and

 testing

---

## 5. Success Criteria

**Functional**:
- ✅ Can run research mission with 5GB ceiling
- ✅ Mission completes when either frontier exhausted or ceiling reached
- ✅ Raw content stored, then condensed into atoms
- ✅ Final report synthesizes atoms, preserves contradictions
- ✅ Sources fully deduplicated (URL + content hash)
- ✅ Progress reporting works (callback or async generator)
- ✅ **Can query mission knowledge while crawling** (real-time)
- ✅ **Query responses include confidence, coverage, and freshness metrics**
- ✅ **Interactive chat: conversation about topic while mission runs**

**Quality**:
- ✅ Report reads as authoritative narrative, not just concatenated summaries
- ✅ Contradictions explicitly called out
- ✅ Confidence levels indicated per claim
- ✅ Source bibliography complete
- ✅ **Query answers distinguish between raw (fresh) and condensed (synthesized) knowledge**

**Performance**:
- ✅ Crawling throughput: ≥10 sources/minute sustained
- ✅ Condensation latency: ≤2x crawl time (runs parallel)
- ✅ Memory usage: bounded by batch sizes, not total corpus
- ✅ **Query latency: <2 seconds for 10k+ atoms** (with vector search)

**Observability**:
- ✅ Metrics: raw_bytes, condensed_bytes, atoms_extracted, frontier_saturation
- ✅ Metrics: query_latency, query_confidence, coverage_ratio
- ✅ Logging: structured with mission_id throughout
- ✅ Debugging: can trace a single source from fetch → atom → report
- ✅ **Can monitor mission progress via API/WebSocket** (sources/min, bytes, frontier state)

**User Experience**:
- ✅ "I'm actively researching X" - clear indication mission is running
- ✅ "Based on N sources so far" - coverage transparency
- ✅ "Fresh data from last X minutes" - temporal awareness
- ✅ "Still gathering data on subtopic Y" - gap disclosure
- ✅ Suggestive: "Would you like me to prioritize Z?" - adaptive prioritization

---

## 6. Risks & Mitigations

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Budget tracking inaccurate | Medium | High | Implement storage backend abstraction with tests; cross-check with actual DB size |
| Frontier stuck in loop | Medium | High | Add timeout and minimum yield thresholds; manual stop |
| Condensation too slow | Medium | Medium | Tune batch size; parallelize across atoms; enable GPU acceleration |
| Storage ceiling too small | Low | Medium | Allow dynamic ceiling adjustment via API; warn at 80% |
| Atom deduplication misses | Medium | Medium | Use both content hash and embedding similarity; manual review |
| Report quality poor | High | High | Iterate on condensation prompts; add human-in-the-loop validation |
| Memory leaks in long missions | Medium | High | Regular memory profiling; batch processing; explicit cleanup |

---

## 7. Alternative: Integrate by Replacing Archivist

Instead of creating a new orchestrator, we could **replace** `archivist/loop.py` with the new system:

**Pros**:
- Single code path
- No deprecation debt
- Cleaner architecture

**Cons**:
- Riskier (breaks existing working system)
- Need to port archivist's good parts (critic loop, planning) to new system
- More work upfront

**Recommendation**: Build `orchestrator` as new module, then gradually migrate. Keep archivist as fallback until new system validated.

---

## 8. Configuration Reference

Once implemented, users will configure via `.env` or API parameters:

```bash
# .env
RESEARCH_EXHAUSTIVE_CEILING_GB=10
RESEARCH_EXHAUSTIVE_BUDGET_LOW_PCT=70
RESEARCH_EXHAUSTIVE_BUDGET_HIGH_PCT=85
RESEARCH_EXHAUSTIVE_BUDGET_CRITICAL_PCT=95
RESEARCH_EXHAUSTIVE_PRUNE_RAW_AT=critical  # low/high/critical/never
RESEARCH_EXHAUSTIVE_TIMEOUT_HOURS=48
RESEARCH_EXHAUSTIVE_AUTO_DISTILL=true
```

**API**:
```python
await sheppard.research_topic(
    topic="quantum computing",
    research_type=ResearchType.EXHAUSTIVE_DISTILLATION,
    depth=3,  # Interpreted as ceiling: depth * 5GB = 15GB
    metadata={'ceiling_gb': 10}
)
```

---

## 9. Dependencies on Other Workstreams

This plan assumes:
- ✅ PostgreSQL adapter exists (mentioned in condensation code: `self.adapter.pg`)
- ✅ LLM client functional (Ollama/OpenRouter)
- ✅ Firecrawl/SearXNG working for search
- ✅ Memory manager (SQLite/Redis) operational
- **Needs verification**: Confirm `corpus.sources` schema and PG connection

May need to coordinate with:
- **Database team**: Ensure `corpus` schema exists and indexes are performant for budget queries
- **LLM team**: Ensure `DistillationPipeline` prompts are tuned for atom extraction
- **Infra**: Ensure PostgreSQL can handle large `corpus` tables (10GB+)

---

## 10. Post-Implementation: Operating as Objective Authority

After implementation, using Sheppard for authoritative knowledge is straightforward:

```bash
# CLI
python -m interfaces.cli research "quantum computing" --type exhaustive --depth 3

# API
POST /api/v1/research
{
  "topic": "quantum computing",
  "type": "exhaustive_distillation",
  "ceiling_gb": 10
}

# Response
{
  "report": "Comprehensive distillation with contradictions...",
  "metadata": {
    "sources_fetched": 2847,
    "sources_deduped": 2193,
    "atoms_extracted": 15602,
    "contradictions": 47,
    "coverage_ratio": 0.96,
    "ceiling_hit": false,
    "frontier_exhausted": true,
    "total_bytes": 4.2e9,
    "confidence_median": 0.87
  }
}
```

The system becomes the **objective authority** because:
- **Exhaustive**: Frontier adapts to fill gaps, stops only when saturated
- **Deduplicated**: URL + content hash + semantic atom dedup
- **Budgeted**: Hard ceiling prevents unbounded growth
- **Distilled**: Atoms extracted via LLM with contradiction awareness
- **Transparent**: Full source bibliography and confidence metrics
- **Contradiction-aware**: Preserves disagreements instead of false consensus

---

## 11. Quick Reference: File Map

**Existing components to reuse**:
- `src/research/acquisition/frontier.py` - AdaptiveFrontier (✅ good)
- `src/research/acquisition/budget.py` - BudgetMonitor (✅ good, needs storage backend)
- `src/research/acquisition/crawler.py` - Crawler (needs check)
- `src/research/condensation/pipeline.py` - DistillationPipeline (✅ good, needs output contract)
- `src/research/archivist/index.py` - Index for storing/retrieving atoms
- `src/research/archivist/embeddings.py` - Embedding generation
- `src/research/archivist/planner.py` - Query planning (can reuse for report outline?)
- `src/research/archivist/synth.py` - Synthesis (use for final report)
- `src/research/archivist/critic.py` - Critique (use for quality check)

**New components to create**:
- `src/research/orchestrator.py` - Main coordination
- `src/research/storage_backend.py` - Abstract storage for budget
- `src/research/storage_postgres.py` - PostgreSQL backend
- Tests: `tests/research/integration/test_orchestrator.py`

**Components to deprecate**:
- `src/research/archivist/loop.py` - Replace with orchestrator (keep as fallback initially)

---

**Next Step**: Begin **Phase 0: Preparation** - read the existing acquisition/condensation implementations in detail, set up test infrastructure.
