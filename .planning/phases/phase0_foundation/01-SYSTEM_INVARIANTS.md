# PHASE 0: FOUNDATION — System Invariants & Contracts

**Status**: AUTHORITATIVE
**Applies To**: Entire V3 codebase
**Based On**: README architecture + ambiguity resolution

---

## 1. Core Invariants (NON-NEGOTIABLE)

### I-1: Data Authority Invariant

```
Postgres = canonical truth
Chroma = semantic projection (retrieval only)
Redis = execution state (queues, locks, transient)
```

**Enforcement Rule**: If Postgres and Chroma disagree, **Postgres wins**. Chroma must be rebuildable from Postgres at any time. Redis state must be disposable without data loss.

---

### I-2: Mission Isolation Invariant

`mission_id` is the **primary tenancy boundary**.

**Rules**:
- No cross-mission reads by default
- All persistent data tables (except config) MUST include `mission_id`
- Cross-mission synthesis requires explicit `cross_mission=True` flag

---

### I-3: Lineage Invariant

Every knowledge atom MUST be traceable:

```
Atom → Evidence → Raw Chunk → Source → Mission
```

**Enforcement**:
- No atom can exist without evidence links
- No evidence without source reference
- Deleting lineage = **INVALID STATE** (forbidden)

---

### I-4: Asynchronous Execution Invariant

- All long-running operations are **non-blocking**
- No API call may depend on crawl/distillation completion
- Use `202 Accepted` + event stream for async operations

---

### I-5: Idempotency Invariant

All writes must be safe to retry. Required for:
- URL ingestion
- Atom creation
- Distillation writes
- Fetch attempts

**Implementation**: Use database unique constraints + `ON CONFLICT DO NOTHING/UPDATE`.

---

## 2. Data Contracts

### D-1: KnowledgeAtom (Final Schema)

```sql
CREATE TABLE corpus.atoms (
    atom_id UUID PRIMARY KEY,
    mission_id UUID NOT NULL,
    atom_type TEXT NOT NULL CHECK (atom_type IN ('fact', 'claim', 'tradeoff', 'definition', 'procedure', 'caveat')),

    title TEXT,
    statement TEXT NOT NULL,
    normalized_statement TEXT,

    subject TEXT,
    predicate TEXT,
    object TEXT,

    confidence NUMERIC(3,2) CHECK (confidence >= 0 AND confidence <= 1),
    freshness_score NUMERIC(3,2),
    coverage_tags JSONB,

    source_count INTEGER,
    agreement_score NUMERIC(3,2),
    contradiction_flag BOOLEAN DEFAULT false,

    status TEXT NOT NULL CHECK (status IN ('provisional', 'verified', 'disputed', 'deprecated')),

    lineage JSONB NOT NULL,  -- Full lineage chain: {source_ids: [], chunk_ids: [], mission_id: ...}

    distilled_by_model TEXT,
    distillation_version TEXT,

    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes
CREATE INDEX idx_atoms_mission_id ON corpus.atoms(mission_id);
CREATE INDEX idx_atoms_mission_status ON corpus.atoms(mission_id, status);
CREATE INDEX idx_atoms_mission_type ON corpus.atoms(mission_id, atom_type);
CREATE INDEX idx_atoms_contradiction ON corpus.atoms(mission_id, contradiction_flag) WHERE contradiction_flag = true;
```

---

### D-2: AtomEvidence (Join Table)

```sql
CREATE TABLE corpus.atom_evidence (
    atom_id UUID NOT NULL REFERENCES corpus.atoms(atom_id) ON DELETE CASCADE,
    source_id UUID NOT NULL,
    raw_chunk_id UUID NOT NULL,
    evidence_span JSONB,  -- {start: int, end: int} within chunk
    quote_hash TEXT,      -- SHA256 of quoted text for dedup

    PRIMARY KEY (atom_id, source_id, raw_chunk_id)
);

CREATE INDEX idx_atom_evidence_atom ON corpus.atom_evidence(atom_id);
CREATE INDEX idx_atom_evidence_source ON corpus.atom_evidence(source_id);
CREATE INDEX idx_atom_evidence_chunk ON corpus.atom_evidence(raw_chunk_id);
```

---

### D-3: ConceptTask Contract (Frontier Output)

