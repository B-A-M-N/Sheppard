# PHASE 1 — IMPLEMENTATION PLAN (GSD Format)

**Base**: V3.1 (Post-README)
**Mission**: Build production-grade substrate for distributed, agent-interactive, continuously learning knowledge refinery
**Duration**: 3-4 weeks
**Owner**: Implementation Team

---

## 1. MISSION STATEMENT

Implement Sheppard V3 as a **distributed, mission-scoped knowledge refinery** with:

* ✅ Triad authority (Postgres truth, Chroma projection, Redis motion)
* ✅ Quarantined crawl state (never visible to agent by default)
* ✅ Atomic distillation with immutable lineage
* ✅ Live agent interaction during active crawl
* ✅ `/nudge`-driven frontier steering
* ✅ Concurrent mission support

**Must not violate**:
* Agent default sees only canonical knowledge
* Redis never stores truth
* Raw crawl data never promoted without evidence
* Mission isolation absolute unless explicitly crossed

---

## 2. ACCEPTANCE CRITERIA (Hard Gates)

Phase 1 complete when **all** of these pass:

| # | Criterion | Test |
|---|-----------|------|
| AC1 | Agent default queries exclude quarantined state | Integration test: run mission, query before any atoms distilled → answer says "insufficient data" |
| AC2 | Duplicate URL fetch prevented across workers | Concurrent fetch of same URL by 2 workers → only one DB insert |
| AC3 | Atom deduplication works | Same chunk processed twice → only one atom with evidence count=2 |
| AC4 | All atoms have evidence lineage | DB constraint: `atom_evidence` must exist for every atom in `mission_active` or `canonical` |
| AC5 | Stop request is asynchronous | API returns 202 immediately; background tasks cancel within 30s |
| AC6 | `/nudge` affects frontier only, not truth | Nudge changes concept priority; does not create atoms directly |
| AC7 | Chroma rebuildable from Postgres | `scripts/rebuild_chroma.py` produces identical search results |
| AC8 | Redis loss does not corrupt knowledge | Flush Redis; restart; system continues from Postgres state |
| AC9 | Mission isolation enforced | Mission A cannot query Mission B's atoms even if Mission B is active |
| AC10 | Retrieval modes work correctly | `agent_default` vs `mission_active` vs `operator_debug` return appropriate sets |

---

## 3. SCOPE & DELIVERABLES

### In Scope (Phase 1)

1. **Database schema** - All V3 tables with constraints and indexes
2. **Mission state machine** - States, transitions, persistence
3. **Knowledge state model** - `visibility` + `status` fields, promotion logic
4. **CorpusAdapter** - Canonical write boundary (Postgres + Chroma projection)
5. **URL deduplication + Redis lease protocol** - Distributed crawl coordination
6. **Crawler worker** - `fetch_url()` with retry, evidence, error handling
7. **Distillation worker** - `reserve_distillable_chunks()` → extract atoms → `write_atoms()`
8. **ArchivistIndex retrieval modes** - `search_atoms()`, `search_raw_chunks()` with visibility filters
9. **MissionOrchestrator** - Coordinates frontier, crawl, distill; handles `/nudge`, `/stop`
10. **API surface** - REST for control, SSE for events; `query_knowledge()` with mode selection
11. **CLI commands** - `mission start/status/stop/nudge/report`, `query`, `worker crawl/distill`
12. **Migrations** - Idempotent SQL + version tracking
13. **Test suite** - Unit, integration (with Firecrawl-local), property tests

### Out of Scope (Later Phases)

* UI (web interface)
* Advanced synthesis model tuning
* Scaling beyond single PostgreSQL instance
* Multi-node Chroma clustering
* Advanced conflict resolution UI
* Graph database integration (SWOC not yet)
* Performance optimization (benchmark after ACs met)

---

## 4. IMPLEMENTATION ORDER (Dependency-Aware)

### Week 1: Foundation

**Day 1-2**: Schema & Migrations
- File: `migrations/V3.1.0__initial_schema.sql`
- Tables: `research.missions`, `research.concepts`, `corpus.sources`, `corpus.raw_chunks`, `corpus.atoms`, `corpus.atom_evidence`, `ops.mission_state`, `ops.mission_events`, `ops.budget_snapshots`
- Indexes: All `mission_id` indexes, unique constraints on `(mission_id, url_hash)`, `(mission_id, atom_hash)`
- Triggers: `updated_at` triggers
- Validation: CHECK constraints for enums (`visibility`, `status`, `atom_type`)

**Day 3-4**: Config & Types
- File: `src/research/config.py` (extend existing)
- Add namespaces: `frontier`, `crawler`, `distillation`, `api`, `budget`
- File: `src/research/models_v3.py` (new)
- Dataclasses: `ConceptTask`, `KnowledgeAtom`, `AtomEvidence`, `MissionState`, `CrawlResult`, `FetchResult`, `DistillationJob`

**Day 5**: CorpusAdapter Protocol
- File: `src/research/adapter.py`
- Define Protocol class with all methods
- Implement `PostgresCorpusAdapter` with:
  - `reserve_distillable_chunks(mission_id, limit)`
  - `write_atoms(mission_id, atoms, evidence)`
  - `mark_chunks_distilled(chunk_ids)`
  - `ensure_source(mission_id, url, meta)` → `source_id` (idempotent)
- Write unit tests with mock DB

### Week 2: Core Ingestion

**Day 6-7**: URL Deduplication + Redis Lease
- File: `src/research/queue.py`
- `acquire_fetch_lease(url_hash) → lease_id` (Redis SET NX EX)
- `release_fetch_lease(lease_id)`
- `enqueue_urls(mission_id, urls)` (priority queue: ZADD with score from frontier)
- File: `src/research/crawler.py` (extend existing)
- `fetch_url()` uses lease, writes to `corpus.sources` with `status='fetched'`, stores raw in `corpus.text_refs` or compressed file

