# Phase 0: Preparation - Understanding & Setup

**Duration**: 2 days (Day 1-2)
**Goal**: Deeply understand existing components, set up test infrastructure, validate assumptions

---

## Task 0.1: Read & Analyze Core Components

### 0.1.1 AdaptiveFrontier Deep Dive
**File**: `src/research/acquisition/frontier.py`

**Questions to answer**:
1. How does `AdaptiveFrontier.run()` generate concepts?
2. What are the 4 epistemic modes and when does it switch between them?
3. How does it detect node saturation? (`exhausted_modes`)
4. What's the `ResearchPolicy` and how is it generated?
5. How does it interact with the crawler (what API does it expose)?
6. State persistence: `_load_checkpoint()` / `_save_checkpoint()` - what state is saved?
7. How does it track `visited_urls` and `total_ingested`?

**Deliverable**: `docs/analysis/adaptive_frontier.md` with answers + diagram of control flow

### 0.1.2 BudgetMonitor Deep Dive
**File**: `src/research/acquisition/budget.py`

**Questions**:
1. How does it measure `raw_bytes` and `condensed_bytes` (currently in-memory only)?
2. What are the threshold defaults (70%, 85%, 95%) and are they configurable?
3. How does `condensation_callback` work? Who provides it and when is it invoked?
4. How does it handle multiple topics (`TopicBudget` instances)?
5. What's the polling interval and can it be event-driven instead?
6. How does `prune_raw()` work and when is it triggered?

**Deliverable**: `docs/analysis/budget_monitor.md` + note about needed storage backend integration

### 0.1.3 DistillationPipeline Deep Dive
**File**: `src/research/condensation/pipeline.py`

**Questions**:
1. What is a `KnowledgeAtom`? What fields does it have? (Look at `domain_schema.py`)
2. What's the extraction process? How does it min "technical atoms" from sources?
3. What's the `adapter` parameter and how does it access PostgreSQL?
4. How does it handle contradictions? (Look for "conflict", "resolution")
5. What's the output? Where do atoms get stored? Table schema?
6. What's the `budget` parameter used for?
7. Priority levels (LOW/HIGH/CRITICAL) - how does behavior change?

**Deliverable**: `docs/analysis/distillation_pipeline.md` + `KnowledgeAtom` schema definition

### 0.1.4 Archivist Index Deep Dive
**Files**: `src/research/archivist/index.py`, `embeddings.py`, `graph_viz.py`, `retriever.py`

**Questions**:
1. What's the storage backend? ChromaDB? FAISS? Custom?
2. How are chunks indexed? What's the schema?
3. How does `search()` work? Vector search? Text search? Graph?
4. What's `add_chunks()` signature? What metadata does it store?
5. Is there a `KnowledgeAtom` → graph node conversion already?
6. Can we add a `search_raw_chunks(mission_id, embedding)` method? What would it filter on?
7. How are embeddings generated and cached?

**Deliverable**: `docs/analysis/archivist_index.md` with API proposal for `search_raw_chunks()`

### 0.1.5 Data Model Exploration
**Goal**: Understand the PostgreSQL schema (if in use)

**Tasks**:
- Find SQL schema files (maybe in `src/research/schema/` or migrations)
- Look for `corpus.sources` table (referenced in condensation code)
- Look for `corpus.atoms` table (if exists)
- What columns are there? Indexes? Constraints?
- How are `mission_id` and `source_id` used?

**Deliverable**: `docs/analysis/database_schema.md` with CREATE TABLE statements or diagram

### 0.1.6 Existing ResearchSystem
**File**: `src/research/system.py`

**Questions**:
1. How does `research_topic()` currently work for `DEEP_RESEARCH`?
2. It calls `run_research()` from archivist - what parameters does it pass?
3. How does it store results in memory? What metadata?
4. What configuration options exist (`config.research.*`)?
5. How are errors handled? Progress callbacks?
6. Can we safely call `orchestrator.run_mission()` from here instead?

**Deliverable**: Integration points documented, proposed changes

---

## Task 0.2: Test Infrastructure Setup

### 0.2.1 Create Test Database
- [ ] Spin up local PostgreSQL with Docker: `docker run -p 5432:5432 -e POSTGRES_PASSWORD=test postgres:15`
- [ ] Run any existing migrations (find them)
- [ ] Create `corpus` schema if needed
- [ ] Verify connection from Python test: `asyncpg.connect(...)`

**Deliverable**: `src/research/tests/conftest.py` with `postgres_fixture` that returns test database

### 0.2.2 Mock Components
Create test doubles for components not fully implemented yet:

