"""
condensation/pipeline.py — Differential Knowledge Distillery

Architectural Shift:
- Coverage before compression: Wait for document clusters before mining.
- Diversity before certainty: Explicitly extract unique differentials between similar sources.
- Contradiction before consensus: Conflict is preserved as a first-class memory object.
"""

import asyncio
import traceback
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
    def __init__(self, ollama: OllamaClient, memory, budget: BudgetMonitor, adapter=None):
        self.ollama = ollama
        self.memory = memory  # V2 removed; expected None in V3
        self.budget = budget
        self.adapter = adapter
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
            except Exception:
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
            # We process a small batch sequentially to ensure high quality with 8B models
            sources = await self.adapter.pg.fetch_many(
                "corpus.sources",
                where={"mission_id": mission_id, "status": "fetched"},
                limit=5
            )
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
                await self._process_sources(sources, mission_id, mission_row, run_id)

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

    async def _process_sources(self, sources, mission_id, mission_row, run_id):
        """Process a batch of sources through the distillation pipeline."""
        import uuid
        from src.research.domain_schema import KnowledgeAtom, AtomLineage

        self._total_atoms = 0

        for s in sources:
            # Guard: ensure source row is actually a dict
            if not isinstance(s, dict):
                logger.error(f"[Distillery] Skipping malformed source row: type={type(s).__name__}, value={repr(s)[:200]}")
                continue

            source_id = s.get("source_id", "unknown")

            # Idempotency check: skip if already extracted
            content_hash = s.get("content_hash")
            if await self._check_source_already_extracted(source_id, content_hash):
                continue

            # Get the content
            text_ref = s.get("canonical_text_ref")
            if not text_ref:
                await transition_source_status(self.adapter, source_id, "error", current_status="fetched")
                continue

            ref = await self.adapter.get_text_ref(text_ref)
            if not ref or not ref.get("inline_text"):
                await transition_source_status(self.adapter, source_id, "error", current_status="fetched")
                continue

            content = ref["inline_text"]

            # Fetch chunks for this source (needed for evidence binding)
            chunks = await self.adapter.list_chunks_for_source(source_id)
            if not chunks:
                logger.error(f"[Distillery] No chunks found for source {source_id}, cannot bind evidence")
                await transition_source_status(self.adapter, source_id, "error", current_status="fetched")
                continue

            # Build quick access to chunk texts
            chunk_infos = [(chunk['chunk_id'], chunk.get('inline_text', '')) for chunk in chunks]

            console.print(f"[dim][Distillery] Smelting: {s.get('url', source_id)[:60]}...[/dim]")

            try:
                # Diagnostic: log types at entry point for debugging smelting failures
                if not isinstance(mission_row, (dict, type(None))):
                    logger.error(f"[Distillery] mission_row has unexpected type: {type(mission_row).__name__} = {repr(mission_row)[:200]}")
                atoms_data = await extract_technical_atoms(
                    self.ollama, content, mission_id,
                    source_url=s.get('url', '')  # Pass source URL for quality gating
                )

                # 3. Storage & Indexing
                atoms_this_source = 0

                # EXTRACT-05: Compute source type for confidence scoring
                content_for_classification = ref.get("inline_text", "")[:4000]
                source_type = classify_source_quality(s.get('url', ''), content_for_classification)

                for atom_dict in atoms_data:
                    # Guard: ensure atom_dict is actually a dict before calling .get()
                    if not isinstance(atom_dict, dict):
                        logger.warning(f"[Distillery] Skipping non-dict atom: {type(atom_dict).__name__} = {repr(atom_dict)[:100]}")
                        continue

                    # Additional guard: ensure text field exists and is a string
                    normalized = normalize_atom_schema(atom_dict)
                    content_value = normalized.get('text', '')
                    if not content_value or not isinstance(content_value, str):
                        logger.warning(f"[Distillery] Skipping atom with invalid content field: {type(content_value).__name__}")
                        continue

                    atom_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{mission_id}:{source_id}:{content_value[:200]}"))
                    profile_id = mission_row.get("domain_profile_id") if isinstance(mission_row, dict) else f"profile_{mission_id[:8]}"

                    atom = KnowledgeAtom(
                        atom_id=atom_id,
                        topic_id=mission_row.get("topic_id") if isinstance(mission_row, dict) else mission_id,
                        domain_profile_id=profile_id,
                        atom_type=atom_dict.get('atom_type', atom_dict.get('type', 'claim')),
                        title=content_value[:50] + "...",
                        statement=content_value,
                        summary=content_value,
                        confidence=compute_confidence(normalized, source_type, atoms_data),
                        importance=0.8 if atom_dict.get('atom_type', atom_dict.get('type')) == 'contradiction' else 0.5,
                        lineage=AtomLineage(
                            mission_id=mission_id,
                            extraction_mode="atomic_distillation"
                        ),
                        metadata={"type": atom_dict.get('atom_type', atom_dict.get('type')), "source_id": source_id}
                    )

                    # Determine appropriate chunk(s) for this atom
                    atom_content = normalized.get('text', '').strip()
                    matched_chunk_ids = []
                    if atom_content:
                        for chunk_id, chunk_text in chunk_infos:
                            if atom_content in chunk_text or chunk_text in atom_content:
                                matched_chunk_ids.append(chunk_id)

                        # If no direct match, fallback to first chunk
                        if not matched_chunk_ids:
                            matched_chunk_ids = [chunks[0]['chunk_id']]
                    else:
                        matched_chunk_ids = [chunks[0]['chunk_id']]

                    # Create evidence rows for all matched chunks
                    evidence_rows = [
                        {
                            "source_id": source_id,
                            "chunk_id": cid,
                            "evidence_strength": 0.9,
                            "supports_statement": True
                        }
                        for cid in matched_chunk_ids
                    ]

                    # Store atom and evidence atomically via V3 Adapter
                    atom_row = atom.to_pg_row()
                    await self.adapter.store_atom_with_evidence(atom_row, evidence_rows)

                    self._total_atoms += 1
                    atoms_this_source += 1

                # 5. Mark individual source as condensed only if atoms were stored
                if atoms_this_source > 0:
                    await transition_source_status(
                        self.adapter, source_id, "condensed", current_status="extracted"
                    )
                    # Notify budget that a source has been condensed
                    await self.budget.record_source_condensed(mission_id)
                elif len(atoms_data) > 0:
                    # Atoms were extracted but all failed quality gates → filtered_out
                    await transition_source_status(
                        self.adapter, source_id, "filtered_out", current_status="extracted"
                    )
                    await self.adapter.pg.update_row(
                        "corpus.sources",
                        "source_id",
                        {
                            "source_id": source_id,
                            "filter_metadata": {
                                "reason": "low_quality",
                                "raw_atoms_count": len(atoms_data),
                                "passed_atoms_count": 0,
                                "details": "All extracted atoms failed quality gates (too short, low score, duplicate, or semantic drift)",
                            },
                        }
                    )
                else:
                    # Zero atoms extracted — extraction failed or content was garbage
                    await transition_source_status(
                        self.adapter, source_id, "rejected", current_status="extracted"
                    )
                    await self.adapter.pg.update_row(
                        "corpus.sources",
                        "source_id",
                        {
                            "source_id": source_id,
                            "filter_metadata": {
                                "reason": "no_atoms",
                                "raw_atoms_count": 0,
                            },
                        }
                    )
            except ExtractionError as e:
                # LLM call failed — mark source as error, write DLQ
                console.print(f"[bold red][Distillery] Extraction failed for {source_id}[/bold red]")
                await transition_source_status(
                    self.adapter, source_id, "error", current_status="fetched"
                )
                await _write_dead_letter(
                    self.adapter, source_id, "extraction", "ExtractionError", str(e),
                    worker_id="pipeline:condensation",
                    payload={"mission_id": mission_id, "url": s.get("url", ""), "content_hash": s.get("content_hash")},
                )
            except Exception as e:
                tb = traceback.format_exc()
                console.print(f"[bold red][Distillery] Smelting failed for {source_id}: {e}[/bold red]")
                console.print(f"[dim]{tb}[/dim]")
                logger.error(f"[Distillery] Smelting failed for {source_id}: {e}\n{tb}")
                await transition_source_status(
                    self.adapter, source_id, "error", current_status="fetched"
                )
                await _write_dead_letter(
                    self.adapter, source_id, "condensation", type(e).__name__, str(e),
                    worker_id="pipeline:condensation",
                    payload={"mission_id": mission_id, "url": s.get("url", ""), "content_hash": s.get("content_hash")},
                )

        console.print(f"[bold green][Refinery][/bold green] Batch complete. Smelted technical atoms: [white]{self._total_atoms}[/white]")

        # 6. Entity Discovery — extract named entities from all atoms for Frontier expansion
        # These entities become new query targets for the Frontier's discovery loop
        if self.adapter and self._total_atoms > 0:
            # Fetch recently condensed atoms for entity extraction
            condensed_atoms = await self.adapter.get_mission_atoms(mission_id, limit=100)
            if condensed_atoms:
                # Use semantic extraction with embedding-assisted clustering
                entities = await _extract_entities_semantic(condensed_atoms, self.ollama)
                if entities:
                    console.print(f"[bold cyan][Discovery][/bold cyan] Extracted {len(entities)} entities for Frontier expansion: {entities[:15]}")
                    # Store entities as discovery targets
                    if hasattr(self.adapter, 'store_discovery_entities'):
                        await self.adapter.store_discovery_entities(mission_id, entities)

        # 7. Higher-Order Refinement
        if self._total_atoms > 0:
            if priority in [CondensationPriority.HIGH, CondensationPriority.CRITICAL]:
                await self.resolve_contradictions(mission_id)

        # 7. Budget Feedback
        await self.budget.record_condensation_result(
            mission_id=mission_id,
            raw_bytes_freed=sum(len(str(s).encode()) for s in sources), # Approximated
            condensed_bytes_added=self._total_atoms * 500 # Estimate
        )

    async def _cluster_sources(self, sources: List[Dict]) -> List[ExtractionCluster]:
        """Group sources by concept proximity."""
        # Simple clustering for the scaffold
        clusters = [ExtractionCluster(mission_id=sources[0].get('mission_id', sources[0].get('topic_id', '')), concept="batch_general", sources=sources)]
        return clusters

    async def resolve_contradictions(self, mission_id: str):
        """The Courtroom: Actively resolves open contradictions."""
        if self.consolidation_engine:
            return await self.consolidation_engine.resolve_contradictions(mission_id)
        return {"mission_id": mission_id, "candidates": 0, "verified_contradictions": 0, "resolved": 0}

    async def consolidate_atoms(self, mission_id: str):
        """The Forgetting Curve: Merges redundant atoms into Golden Atoms."""
        if self.consolidation_engine:
            return await self.consolidation_engine.consolidate_atoms(mission_id)
        return {"mission_id": mission_id, "total_atoms": 0, "clusters": 0, "golden_atoms_created": 0, "atoms_obsoleted": 0}