**Day 8-9**: Crawler Worker
- File: `src/workers/crawl_worker.py` (new)
- Loops: `while True: task = redis.blpop(...); crawl_and_store(task)`
- Error handling per retry policy (F-1)
- Update `corpus.sources.status` appropriately
- Publish `crawl.complete` event to Redis pub/sub

**Day 10**: Frontier → Queue Integration
- File: `src/research/frontier.py` (extend existing AdaptiveFrontier)
- Replace `sm.crawler.discover_and_enqueue()` with direct Redis queue push
- Ensure `ConceptTask` includes `mode` and `priority`
- Add `apply_nudge(mission_id, instruction)` method

### Week 3: Distillation & Retrieval

**Day 11-12**: Distillation Worker
- File: `src/workers/distill_worker.py` (new)
- Subscribe to `distill.*` channel
- Call `adapter.reserve_distillable_chunks(mission_id, limit)`
- Run LLM extraction (use `extract_technical_atoms` from existing)
- Call `adapter.write_atoms()`
- Publish `distill.complete` event

**Day 13-14**: ArchivistIndex Retrieval Modes
- File: `src/research/archivist/index.py` (extend)
- Add `search_raw_chunks(mission_id, query, k, visibility_filter)` → queries Chroma with `mission_id` metadata
- Add `search_atoms(mission_id, query, k, mode)` → queries atoms table + optional Chroma embedding
- Implement `get_mission_sources(mission_id)`
- Add `visibility` filter logic (AC1)

**Day 15**: MissionOrchestrator
- File: `src/research/orchestrator.py` (new)
- `start_mission(topic, config)` → creates `mission_id`, initializes frontier task
- `run_mission_async(mission_id)` → orchestrates:
  - frontier loop (produces ConceptTask → enqueue)
  - monitor budget (triggers distillation)
  - handle `/nudge`
  - update `ops.mission_state`
- `query_knowledge(mission_id, question, mode)` → uses ArchivistIndex
- `stop_mission(mission_id)` → sets cancelled flag, signals workers

### Week 4: API, CLI & Tests

**Day 16-17**: REST + SSE API
- File: `src/interfaces/api.py` (new or extend)
- Endpoints:
  - `POST /api/v1/missions` → `start_mission()`
  - `DELETE /api/v1/missions/{id}` → `stop_mission()`
  - `GET /api/v1/missions/{id}/status` → reads `ops.mission_state`
  - `POST /api/v1/missions/{id}/nudge` → `orchestrator.apply_nudge()`
  - `POST /api/v1/missions/{id}/query` → `query_knowledge()`
  - `GET /api/v1/missions/{id}/events` → SSE stream (mission events)
  - `GET /api/v1/missions/{id}/report` → async, stores report in `authority.synthesis_artifacts`
- WebSocket optional (can defer to UI phase)

**Day 18-19**: CLI
- File: `src/interfaces/cli.py` (new)
- Commands as defined in A.21
- Use Typer or Click
- Hook to `ResearchOrchestrator` methods

**Day 20-21**: Integration Tests
- File: `tests/integration/test_mission_lifecycle.py`
- Test: start mission → simulate crawl (mock worker) → simulate distill → query → stop
- Verify AC1-AC10
- File: `tests/integration/test_distributed_crawl.py`
- Test concurrent workers fetching same URL → dedupe
- File: `tests/integration/test_nudge.py`
- Test nudge modifies frontier priority
- Run full suite; ensure coverage ≥80%

---

## 5. DETAILED TASK BREAKDOWN

### Task 1: Schema Design & Migrations

**Files**:
- `migrations/V3.1.0__initial_schema.sql`
- `src/research/schema.py` (helpers)

**Spec**:

```sql
-- research.missions
CREATE TABLE research.missions (
    mission_id UUID PRIMARY KEY,
    topic TEXT NOT NULL,
    title TEXT,
    status TEXT NOT NULL CHECK (status IN ('initializing','discovering','crawling','distilling','condensing','awaiting_input','completed','failed','stopped')),
    config_json JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- research.concepts (frontier nodes)
CREATE TABLE research.concepts (
    concept_id UUID PRIMARY KEY,
    mission_id UUID NOT NULL REFERENCES research.missions(mission_id) ON DELETE CASCADE,
    parent_concept_id UUID REFERENCES research.concepts(concept_id),
    label TEXT NOT NULL,
    mode TEXT NOT NULL CHECK (mode IN ('grounding','verification','dialectic','expansion')),
    priority FLOAT NOT NULL DEFAULT 0.0,
    status TEXT NOT NULL CHECK (status IN ('underexplored','active','saturated','closed')),
    metadata_json JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_concepts_mission_id ON research.concepts(mission_id);
CREATE UNIQUE INDEX uq_concepts_mission_label ON research.missions(mission_id, label);  -- dedupe

-- corpus.sources
CREATE TABLE corpus.sources (
    source_id UUID PRIMARY KEY,
    mission_id UUID NOT NULL REFERENCES research.missions(mission_id) ON DELETE CASCADE,
    url TEXT NOT NULL,
    url_hash TEXT NOT NULL,
    domain TEXT,
    title TEXT,
    source_class TEXT,
    status TEXT NOT NULL DEFAULT 'discovered',
    canonical_text_ref TEXT,  -- references corpus.text_refs.blob_id
    content_hash TEXT,
    fetched_at TIMESTAMPTZ,
    metadata_json JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE UNIQUE INDEX uq_sources_mission_url_hash ON corpus.sources(mission_id, url_hash);
CREATE INDEX idx_sources_mission_status ON corpus.sources(mission_id, status);

-- corpus.text_refs (for raw content storage)
CREATE TABLE corpus.text_refs (
    blob_id UUID PRIMARY KEY,
    storage_uri TEXT,
    compression_codec TEXT,
    byte_size BIGINT,
    sha256 TEXT,
    inline_text TEXT,
    metadata_json JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (storage_uri IS NOT NULL OR inline_text IS NOT NULL)
);

-- corpus.raw_chunks (optional, if storing chunks separately)
CREATE TABLE corpus.raw_chunks (
    chunk_id UUID PRIMARY KEY,
    source_id UUID NOT NULL REFERENCES corpus.sources(source_id) ON DELETE CASCADE,
    mission_id UUID NOT NULL REFERENCES research.missions(mission_id) ON DELETE CASCADE,
    chunk_index INT NOT NULL,
    chunk_hash TEXT NOT NULL,
    text_ref UUID REFERENCES corpus.text_refs(blob_id),
    inline_text TEXT,
    metadata_json JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(mission_id, chunk_hash)
);

-- corpus.atoms (knowledge atoms)
CREATE TABLE corpus.atoms (
    atom_id UUID PRIMARY KEY,
    mission_id UUID NOT NULL REFERENCES research.missions(mission_id) ON DELETE CASCADE,
    atom_hash TEXT NOT NULL,
    atom_type TEXT NOT NULL CHECK (atom_type IN ('fact','claim','tradeoff','definition','procedure','caveat')),
    title TEXT NOT NULL,
    statement TEXT NOT NULL,
    normalized_statement TEXT NOT NULL,
    subject TEXT,
    predicate TEXT,
    object TEXT,
    confidence FLOAT NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
    freshness_score FLOAT NOT NULL CHECK (freshness_score >= 0 AND freshness_score <= 1),
    source_count INT NOT NULL DEFAULT 0,
    agreement_score FLOAT NOT NULL CHECK (agreement_score >= 0 AND agreement_score <= 1),
    contradiction_flag BOOLEAN NOT NULL DEFAULT FALSE,
    visibility TEXT NOT NULL CHECK (visibility IN ('quarantined','mission_active','canonical','archived')),
    status TEXT NOT NULL CHECK (status IN ('distilled','verified','promoted','disputed','deprecated')),
    distilled_by_model TEXT,
    distillation_version TEXT,
    lineage_json JSONB NOT NULL DEFAULT '{}',
    metadata_json JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE UNIQUE INDEX uq_atoms_mission_hash ON corpus.atoms(mission_id, atom_hash);
CREATE INDEX idx_atoms_mission_visibility_status ON corpus.atoms(mission_id, visibility, status);
CREATE INDEX idx_atoms_contradiction ON corpus.atoms(mission_id, contradiction_flag) WHERE contradiction_flag = true;

-- corpus.atom_evidence
CREATE TABLE corpus.atom_evidence (
    atom_id UUID NOT NULL REFERENCES corpus.atoms(atom_id) ON DELETE CASCADE,
    source_id UUID NOT NULL REFERENCES corpus.sources(source_id) ON DELETE CASCADE,
    chunk_id UUID REFERENCES corpus.raw_chunks(chunk_id) ON DELETE SET NULL,
    evidence_strength FLOAT NOT NULL CHECK (evidence_strength >= 0 AND evidence_strength <= 1),
    supports_statement BOOLEAN NOT NULL DEFAULT TRUE,
    PRIMARY KEY (atom_id, source_id, chunk_id)
);
CREATE INDEX idx_atom_evidence_source ON corpus.atom_evidence(source_id);

-- ops.mission_state (current runtime state, rebuildable from events)
CREATE TABLE ops.mission_state (
    mission_id UUID PRIMARY KEY REFERENCES research.missions(mission_id) ON DELETE CASCADE,
    current_state TEXT NOT NULL,
    frontier_state JSONB NOT NULL DEFAULT '{}',
    budget_state JSONB NOT NULL DEFAULT '{}',
    stats JSONB NOT NULL DEFAULT '{}',
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ops.mission_events (event sourcing)
CREATE TABLE ops.mission_events (
    event_id BIGSERIAL PRIMARY KEY,
    mission_id UUID NOT NULL REFERENCES research.missions(mission_id) ON DELETE CASCADE,
    event_type TEXT NOT NULL,
    event_payload JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_mission_events_mission_created ON ops.mission_events(mission_id, created_at DESC);

-- ops.budget_snapshots (for accurate budget tracking)
CREATE TABLE ops.budget_snapshots (
    snapshot_id BIGSERIAL PRIMARY KEY,
    mission_id UUID NOT NULL REFERENCES research.missions(mission_id) ON DELETE CASCADE,
    raw_bytes BIGINT NOT NULL DEFAULT 0,
    chunk_bytes BIGINT NOT NULL DEFAULT 0,
    atom_count INT NOT NULL DEFAULT 0,
    embedding_count INT NOT NULL DEFAULT 0,
    queue_depth INT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_budget_snapshots_mission_created ON ops.budget_snapshots(mission_id, created_at DESC);
```

**Validation**: Run migration on clean DB; should succeed without errors.

---

### Task 2: Knowledge State Model

**Enums** (in `src/research/models_v3.py`):

```python
class KnowledgeVisibility(str, Enum):
    QUARANTINED = "quarantined"    # raw crawl, not agent-visible
    MISSION_ACTIVE = "mission_active"  # distilled in current mission
    CANONICAL = "canonical"        # verified, globally visible
    ARCHIVED = "archived"          # old mission, soft-deleted

class KnowledgeStatus(str, Enum):
    DISTILLED = "distilled"        # just extracted
    VERIFIED = "verified"          # evidence validated
    PROMOTED = "promoted"          # promoted to mission-active
    DISPUTED = "disputed"          # contradiction detected
    DEPRECATED = "deprecated"      # superseded
```