- [ ] `MockAdaptiveFrontier`: Returns predetermined concepts, tracks visited URLs
- [ ] `MockBudgetMonitor`: Simulates threshold crossings, tracks usage
- [ ] `MockDistillationPipeline`: Generates fake atoms from sources
- [ ] `MockCrawler`: Simulates fetching URLs with configurable latency

**Deliverable**: `src/research/tests/mocks.py`

### 0.2.3 Integration Test Fixtures
Create sample data for end-to-end testing:

- [ ] Sample corpus: 100 fake sources across 5 topics (JSON)
  - Each source: `source_id`, `url`, `content` (short text), `mission_id`, `status`
- [ ] Sample atoms: 100 knowledge atoms derived from sources (JSON)
- [ ] Sample frontier state: 20 concepts with yield history

**Deliverable**: `tests/fixtures/research/sample_corpus.json`, `sample_atoms.json`

### 0.2.4 Integration Test: Smoke Test
Write a minimal integration test that proves the pieces can talk:

```python
@pytest.mark.asyncio
async def test_basic_dataflow():
    # Arrange: create orchestrator with mocks
    orchestrator = ResearchOrchestrator(
        frontier=MockFrontier(),
        crawler=MockCrawler(),
        budget=MockBudgetMonitor(),
        condensation=MockDistillationPipeline(),
        index=ArchivistIndex(...)  # maybe in-memory?
    )

    # Act: run mission for 10 seconds
    result = await asyncio.wait_for(
        orchestrator.run_mission("test topic", ceiling_gb=0.001),
        timeout=10.0
    )

    # Assert: some sources fetched, some atoms extracted
    assert result['sources_fetched'] > 0
    assert result['atoms_extracted'] > 0
```

**Deliverable**: `tests/research/integration/test_smoke.py`

---

## Task 0.3: Validate Assumptions

### 0.3.1 Confirm PostgreSQL Access
- [ ] Find where condensation code uses `self.adapter.pg`
- [ ] What is `self.adapter`? (Look at `condensation/pipeline.py:__init__`)
- [ ] Find the adapter class (maybe in `src/research/` or `src/core/`)
- [ ] Confirm we can write to `corpus.sources` and `corpus.atoms`
- [ ] Run a simple INSERT/SELECT test

**Deliverable**: Confirmation note in `docs/analysis/postgres_validation.md`

### 0.3.2 Check Existing Schema
- [ ] Search for `.sql` files: `find . -name "*.sql"`
- [ ] Search for `CREATE TABLE`: `grep -r "CREATE TABLE" src/`
- [ ] Look for Alembic migrations: `find . -name "*migration*" -o -name "alembic"`
- [ ] If none exist, we need to define schema ourselves

**Deliverable**: `docs/analysis/schema_status.md` - "Schema exists at X" OR "Need to create"

### 0.3.3 Verify Archivist Index is Extensible
- [ ] Read `archivist/index.py` thoroughly
- [ ] Can we add `search_raw_chunks()` without breaking existing functionality?
- [ ] What would the query filter look like? Where would `mission_id` be stored?
- [ ] How are raw chunks currently stored? In the same table as atoms?

**Deliverable**: `docs/analysis/index_extension_plan.md`

### 0.3.4 Check Existing Monitoring
- [ ] Look for existing Prometheus metrics in the codebase
- [ ] Is there already a `/metrics` endpoint? Where?
- [ ] What monitoring exists for research missions currently?
- [ ] Look for structured logging patterns

**Deliverable**: `docs/analysis/monitoring_inventory.md`

---

## Task 0.4: Environment & Tooling

