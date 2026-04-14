"""
src/research/acquisition/ingestion_control.py — Multi-tier digestion pipeline.

Controls the flow from crawled content → distilled atoms via:
  Tier 0: Surface scan — dedup, novelty, quality gate (FAST, cheap)
  Tier 1: Shallow extraction — batched LLM extraction (MEDIUM)
  Tier 2: Deep distillation — existing pipeline passthrough (EXPENSIVE, limited)

Redis Schema:
  ingest:queue:tier0  — ZSET (score=priority, value=doc_id)
  ingest:queue:tier1  — ZSET (score=priority, value=doc_id)
  ingest:queue:tier2  — ZSET (score=priority, value=doc_id)
  doc:{doc_id}        — HASH (url, source, priority, status, created_at)
  dedup:hashes        — SET with 72h TTL
  lock:doc:{doc_id}   — STRING with 60s TTL (prevents double-processing)
"""

import asyncio
import hashlib
import json
import logging
import time
from typing import Dict, Any, Optional, Callable, Awaitable, List

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────
# Configuration
# ──────────────────────────────────────────────────────────────

TIER0_CONCURRENCY = 4
TIER1_CONCURRENCY = 3
TIER2_CONCURRENCY = 2  # Strictly limited — deep reasoning is expensive

BATCH_SIZE_TIER1 = 8

NOVELTY_THRESHOLD = 0.3  # Drop docs below this novelty score
MIN_PRIORITY = 0.2  # Minimum priority to process

BACKLOG_SAFETY_VALVE = 10_000  # Auto-raise novelty threshold if queue exceeds this
BACKLOG_NOVELTY_BOOST = 0.2  # How much to raise novelty threshold when backlog is high

# Redis keys
QUEUE_TIER0 = "ingest:queue:tier0"
QUEUE_TIER1 = "ingest:queue:tier1"
QUEUE_TIER2 = "ingest:queue:tier2"
DEDUP_HASHES = "dedup:hashes"
DOC_META_PREFIX = "doc:"
LOCK_PREFIX = "lock:doc:"

DEDUP_TTL = 86400 * 3  # 72 hours
LOCK_TTL = 60  # 60 seconds


# ──────────────────────────────────────────────────────────────
# Priority Queue Operations
# ──────────────────────────────────────────────────────────────

async def push_doc(redis, doc_id: str, priority: float, tier: str = "tier0"):
    """Push a document to a tier queue with priority score."""
    queue_key = f"ingest:queue:{tier}"
    await redis.zadd(queue_key, {doc_id: priority})

    # Store metadata
    await redis.hset(f"{DOC_META_PREFIX}{doc_id}", mapping={
        "priority": str(priority),
        "status": "pending",
        "tier": tier,
        "pushed_at": str(time.time()),
    })


async def pop_doc(redis, tier: str = "tier0") -> Optional[tuple]:
    """Pop highest-priority document from a tier queue."""
    queue_key = f"ingest:queue:{tier}"
    result = await redis.zpopmax(queue_key, count=1)
    return result[0] if result else None


async def pop_batch(redis, tier: str = "tier1", batch_size: int = BATCH_SIZE_TIER1) -> List[tuple]:
    """Pop a batch of documents from a tier queue."""
    queue_key = f"ingest:queue:{tier}"
    result = await redis.zpopmax(queue_key, count=batch_size)
    return result if result else []


async def get_queue_size(redis, tier: str = None) -> Dict[str, int]:
    """Get queue sizes for all tiers or a specific tier."""
    if tier:
        return {tier: await redis.zcard(f"ingest:queue:{tier}")}
    return {
        "tier0": await redis.zcard(QUEUE_TIER0),
        "tier1": await redis.zcard(QUEUE_TIER1),
        "tier2": await redis.zcard(QUEUE_TIER2),
    }


async def lock_doc(redis, doc_id: str) -> bool:
    """Acquire a processing lock for a document. Returns True if acquired."""
    lock_key = f"{LOCK_PREFIX}{doc_id}"
    return bool(await redis.set(lock_key, "1", ex=LOCK_TTL, nx=True))


