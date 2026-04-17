"""
condensation/pipeline.py — Differential Knowledge Distillery

Architectural Shift:
- Coverage before compression: Wait for document clusters before mining.
- Diversity before certainty: Explicitly extract unique differentials between similar sources.
- Contradiction before consensus: Conflict is preserved as a first-class memory object.
"""

import asyncio
import traceback
import re
from datetime import datetime
from src.utils.distillation_pipeline import compute_confidence, ExtractionError
from src.utils.source_classifier import classify_source_quality
from src.utils.normalize_atom_schema import normalize_atom_schema
from src.research.state_machine import transition_source_status
from src.utils.pipeline_metrics import MetricsCollector
from src.research.consolidation import ConsolidationEngine
import json
import logging
import math
import os
import re
from typing import Dict, List, Set, Any, Optional
from dataclasses import dataclass, field

from src.research.acquisition.budget import BudgetMonitor, CondensationPriority
from src.llm.client import OllamaClient
from src.llm.model_router import TaskType
from src.core.memory.cmk.runtime import CMKRuntime
from src.research.acquisition.ingestion_control import push_doc, compute_content_hash, compute_priority


# Canonical filter reasons matching DB CHECK constraint:
# 'too_short', 'low_quality', 'duplicate', 'semantic_drift', 'no_atoms'
_CANONICAL_REASONS = {"too_short", "low_quality", "duplicate", "semantic_drift", "no_atoms"}
_LOW_SIGNAL_ATOM_PATTERNS = (
    "federal government website",
    "official website",
    "encrypted and transmitted securely",
    "end in .gov",
    "end in .mil",
    "site is secure",
    "https:// ensures",
    "search the dictionary",
    "provides definitions",
)


def _normalize_filter_reason(human_reason: str) -> str:
    """
    Map human-readable Gate 0a rejection reason to canonical DB constraint value.

    DB constraint: chk_source_filter_reason
    Allowed: 'too_short', 'low_quality', 'duplicate', 'semantic_drift', 'no_atoms'
    """
    reason_lower = human_reason.lower()

    if "short" in reason_lower or "word" in reason_lower:
        return "too_short"
    if "empty" in reason_lower:
        return "too_short"
    if "junk" in reason_lower or "content density" in reason_lower:
        return "low_quality"
    if "repetition" in reason_lower or "repeat" in reason_lower or "spam" in reason_lower:
        return "duplicate"
    if "drift" in reason_lower:
        return "semantic_drift"

    # Fallback: use original if it's already canonical
    if human_reason in _CANONICAL_REASONS:
        return human_reason

    return "low_quality"  # Safe default


def _is_low_signal_atom(atom_dict: Dict[str, Any], mission_title: str) -> bool:
    text = (atom_dict.get("text") or atom_dict.get("content") or "").strip()
    if not text:
        return True
    lowered = text.lower()
    if any(pattern in lowered for pattern in _LOW_SIGNAL_ATOM_PATTERNS):
        return True

    mission_tokens = {token for token in re.findall(r"[a-z0-9]+", mission_title.lower()) if len(token) > 2}
    text_tokens = {token for token in re.findall(r"[a-z0-9]+", lowered) if len(token) > 2}
    concept_tokens = {
        token for token in re.findall(r"[a-z0-9]+", str(atom_dict.get("concept", "")).lower())
        if len(token) > 2
    }
    # Generic or very short mission titles are too noisy to use as a hard lexical gate.
    if len(mission_tokens) >= 3 and not (mission_tokens & text_tokens) and not (concept_tokens & text_tokens):
        return True
    return False

from src.utils.console import console
from src.utils.json_validator import JSONValidator, extract_technical_atoms, _extract_entities_semantic

logger = logging.getLogger(__name__)


async def _write_dead_letter(adapter, source_id: str, stage: str,
                            error_class: str, error_detail: str,
                            retry_count: int = 0, worker_id: str = "",
                            payload: dict = None) -> None:
    """Write a structured dead-letter entry for replay. Fails gracefully if table doesn't exist."""
    try:
        await adapter.pg.insert_row("audit.dead_letter_queue", {
            "source_id": source_id,
            "stage": stage,
            "error_class": error_class,
            "error_detail": error_detail,
            "retry_count": retry_count,
            "max_retries": 3,
            "last_seen_worker": worker_id,
            "payload": json.dumps(payload or {}),
            "status": "pending",
        })
    except Exception as e:
        logger.debug(f"[Distillery] Dead-letter write failed (table may not exist): {e}")


@dataclass
class ExtractionCluster:
    mission_id: str
    concept: str
    sources: List[Dict] = field(default_factory=list)
    atoms: List[Dict] = field(default_factory=list)