**Promotion Logic**:

```python
def promote_to_mission_active(atom: KnowledgeAtom) -> bool:
    """An atom is mission-usable if it has at least one evidence link and passes validation."""
    return (
        atom.visibility == KnowledgeVisibility.QUARANTINED and
        atom.status == KnowledgeStatus.DISTILLED and
        atom.lineage_json.get("evidence_links", [])  # non-empty
    )

def promote_to_canonical(atom: KnowledgeAtom) -> bool:
    """Canonical requires either multi-source agreement or high-confidence single-source."""
    if atom.contradiction_flag:
        return False
    if atom.source_count >= 2:
        return True
    if atom.agreement_score >= 0.9 and atom.confidence >= 0.95:
        return True  # high-confidence single-source exception (e.g., authoritative publication)
    return False
```

**Test**: Unit tests for these functions with edge cases.

---

### Task 3: CorpusAdapter Implementation

**File**: `src/research/adapter.py`

**Protocol** (interface):

```python
class CorpusAdapter(Protocol):
    async def reserve_distillable_chunks(self, mission_id: str, limit: int) -> List[RawChunk]:
        """Reserve chunks that are fetched but not yet distilled. Return list of RawChunk.
        Must be idempotent: same chunk should not be reserved by multiple workers.
        Implementation: UPDATE corpus.raw_chunks SET status='reserved' WHERE mission_id=$1 AND status='fetched' LIMIT $2 RETURNING *"""
        ...

    async def write_atoms(self, mission_id: str, atoms: List[KnowledgeAtom], evidence: List[AtomEvidence]):
        """Upsert atoms and evidence in a single transaction."""
        ...

    async def mark_chunks_distilled(self, chunk_ids: List[str]):
        """Mark chunks as distilled, optionally linking to atom_ids."""
        ...

    async def ensure_source(self, mission_id: str, url: str, metadata: dict) -> str:
        """Idempotent source creation. Returns source_id.
        Uses url_hash deduplication."""
        ...

    async def fetch_source_context(self, source_id: str) -> SourceContext:
        """Get source row + text_ref content."""
        ...
```

**Implementation**: `PostgresCorpusAdapter` using `asyncpg` connection pool.

**Tests**:
- `test_reserve_distillable_chunks_idempotent()`: two workers reserve same chunk → only one gets it
- `test_write_atoms_creates_evidence()`: atoms + evidence inserted atomically
- `test_ensure_source_dedupes_url_hash()`: same URL twice → same source_id

---

### Task 4: URL Deduplication & Redis Lease

**File**: `src/research/queue.py`

**Lease Protocol**:

```python
async def acquire_fetch_lease(url_hash: str, ttl: int = 300) -> str | None:
    """Try to acquire lease for this URL. Returns lease_id if successful, None if already held."""
    lease_id = str(uuid.uuid4())
    acquired = await redis.set(
        f"lease:{url_hash}",
        lease_id,
        ex=ttl,
        nx=True  # only set if not exists
    )
    return lease_id if acquired else None

async def release_fetch_lease(url_hash: str, lease_id: str) -> bool:
    """Release lease only if we own it (compare-and-delete)."""
    script = """
    if redis.call('GET', KEYS[1]) == ARGV[1] then
        return redis.call('DEL', KEYS[1])
    else
        return 0
    end
    """
    return await redis.eval(script, 1, f"lease:{url_hash}", lease_id)
```

**Enqueue**:

```python
async def enqueue_urls(mission_id: str, urls: List[str], priority: float = 0.5):
    """Add URLs to global fetch queue with priority scoring."""
    pipe = redis.pipeline()
    for url in urls:
        url_hash = hashlib.sha256(url.encode()).hexdigest()[:16]
        # ZADD: score = priority (higher = sooner)
        await redis.zadd(
            "queue:frontier",
            {url: priority}
        )
        # Also track by mission for monitoring
        await redis.sadd(f"mission:{mission_id}:queued_urls", url)
    await pipe.execute()
```

**Dequeue** (worker side):

```python
async def dequeue_url(batch_size: int = 10) -> List[Tuple[str, float]]:
    """Pop highest-priority URLs from queue."""
    # Use ZRANGE with scores, then ZREM atomically via Lua script or WATCH/MULTI
    # Simplified: ZPOPMAX (Redis 5+)
    results = await redis.zpopmax("queue:frontier", batch_size)
    return [(url, score) for url, score in results]
```

**Tests**:
- `test_lease_prevents_double_fetch()`: two workers try same url_hash, only one gets lease
- `test_enqueue_dequeue_ordering()`: priorities respected

---

### Task 5: Crawler Worker

**File**: `src/workers/crawl_worker.py`

**Logic**:

```python
async def crawl_loop():
    while True:
        # Dequeue batch
        items = await dequeue_url(batch_size=10)
        if not items:
            await asyncio.sleep(1)
            continue

        for url, priority in items:
            # Check if we already have this source (duplicate check)
            url_hash = hashlib.sha256(url.encode()).hexdigest()[:16]
            existing = await adapter.get_source_by_url_hash(mission_id, url_hash)  # need to infer mission from context? Or store in separate set
            if existing:
                continue  # already fetched

            # Acquire lease (pre-enqueue should have done this, but double-check)
            lease_id = await acquire_fetch_lease(url_hash)
            if not lease_id:
                continue  # someone else fetching

            try:
                # Fetch via Firecrawl or Playwright fallback
                result: FetchResult = await crawler.fetch_url(url)

                # Store source
                source_id = await adapter.ensure_source(
                    mission_id=mission_id,  # need to determine mission: could be from metadata or separate tracking
                    url=url,
                    metadata={
                        "title": result.title,
                        "domain": urlparse(url).netloc,
                        "priority": priority,
                        "fetch_method": result.method
                    }
                )

                # Store raw text
                text_ref_id = str(uuid.uuid4())
                await db.execute(
                    "INSERT INTO corpus.text_refs (blob_id, inline_text, sha256) VALUES ($1, $2, $3)",
                    text_ref_id, result.markdown, hashlib.sha256(result.markdown.encode()).hexdigest()
                )

                # Update source with text_ref
                await db.execute(
                    "UPDATE corpus.sources SET canonical_text_ref=$1, fetched_at=NOW(), status='fetched' WHERE source_id=$2",
                    text_ref_id, source_id
                )

                # Release lease
                await release_fetch_lease(url_hash, lease_id)

                # Publish event
                await redis.publish("events", json.dumps({
                    "type": "crawl.complete",
                    "mission_id": mission_id,
                    "source_id": source_id,
                    "url": url
                }))

            except Exception as e:
                logger.error(f"Fetch failed: {url}: {e}")
                await release_fetch_lease(url_hash, lease_id)  # still release
                # Record failure in fetch_attempts
                continue
```