async def unlock_doc(redis, doc_id: str):
    """Release a processing lock."""
    lock_key = f"{LOCK_PREFIX}{doc_id}"
    await redis.delete(lock_key)


async def update_doc_status(redis, doc_id: str, status: str, **extra):
    """Update document metadata status."""
    fields = {"status": status, "updated_at": str(time.time())}
    fields.update({k: str(v) for k, v in extra.items()})
    await redis.hset(f"{DOC_META_PREFIX}{doc_id}", mapping=fields)


# ──────────────────────────────────────────────────────────────
# Deduplication
# ──────────────────────────────────────────────────────────────

async def is_duplicate(redis, content_hash: str) -> bool:
    """Check if content hash is already in dedup cache."""
    return bool(await redis.sismember(DEDUP_HASHES, content_hash))


async def mark_seen(redis, content_hash: str):
    """Add content hash to dedup cache with TTL."""
    await redis.sadd(DEDUP_HASHES, content_hash)
    await redis.expire(DEDUP_HASHES, DEDUP_TTL)


def compute_content_hash(content: str) -> str:
    """Compute SHA256 hash of content (first 2000 chars for speed)."""
    return hashlib.sha256(content[:2000].encode()).hexdigest()


# ──────────────────────────────────────────────────────────────
# Priority Scoring
# ──────────────────────────────────────────────────────────────

def compute_priority(
    doc: Dict[str, Any],
    novelty_score: float = 0.5,
    graph_gap_score: float = 0.0,
    novelty_threshold: float = NOVELTY_THRESHOLD,
) -> float:
    """
    Compute document priority for queue ordering.

    priority = novelty × 0.35 + authority × 0.25 + relevance × 0.20 + graph_gap × 0.20

    Returns 0.0-1.0. Documents below novelty_threshold get 0.0 priority (dropped).
    """
    if novelty_score < novelty_threshold:
        return 0.0

    # Authority: prefer academic/research sources
    url = doc.get("url", "").lower()
    if any(domain in url for domain in ["arxiv", "nature.com", "science.org", "ncbi.nlm.nih.gov", "ieeexplore"]):
        authority_score = 1.0
    elif any(domain in url for domain in ["github.com", "wikipedia.org", "docs.", ".edu"]):
        authority_score = 0.8
    else:
        authority_score = 0.5

    # Relevance: content length as proxy for informativeness
    content_len = len(doc.get("content", ""))
    length_score = min(content_len / 5000.0, 1.0)

    priority = (
        0.35 * novelty_score +
        0.25 * authority_score +
        0.20 * length_score +
        0.20 * graph_gap_score
    )

    return max(0.0, min(1.0, priority))


# ──────────────────────────────────────────────────────────────
# Novelty Gate (Tier 0)
# ──────────────────────────────────────────────────────────────

class NoveltyGate:
    """
    Fast novelty check — decides if content is worth deeper processing.

    Uses content hash dedup + optional Chroma embedding similarity.
    """

    def __init__(self, redis_client, chroma_client=None, similarity_threshold: float = 0.9):
        self.redis = redis_client
        self.chroma = chroma_client
        self.similarity_threshold = similarity_threshold

    async def check(self, doc: Dict[str, Any]) -> tuple[bool, float]:
        """
        Check if document is novel enough to process.

        Returns:
            (is_novel, novelty_score)
        """
        content = doc.get("content", "")
        if not content:
            return False, 0.0

        # 1. Hash-based dedup (fastest)
        content_hash = compute_content_hash(content)
        if await is_duplicate(self.redis, content_hash):
            return False, 0.0

        # 2. Embedding-based novelty (if Chroma available)
        novelty_score = 0.5  # Default medium novelty
        if self.chroma:
            novelty_score = await self._chroma_novelty(content)

        return novelty_score >= NOVELTY_THRESHOLD, novelty_score

    async def _chroma_novelty(self, content: str) -> float:
        """
        Check novelty via Chroma similarity search.

        Returns novelty score (0.0 = duplicate, 1.0 = completely novel).
        """
        try:
            # Query existing knowledge with content snippet
            result = await self.chroma.query(
                collection="knowledge_atoms",
                query_text=content[:512],
                limit=3,
            )

            if not result or not result.get("distances"):
                return 0.8  # No similar atoms found = novel

            # Best similarity = lowest distance
            distances = result["distances"]
            if distances and distances[0]:
                best_distance = min(distances[0])
                # Convert distance to novelty (higher distance = more novel)
                # Typical chroma cosine distance range: 0.0-2.0
                novelty = min(1.0, best_distance / 1.5)
                return novelty

            return 0.5
        except Exception as e:
            logger.debug(f"[NoveltyGate] Chroma check failed: {e}")
            return 0.5