class DistillationPipeline:
    def __init__(self, ollama: OllamaClient, memory, budget: BudgetMonitor, adapter=None, cmk_runtime: Optional[CMKRuntime] = None, ingest_redis=None):
        self.ollama = ollama
        self.memory = memory  # V2 removed; expected None in V3
        self.budget = budget
        self.adapter = adapter
        self.cmk_runtime = cmk_runtime
        self.ingest_redis = ingest_redis
        self._semaphore = asyncio.Semaphore(2)
        self.consolidation_engine = ConsolidationEngine(adapter, ollama) if adapter and ollama else None

        # PERSIST-08: Embedding registry
        # OBS-01: Pipeline metrics
        if adapter:
            from src.memory.embedding_registry import EmbeddingRegistry
            from src.utils.pipeline_metrics import MetricsCollector
            from src.config.settings import settings

            embed_model = getattr(settings, 'OLLAMA_EMBED_MODEL', 'mxbai-embed-large:latest')
            embed_host = getattr(settings, 'OLLAMA_EMBED_HOST', 'http://localhost:11434')
            embed_dim = getattr(settings, 'EMBEDDING_DIMENSION', 1024)

            self.embedding_registry = EmbeddingRegistry(adapter.pg, embed_model, embed_host, embed_dim)
            self.metrics = MetricsCollector(adapter.pg)
            # Pass registry to consolidation engine
            if self.consolidation_engine:
                self.consolidation_engine.embedding_registry = self.embedding_registry
        else:
            self.embedding_registry = None
            self.metrics = None

    async def _check_source_already_extracted(
        self, source_id: str, content_hash: str | None
    ) -> bool:
        """
        Tier 1 + Tier 2 idempotency check.
        Returns True if this source has already been extracted.
        """
        # Fast path: Redis cache (ephemeral, skip on failure)
        if content_hash:
            try:
                cache_key = f"pipeline:extracted:{source_id}:{content_hash}"
                exists = await self.adapter.redis_runtime.get(cache_key)
                if exists:
                    logger.info(f"[Idempotency] SKIP {source_id}: found in Redis cache")
                    return True
            except Exception as e:
                logger.debug(f"[Idempotency] Redis cache check failed: {e}")
                pass

        # Authoritative: Postgres state check
        if content_hash:
            row = await self.adapter.pg.fetch_one(
                "corpus.sources",
                {"source_id": source_id, "content_hash": content_hash},
            )
        else:
            row = await self.adapter.pg.fetch_one(
                "corpus.sources", {"source_id": source_id}
            )

        if row and row.get("status") in ("extracted", "condensed", "indexed"):
            if content_hash:
                try:
                    cache_key = f"pipeline:extracted:{source_id}:{content_hash}"
                    await self.adapter.redis_runtime.set(cache_key, "1", ttl_s=3600)
                except Exception:
                    pass
            logger.info(f"[Idempotency] SKIP {source_id}: status={row['status']}")
            return True

        return False

    async def run(self, mission_id: str, priority: CondensationPriority):
        """Metabolic Distillation pass using V3 Triad (Sequential-Atomic)."""
        console.print(f"[bold magenta][Distillery][/bold magenta] Starting distillation pass for mission {mission_id[:8]}... (priority={priority.value})")
        async with self._semaphore:
            # 1. Fetch raw technical ore from V3 Corpus
            # Dynamic batch size: scale with backlog to prevent throughput bottleneck
            sources = await self.adapter.pg.fetch_many(
                "corpus.sources",
                where={"mission_id": mission_id, "status": "fetched"},
                limit=15  # Increased from 5 — LLM calls are the limiter, not batch size
            )
            logger.info(f"[Distillery] Fetched {len(sources) if sources else 0} sources for mission {mission_id}")
            if not sources:
                console.print(f"[yellow][Distillery][/yellow] No 'fetched' sources found for mission {mission_id[:8]} — skipping distillation")
                return

            console.print(f"[dim][Distillery] Found {len(sources)} fetched sources to process[/dim]")

            # 2. Fetch mission metadata for domain profile and topic
            mission_row = await self.adapter.get_mission(mission_id)

            # Generate audit run_id and write start row
            run_id = f"run-{mission_id[:8]}-{datetime.utcnow().isoformat()}"
            topic_id = mission_row.get("topic_id", mission_id) if isinstance(mission_row, dict) else mission_id[:8]

            try:
                await self.adapter.pg.insert_row("audit.pipeline_runs", {
                    "run_id": run_id,
                    "mission_id": mission_id,
                    "topic_id": topic_id,
                    "pipeline_type": "condensation",
                    "pipeline_version": "v1.3.0-phase13",
                    "status": "running",
                })
            except Exception:
                logger.warning("[Distillery] Failed to write audit start row — pipeline_runs table may not exist yet. Run migrations/phase_13_pipeline_audit.sql")
                run_id = None  # Disable audit tracking for this run

            try:
                await self._process_sources(sources, mission_id, mission_row, run_id, priority)

                # Write success row
                if run_id:
                    try:
                        await self.adapter.pg.update_row("audit.pipeline_runs", "run_id", {
                            "run_id": run_id,
                            "status": "completed",
                            "completed_at": datetime.utcnow(),
                            "source_count": len(sources),
                            "atom_count": self._total_atoms,
                        })
                    except Exception:
                        pass

                # Run consolidation + contradiction resolution
                if self.consolidation_engine and self._total_atoms > 0:
                    try:
                        consolidation_summary = await self.consolidation_engine.consolidate_atoms(mission_id)
                        logger.info(f"[Consolidation] {consolidation_summary['golden_atoms_created']} golden atoms created, "
                                    f"{consolidation_summary['atoms_obsoleted']} atoms obsoleted")

                        if self.metrics:
                            self.metrics.record(run_id, "golden_atoms", float(consolidation_summary['golden_atoms_created']), {"mission_id": mission_id})
                            self.metrics.record(run_id, "atoms_obsoleted", float(consolidation_summary['atoms_obsoleted']), {"mission_id": mission_id})

                        contradiction_summary = await self.consolidation_engine.resolve_contradictions(mission_id)
                        logger.info(f"[Contradictions] {contradiction_summary['verified_contradictions']} verified, "
                                    f"{contradiction_summary['resolved']} resolved")

                        if self.metrics:
                            self.metrics.record(run_id, "contradictions_verified", float(contradiction_summary['verified_contradictions']), {"mission_id": mission_id})
                            self.metrics.record(run_id, "contradictions_resolved", float(contradiction_summary['resolved']), {"mission_id": mission_id})
                    except Exception as e:
                        logger.warning(f"[Consolidation] Consolidation failed: {e}")
                        if self.metrics:
                            self.metrics.record(run_id, "consolidation_error", 1.0, {"error": str(e)})

                # Record extraction metrics
                if self.metrics:
                    self.metrics.record(run_id, "atoms_extracted", float(self._total_atoms), {"mission_id": mission_id})
                    self.metrics.record(run_id, "sources_processed", float(len(sources)), {"mission_id": mission_id})
                    self.metrics.flush()

                # TUI-02: Publish batch complete event
                try:
                    from src.utils.status_pubsub import publish_status
                    redis_client = self.adapter.redis_runtime.client if hasattr(self.adapter.redis_runtime, 'client') else self.adapter.redis_runtime
                    await publish_status(redis_client, "distillery", "batch_complete", {
                        "atoms": self._total_atoms, "mission_id": mission_id[:8],
                    })
                except Exception:
                    pass

            except Exception as e:
                tb = traceback.format_exc()
                logger.error(f"[Distillery] Distillation pipeline failed: {e}\n{tb}")
                if self.metrics:
                    self.metrics.record(run_id, "pipeline_error", 1.0, {"error_class": type(e).__name__})
                    self.metrics.flush()
                if run_id:
                    try:
                        await self.adapter.pg.update_row("audit.pipeline_runs", "run_id", {
                            "run_id": run_id,
                            "status": "failed",
                            "completed_at": datetime.utcnow(),
                            "error_stage": "condensation",
                            "error_class": type(e).__name__,
                            "error_detail": str(e),
                            "error_traceback": tb,
                        })
                    except Exception:
                        pass
                raise

    async def _process_sources(self, sources, mission_id, mission_row, run_id, priority):
        """Process a batch of sources through the distillation pipeline with parallel workers."""
        import uuid
        from src.research.domain_schema import KnowledgeAtom, AtomLineage

        self._total_atoms = 0
        _concept_counts: dict = {}  # concept_name -> atom count this batch (for emergent topic detection)
        # High-throughput: process sources in parallel with bounded concurrency
        worker_semaphore = asyncio.Semaphore(4)  # 4 parallel distillation workers
        results_lock = asyncio.Lock()  # Protect _total_atoms and _concept_counts
        error_count = [0]

        async def _process_single(s):
            """Process one source through the full distillation pipeline."""
            async with worker_semaphore:
                if not isinstance(s, dict):
                    logger.error(f"[Distillery] Skipping malformed source row: type={type(s).__name__}")
                    return 0

                source_id = s.get("source_id", "unknown")
                console.print(f"[dim][Distillery] Worker started for {source_id}[/dim]")

                # Idempotency check: skip if already extracted
                content_hash = s.get("content_hash")
                if await self._check_source_already_extracted(source_id, content_hash):
                    return 0

                # Check metadata for HTTP error status (403, 404, etc.) before processing
                metadata = s.get("metadata_json")
                console.print(f"[dim][Distillery] Source {source_id} metadata: {metadata}[/dim]")
                if isinstance(metadata, str):
                    try:
                        import json as _json
                        meta = _json.loads(metadata)
                        status_code = meta.get("statusCode", meta.get("status_code", 0))
                        if isinstance(status_code, int) and status_code >= 400:
                            logger.info(f"[Pipeline] Skipping source {source_id}: HTTP {status_code}")
                            await transition_source_status(self.adapter, source_id, "filtered_out", current_status="fetched")
                            await self.adapter.pg.update_row("corpus.sources", "source_id", {
                                "source_id": source_id,
                                "filter_metadata": {"gate": "http_error", "status_code": status_code},
                            })
                            return 0
                    except (json.JSONDecodeError, TypeError):
                        pass  # Metadata not parseable, continue

                # Get the content
                text_ref = s.get("canonical_text_ref")
                console.print(f"[dim][Distillery] Source {source_id} text_ref: {text_ref}[/dim]")
                if not text_ref:
                    console.print(f"[dim][Distillery] Source {source_id} aborted: no text_ref[/dim]")
                    await transition_source_status(self.adapter, source_id, "error", current_status="fetched")
                    return 0

                ref = await self.adapter.get_text_ref(text_ref)
                console.print(f"[dim][Distillery] Source {source_id} ref object: {bool(ref)} (has text: {bool(ref.get('inline_text') if ref else False)})[/dim]")
                if not ref or not ref.get("inline_text"):
                    console.print(f"[dim][Distillery] Source {source_id} aborted: ref or inline_text missing[/dim]")
                    await transition_source_status(self.adapter, source_id, "error", current_status="fetched")
                    return 0

                content = ref["inline_text"]
                console.print(f"[dim][Distillery] Source {source_id} content: {len(content)} chars. CMK: {bool(self.cmk_runtime)}, Redis: {bool(self.ingest_redis)}[/dim]")

                # ── CMK Integration: Push to ingestion control Tier 0 ──
                if self.cmk_runtime and self.ingest_redis:
                    console.print(f"[dim][Distillery] Source {source_id} Redirecting to CMK...[/dim]")
                    try:
                        doc_id = source_id
                        chash = compute_content_hash(content)
                        doc_meta = {
                            "id": doc_id,
                            "url": s.get("url", ""),
                            "content": content[:5000],
                            "mission_id": mission_id,
                            "source": s.get("source", ""),
                        }
                        pri = compute_priority(doc_meta, novelty_score=0.5, graph_gap_score=0.0)
                        await push_doc(self.ingest_redis, doc_id, pri, tier="tier0", metadata=doc_meta)
                        await transition_source_status(
                            self.adapter, source_id, "queued_for_ingestion", current_status="fetched"
                        )
                        return 0  # Handled by ingestion pipeline
                    except Exception:
                        pass  # Fall through to direct processing

                console.print(f"[dim][Distillery] Source {source_id} Proceeding to quality gates...[/dim]")

                # ── GATE 0b: Source quality classification ──
                # Run before LLM extraction so we skip low-value sources cheaply.
                # Scores: academic=0.85, standard=0.55, skip=0.10
                _QUALITY_SCORE_MAP = {"academic": 0.85, "standard": 0.55, "skip": 0.10}
                content_for_classification = content[:4000]
                source_type = classify_source_quality(s.get('url', ''), content_for_classification)
                logger.info(f"[Distillery] Source {source_id} quality: {source_type}")
                quality_score = _QUALITY_SCORE_MAP.get(source_type, 0.55)
                
                logger.info(f"[Pipeline] Source {source_id} quality classification: {source_type} (score={quality_score})")

                # Write quality_score + trust_score back to corpus.sources so they're queryable
                await self.adapter.pg.update_row("corpus.sources", "source_id", {
                    "source_id": source_id,
                    "quality_score": quality_score,
                    "trust_score": quality_score,  # same signal for now; can diverge later
                })
                console.print(f"[dim][Distillery] Source {source_id} quality score written: {quality_score}[/dim]")

                if source_type == "skip":
                    logger.info(f"[Pipeline] Skipping source {source_id}: quality classification 'skip'")
                    await transition_source_status(self.adapter, source_id, "filtered_out", current_status="fetched")
                    await self.adapter.pg.update_row("corpus.sources", "source_id", {
                        "source_id": source_id,
                        "filter_metadata": {"gate": "0b_quality", "reason": "low_quality"},
                    })
                    return 0

                # ── GATE 0a: Heuristic pre-filter ──
                from src.utils.embedding_distiller import gate_0a_heuristic
                verdict, reason = gate_0a_heuristic(content, ref.get("raw_html", ""))
                console.print(f"[dim][Distillery] Source {source_id} Gate 0a verdict: {verdict} (reason: {reason})[/dim]")
                if verdict == "SKIP":
                    logger.info(f"[Pipeline] Skipping source {source_id}: gate_0a verdict 'SKIP'")
                    await transition_source_status(self.adapter, source_id, "filtered_out", current_status="fetched")
                    canonical_reason = _normalize_filter_reason(reason)
                    await self.adapter.pg.update_row("corpus.sources", "source_id", {
                        "source_id": source_id,
                        "filter_metadata": {"gate": "0a_heuristic", "reason": canonical_reason},
                    })
                    return 0

                # Fetch chunks for evidence binding
                chunks = await self.adapter.list_chunks_for_source(source_id)
                console.print(f"[dim][Distillery] Source {source_id} chunks: {len(chunks) if chunks else 0}[/dim]")
                if not chunks:
                    await transition_source_status(self.adapter, source_id, "error", current_status="fetched")
                    return 0

                chunk_infos = [(chunk['chunk_id'], chunk.get('inline_text', '')) for chunk in chunks]

                console.print(f"[dim][Distillery] Source {source_id} calling extract_technical_atoms...[/dim]")
                try:
                    atoms_data = await extract_technical_atoms(
                        self.ollama, content, mission_id,
                        source_url=s.get('url', '')
                    )
                    console.print(f"[dim][Distillery] Source {source_id} extraction returned {len(atoms_data)} atoms[/dim]")

                    # Transition fetched -> extracted before processing atoms
                    await transition_source_status(self.adapter, source_id, "extracted", current_status="fetched")

                    atoms_this_source = 0
                    mission_title = mission_row.get("title", "") if isinstance(mission_row, dict) else ""

                    for atom_dict in atoms_data:
                        if not isinstance(atom_dict, dict):
                            continue

                        normalized = normalize_atom_schema(atom_dict)
                        content_value = normalized.get('text', '')
                        logger.info(f"[Distillery] Processing atom: {content_value[:50]}...")
                        if not content_value or not isinstance(content_value, str):
                            logger.info(f"[Distillery] Atom skipped: no content")
                            continue
                        if _is_low_signal_atom(normalized, mission_title):
                            logger.info(f"[Distillery] Atom skipped: low-signal content for mission '{mission_title}'")
                            continue
                        atom_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{mission_id}:{source_id}:{content_value[:200]}"))
                        profile_id = mission_row.get("domain_profile_id") if isinstance(mission_row, dict) else f"profile_{mission_id[:8]}"

                        # Compute importance/novelty if LLM didn't provide them
                        atom_importance = normalized.get("importance")
                        atom_novelty = normalized.get("novelty")
                        if atom_importance is None:
                            from src.utils.atom_scorer import compute_importance
                            atom_importance = compute_importance(content_value)
                        if atom_novelty is None:
                            from src.utils.atom_scorer import compute_novelty
                            atom_novelty = compute_novelty(content_value, atoms_data)

                        atom = KnowledgeAtom(
                            atom_id=atom_id,
                            topic_id=mission_row.get("topic_id") if isinstance(mission_row, dict) else mission_id,
                            domain_profile_id=profile_id,
                            atom_type=atom_dict.get('atom_type', atom_dict.get('type', 'claim')),
                            title=content_value[:50] + "...",
                            statement=content_value,
                            summary=content_value,
                            confidence=compute_confidence(normalized, source_type, atoms_data),
                            importance=atom_importance,
                            novelty=atom_novelty,
                            lineage=AtomLineage(mission_id=mission_id, extraction_mode="atomic_distillation"),
                            metadata={"type": atom_dict.get('atom_type', atom_dict.get('type')), "source_id": source_id}
                        )

                        atom_content = normalized.get('text', '').strip()
                        matched_chunk_ids = []
                        if atom_content:
                            atom_words = set(atom_content.lower().split())
                            best_score = 0.0
                            best_chunk_id = chunks[0]['chunk_id']
                            for chunk_id, chunk_text in chunk_infos:
                                # Exact substring match first (fast path)
                                if atom_content in chunk_text or chunk_text in atom_content:
                                    matched_chunk_ids.append(chunk_id)
                                    continue
                                # Word-overlap (Jaccard) for paraphrased atoms
                                chunk_words = set(chunk_text.lower().split())
                                union = atom_words | chunk_words
                                if union:
                                    score = len(atom_words & chunk_words) / len(union)
                                    if score > best_score:
                                        best_score = score
                                        best_chunk_id = chunk_id
                            if not matched_chunk_ids:
                                # Use the chunk with highest word overlap (min 0.15 to be meaningful)
                                matched_chunk_ids = [best_chunk_id] if best_score >= 0.15 else [chunks[0]['chunk_id']]
                        else:
                            matched_chunk_ids = [chunks[0]['chunk_id']]

                        evidence_rows = [
                            {"source_id": source_id, "chunk_id": cid, "evidence_strength": 0.9, "supports_statement": True}
                            for cid in matched_chunk_ids
                        ]

                        atom_row = atom.to_pg_row()
                        await self.adapter.store_atom_with_evidence(atom_row, evidence_rows)
                        logger.info(f"[Distillery] Atom {atom_id} persisted with {len(evidence_rows)} evidence rows")

                        # Entity / concept tagging — populate knowledge.atom_entities
                        raw_concept = atom_dict.get('concept', '').strip()
                        if raw_concept:
                            from src.utils.atom_quality import is_noise_concept
                            if not is_noise_concept(raw_concept):
                                try:
                                    await self.adapter.replace_atom_entities(atom_id, [
                                        {"atom_id": atom_id, "entity_name": raw_concept, "entity_type": "concept"}
                                    ])
                                    # Track concept frequency in-memory for emergent topic detection
                                    async with results_lock:
                                        _concept_counts[raw_concept.lower()] = _concept_counts.get(raw_concept.lower(), 0) + 1
                                except Exception as ent_err:
                                    logger.debug(f"[Distillery] Entity tag failed for {atom_id}: {ent_err}")

                        # CMK Integration: activate + belief graph
                        if self.cmk_runtime:
                            try:
                                await self._cmk_ingest_atom(atom, mission_id)
                            except Exception as cmk_err:
                                logger.debug(f"[Distillery] CMK ingest failed for {atom_id}: {cmk_err}")

                        async with results_lock:
                            self._total_atoms += 1
                        atoms_this_source += 1

                    # Mark source status
                    if atoms_this_source > 0:
                        await transition_source_status(self.adapter, source_id, "condensed", current_status="extracted")
                        await self.budget.record_source_condensed(mission_id)
                    elif len(atoms_data) > 0:
                        await transition_source_status(self.adapter, source_id, "filtered_out", current_status="extracted")
                        await self.adapter.pg.update_row("corpus.sources", "source_id", {
                            "source_id": source_id,
                            "filter_metadata": {
                                "reason": "low_quality", "raw_atoms_count": len(atoms_data),
                                "passed_atoms_count": 0,
                                "details": "All extracted atoms failed quality gates",
                            },
                        })
                    else:
                        await transition_source_status(self.adapter, source_id, "rejected", current_status="extracted")
                        await self.adapter.pg.update_row("corpus.sources", "source_id", {
                            "source_id": source_id,
                            "filter_metadata": {"reason": "no_atoms", "raw_atoms_count": 0},
                        })

                    return atoms_this_source

                except ExtractionError as e:
                    console.print(f"[bold red][Distillery] Extraction failed for {source_id}[/bold red]")
                    await transition_source_status(self.adapter, source_id, "error", current_status="fetched")
                    await _write_dead_letter(self.adapter, source_id, "extraction", "ExtractionError", str(e),
                        worker_id="pipeline:condensation",
                        payload={"mission_id": mission_id, "url": s.get("url", ""), "content_hash": s.get("content_hash")})
                    error_count[0] += 1
                    return 0
                except Exception as e:
                    tb = traceback.format_exc()
                    console.print(f"[bold red][Distillery] Smelting failed for {source_id}: {e}[/bold red]")
                    console.print(f"[dim]{tb}[/dim]")
                    logger.error(f"[Distillery] Smelting failed for {source_id}: {e}\n{tb}")
                    await transition_source_status(self.adapter, source_id, "error", current_status="fetched")
                    await _write_dead_letter(self.adapter, source_id, "condensation", type(e).__name__, str(e),
                        worker_id="pipeline:condensation",
                        payload={"mission_id": mission_id, "url": s.get("url", ""), "content_hash": s.get("content_hash")})
                    error_count[0] += 1
                    return 0

        # Run all sources in parallel with bounded concurrency
        console.print(f"[dim][Distillery] Running {len(sources)} worker tasks...[/dim]")
        results = await asyncio.gather(*[_process_single(s) for s in sources], return_exceptions=True)
        logger.info(f"[Distillery] Gather complete with {len(results)} results")

        # Log and raise any exceptions from gather to avoid silent failures
        for i, r in enumerate(results):
            if isinstance(r, Exception):
                logger.error(f"[Distillery] Parallel worker exception for source {i}: {r}")
                error_count[0] += 1
                # In test or debug mode, we want to know exactly what failed
                raise r

        console.print(f"[bold green][Refinery][/bold green] Batch complete. Smelted technical atoms: [white]{self._total_atoms}[/white]")

        # Emergent topic detection — find adjacent concepts that accumulated enough atoms
        # to warrant follow-on learning when this mission completes
        if _concept_counts and self.adapter:
            mission_title = mission_row.get("title", "") if isinstance(mission_row, dict) else ""
            await self._record_emergent_topics(mission_id, mission_title, _concept_counts)

        # Entity Discovery
        if self.adapter and self._total_atoms > 0:
            condensed_atoms = await self.adapter.get_mission_atoms(mission_id, limit=100)
            if condensed_atoms:
                entities = await _extract_entities_semantic(condensed_atoms, self.ollama)
                if entities:
                    console.print(f"[bold cyan][Discovery][/bold cyan] Extracted {len(entities)} entities for Frontier expansion: {entities[:15]}")
                    if hasattr(self.adapter, 'store_discovery_entities'):
                        await self.adapter.store_discovery_entities(mission_id, entities)

        # Higher-Order Refinement
        if self._total_atoms > 0:
            if priority in [CondensationPriority.HIGH, CondensationPriority.CRITICAL]:
                await self.resolve_contradictions(mission_id)
            # Run belief graph cross-linking + self-correction for new atoms
            if self.cmk_runtime:
                try:
                    await self._belief_graph_cross_link(mission_id)
                    await self._self_correct_beliefs(mission_id)
                except Exception as e:
                    logger.debug(f"[Distillery] Belief graph pipeline failed: {e}")

        # Budget Feedback
        await self.budget.record_condensation_result(
            mission_id=mission_id,
            raw_bytes_freed=sum(len(str(s).encode()) for s in sources),
            condensed_bytes_added=self._total_atoms * 500
        )

    async def _cluster_sources(self, sources: List[Dict]) -> List[ExtractionCluster]:
        """Group sources by concept proximity."""
        # Simple clustering for the scaffold
        clusters = [ExtractionCluster(mission_id=sources[0].get('mission_id', sources[0].get('topic_id', '')), concept="batch_general", sources=sources)]
        return clusters

    # ── Emergent Topic Detection ──────────────────────────────────────────────

    # Minimum atoms from an adjacent concept before it's flagged as emergent
    _EMERGENT_THRESHOLD = 5
    # Minimum distinct atoms (not just raw count) — avoids flagging repeated mentions
    _EMERGENT_DISTINCT_THRESHOLD = 3

    async def _record_emergent_topics(
        self,
        mission_id: str,
        mission_title: str,
        concept_counts: dict,
    ) -> None:
        """
        Examine concepts that accumulated during this distillation pass.
        Any concept that:
          - appears >= _EMERGENT_THRESHOLD times
          - is NOT a substring match of the current mission title (i.e. it's adjacent)
        is recorded as an emergent topic candidate in the mission frontier snapshot.

        These candidates are queued as follow-on missions when the current
        mission completes — the system learns about what it encountered
        organically without derailing the active mission.
        """
        from src.utils.atom_quality import is_noise_concept

        mission_lower = mission_title.lower()
        candidates = []

        for concept, count in concept_counts.items():
            if count < self._EMERGENT_THRESHOLD:
                continue
            if is_noise_concept(concept):
                continue
            # Skip if the concept is the mission topic or a substring of it
            if concept in mission_lower or mission_lower in concept:
                continue
            candidates.append({"concept": concept, "atom_count": count, "source_mission": mission_id})

        if not candidates:
            return

        # Sort by atom count descending — most prominent adjacent topics first
        candidates.sort(key=lambda c: c["atom_count"], reverse=True)
        top = candidates[:10]  # Cap at 10 emergent candidates per pass

        logger.info(
            "[Distillery] Emergent topics detected: %s",
            [c["concept"] for c in top],
        )
        console.print(
            f"[bold yellow][Discovery][/bold yellow] {len(top)} emergent topic(s) detected: "
            + ", ".join(f"[cyan]{c['concept']}[/cyan] ({c['atom_count']} atoms)" for c in top[:5])
        )

        # Store in mission frontier snapshot for retrieval at mission completion
        try:
            existing_snapshot = await self.adapter.get_latest_frontier_checkpoint(mission_id) if self.adapter else None
            existing_candidates = []
            if existing_snapshot:
                existing_candidates = existing_snapshot.get("emergent_topics", [])

            # Merge: add new candidates, update counts for existing ones
            existing_by_concept = {c["concept"]: c for c in existing_candidates}
            for cand in top:
                key = cand["concept"]
                if key in existing_by_concept:
                    existing_by_concept[key]["atom_count"] = max(
                        existing_by_concept[key]["atom_count"], cand["atom_count"]
                    )
                else:
                    existing_by_concept[key] = cand

            merged = sorted(existing_by_concept.values(), key=lambda c: c["atom_count"], reverse=True)

            await self.adapter.checkpoint_frontier(mission_id, {"emergent_topics": merged})
        except Exception as e:
            logger.warning("[Distillery] Failed to record emergent topics: %s", e)

    async def get_emergent_topics_to_spawn(self, mission_id: str) -> list[dict]:
        """
        Called when a mission completes. Reads the emergent topic candidates
        accumulated during distillation and returns the ones that should become
        follow-on missions — deduplicating against existing missions.

        Returns list of dicts: {"concept": str, "atom_count": int}
        Caller (system.py) is responsible for creating the actual missions via learn().
        """
        try:
            snapshot = await self.adapter.get_latest_frontier_checkpoint(mission_id)
            if not snapshot:
                return []

            candidates = snapshot.get("emergent_topics", [])
            if not candidates:
                return []

            # Only auto-spawn the top 3 emergent topics to avoid runaway expansion
            above_threshold = [c for c in candidates if c["atom_count"] >= self._EMERGENT_THRESHOLD][:3]
            if not above_threshold:
                return []

            to_spawn = []
            for cand in above_threshold:
                concept = cand["concept"]
                try:
                    # Skip if a mission for this concept already exists
                    existing = await self.adapter.pg.fetch_many(
                        "mission.research_missions",
                        where={"title": concept},
                        limit=1,
                    )
                    if existing:
                        logger.info("[Distillery] Skipping emergent spawn for '%s' — mission exists", concept)
                        continue
                    to_spawn.append({"concept": concept, "atom_count": cand["atom_count"]})
                except Exception as e:
                    logger.warning("[Distillery] Dedup check failed for '%s': %s", concept, e)

            return to_spawn

        except Exception as e:
            logger.warning("[Distillery] get_emergent_topics_to_spawn failed: %s", e)
            return []

    async def resolve_contradictions(self, mission_id: str):
        """The Courtroom: Actively resolves open contradictions."""
        if self.consolidation_engine:
            return await self.consolidation_engine.resolve_contradictions(mission_id)
        return {"mission_id": mission_id, "candidates": 0, "verified_contradictions": 0, "resolved": 0}

    # ── CMK Integration ──

    async def _cmk_ingest_atom(self, atom, mission_id: str):
        """
        Ingest an atom into the Cognitive Memory Kernel.

        1. Activate in working memory (activation boost)
        2. Create belief node if high-confidence
        3. Link to concept anchors based on atom type
        4. Cross-link with existing beliefs (supports/contradicts)
        """
        from src.core.memory.cmk.types import CMKAtom

        # Create CMK atom
        cmk_atom = CMKAtom(
            id=atom.atom_id,
            content=atom.statement or atom.title or "",
            atom_type=atom.atom_type or "claim",
            reliability=atom.confidence or 0.5,
            specificity=min(1.0, len(atom.statement or "") / 200.0),
            centrality=atom.importance or 0.5,
            source_id=atom.metadata.get("source_id", "") if atom.metadata else "",
            mission_id=mission_id,
            topic_id=atom.topic_id or mission_id,
            confidence=atom.confidence or 0.5,
        )

        # 1. Activate in working memory
        await self.cmk_runtime.ingest([cmk_atom])
        await self.cmk_runtime.activate_atom(atom.atom_id, amount=0.5)

        # 2. Create belief node if high-confidence
        if atom.confidence and atom.confidence >= 0.7:
            belief_id = self.cmk_runtime.create_belief_node(
                claim=atom.statement or atom.title or "",
                domain=atom.atom_type or "general",
                authority_score=atom.confidence,
                canonical_id=atom.atom_id,
            )

            # 3. Link to concept anchors based on atom type
            concept_map = {
                "mechanism": ["feedback_loop", "optimization"],
                "definition": ["hierarchical_organization"],
                "principle": ["energy_minimization", "tradeoff"],
                "constraint": ["tradeoff", "signal_vs_noise"],
                "process": ["adaptation", "emergence"],
                "claim": ["signal_vs_noise"],
            }
            concepts = concept_map.get(atom.atom_type, ["signal_vs_noise"])
            self.cmk_runtime.link_belief_to_concepts(
                belief_id, concepts, atom.atom_type or "general"
            )

    async def _belief_graph_cross_link(self, mission_id: str):
        """
        Cross-link new beliefs with existing ones.

        For each new belief in this mission:
        1. Find semantically similar existing beliefs
        2. Create SUPPORTS edge if aligned
        3. Create CONTRADICTS edge if opposed
        4. Update confidence based on evidence weight
        """
        if not self.cmk_runtime or not self.cmk_runtime.belief_graph:
            return

        bg = self.cmk_runtime.belief_graph

        # Get new beliefs from this mission
        new_beliefs = bg.get_beliefs_by_mission(mission_id) if hasattr(bg, 'get_beliefs_by_mission') else []
        if not new_beliefs:
            return

        cross_links = 0
        for belief in new_beliefs:
            # Find similar beliefs via embedding similarity
            similar = bg.find_similar_beliefs(belief.id, limit=5, threshold=0.7) if hasattr(bg, 'find_similar_beliefs') else []

            for other_id, sim_score in similar:
                if other_id == belief.id:
                    continue

                other = bg.get_belief(other_id)
                if not other:
                    continue

                # Determine relationship type
                if sim_score > 0.85:
                    # High similarity → likely supports
                    if not bg.has_edge(belief.id, other_id, "supports"):
                        bg.create_edge(
                            from_node=belief.id, to_node=other_id,
                            relation_type="supports",
                            strength=sim_score,
                            reason=f"Semantic similarity {sim_score:.2f}"
                        )
                        # Boost confidence — corroborating evidence
                        belief.authority_score = min(1.0, belief.authority_score + 0.05 * sim_score)
                        other.authority_score = min(1.0, other.authority_score + 0.05 * sim_score)
                        cross_links += 1

                elif sim_score > 0.7:
                    # Moderate similarity → check for contradiction
                    is_contradiction = await self._detect_contradiction(belief, other)
                    if is_contradiction:
                        if not bg.has_edge(belief.id, other_id, "contradicts"):
                            bg.create_edge(
                                from_node=belief.id, to_node=other_id,
                                relation_type="contradicts",
                                strength=sim_score,
                                reason=f"Contradictory claims at similarity {sim_score:.2f}"
                            )
                            # Reduce confidence — contradiction pressure
                            belief.contradiction_pressure = getattr(belief, 'contradiction_pressure', 0.0) + 0.1
                            other.contradiction_pressure = getattr(other, 'contradiction_pressure', 0.0) + 0.1
                            cross_links += 1

        if cross_links > 0:
            # Persist updated belief graph
            bg.persist() if hasattr(bg, 'persist') else None
            logger.info(f"[BeliefGraph] Cross-linked {cross_links} edges for mission {mission_id[:8]}")

    async def _detect_contradiction(self, belief_a, belief_b) -> bool:
        """
        Detect if two beliefs contradict each other.

        Uses LLM-based contradiction detection for accuracy.
        Returns True if beliefs are contradictory.
        """
        try:
            prompt = (
                f"Do these two claims contradict each other? Answer ONLY with 'yes' or 'no'.\n\n"
                f"Claim A: {belief_a.claim}\n"
                f"Claim B: {belief_b.claim}\n"
            )
            answer = await self.ollama.complete(
                TaskType.CONTRADICTION_DETECTION,
                prompt,
                max_tokens=10,
            )
            return (answer or "").strip().lower().startswith("yes")
        except Exception:
            # Fallback: if LLM unavailable, assume no contradiction
            return False

    async def _self_correct_beliefs(self, mission_id: str):
        """
        Self-correcting belief loop.

        After new evidence arrives from a mission:
        1. Find beliefs affected by new atoms
        2. Update confidence based on supporting/contradicting evidence
        3. Deprecate beliefs with confidence below threshold
        NEVER delete beliefs — only reduce confidence.
        """
        if not self.cmk_runtime or not self.cmk_runtime.belief_graph:
            return

        bg = self.cmk_runtime.belief_graph
        all_beliefs = bg.get_all_beliefs() if hasattr(bg, 'get_all_beliefs') else []

        updated = 0
        for belief in all_beliefs:
            # Get supporting edges
            support_weight = 0.0
            contradict_weight = 0.0

            for edge in bg.get_edges_for_node(belief.id):
                if edge.relation_type == "supports":
                    support_weight += edge.strength
                elif edge.relation_type == "contradicts":
                    contradict_weight += edge.strength

            # Recalculate confidence
            total_evidence = support_weight + contradict_weight
            if total_evidence > 0:
                new_confidence = (support_weight - contradict_weight * 0.5) / total_evidence
                new_confidence = max(0.0, min(1.0, new_confidence))

                # Smooth update — don't jump too fast
                old_confidence = belief.authority_score
                belief.authority_score = old_confidence * 0.7 + new_confidence * 0.3
                updated += 1

                # Deprecate if confidence too low (but never delete)
                if belief.authority_score < 0.2:
                    belief.stability_score = max(0.0, belief.stability_score - 0.1)

        if updated > 0:
            bg.persist() if hasattr(bg, 'persist') else None
            logger.info(f"[BeliefCorrection] Updated {updated} beliefs for mission {mission_id[:8]}")

    async def query_with_reasoning(self, query: str, mission_id: str = None) -> dict:
        """
        Cross-document reasoning engine.

        1. Retrieve relevant beliefs via embedding search
        2. Expand via graph traversal (depth=2)
        3. Aggregate supporting/contradicting evidence
        4. Generate grounded answer with conflict awareness

        Returns: {answer, supporting_beliefs, contradicting_beliefs, confidence}
        """
        if not self.cmk_runtime:
            return {"answer": "CMK not available", "supporting": [], "contradicting": [], "confidence": 0.0}

        # Step 1: Retrieve relevant beliefs
        relevant = await self.cmk_runtime.query(query)

        # Step 2: Expand via graph
        expanded = set()
        if self.cmk_runtime.belief_graph:
            for belief_id in [b.get("id") for b in relevant.get("beliefs", [])]:
                expanded.add(belief_id)
                neighbors = self.cmk_runtime.belief_graph.get_neighbors(belief_id) if hasattr(self.cmk_runtime.belief_graph, 'get_neighbors') else []
                expanded.update(neighbors)

        # Step 3: Aggregate evidence
        supporting = []
        contradicting = []
        for belief_id in expanded:
            belief = self.cmk_runtime.belief_graph.get_belief(belief_id) if hasattr(self.cmk_runtime.belief_graph, 'get_belief') else None
            if belief and belief.authority_score > 0.5:
                if getattr(belief, 'contradiction_pressure', 0.0) < 0.3:
                    supporting.append({"claim": belief.claim, "confidence": belief.authority_score})
                else:
                    contradicting.append({"claim": belief.claim, "confidence": belief.authority_score})

        # Step 4: Generate answer
        context_text = "\n".join(f"- {b['claim']} (confidence: {b['confidence']:.2f})" for b in supporting)
        conflict_text = "\n".join(f"- {b['claim']} (confidence: {b['confidence']:.2f})" for b in contradicting)

        prompt = (
            f"Based on the following evidence, answer the query.\n\n"
            f"Query: {query}\n\n"
            f"Supporting evidence:\n{context_text or 'None'}\n\n"
        )
        if conflict_text:
            prompt += f"Contradicting evidence (acknowledge these):\n{conflict_text}\n\n"

        prompt += "Provide a concise answer that acknowledges any conflicts in the evidence."

        try:
            response = await self.ollama.complete(
                TaskType.CHAT,
                prompt,
                max_tokens=500,
            )
        except Exception:
            response = "Unable to generate response."

        return {
            "answer": response,
            "supporting_beliefs": supporting,
            "contradicting_beliefs": contradicting,
            "confidence": max([b["confidence"] for b in supporting], default=0.0),
        }

    async def consolidate_atoms(self, mission_id: str):
        """The Forgetting Curve: Merges redundant atoms into Golden Atoms."""
        if self.consolidation_engine:
            return await self.consolidation_engine.consolidate_atoms(mission_id)
        return {"mission_id": mission_id, "total_atoms": 0, "clusters": 0, "golden_atoms_created": 0, "atoms_obsoleted": 0}