**Key Points**:
- `mission_id` must be tracked per URL. Solution: enqueue with metadata: `ZADD` with member `json:{url, mission_id}` or use separate sorted set per mission then aggregate. Let's use: `queue:frontier:priority` with score, but member is `url` and we track mission in parallel hash `url_to_mission:{url} → mission_id`. Or simpler: store as `url|mission_id` as queue member, dedupe on `url_hash` independent of mission. Since per-mission dedupe is needed, we can keep `mission_id` in the queue item and still dedupe by `url_hash` globally via lease.
- Lease prevents two workers from fetching same URL even across missions.
- After fetch, `ensure_source` uses `(mission_id, url_hash)` unique constraint → safe even if multiple missions try same URL.

**Tests**:
- Mock Redis and DB; simulate concurrent workers; verify single fetch per URL.

---

### Task 6: Distillation Worker

**File**: `src/workers/distill_worker.py`

**Logic**:

```python
async def distill_loop():
    while True:
        # Check if any mission needs distillation
        # Could be triggered by budget event or periodic check
        # For simplicity: poll DB for missions with available chunks
        missions = await db.fetch(
            "SELECT mission_id FROM ops.mission_state WHERE current_state IN ('crawling','distilling')"
        )

        for mission_row in missions:
            mission_id = mission_row['mission_id']

            # Reserve batch of chunks
            chunks = await adapter.reserve_distillable_chunks(mission_id, limit=10)
            if not chunks:
                await asyncio.sleep(5)
                continue

            # Group chunks by source for context
            source_chunks = defaultdict(list)
            for chunk in chunks:
                source_chunks[chunk.source_id].append(chunk)

            atom_ids_created = []
            for source_id, chunk_list in source_chunks.items():
                # Combine chunk texts (or process one by one)
                source_text = "\n\n".join(c.inline_text for c in chunk_list if c.inline_text)

                # Call LLM to extract atoms
                atoms_data = await extract_technical_atoms(ollama, source_text, topic_name)

                for atom_dict in atoms_data:
                    # Validate structure
                    if not isinstance(atom_dict, dict) or 'content' not in atom_dict:
                        continue

                    atom_id = str(uuid.uuid4())
                    atom_hash = hashlib.sha256(
                        atom_dict['content'].encode()
                    ).hexdigest()[:32]

                    atom = KnowledgeAtom(
                        atom_id=atom_id,
                        mission_id=mission_id,
                        atom_hash=atom_hash,
                        atom_type=atom_dict.get('type', 'claim'),
                        title=atom_dict['content'][:100],
                        statement=atom_dict['content'],
                        normalized_statement=normalize_text(atom_dict['content']),
                        confidence=atom_dict.get('confidence', 0.7),
                        freshness_score=compute_freshness(source_chunks[0]),  # from source metadata
                        source_count=1,
                        agreement_score=1.0,  # initially
                        contradiction_flag=False,
                        visibility=KnowledgeVisibility.QUARANTINED,
                        status=KnowledgeStatus.DISTILLED,
                        distilled_by_model="llama3:8b",
                        distillation_version="v1",
                        lineage_json={
                            "mission_id": mission_id,
                            "source_ids": [source_id],
                            "chunk_ids": [c.chunk_id for c in chunk_list],
                            "extraction_mode": "atomic_distillation"
                        }
                    )

                    evidence = AtomEvidence(
                        atom_id=atom_id,
                        source_id=source_id,
                        chunk_id=chunk_list[0].chunk_id,  # primary chunk
                        evidence_strength=0.9,
                        supports_statement=True
                    )

                    atom_ids_created.append(atom_id)
                    # Batch insert later
                    atoms_batch.append(atom)
                    evidence_batch.append(evidence)

            # Write batch
            await adapter.write_atoms(mission_id, atoms_batch, evidence_batch)

            # Mark chunks as distilled
            chunk_ids = [c.chunk_id for c in chunks]
            await adapter.mark_chunks_distilled(chunk_ids)

            # Publish event
            await redis.publish("events", json.dumps({
                "type": "distill.complete",
                "mission_id": mission_id,
                "atom_count": len(atoms_batch)
            }))

            # Check promotion
            for atom in atoms_batch:
                if promote_to_mission_active(atom):
                    await db.execute(
                        "UPDATE corpus.atoms SET visibility='mission_active', status='verified' WHERE atom_id=$1",
                        atom.atom_id
                    )
```

**Note**: This is a simplified version. Real implementation needs batching, error handling, and careful transaction management.

**Tests**:
- `test_distillation_creates_atoms_with_evidence()`
- `test_atom_deduplication_by_hash()`
- `test_promotion_logic()`

---

### Task 7: ArchivistIndex Retrieval Modes