# ──────────────────────────────────────────────────────────────
# Graph Gap Scoring
# ──────────────────────────────────────────────────────────────

class GraphGapScorer:
    """
    Scores documents based on how much they fill gaps in the belief graph.

    Documents that touch unstable concepts, contradictions, or missing edges
    get boosted priority.
    """

    def __init__(self, cmk_runtime=None):
        self.cmk_runtime = cmk_runtime

    async def score(self, doc: Dict[str, Any]) -> float:
        """
        Compute graph gap score (0.0-1.0).

        Higher = document fills a gap in the belief graph.
        """
        if not self.cmk_runtime:
            return 0.0  # No graph available, neutral score

        try:
            # Extract concepts from document content
            content = doc.get("content", "")[:1000]
            concepts = _extract_concepts(content)

            if not concepts:
                return 0.0

            gap_score = 0.0
            gap_count = 0

            for concept_name in concepts:
                concept = self.cmk_runtime.concept_anchors.find_by_name(concept_name)
                if concept:
                    # Check for unresolved contradictions in this concept
                    gap_score += concept.authority_score * 0.5  # Low authority = gap
                    gap_count += 1

            # Check for hypothesis coverage gaps
            hypotheses = self.cmk_runtime.hypothesis_engine.detect_missing_edges()
            if hypotheses:
                # Document mentions concepts that have missing edges
                gap_score += min(1.0, len(hypotheses) / 10.0) * 0.3
                gap_count += 1

            return gap_score / max(1, gap_count) if gap_count > 0 else 0.0

        except Exception as e:
            logger.debug(f"[GraphGapScorer] Failed: {e}")
            return 0.0


def _extract_concepts(text: str) -> List[str]:
    """Extract concept keywords from text (simple heuristic)."""
    import re
    # Look for known concept anchor names
    from src.core.memory.cmk.concept_anchors import CANONICAL_CONCEPTS
    text_lower = text.lower()
    found = []
    for name, _ in CANONICAL_CONCEPTS:
        if name.lower() in text_lower:
            found.append(name)
    return found[:5]  # Limit to 5 concepts


# ──────────────────────────────────────────────────────────────
# Tier 0 Worker — Surface Scan + Dedup Gate
# ──────────────────────────────────────────────────────────────