### 0.4.1 Development Environment Checklist
- [ ] Python 3.10+ virtualenv
- [ ] `pip install -e .[dev]` (find correct extras)
- [ ] Docker and docker-compose for PostgreSQL + Redis
- [ ] `make` installed (if we'll use Makefile)
- [ ] IDE configured: Black, isort, mypy pre-commit hooks

**Deliverable**: `docs/setup/dev_environment_checklist.md`

### 0.4.2 Testing Tools
- [ ] Install pytest-asyncio: `pip install pytest-asyncio`
- [ ] Install pytest-mock: `pip install pytest-mock`
- [ ] Install testcontainers (optional, for integration tests): `pip install testcontainers[postgresql]`
- [ ] Verify `pytest` runs existing tests: `pytest tests/research/`

**Deliverable**: `docs/setup/testing_tools.md`

### 0.4.3 Logging & Debugging Setup
- [ ] Confirm `structlog` is configured (check `src/utils/logging_config.py`)
- [ ] Set log level to DEBUG for development: `LOG_LEVEL=DEBUG`
- [ ] Create `.env.dev` with appropriate settings for testing
- [ ] Test: can we see logs from different modules?

**Deliverable**: `docs/setup/logging_debugging.md`

---

## Task 0.5: Create Planning Artifacts

### 0.5.1 Update ARCHITECTURE.md
Add section describing the **new unified architecture** (from this roadmap).

**Where to insert**: After existing architecture section, before code structure.
**Content**: High-level diagram (from §2.1), data flows (§2.2), storage model (§2.3)

**Deliverable**: Updated `docs/ARCHITECTURE.md`

### 0.5.2 Create ADRs (Architecture Decision Records)
Create ADRs for major decisions:

- [ ] **ADR-001**: Why unified orchestrator vs replacing archivist?
- [ ] **ADR-002**: Two-tier knowledge storage (raw + condensed) - why?
- [ ] **ADR-003**: Interactive query design - why separate endpoint vs extending run_research?
- [ ] **ADR-004**: PostgreSQL schema choice for corpus storage

**Directory**: `docs/adr/` (create if not exists)
**Format**: Use standard ADR template (context, decision, consequences, alternatives)

**Deliverable**: 4 ADR files in `docs/adr/`

### 0.5.3 Create Phase Documentation
Create detailed planning for next phases:

- [ ] `docs/planning/phase1_orchestrator.md` - detailed class design, method signatures
- [ ] `docs/planning/phase2_condensation_bridge.md` - data model transformations
- [ ] `docs/planning/phase3_exhaustion.md` - algorithm details, edge cases
- [ ] `docs/planning/phase4_testing.md` - test matrix, fixtures needed
- [ ] `docs/planning/phase5_migration.md` - backward compatibility strategy
- [ ] `docs/planning/phase6_query_layer.md` - API design, confidence scoring algorithm

**Deliverable**: 6 phase planning docs

---

## Phase 0 Deliverables Checklist

**Codebase Understanding**:
- [ ] `docs/analysis/adaptive_frontier.md`
- [ ] `docs/analysis/budget_monitor.md`
- [ ] `docs/analysis/distillation_pipeline.md`
- [ ] `docs/analysis/archivist_index.md`
- [ ] `docs/analysis/database_schema.md`
- [ ] `docs/analysis/postgres_validation.md`
- [ ] `docs/analysis/index_extension_plan.md`
- [ ] `docs/analysis/monitoring_inventory.md`

**Test Infrastructure**:
- [ ] `src/research/tests/conftest.py` with fixtures
- [ ] `src/research/tests/mocks.py`
- [ ] `tests/fixtures/research/sample_corpus.json`
- [ ] `tests/integration/research/test_smoke.py`

**Environment**:
- [ ] `docs/setup/dev_environment_checklist.md`
- [ ] `docs/setup/testing_tools.md`
- [ ] `docs/setup/logging_debugging.md`

**Planning**:
- [ ] Updated `docs/ARCHITECTURE.md`
- [ ] `docs/adr/001-unified-orchestrator.md`
- [ ] `docs/adr/002-two-tier-storage.md`
- [ ] `docs/adr/003-interactive-query.md`
- [ ] `docs/adr/004-postgres-schema.md`
- [ ] 6 phase planning documents

**Validation**:
- [ ] `docs/analysis/schema_status.md` - exists or create
- [ ] Confirmed PostgreSQL connectivity
- [ ] Confirmed ArchivistIndex extensibility
- [ ] Verified logging configuration
- [ ] All existing tests passing locally

---

## Phase 0 Entry Criteria
- ✅ Roadmap approved (`.planning/knowledge_distillation_roadmap.md`)
- ✅ Environment set up with Python, Docker, dependencies
- ✅ Database credentials configured (`.env`)

## Phase 0 Exit Criteria
- ✅ All deliverables above complete
- ✅ Team has read all analysis docs
- ✅ Integration test at least 50% passing (mocks can fill gaps)
- ✅ ADRs reviewed and approved
- ✅ Ready to start Phase 1 (Orchestrator implementation)

---

## Quick Start Commands

```bash
# 1. Create analysis directory
mkdir -p docs/analysis
mkdir -p docs/adr
mkdir -p docs/planning
mkdir -p docs/setup
mkdir -p src/research/tests
mkdir -p tests/fixtures/research

# 2. Start test database
docker run -d --name sheppard-test-postgres \
  -p 5433:5432 \
  -e POSTGRES_PASSWORD=test \
  -e POSTGRES_DB=sheppard_test \
  postgres:15

# 3. Create .env.dev if not exists
cp .env.example .env.dev
# Edit .env.dev with test database connection

# 4. Verify imports work
python -c "from src.research.acquisition.frontier import AdaptiveFrontier; print('OK')"
```

---

**Notes**:
- This phase is about **discovery and preparation**, not implementation
- The goal is to de-risk Phase 1 by understanding all components thoroughly
- If major architectural issues discovered during analysis, update roadmap and ADRs
- Keep analysis docs concise but precise - they're reference for implementation