```python
@dataclass
class ConceptTask:
    concept_id: str          # UUID
    mission_id: str          # UUID
    label: str               # Human-readable concept name
    depth: int               # 0=root, 1=child, etc.
    parent_concept_id: str | None

    mode: Literal["grounding", "expansion", "dialectic", "verification"]
    priority: float          # 0.0-1.0

    search_queries: List[str]
    stop_reason: str | None  # Populated when concept is closed
```

---

### D-4: Mission State (ops.mission_state)

```sql
CREATE TABLE ops.mission_state (
    mission_id UUID PRIMARY KEY,
    topic TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('initializing', 'crawling', 'distilling', 'queryable', 'completed', 'cancelled', 'failed')),

    frontier_state JSONB,      -- Current frontier nodes, exhaustion info
    budget_state JSONB,        -- raw_bytes, condensed_bytes, ceiling
    stats JSONB,               -- sources_fetched, atoms_extracted, etc.

    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
```

---

## 3. Execution Contracts

### E-1: Frontier Contract

```python
class AdaptiveFrontier:
    async def run(
        self,
        mission_id: str,
        topic: str
    ) -> AsyncIterator[ConceptTask]:
        """
        Yields ConceptTask objects. Does NOT fetch.
        Stateless across workers; all state persisted to ops.mission_state.
        """
```

**Rules**:
- Emits tasks only
- No network I/O (except policy fetch if needed)
- All state persisted transactionally

---

### E-2: Crawler Contract

```python
class Crawler:
    async def crawl_concept(
        self,
        mission_id: str,
        task: ConceptTask
    ) -> CrawlBatchResult:
        """
        Returns batch of fetched URLs + extracted chunks.
        Does NOT write to DB directly. Returns data for adapter to persist.
        """

    async def fetch_url(
        self,
        mission_id: str,
        url: str,
        context: FetchContext
    ) -> FetchResult:
        """Low-level fetch used by workers."""
```

**Rules**:
- Deduplication at DB layer (unique constraint on `(mission_id, url_hash)`)
- Never writes atoms
- Returns structured `RawChunk` objects

---

### E-3: DistillationPipeline Contract

```python
class DistillationPipeline:
    def __init__(self, adapter: CorpusAdapter, llm: LLMClient, budget: BudgetMonitor):
        ...

    async def run(self, mission_id: str, priority: CondensationPriority):
        """
        Pulls unprocessed chunks via adapter.
        Writes atoms + evidence via adapter.
        Does NOT fetch.
        """
```

**Rules**:
- Pull-based from `adapter.get_unprocessed_chunks(mission_id, limit)`
- Writes only via `adapter.write_atoms()`
- Updates chunk status via `adapter.mark_chunks_distilled()`

---

### E-4: CorpusAdapter Contract (CRITICAL BOUNDARY)

```python
class CorpusAdapter(Protocol):
    # Read
    async def get_unprocessed_chunks(
        self,
        mission_id: str,
        limit: int
    ) -> List[RawChunk]: ...

    async def fetch_source_context(
        self,
        source_id: str
    ) -> SourceContext: ...

    # Write
    async def write_atoms(
        self,
        mission_id: str,
        atoms: List[KnowledgeAtom],
        evidence: List[AtomEvidence]
    ) -> None: ...

    async def mark_chunks_distilled(
        self,
        chunk_ids: List[str]
    ) -> None: ...

    async def record_source(
        self,
        mission_id: str,
        url: str,
        metadata: dict
    ) -> str: ...  # Returns source_id

    async def ensure_source(
        self,
        mission_id: str,
        url: str,
        metadata: dict
    ) -> str: ...  # Idempotent: returns existing or creates
```

**Invariant**: This is the **ONLY** component allowed to write to Postgres corpus tables.

---

### E-5: ArchivistIndex Contract (Retrieval Facade)

```python
class ArchivistIndex:
    async def search_atoms(
        self,
        mission_id: str,
        query: str,
        k: int = 10,
        filters: dict | None = None
    ) -> List[AtomSearchResult]: ...

    async def search_raw_chunks(
        self,
        mission_id: str,
        query: str,
        k: int = 20,
        include_distilled: bool = False  # Exclude if already atomized
    ) -> List[ChunkSearchResult]: ...

    async def get_source(self, source_id: str) -> SourceRecord | None: ...
    async def get_atom(self, atom_id: str) -> AtomRecord | None: ...
    async def list_mission_sources(self, mission_id: str) -> List[SourceSummary]: ...
```