async def tier0_worker(
    redis,
    crawl_source: asyncio.Queue,
    novelty_gate: NoveltyGate,
    graph_gap_scorer: Optional[GraphGapScorer] = None,
    novelty_threshold: float = NOVELTY_THRESHOLD,
):
    """
    Tier 0 worker — fast surface scan.

    For each crawled document:
      1. Compute content hash
      2. Check dedup cache
      3. Run novelty gate
      4. Compute priority score
      5. Push to Tier 1 queue (or drop)
    """
    worker_id = id(asyncio.current_task())
    logger.info(f"[Tier0-{worker_id}] Starting")

    while True:
        try:
            doc = await crawl_source.get()
        except asyncio.CancelledError:
            break

        try:
            doc_id = doc.get("id", doc.get("url", f"doc_{int(time.time() * 1000)}"))
            content = doc.get("content", "")

            if not content:
                await update_doc_status(redis, doc_id, "skipped", reason="empty_content")
                continue

            # 1. Dedup check
            content_hash = compute_content_hash(content)
            if await is_duplicate(redis, content_hash):
                await update_doc_status(redis, doc_id, "skipped", reason="duplicate")
                continue

            # 2. Mark as seen
            await mark_seen(redis, content_hash)

            # 3. Novelty gate
            is_novel, novelty_score = await novelty_gate.check(doc)
            if not is_novel:
                await update_doc_status(redis, doc_id, "skipped", reason="low_novelty", novelty=novelty_score)
                continue

            # 4. Graph gap scoring (optional, requires CMK)
            graph_gap = 0.0
            if graph_gap_scorer:
                graph_gap = await graph_gap_scorer.score(doc)

            # 5. Compute priority
            priority = compute_priority(doc, novelty_score, graph_gap, novelty_threshold)

            if priority < MIN_PRIORITY:
                await update_doc_status(redis, doc_id, "skipped", reason="low_priority", priority=priority)
                continue

            # 6. Store metadata and push to Tier 1
            await redis.hset(f"{DOC_META_PREFIX}{doc_id}", mapping={
                "url": doc.get("url", ""),
                "source": doc.get("source", ""),
                "novelty": str(novelty_score),
                "graph_gap": str(graph_gap),
                "priority": str(priority),
                "status": "pending",
                "tier": "tier0",
                "created_at": str(time.time()),
            })

            await push_doc(redis, doc_id, priority, "tier1")
            logger.debug(f"[Tier0-{worker_id}] Passed gate: {doc_id[:20]} (novelty={novelty_score:.2f}, priority={priority:.2f})")

        except Exception as e:
            logger.error(f"[Tier0] Error processing doc: {e}")


# ──────────────────────────────────────────────────────────────
# Tier 1 Worker — Shallow Extraction (Batched)
# ──────────────────────────────────────────────────────────────

async def tier1_worker(
    redis,
    extract_fn: Callable,
    fetch_doc_fn: Callable,
    novelty_threshold: float = NOVELTY_THRESHOLD,
):
    """
    Tier 1 worker — batched shallow extraction.

    Pops documents from Tier 1 queue, runs LLM extraction in batches,
    promotes high-confidence candidates to Tier 2.
    """
    worker_id = id(asyncio.current_task())
    logger.info(f"[Tier1-{worker_id}] Starting")

    while True:
        try:
            batch = await pop_batch(redis, "tier1", BATCH_SIZE_TIER1)
        except asyncio.CancelledError:
            break

        if not batch:
            await asyncio.sleep(0.5)
            continue

        try:
            # Fetch all docs in batch
            docs = []
            doc_ids = []
            for doc_id, _ in batch:
                if not await lock_doc(redis, doc_id):
                    continue  # Already being processed

                try:
                    doc = await fetch_doc_fn(doc_id)
                    if doc:
                        docs.append(doc)
                        doc_ids.append(doc_id)
                except Exception as e:
                    logger.error(f"[Tier1] Failed to fetch {doc_id}: {e}")
                    await unlock_doc(redis, doc_id)

            if not docs:
                continue

            # Run batched extraction
            try:
                results = await extract_fn(docs)
            except Exception as e:
                logger.error(f"[Tier1] Batch extraction failed: {e}")
                for doc_id in doc_ids:
                    await update_doc_status(redis, doc_id, "failed")
                    await unlock_doc(redis, doc_id)
                continue

            # Process results
            for doc_id, result in zip(doc_ids, results):
                confidence = result.get("confidence", 0.0)

                await update_doc_status(redis, doc_id, "extracted", confidence=confidence)
                await unlock_doc(redis, doc_id)

                # Promote high-confidence to Tier 2
                if confidence > 0.6:
                    await push_doc(redis, doc_id, confidence, "tier2")

            logger.debug(f"[Tier1-{worker_id}] Processed batch of {len(docs)}: {sum(1 for r in results if r.get('confidence', 0) > 0.6)} promoted to Tier 2")

        except Exception as e:
            logger.error(f"[Tier1] Worker error: {e}")
            await asyncio.sleep(1)