**File**: `src/research/archivist/index.py`

**Add methods**:

```python
class ArchivistIndex:
    def __init__(self, chroma_collection):
        self.collection = chroma_collection

    async def search_atoms(
        self,
        mission_id: str,
        query: str,
        embedding: List[float],
        k: int = 10,
        mode: QueryMode = QueryMode.AGENT_DEFAULT
    ) -> List[AtomSearchResult]:
        """Search atoms with visibility filtering."""
        # Build filter
        if mode == QueryMode.AGENT_DEFAULT:
            visibility_filter = {"visibility": "canonical"}
            status_filter = ["verified", "promoted"]
        elif mode == QueryMode.MISSION_ACTIVE:
            visibility_filter = {"mission_id": mission_id, "visibility": ["mission_active", "canonical"]}
            status_filter = None  # include all statuses for mission
        elif mode == QueryMode.OPERATOR_DEBUG:
            visibility_filter = {"mission_id": mission_id}  # all
            status_filter = None
        else:
            visibility_filter = {}
            status_filter = None

        # Query atoms table directly (Postgres is source of truth)
        # Use embedding similarity via Chroma for ranking, but filter in SQL
        # Approach: get top-k from Chroma with mission_id filter, then fetch full records from Postgres
        results = self.collection.query(
            query_embeddings=[embedding],
            n_results=k * 2,  # overfetch to allow filtering
            where=visibility_filter
        )
        # Filter by status and mission_id, return top k
        filtered = []
        for i, (doc, meta) in enumerate(zip(results['documents'][0], results['metadatas'][0])):
            if meta.get('atom_id') and meta.get('mission_id') == mission_id:
                if status_filter is None or meta.get('status') in status_filter:
                    filtered.append({
                        "atom_id": meta['atom_id'],
                        "statement": doc,
                        "score": results['distances'][0][i],
                        "metadata": meta
                    })
        return filtered[:k]

    async def search_raw_chunks(
        self,
        mission_id: str,
        query: str,
        embedding: List[float],
        k: int = 20,
        include_distilled: bool = False
    ) -> List[ChunkSearchResult]:
        """Search raw chunks (quarantined state) for mission."""
        # Only visible in OPERATOR_DEBUG or if explicitly requested for a mission
        filter_ = {"mission_id": mission_id}
        if not include_distilled:
            # But raw chunks are always quarantined; this is fine
            pass

        results = self.collection.query(
            query_embeddings=[embedding],
            n_results=k,
            where=filter_
        )
        # Return raw chunks with metadata
        ...
```

**Note**: Chroma collection must store `atom_id` or `chunk_id` in metadata for lookup.

**Tests**:
- `test_search_atoms_filters_by_visibility()`
- `test_search_raw_chunks_mission_scoped()`

---

### Task 8: MissionOrchestrator

**File**: `src/research/orchestrator.py`

**Core class**:

```python
class MissionOrchestrator:
    def __init__(
        self,
        adapter: CorpusAdapter,
        frontier: AdaptiveFrontier,
        index: ArchivistIndex,
        redis_client: aioredis.Redis,
        config: ResearchConfig
    ):
        self.adapter = adapter
        self.frontier = frontier
        self.index = index
        self.redis = redis_client
        self.config = config
        self._running: Dict[str, asyncio.Task] = {}
        self._cancelled: Set[str] = set()

    async def start_mission(self, topic: str, config_overrides: dict = None) -> str:
        mission_id = str(uuid.uuid4())
        # Create mission record
        await self.adapter.create_mission({
            "mission_id": mission_id,
            "topic": topic,
            "status": "initializing",
            "config_json": config_overrides or {}
        })
        # Start async task
        task = asyncio.create_task(self.run_mission(mission_id))
        self._running[mission_id] = task
        return mission_id

    async def run_mission(self, mission_id: str):
        """Main orchestration loop."""
        try:
            # Update state to discovering
            await self.adapter.update_mission_status(mission_id, "discovering")

            # Frontier loop (runs in same task for now; could be separate worker)
            async for concept_task in self.frontier.run(mission_id, topic):
                if mission_id in self._cancelled:
                    break
                # Enqueue URLs from concept_task
                await self.enqueue_concept_urls(mission_id, concept_task)

            # After frontier exhausted or cancelled, transition
            await self.adapter.update_mission_status(mission_id, "crawling")

            # Wait for queue to drain and distillation to catch up
            while not self._cancelled:
                queue_len = await self.redis.zcard("queue:frontier")
                if queue_len == 0:
                    # Check if any chunks left to distill
                    remaining = await self.adapter.count_unreserved_chunks(mission_id)
                    if remaining == 0:
                        break
                await asyncio.sleep(10)

            # Final distillation sweep
            await self.adapter.update_mission_status(mission_id, "distilling")
            # Could trigger additional distillation runs here

            # Mark complete
            await self.adapter.update_mission_status(mission_id, "completed")

        except Exception as e:
            logger.error(f"Mission {mission_id} failed: {e}")
            await self.adapter.update_mission_status(mission_id, "failed", stop_reason=str(e))
        finally:
            self._running.pop(mission_id, None)

    async def query_knowledge(
        self,
        mission_id: str,
        question: str,
        mode: QueryMode = QueryMode.AGENT_DEFAULT
    ) -> QueryResponse:
        # Generate embedding
        embedding = await self.ollama.embed(question)

        # Search based on mode
        if mode == QueryMode.AGENT_DEFAULT:
            # Only canonical
            atoms = await self.index.search_atoms(mission_id, question, embedding, k=10, mode=mode)
            chunks = []  # no raw chunks for agent default
        elif mode == QueryMode.MISSION_ACTIVE:
            atoms = await self.index.search_atoms(mission_id, question, embedding, k=5, mode=mode)
            chunks = await self.index.search_raw_chunks(mission_id, question, embedding, k=5)
        else:  # operator_debug
            atoms = await self.index.search_atoms(mission_id, question, embedding, k=5, mode=mode)
            chunks = await self.index.search_raw_chunks(mission_id, question, embedding, k=10)

        # Build context and generate answer (defer to separate method)
        answer = await self.synthesize_answer(question, atoms, chunks)

        return QueryResponse(
            answer=answer,
            atoms=atoms,
            chunks=chunks,
            coverage_estimate=self.estimate_coverage(atoms, chunks),
            confidence=self.compute_confidence(atoms)
        )

    async def apply_nudge(self, mission_id: str, instruction: str):
        """Parse instruction and adjust frontier parameters."""
        # Parse with LLM or rules: e.g., "focus more on quantum error correction"
        # Then call frontier.apply_nudge(mission_id, nudge_params)
        ...

    async def stop_mission(self, mission_id: str):
        """Request graceful shutdown."""
        self._cancelled.add(mission_id)
        if mission_id in self._running:
            # Wait for task to finish (with timeout)
            try:
                await asyncio.wait_for(self._running[mission_id], timeout=30.0)
            except asyncio.TimeoutError:
                self._running[mission_id].cancel()
        await self.adapter.update_mission_status(mission_id, "stopped")
```