**Rules**:
- Read-only from Postgres + Chroma projection
- If Chroma and Postgres disagree, Postgres wins
- All queries filtered by `mission_id` unless `cross_mission=True`

---

## 4. Retrieval Visibility Policy (QUARANTINE RULE)

### V-1: Visibility Levels

| Level | Description | Who Can See |
|-------|-------------|-------------|
| `canonical` | Verified/promoted knowledge | All agent queries |
| `mission_local` | Distilled in current mission | Current mission queries |
| `quarantined` | Raw, unprocessed crawl artifacts | Operator debug only |
| `archived` | Old missions, soft-deleted | Special admin mode |

---

### V-2: Query Mode Filters

```python
class QueryMode(Enum):
    AGENT_DEFAULT = "agent_default"       # canonical only
    MISSION_ACTIVE = "mission_active"     # canonical + current mission mission_local
    OPERATOR_DEBUG = "operator_debug"     # includes quarantined
    REPORT_GENERATION = "report"          # canonical + mission_local for specific mission

# Filter rules
QUERY_FILTERS = {
    QueryMode.AGENT_DEFAULT: {
        "visibility": ["canonical"],
        "status": ["verified", "promoted"]
    },
    QueryMode.MISSION_ACTIVE: {
        "mission_id": current_mission,
        "visibility": ["canonical", "mission_local"],
        "status": ["distilled", "verified", "promoted"]
    },
    QueryMode.OPERATOR_DEBUG: {
        "mission_id": current_mission,
        "visibility": ["canonical", "mission_local", "quarantined"]
    }
}
```

**Rule**: The agent's normal conversation uses `AGENT_DEFAULT`. Active research missions can query their own `MISSION_ACTIVE` data. Never leak one mission's quarantined data to another mission or to agent default.

---

## 5. Budget & Condensation Model

### B-1: Budget Dimensions (Track Per Mission)

- `raw_storage_bytes` (sum of source body lengths)
- `chunk_count`
- `atom_count`
- `embedding_count` (approx from Chroma)
- `queue_pressure` (Redis queue depth)

**Source of Truth**: `ops.budget_events` table with aggregated counters.

---

### B-2: Condensation Trigger Policy

| Threshold | Action |
|-----------|--------|
| soft (70%) | Schedule condensation job (low priority) |
| hard (85%) | Block new raw ingestion, urgent condensation |
| critical (95%) | Aggressive condensation + prune raw |

**Implementation**:
- Emit `CONDENSATION_REQUESTED` event
- Enqueue mission-scoped job to Redis
- Deduplicate by `(mission_id, generation)`
- Backpressure at hard threshold

---

## 6. Failure Contracts

### F-1: Fetch Failure Policy

| Error Type | Retry | Max Attempts | Action |
|------------|-------|--------------|--------|
| Timeout | exponential backoff | 3 | Fail to next URL |
| 5xx | exponential backoff | 3 | Fail to next URL |
| 429 | respect `Retry-After` + jitter | 5 | Fail if still rate-limited |
| 403 | single retry (if proxy rotation) | 1-2 | Mark as blocked |
| Parse error | repair attempt (clean HTML) | 1 | Mark as parse_failed |
| robots.txt denied | none | 0 | Mark as blocked |

**Record**: Every attempt in `corpus.source_fetch_attempts(mission_id, source_id, attempt_num, status, error)`.

---

### F-2: LLM Failure Policy

**During distillation**:
- Retry once on network error
- On second failure: mark source as `llm_failed`, continue with others
- Log structured error with `mission_id`, `source_id`

**During query**:
- Fast retry once (transient)
- Fallback from synthesis mode to retrieval-only answer
- Return `{"status": "degraded", "answer": "...", "sources": [...]}`

---

### F-3: Storage Failure Policy

| Component | Failure Mode | Response |
|-----------|--------------|----------|
| Postgres | HARD FAIL | Cannot proceed; log CRITICAL; halt mission |
| Redis | degraded | Queue locally, retry with backoff; continue |
| Chroma | degraded | Retrieval falls back to Postgres text search; continue |

---

## 7. Concurrency & Race Protection

### Required Protections

1. **Database unique constraints**:
   ```sql
   UNIQUE(mission_id, url_hash) ON corpus.sources
   UNIQUE(mission_id, normalized_statement) ON corpus.atoms
   ```