# ──────────────────────────────────────────────────────────────
# Tier 2 Worker — Deep Distillation (Existing Pipeline Passthrough)
# ──────────────────────────────────────────────────────────────

async def tier2_worker(
    redis,
    distill_fn: Callable,
    fetch_doc_fn: Callable,
    store_atoms_fn: Callable,
):
    """
    Tier 2 worker — deep distillation via existing pipeline.

    This is the EXPENSIVE step. Limited to TIER2_CONCURRENCY workers.
    """
    worker_id = id(asyncio.current_task())
    logger.info(f"[Tier2-{worker_id}] Starting")

    while True:
        try:
            result = await pop_doc(redis, "tier2")
        except asyncio.CancelledError:
            break

        if not result:
            await asyncio.sleep(0.5)
            continue

        doc_id, priority = result

        # Acquire lock
        if not await lock_doc(redis, doc_id):
            continue

        try:
            await update_doc_status(redis, doc_id, "processing")

            # Fetch document
            doc = await fetch_doc_fn(doc_id)
            if not doc:
                await update_doc_status(redis, doc_id, "failed", reason="fetch_failed")
                continue

            # 🔥 CALL EXISTING DISTILLATION PIPELINE
            atoms = await distill_fn(doc)

            # Store atoms
            if store_atoms_fn:
                await store_atoms_fn(atoms, doc_id)

            await update_doc_status(redis, doc_id, "done", atoms_count=len(atoms) if atoms else 0)
            logger.debug(f"[Tier2-{worker_id}] Distilled {doc_id[:20]}: {len(atoms) if atoms else 0} atoms")

        except Exception as e:
            logger.error(f"[Tier2-{worker_id}] Failed to distill {doc_id}: {e}")
            await update_doc_status(redis, doc_id, "failed", error=str(e))

        finally:
            await unlock_doc(redis, doc_id)


# ──────────────────────────────────────────────────────────────
# Lazy Tier 2 Triggers
# ──────────────────────────────────────────────────────────────

async def trigger_tier2_for_query(
    redis,
    query_text: str,
    retriever,
    priority: float = 0.9,
):
    """
    Lazy Tier 2 trigger: when a query retrieves results without deep atoms,
    enqueue the source documents for Tier 2 processing.
    """
    # This would be called from V3Retriever when results lack deep atoms
    pass  # Hook point — wire into retriever when needed


async def trigger_tier2_for_contradiction(
    redis,
    contradiction: Dict[str, Any],
    priority: float = 0.95,
):
    """
    Lazy Tier 2 trigger: when contradiction is detected, boost related docs.
    """
    # Hook point — wire into belief graph contradiction detection
    pass


# ──────────────────────────────────────────────────────────────
# Backlog Monitor + Safety Valve
# ──────────────────────────────────────────────────────────────

async def monitor_backlog(
    redis,
    novelty_threshold_ref: List[float],
    check_interval: int = 30,
):
    """
    Monitor queue sizes and auto-adjust novelty threshold if backlog grows.

    Runs as a background task. Pass novelty_threshold_ref as a single-element
    list so workers can read the updated threshold.
    """
    while True:
        try:
            sizes = await get_queue_size(redis)
            total = sum(sizes.values())

            if total > BACKLOG_SAFETY_VALVE:
                # Raise novelty threshold to drop more docs
                new_threshold = min(0.8, NOVELTY_THRESHOLD + BACKLOG_NOVELTY_BOOST)
                novelty_threshold_ref[0] = new_threshold
                logger.warning(f"[BacklogMonitor] Queue backlog: {sizes} (total={total}). "
                              f"Raised novelty threshold to {new_threshold:.2f}")
            elif total < BACKLOG_SAFETY_VALVE // 2:
                # Reset threshold
                if novelty_threshold_ref[0] > NOVELTY_THRESHOLD:
                    novelty_threshold_ref[0] = NOVELTY_THRESHOLD
                    logger.info(f"[BacklogMonitor] Backlog cleared. Reset novelty threshold to {NOVELTY_THRESHOLD:.2f}")

        except Exception as e:
            logger.debug(f"[BacklogMonitor] Error: {e}")

        await asyncio.sleep(check_interval)