**Tests**:
- `test_orchestrator_starts_and_transitions_states()`
- `test_query_knowledge_respects_visibility()`
- `test_nudge_modifies_frontier()`

---

### Task 9: API Layer

**File**: `src/interfaces/api.py`

**FastAPI app**:

```python
app = FastAPI(title="Sheppard V3 Research API")

@app.post("/api/v1/missions")
async def api_start_mission(req: StartMissionRequest):
    mission_id = await orchestrator.start_mission(req.topic, req.config)
    return {"mission_id": mission_id, "status": "starting"}

@app.delete("/api/v1/missions/{mission_id}")
async def api_stop_mission(mission_id: str):
    await orchestrator.stop_mission(mission_id)
    return {"status": "stopping"}  # 202 Accepted

@app.get("/api/v1/missions/{mission_id}/status")
async def api_mission_status(mission_id: str):
    state = await adapter.get_mission_state(mission_id)
    return state

@app.post("/api/v1/missions/{mission_id}/nudge")
async def api_nudge(mission_id: str, req: NudgeRequest):
    await orchestrator.apply_nudge(mission_id, req.instruction)
    return {"status": "nudge_applied"}

@app.post("/api/v1/missions/{mission_id}/query")
async def api_query(mission_id: str, req: QueryRequest):
    resp = await orchestrator.query_knowledge(
        mission_id, req.question, mode=QueryMode(req.mode)
    )
    return resp

@app.get("/api/v1/missions/{mission_id}/events")
async def api_mission_events(mission_id: str, request: Request):
    """SSE stream of mission events."""
    async def event_generator():
        # Subscribe to Redis pub/sub for this mission
        pubsub = redis.pubsub()
        await pubsub.subscribe(f"mission:{mission_id}:events")
        async for message in pubsub.listen():
            if message['type'] == 'message':
                yield f"data: {message['data'].decode()}\n\n"
    return StreamingResponse(event_generator(), media_type="text/event-stream")

@app.get("/api/v1/missions/{mission_id}/report")
async def api_generate_report(mission_id: str):
    # Async job: generate report and store in authority table
    # Return 202 with job_id
    ...
```

**Tests**: Use TestClient; mock orchestrator.

---

### Task 10: CLI Layer

**File**: `src/interfaces/cli.py`

**Typer app**:

```python
@app.command()
def start(topic: str, ceiling_gb: float = 5.0):
    """Start a new research mission."""
    mission_id = asyncio.run(orchestrator.start_mission(topic, {"ceiling_gb": ceiling_gb}))
    print(mission_id)

@app.command()
def status(mission_id: str):
    """Show mission status."""
    state = asyncio.run(orchestrator.get_mission_state(mission_id))
    print(json.dumps(state, indent=2))

@app.command()
def query(mission_id: str, question: str):
    """Ask a question about the mission."""
    resp = asyncio.run(orchestrator.query_knowledge(mission_id, question, mode=QueryMode.MISSION_ACTIVE))
    print(resp.answer)

@app.command()
def nudge(mission_id: str, instruction: str):
    """Nudge the frontier."""
    asyncio.run(orchestrator.apply_nudge(mission_id, instruction))
    print("Nudge applied")

@app.command()
def stop(mission_id: str):
    """Stop a mission."""
    asyncio.run(orchestrator.stop_mission(mission_id))
    print("Stopping...")
```

**Entry point**: `sheppard` console script in `pyproject.toml`.

---

### Task 11: Integration Test Suite

**File**: `tests/integration/test_mission_lifecycle.py`

**Scenario**:

```python
@pytest.mark.asyncio
async def test_full_mission_lifecycle():
    # 1. Start mission
    mission_id = await orchestrator.start_mission("quantum computing basics")

    # 2. Simulate crawler worker (mock or use real with Firecrawl-local)
    # Enqueue a few known URLs via frontier or directly
    await redis.zadd("queue:frontier", {"https://en.wikipedia.org/wiki/Quantum_computing": 1.0})

    # 3. Run crawl worker briefly
    await asyncio.sleep(5)  # let worker process
    # Could directly call crawler.fetch_url for deterministic test

    # 4. Run distillation worker
    await asyncio.sleep(5)

    # 5. Query while mission active → should include mission-active atoms but not quarantined raw
    resp1 = await orchestrator.query_knowledge(mission_id, "What is quantum entanglement?", mode=QueryMode.MISSION_ACTIVE)
    assert resp1.answer is not None
    assert len(resp1.atoms) >= 0  # may be zero if not yet distilled
    assert len(resp1.chunks) >= 0

    # 6. Agent default query → should NOT see raw chunks, only canonical (none yet)
    resp2 = await orchestrator.query_knowledge(mission_id, "What is quantum computing?", mode=QueryMode.AGENT_DEFAULT)
    assert len(resp2.chunks) == 0  # raw excluded

    # 7. Stop mission
    await orchestrator.stop_mission(mission_id)
    state = await adapter.get_mission_state(mission_id)
    assert state['status'] in ('stopped', 'completed')
```