2. **Redis distributed locks**:
   - Mission coordinator leadership
   - Condensation job execution

3. **Idempotency keys**: On all fetch and distillation writes

4. **Atomic transactions**:
   ```python
   async with db.transaction():
       source = await adapter.ensure_source(mission_id, url, meta)
       await adapter.write_chunks(chunks)
   ```

---

## 8. API Architecture

### 8.1 REST (Control Plane)

```http
POST   /api/v1/missions              # Create mission, returns mission_id
DELETE /api/v1/missions/{id}         # Cancel mission (202 Accepted)
GET    /api/v1/missions/{id}         # Get mission metadata
GET    /api/v1/missions/{id}/status  # Current status, stats
POST   /api/v1/missions/{id}/query   # Query knowledge (blocking, <5s)
GET    /api/v1/missions/{id}/report  # Generate final report (async, 202)
```

---

### 8.2 Event Stream (Data Plane)

**WebSocket**: `/ws/missions/{id}/events`

**Events**:
```json
{"type": "frontier.concept", "data": {concept: {...}}}
{"type": "crawl.source_fetched", "data": {source_id: "...", url: "..."}}
{"type": "distillation.atoms_extracted", "data": {count: 42}}
{"type": "budget.threshold_crossed", "data": {threshold: "hard", usage: 0.87}}
{"type": "mission.completed", "data": {reason: "exhausted"}}
```

---

## 9. CLI Contract

```bash
# Create and start mission (non-blocking, returns mission_id)
sheppard mission start "quantum computing" --ceiling 10GB

# Check status
sheppard mission status <mission_id>

# Query (blocking, returns answer)
sheppard query <mission_id> "What is quantum entanglement?"

# Stop mission
sheppard mission stop <mission_id>

# Get final report (when completed)
sheppard mission report <mission_id> > report.md

# List missions
sheppard mission list

# Stream events (like tail -f)
sheppard mission logs <mission_id> --follow
```

---

## 10. Configuration System

**Layered** (later overrides earlier):

1. `config.defaults.YAML`
2. Environment variables (PREFIXED: `SHEPPARD_`)
3. Config file (`~/.config/sheppard/config.yaml`)
4. CLI flags

**Typed structure** (Pydantic):

```python
class DatabaseConfig(BaseSettings):
    postgres_url: str
    chroma_url: str
    redis_url: str

class FrontierConfig(BaseSettings):
    max_concepts_per_mission: int = 1000
    concept_expansion_factor: int = 3
    saturation_window: int = 10

class BudgetConfig(BaseSettings):
    ceiling_gb: float = 5.0
    threshold_soft: float = 0.70
    threshold_hard: float = 0.85
    threshold_critical: float = 0.95
    poll_interval_secs: float = 10.0

class ResearchConfig(BaseSettings):
    frontier: FrontierConfig
    budget: BudgetConfig
    distillation: DistillationConfig
    crawler: CrawlerConfig
```

---

## 11. Implementation Order (Phase 1-7)

1. **Schema migrations** (Postgres tables + indexes)
2. **CorpusAdapter** (persistence boundary)
3. **AdaptiveFrontier** (with state persistence)
4. **Crawler + Worker pool** (with Redis queue)
5. **DistillationPipeline** (with adapter)
6. **ArchivistIndex** (read facade + Chroma projection)
7. **ResearchOrchestrator** (coordination + query)
8. **API layer** (REST + WebSocket)
9. **CLI layer**
10. **Integration tests** (end-to-end)

---

## 12. Verification Checklist

Phase 0 complete when:

- [ ] All contracts documented above
- [ ] Schema SQL reviewed and approved
- [ ] CorpusAdapter interface locked
- [ ] Frontier API fixed (`ConceptTask` dataclass)
- [ ] Retrieval visibility policy implemented in index
- [ ] Failure policies coded (retry handlers)
- [ ] Concurrency protections verified (constraints, locks)
- [ ] Test plan for each subsystem written
- [ ] Configuration system designed

---

## 13. Non-Goals (Deferred)

- UI/UX (separate track after backend)
- Advanced synthesis model tuning
- Performance optimization (benchmark after MVP)
- Multi-tenancy auth (assume trusted environment)
- Graph database scaling (tolerate in-memory for <10k nodes)

---

**Document Version**: 1.0
**Last Updated**: 2025-03-27
**Owner**: Architecture Review Board