# ──────────────────────────────────────────────────────────────
# Worker Manager — Startup + Lifecycle
# ──────────────────────────────────────────────────────────────

class IngestionControl:
    """
    Manages the full multi-tier ingestion pipeline.

    Usage:
      ic = IngestionControl(redis, cmk_runtime, chroma_client)
      workers = ic.start_workers(crawl_source, distill_fn, fetch_doc_fn, store_atoms_fn)
      ...
      await ic.stop_workers(workers)
    """

    def __init__(self, redis, cmk_runtime=None, chroma_client=None):
        self.redis = redis
        self.cmk_runtime = cmk_runtime
        self.chroma_client = chroma_client

        self.novelty_gate = NoveltyGate(redis, chroma_client)
        self.graph_gap_scorer = GraphGapScorer(cmk_runtime) if cmk_runtime else None

        self._workers: List[asyncio.Task] = []
        self._novelty_threshold = [NOVELTY_THRESHOLD]

    def start_workers(
        self,
        crawl_source: asyncio.Queue,
        extract_fn: Callable = None,
        fetch_doc_fn: Callable = None,
        distill_fn: Callable = None,
        store_atoms_fn: Callable = None,
    ) -> List[asyncio.Task]:
        """
        Start all ingestion workers.

        Args:
            crawl_source: asyncio.Queue where crawler pushes documents
            extract_fn: Tier 1 batched extraction function (optional)
            fetch_doc_fn: Function to fetch doc content by ID (optional)
            distill_fn: Existing distillation pipeline function (required for Tier 2)
            store_atoms_fn: Function to store atoms (required for Tier 2)
        """
        workers = []

        # Tier 0 workers (fast surface scan)
        for _ in range(TIER0_CONCURRENCY):
            w = asyncio.create_task(
                tier0_worker(
                    self.redis,
                    crawl_source,
                    self.novelty_gate,
                    self.graph_gap_scorer,
                    self._novelty_threshold[0],
                )
            )
            workers.append(w)

        # Tier 1 workers (shallow extraction) — only if extract_fn provided
        if extract_fn and fetch_doc_fn:
            for _ in range(TIER1_CONCURRENCY):
                w = asyncio.create_task(
                    tier1_worker(
                        self.redis,
                        extract_fn,
                        fetch_doc_fn,
                        self._novelty_threshold[0],
                    )
                )
                workers.append(w)

        # Tier 2 workers (deep distillation) — strictly limited
        if distill_fn and fetch_doc_fn and store_atoms_fn:
            for _ in range(TIER2_CONCURRENCY):
                w = asyncio.create_task(
                    tier2_worker(
                        self.redis,
                        distill_fn,
                        fetch_doc_fn,
                        store_atoms_fn,
                    )
                )
                workers.append(w)

        # Backlog monitor
        w = asyncio.create_task(
            monitor_backlog(self.redis, self._novelty_threshold)
        )
        workers.append(w)

        self._workers = workers
        logger.info(f"[IngestionControl] Started {len(workers)} workers "
                   f"(T0={TIER0_CONCURRENCY}, T1={TIER1_CONCURRENCY if extract_fn else 0}, "
                   f"T2={TIER2_CONCURRENCY if distill_fn else 0})")

        return workers

    async def stop_workers(self, workers: List[asyncio.Task] = None):
        """Gracefully stop all workers."""
        workers = workers or self._workers
        for w in workers:
            w.cancel()
        await asyncio.gather(*workers, return_exceptions=True)
        logger.info("[IngestionControl] All workers stopped")

    async def get_stats(self) -> Dict[str, Any]:
        """Get current ingestion pipeline stats."""
        sizes = await get_queue_size(self.redis)
        return {
            "queue_sizes": sizes,
            "total_backlog": sum(sizes.values()),
            "novelty_threshold": self._novelty_threshold[0],
            "active_workers": len([w for w in self._workers if not w.done()]),
        }