**Additional integration tests**:
- `test_concurrent_url_fetch_deduplication`
- `test_nudge_changes_frontier_priority`
- `test_budget_triggers_distillation`
- `test_retrieval_visibility_filters`

**CI**: Use `pytest -m integration` with Docker compose (Postgres, Redis, Chroma).

---

## 6. TEST CONTRACTS (Property-Based Where Possible)

### Contract C1: Idempotent Source Ingestion

```python
@given(url=st.text(min_size=1), metadata=st.fixed_dictionaries({...}))
async def test_ensure_source_idempotent(url, metadata):
    sid1 = await adapter.ensure_source(mission_id, url, metadata)
    sid2 = await adapter.ensure_source(mission_id, url, metadata)
    assert sid1 == sid2
```

### Contract C2: Lease Serialization

```python
async def test_lease_serialization():
    # Two coroutines try same url_hash
    results = await asyncio.gather(
        acquire_fetch_lease("hash123"),
        acquire_fetch_lease("hash123")
    )
    assert sum(1 for r in results if r is not None) == 1
```

### Contract C3: Atom Evidence Mandatory

```python
async def test_atom_without_evidence_rejected():
    atom = KnowledgeAtom(..., evidence_links=[])
    with pytest.raises(ValidationError):
        await adapter.write_atoms([atom], [])
```

### Contract C4: Retrieval Mode Isolation

```python
async def test_retrieval_mode_filters():
    # Setup: create atoms with different visibility
    await adapter.write_atoms([
        KnowledgeAtom(visibility=KnowledgeVisibility.QUARANTINED, ...),
        KnowledgeAtom(visibility=KnowledgeVisibility.CANONICAL, ...)
    ])
    resp_default = await orchestrator.query_knowledge(mission_id, "q", mode=QueryMode.AGENT_DEFAULT)
    resp_debug = await orchestrator.query_knowledge(mission_id, "q", mode=QueryMode.OPERATOR_DEBUG)
    assert len(resp_debug.atoms) > len(resp_default.atoms)
```

---

## 7. RISKS & MITIGATIONS

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Schema changes late | Medium | High | Lock schema in first 2 days; use migrations, not hand-edits |
| Concurrent fetch still duplicates | Medium | High | Stress test with 10+ workers; monitor unique constraint violations |
| Chroma/Postgres drift | Medium | Medium | Implement `rebuild_chroma.py` early; run nightly |
| Distillation too slow | High | Medium | Batch size tuning; consider GPU; add more workers |
| Query latency high | Medium | Medium | Cache embeddings; limit context size; benchmark after ACs |
| /nudge causes loops | Low | High | Rate-limit nudges; validate instructions; cap priority range |
| Mission state corruption | Low | High | All state changes via events; state table derived; backup/restore test |
| Redis unavailable | Low | Medium | Fail gracefully: crawl pauses, queries still work from Postgres |

---

## 8. VERIFICATION CHECKLIST

**Pre-merge checklist for each task**:
- [ ] Unit tests pass (100% for new code)
- [ ] Integration test covers main flow
- [ ] Schema constraints verified (unique, foreign keys, checks)
- [ ] Migration applied cleanly on fresh DB
- [ ] Logging includes `mission_id` and structured fields
- [ ] API endpoint returns correct status codes and shapes
- [ ] Performance benchmark baseline recorded

---

## 9. FILE MANIFEST (What Gets Created)

```
migrations/
  V3.1.0__initial_schema.sql

src/research/
  models_v3.py           # dataclasses for ConceptTask, KnowledgeAtom, etc.
  adapter.py             # CorpusAdapter protocol + PostgresCorpusAdapter
  frontier.py            # AdaptiveFrontier with nudge support
  queue.py               # Redis lease + enqueue/dequeue
  orchestrator.py        # MissionOrchestrator
  config.py              # extended with namespaces
  workers/
    __init__.py
    crawl_worker.py
    distill_worker.py
    __main__.py          # entry points

src/interfaces/
  api.py                 # FastAPI app
  cli.py                 # Typer CLI

src/research/archivist/
  index.py               # extended with search modes

tests/
  integration/
    test_mission_lifecycle.py
    test_distributed_crawl.py
    test_nudge.py
    test_query_visibility.py
  unit/
    test_adapter.py
    test_models.py
    test_queue.py
    test_promotion.py

scripts/
  rebuild_chroma.py
  migrate.py

docs/
  phases/phase1_implementation.md  (this document)
```

---

## 10. COMMITMENT CHECKLIST

Before mark Phase 1 complete, team must affirm:

- [ ] AC1-AC10 all passing repeatedly (flaky-free)
- [ ] Schema reviewed by DBA (if any)
- [ ] Performance baseline: query <2s (retrieval), <5s (synthesis) on 10k atoms
- [ ] Load test: 3 concurrent missions, 10 workers each, no cross-leak
- [ ] Documentation updated: API reference, CLI usage, config options
- [ ] Operational runbooks: restart procedures, DB backup, Redis flush safety

---

**Phase 1 is the foundation**. If these 3 weeks are done right, V3 is real. If not, we have architectural debt forever.

Let's build.

---

**Next Action**: Begin Task 1 (Schema) immediately. Do not pass Go until schema is locked and reviewed.
