"""
core/system.py — Integrated Sheppard V2 System Orchestrator

Wires together all legacy and V2 subsystems:
  - Acquisition (Firecrawl crawler + budget monitor)
  - Condensation (multi-level distillation pipeline)
  - Memory (ChromaDB + Postgres V2 Schema)
  - Reasoning (hybrid multi-stage retriever)
  - LLM (Ollama client + model router)
"""

import asyncio
import json
import logging
import os
import re
from typing import AsyncGenerator, List, Optional, Dict, Any, Tuple, Set

# V2 Acquisitions
from src.research.acquisition.budget import BudgetMonitor, BudgetConfig, CondensationPriority
from src.research.acquisition.crawler import FirecrawlLocalClient, CrawlerConfig
from src.research.acquisition.frontier import AdaptiveFrontier
from src.research.acquisition.ingestion_control import IngestionControl
from src.utils.console import console
from src.utils.status_pubsub import publish_status
# V2 Condensation
from src.research.condensation.pipeline import DistillationPipeline
# V2 Reasoning (deprecated — not used in V3)
# from src.research.reasoning.retriever import HybridRetriever, RetrievalQuery
from src.research.reasoning.retriever import RetrievalQuery  # Shared types only
from src.research.reasoning.v3_retriever import V3Retriever
from src.research.reasoning.assembler import EvidenceAssembler
from src.research.reasoning.synthesis_service import SynthesisService
# LLM & Memory
from src.llm.client import OllamaClient
from src.llm.model_router import ModelRouter, TaskType
# NOTE: MemoryManager is deprecated; V3 uses SheppardStorageAdapter exclusively.
from src.research.system import ResearchSystem

# V3 Storage
import aiohttp
import asyncpg
import redis.asyncio as redis
import chromadb
from src.memory.storage_adapter import SheppardStorageAdapter
from src.memory.adapters.postgres import PostgresStoreImpl
from src.memory.adapters.redis import RedisStoresImpl
from src.memory.adapters.chroma import ChromaSemanticStoreImpl

from src.config.settings import settings

logger = logging.getLogger(__name__)

class SystemManager:
    """
    Unified system manager for Sheppard.
    Orchestrates legacy research tasks and V2 accretive learning missions.
    """

    def __init__(self):
        self.adapter: Optional[SheppardStorageAdapter] = None
        self.ollama: Optional[OllamaClient] = None
        self.model_router = ModelRouter()
        self.budget: Optional[BudgetMonitor] = None
        self.crawler: Optional[FirecrawlLocalClient] = None
        self.condenser: Optional[DistillationPipeline] = None
        self.retriever: Optional[V3Retriever] = None
        self.synthesis_service: Optional[SynthesisService] = None
        self.analysis_service = None  # AnalysisService — reasoning layer
        self.research_system: Optional[ResearchSystem] = None
        # CMK (Cognitive Memory Kernel)
        self.cmk_runtime = None
        # Ingestion Control (multi-tier digestion)
        self.ingestion_control: Optional[IngestionControl] = None
        self._ingestion_workers: List[asyncio.Task] = []
        # V2 MemoryManager removed — canonical truth is V3 adapter only
        self.memory = None

        self._crawl_tasks: Dict[str, asyncio.Task] = {}
        self.active_frontiers: Dict[str, AdaptiveFrontier] = {}
        self._monitor_task: Optional[asyncio.Task] = None
        self._vampire_tasks: List[asyncio.Task] = []
        self._condensation_tasks: Set[asyncio.Task] = set()
        self._initialized = False

    async def initialize(self) -> Tuple[bool, Optional[str]]:
        """Boot all subsystems. Returns (success, error_message)."""
        if self._initialized:
            return True, None

        try:
            logger.info("[System] Initializing Sheppard Infrastructure...")

            # 0a. Ensure external research services are running (SearXNG, Playwright, Firecrawl)
            from src.research.service_watchdog import ensure_research_stack
            await ensure_research_stack()

            # 0. Boot V3 Triad Adapters
            from src.config.database import DatabaseConfig
            pg_dsn = DatabaseConfig.DB_URLS.get("sheppard_v3")
            
            self.pg_pool = await asyncpg.create_pool(
                pg_dsn,
                min_size=2, max_size=10
            )
            self.redis_client = redis.Redis.from_url("redis://localhost:6379", decode_responses=False)
            self.chroma_client = chromadb.PersistentClient(path=settings.CHROMADB_PERSIST_DIRECTORY)

            pg_store = PostgresStoreImpl(self.pg_pool)
            redis_store = RedisStoresImpl(self.redis_client)
            chroma_store = ChromaSemanticStoreImpl(self.chroma_client)

            self.adapter = SheppardStorageAdapter(
                pg=pg_store,
                redis_runtime=redis_store,
                redis_cache=redis_store,
                redis_queue=redis_store,
                chroma=chroma_store
            )

            # 1. LLM Client
            self.ollama = OllamaClient(model_router=self.model_router)
            await self.ollama.initialize()

            # 2. Budget monitor
            self.budget = BudgetMonitor(
                config=BudgetConfig(),
                condensation_callback=self._condensation_callback,
            )

            # 3. CMK — Cognitive Memory Kernel (optional, falls back gracefully)
            try:
                from src.core.memory.cmk.runtime import CMKRuntime
                from src.core.memory.cmk.config import CMKConfig

                cmk_config = CMKConfig.from_env()
                cmk_config.embedding.host = settings.OLLAMA_API_HOST
                cmk_config.embedding.model = "nomic-embed-text"

                self.cmk_runtime = CMKRuntime(config=cmk_config)
                logger.info("[System] CMK Runtime initialized")
            except Exception as cmk_err:
                logger.debug(f"[System] CMK Runtime not available: {cmk_err}")
                self.cmk_runtime = None

            # 3.5 Ingestion Control — multi-tier digestion pipeline
            async_redis = None
            try:
                from src.core.memory.cmk.runtime import CMKRuntime
                from src.core.memory.cmk.config import CMKConfig

                # Create async Redis client for ingestion control
                async_redis = redis.from_url("redis://localhost:6379", decode_responses=True)

                self.ingestion_control = IngestionControl(
                    redis=async_redis,
                    cmk_runtime=self.cmk_runtime,
                    chroma_client=self.chroma_client,
                )

                # Create crawl source queue (crawlers push here)
                self._crawl_source = asyncio.Queue(maxsize=5000)

                # Start workers with hooks into existing pipeline
                self._ingestion_workers = self.ingestion_control.start_workers(
                    crawl_source=self._crawl_source,
                    distill_fn=self._distill_doc,
                    fetch_doc_fn=self._fetch_doc,
                    store_atoms_fn=self._store_atoms,
                )
                logger.info("[System] Ingestion Control workers started")
            except Exception as ic_err:
                logger.debug(f"[System] Ingestion Control not available: {ic_err}")
                self.ingestion_control = None
                self._crawl_source = asyncio.Queue(maxsize=5000)

            # 4. Condensation pipeline (V3-only, memory=None)
            self.condenser = DistillationPipeline(
                ollama=self.ollama,
                memory=None,  # MemoryManager removed
                budget=self.budget,
                adapter=self.adapter,
                cmk_runtime=self.cmk_runtime,
                ingest_redis=async_redis,
            )

            # 4.1 CMK Chat Bridge — cross-document reasoning layer
            try:
                from src.core.memory.cmk.chat_bridge import CMKChatBridge

                self.chat_bridge = CMKChatBridge(
                    redis_client=async_redis,
                    pg_pool=self.adapter.pg,
                    ollama_host=settings.OLLAMA_API_HOST,
                    distillation_pipeline=self.condenser,
                )
                await self.chat_bridge.initialize()
                logger.info("[System] CMK Chat Bridge initialized with cross-document reasoning")
            except Exception as bridge_err:
                logger.debug(f"[System] CMK Chat Bridge not available: {bridge_err}")
                self.chat_bridge = None

            # 4.5 Auto-apply pending migrations (never ask user to run SQL manually)
            await self._apply_pending_migrations()

            # 5. Crawler
            self.crawler = FirecrawlLocalClient(
                config=CrawlerConfig(),
                on_bytes_crawled=self.budget.record_bytes,
                academic_only=True,
            )
            await self.crawler.initialize()

            # 6. Retriever (V3 only)
            self.retriever = V3Retriever(
                adapter=self.adapter,
                cmk_runtime=self.cmk_runtime,
            )

            # 7. Synthesis pipeline (V3 truth contract)
            assembler = EvidenceAssembler(
                ollama=self.ollama,
                memory=None,
                retriever=self.retriever,
                adapter=self.adapter
            )
            self.synthesis_service = SynthesisService(
                ollama=self.ollama,
                memory=None,
                assembler=assembler,
                adapter=self.adapter
            )

            # 7b. Analysis service (reasoning layer — Analyst + Adversarial Critic)
            from src.research.reasoning.analysis_service import AnalysisService
            self.analysis_service = AnalysisService(
                ollama=self.ollama,
                retriever=self.retriever,
                assembler=assembler,
            )

            # 7. Research system (V3 deep research)
            self.research_system = ResearchSystem(
                chroma_store=self.adapter.chroma,
                ollama_client=self.ollama,
                memory_manager=None  # V2 memory deprecated; intermediate storage disabled
            )
            await self.research_system.initialize()

            # 8. Start background tasks
            self._monitor_task = asyncio.create_task(self.budget.run_monitor_loop())

            # FIRE-04: Start DLQ consumer
            from src.core.dlq_consumer import DLQConsumer
            self.dlq_consumer = DLQConsumer(self.adapter.pg, self.adapter.redis_runtime)
            self._dlq_task = asyncio.create_task(self.dlq_consumer.run())
            
            # 8. Unleash Local Vampires
            # INFRA-01: Configurable vampire count with clamped range
            num_vampires = int(os.environ.get("NUM_VAMPIRES", "8"))
            num_vampires = max(1, min(num_vampires, 32))  # Clamp 1-32
            logger.info(f"[System] Launching {num_vampires} vampire workers")
            for i in range(num_vampires):
                self._vampire_tasks.append(asyncio.create_task(self._vampire_loop(i)))

            self._initialized = True
            logger.info("[System] Sheppard V2 ready")
            return True, None

        except Exception as e:
            logger.error(f"[System] Initialization failed: {e}", exc_info=True)
            return False, str(e)

    async def learn(
        self,
        topic_name: str,
        query: str,
        ceiling_gb: float = 5.0,
        academic_only: bool = False,
    ) -> str:
        """Starts a background accretive learning mission."""
        self._check_initialized()
        import uuid
        from src.research.domain_schema import ResearchMission, DomainProfile, SourcePreferences

        # V3 identity model: mission_id is canonical (topic_id eliminated)
        mission_id = str(uuid.uuid4())

        # 1. Create Domain Profile
        profile_id = f"profile_{mission_id[:8]}"
        profile = DomainProfile(
            profile_id=profile_id,
            name=f"Profile for {topic_name}",
            description=query,
            domain_type="mixed",
            source_preferences=SourcePreferences(
                preferred_classes=["official_docs", "academic_paper"] if academic_only else []
            )
        )
        await self.adapter.upsert_domain_profile(profile.to_pg_row())

        # 2. Create Mission
        mission = ResearchMission(
            mission_id=mission_id,
            topic_id=mission_id,  # For legacy schema compatibility; in V3, topic_id == mission_id
            domain_profile_id=profile.profile_id,
            title=topic_name,
            objective=query,
            budget_bytes=int(ceiling_gb * 1024**3)
        )
        await self.adapter.create_mission(mission.to_pg_row())

        # 3. Register with Budget Monitor
        self.budget.register_topic(
            mission_id=mission_id,
            topic_name=topic_name,
            ceiling_gb=ceiling_gb,
        )

        self.crawler.academic_only = academic_only

        task = asyncio.create_task(self._crawl_and_store(mission_id, topic_name, query))
        self._crawl_tasks[mission_id] = task

        logger.info(f"[System] Learning mission '{topic_name}' started (Mission ID: {mission_id})")
        return mission_id

    async def query(
        self,
        text: str,
        project_filter: Optional[str] = None,
        topic_filter: Optional[str] = None,
        max_results: int = 12
    ) -> str:
        """Run hybrid retrieval with cross-document reasoning."""
        self._check_initialized()

        # Try CMK reasoning path first (belief graph expansion)
        if self.chat_bridge:
            try:
                result = await self.chat_bridge.query_with_cmk(
                    user_query=text,
                    topic_filter=topic_filter,
                    mission_filter=project_filter,
                    use_reasoning=True,
                )
                pack = result.get("evidence_pack")
                if pack and not pack.is_empty:
                    from src.core.memory.cmk.prompt_contract import _format_evidence_context
                    return _format_evidence_context(pack)
            except Exception as e:
                logger.debug(f"[System] CMK query failed, falling back to retriever: {e}")

        # Fallback: direct retriever
        q = RetrievalQuery(
            text=text,
            project_filter=project_filter,
            topic_filter=topic_filter,
            max_results=max_results
        )
        ctx = await self.retriever.retrieve(q)
        return self.retriever.build_context_block(ctx, project_name=project_filter)

    async def analyze(
        self,
        problem_statement: str,
        mission_filter: Optional[str] = None,
        topic_filter: Optional[str] = None,
    ):
        """
        Applied reasoning pipeline: frame the problem → retrieve evidence →
        Analyst forms a position → Adversarial Critic challenges it →
        return AnalysisReport with formatted output.

        Unlike query() (which returns facts) and generate_report() (which
        writes a library document), analyze() reasons toward a recommendation
        and stress-tests it. Both layers are grounded in the same atom store.
        """
        self._check_initialized()
        if not self.analysis_service:
            raise RuntimeError("AnalysisService not initialized")
        return await self.analysis_service.analyze(
            problem_statement=problem_statement,
            mission_filter=mission_filter,
            topic_filter=topic_filter,
        )

    async def analyze_stream(
        self,
        problem_statement: str,
        mission_filter: Optional[str] = None,
        topic_filter: Optional[str] = None,
    ):
        """Streaming version of analyze() for TUI display."""
        self._check_initialized()
        if not self.analysis_service:
            raise RuntimeError("AnalysisService not initialized")
        async for chunk in self.analysis_service.analyze_stream(
            problem_statement=problem_statement,
            mission_filter=mission_filter,
            topic_filter=topic_filter,
        ):
            yield chunk

    async def chat(
        self,
        messages: List[dict],
        project_context: Optional[str] = None,
    ) -> AsyncGenerator[str, None]:
        """Conversational turn with self-extending response loop."""
        self._check_initialized()

        user_msg = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")

        # ── PASS 1: Initial response ──
        context_block = ""
        if user_msg:
            context_block = await self.query(text=user_msg, project_filter=project_context, max_results=30)

        system_prompt = self._build_system_prompt(context_block, project_context)

        # Buffer the initial response for reflection
        initial_response = ""
        async for token in self.ollama.chat_stream(
            model=self.model_router.get_model_name(TaskType.CHAT),
            messages=messages,
            system_prompt=system_prompt,
        ):
            initial_response += token
            yield token

        # ── PASS 2: Reflection — should we expand? ──
        expansion_budget = 2  # max additional passes
        for pass_num in range(expansion_budget):
            reflection = await self._reflect_on_response(
                initial_response, user_msg, context_block
            )
            
            if not reflection.get("expand"):
                break  # Response is complete enough

            # Retrieve new atoms for the missing angles
            missing_topics = reflection.get("topics", [])
            if not missing_topics:
                break

            # Get fresh context for the missing angles
            expansion_context = await self.query(
                text=" ".join(missing_topics[:3]),  # Top 3 missing topics
                project_filter=project_context,
                max_results=15  # More retrieval for expansion
            )

            if not expansion_context.strip():
                break  # No new knowledge found

            # Generate continuation
            continuation_prompt = (
                "Continue the previous response naturally. "
                "Do NOT repeat any concepts already explained. "
                "Do NOT use phrases like 'additionally', 'expanding on this', 'more information'. "
                "Just continue as if you're naturally elaborating. "
                "Only add genuinely useful new insights.\n\n"
                f"--- NEW CONTEXT ---\n{expansion_context}\n--- END CONTEXT ---\n"
            )

            continuation_messages = [
                {"role": "system", "content": continuation_prompt},
                {"role": "assistant", "content": initial_response},
                {"role": "user", "content": f"What else is important about {user_msg}?"},
            ]

            continuation = ""
            async for token in self.ollama.chat_stream(
                model=self.model_router.get_model_name(TaskType.CHAT),
                messages=continuation_messages,
                system_prompt="Continue the explanation with new insights not already covered.",
            ):
                continuation += token
                yield token

            initial_response += "\n\n" + continuation

    async def _reflect_on_response(
        self,
        response: str,
        user_input: str,
        context_used: str,
    ) -> dict:
        """Reflection pass: decide if the response is complete or needs expansion."""
        try:
            reflection_prompt = (
                f"Given this user question: \"{user_input}\"\n\n"
                f"And this answer that was just provided:\n\"\"\"{response}\"\"\"\n\n"
                f"Determine:\n"
                f"1. Is this answer shallow or incomplete? (Consider: does it skip important "
                f"subtopics, mechanisms, tradeoffs, or real-world implications?)\n"
                f"2. What important subtopics or angles were NOT covered?\n"
                f"3. What would an expert naturally explain next?\n\n"
                f"Return ONLY JSON, no other text:\n"
                f'{{"expand": true/false, "topics": ["angle1", "angle2", "angle3"]}}\n\n'
                f"Only expand if there are genuinely important missing angles. "
                f"Do not expand for minor details, examples, or edge cases. "
                f"If the answer already covers the core question well, expand=false."
            )

            # Use chat_stream and collect the full response for JSON parsing
            reflection_text = ""
            async for token in self.ollama.chat_stream(
                model=self.model_router.get_model_name(TaskType.CHAT),
                messages=[{"role": "user", "content": reflection_prompt}],
                system_prompt="You are a strict completeness judge. Return only JSON.",
                temperature=0.1,  # Low temp for deterministic JSON
            ):
                reflection_text += token

            # Parse JSON from the response
            # Handle potential markdown code blocks
            reflection_text = reflection_text.strip()
            if reflection_text.startswith("```"):
                # Strip markdown code blocks
                lines = reflection_text.split("\n")
                json_lines = []
                in_json = False
                for line in lines:
                    if line.strip().startswith("```"):
                        in_json = not in_json
                        continue
                    if in_json or not line.strip().startswith("```"):
                        json_lines.append(line)
                reflection_text = "\n".join(json_lines).strip()

            # Find JSON in the text
            start = reflection_text.find("{")
            end = reflection_text.rfind("}")
            if start >= 0 and end > start:
                json_str = reflection_text[start:end+1]
                return json.loads(json_str)

        except Exception as e:
            logger.warning(f"Reflection pass failed: {e}")

        return {"expand": False, "topics": []}

    def status(self) -> dict:
        """System health and mission status."""
        budget_statuses = self.budget.all_statuses() if self.budget else {}
        return {
            "initialized": self._initialized,
            "missions": {
                tid: {
                    "name": b.topic_name,
                    "usage": f"{b.usage_ratio:.1%}",
                    "raw_mb": f"{b.raw_bytes / 1024**2:.1f}",
                    "crawling": tid in self._crawl_tasks and not self._crawl_tasks[tid].done(),
                    "scout_queue_size": self.crawler.queue_size if tid in self._crawl_tasks else 0
                }
                for tid, b in budget_statuses.items()
            },
            "models": self.model_router.summary(),
        }

    async def cleanup(self) -> None:
        """Graceful shutdown of all tasks and network sessions."""
        if self._monitor_task:
            self._monitor_task.cancel()
        for task in self._crawl_tasks.values():
            if not task.done():
                task.cancel()

        for vt in self._vampire_tasks:
            if not vt.done(): vt.cancel()

        # Wait for any in-flight condensation to finish (up to 120s) before shutting down.
        # Condensation involves LLM calls that write knowledge atoms — cancelling mid-run
        # produces 0 atoms and wastes all the work done so far.
        if self._condensation_tasks:
            active = {t for t in self._condensation_tasks if not t.done()}
            if active:
                console.print(f"[yellow][Distillery][/yellow] Waiting for {len(active)} condensation task(s) to finish...")
                try:
                    await asyncio.wait_for(
                        asyncio.gather(*active, return_exceptions=True),
                        timeout=120.0
                    )
                    console.print(f"[green][Distillery][/green] Condensation tasks completed cleanly.")
                except asyncio.TimeoutError:
                    console.print(f"[yellow][Distillery][/yellow] Condensation timed out after 120s — cancelling.")
                    for t in active:
                        t.cancel()

        # Close network sessions
        if self.crawler:
            await self.crawler.cleanup()
        if self.ollama:
            await self.ollama.cleanup()

        # Close V3 Triad connections
        if getattr(self, 'pg_pool', None):
            await self.pg_pool.close()
        if getattr(self, 'redis_client', None):
            await self.redis_client.aclose()

        # Stop ingestion control workers
        if self.ingestion_control and self._ingestion_workers:
            await self.ingestion_control.stop_workers(self._ingestion_workers)
            self._ingestion_workers = []
            # Close async Redis client
            if hasattr(self.ingestion_control, 'redis') and self.ingestion_control.redis:
                try:
                    await self.ingestion_control.redis.aclose()
                except Exception:
                    pass

        # Stop DLQ consumer
        if getattr(self, '_dlq_task', None):
            self.dlq_consumer.stop()
            self._dlq_task.cancel()
            try:
                await self._dlq_task
            except asyncio.CancelledError:
                pass
            
        logger.info("[System] Sheppard shut down cleanly")

    # ──────────────────────────────────────────────────
    # Internal Helpers
    # ──────────────────────────────────────────────────

    async def _apply_pending_migrations(self):
        """Auto-apply database migrations at startup. Never ask user to run SQL manually."""
        import os
        migrations_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), '..', 'migrations')
        if not os.path.isdir(migrations_dir):
            return

        migration_files = sorted([
            f for f in os.listdir(migrations_dir)
            if f.endswith('.sql') and f.startswith('phase_')
        ])

        async with self.pg_pool.acquire() as conn:
            for migration_file in migration_files:
                # Check if this migration has already been applied
                # by looking for a key table/column it creates
                migration_name = migration_file.replace('.sql', '')
                check_query = self._migration_check_query(migration_name)
                if check_query:
                    try:
                        exists = await conn.fetchval(check_query)
                        if exists:
                            continue  # Already applied
                    except Exception:
                        pass  # Table doesn't exist yet — apply migration

                # Apply migration
                migration_path = os.path.join(migrations_dir, migration_file)
                try:
                    with open(migration_path, 'r') as f:
                        sql = f.read()
                    await conn.execute(sql)
                    logger.info(f"[Migrations] Applied {migration_file}")
                except Exception as e:
                    # If it fails, check if it's just a missing table that the migration itself creates
                    err_str = str(e).lower()
                    if 'already exists' in err_str or 'does not exist' in err_str:
                        logger.warning(f"[Migrations] {migration_file}: partially applied or already exists — continuing")
                    else:
                        logger.warning(f"[Migrations] Skipping {migration_file}: {e}")

    def _migration_check_query(self, migration_name: str) -> str | None:
        """Return a query that returns True if migration already applied."""
        checks = {
            'phase_13_pipeline_audit': "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='audit' AND table_name='pipeline_runs')",
            'phase_14_pipeline_integrity': "SELECT EXISTS (SELECT 1 FROM information_schema.schemas WHERE schema_name='audit') AND EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='audit' AND table_name='embedding_registry')",
            'phase_17_consolidation': "SELECT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='knowledge' AND table_name='knowledge_atoms' AND column_name='is_golden')",
        }
        return checks.get(migration_name)

    # ──────────────────────────────────────────────────────────────────────
    # RETRY POLICY INVENTORY — Pipeline-Wide Summary
    # ──────────────────────────────────────────────────────────────────────
    #
    # Layer 1 — Fetch (crawler._scrape_with_retry):
    #   Scope:      Per URL, fast-lane scrapes only.
    #   Attempts:   3 (CrawlerConfig.max_retries default).
    #   Backoff:    Exponential — delay = retry_base_delay * 2^attempt (1s, 2s, 4s).
    #   Trigger:    Any exception during aiohttp POST to firecrawl-local.
    #   Terminal:   Returns None after 3 failures; caller receives None and skips ingestion.
    #   Non-retryable: HTTP non-200 and empty markdown are treated as immediate None
    #                  (no retry on 4xx — firecrawl returns 200 on most errors).
    #
    # Layer 2 — Distillation (pipeline.py per-source try/except):
    #   Scope:      Per source in a condensation batch.
    #   Attempts:   1 (no retry — each source is processed once per batch run).
    #   Backoff:    N/A.
    #   Trigger:    Any exception during LLM extraction or atom storage.
    #   Terminal:   Source status set to "error" in corpus.sources; batch continues.
    #   Non-retryable: All failures are terminal at this layer (rely on job-level retry
    #                  to re-present the source in a future batch if needed).
    #
    # Layer 3 — Job (this loop, _vampire_loop):
    #   Scope:      Per job dequeued from queue:scraping.
    #   Attempts:   3 (job["retry_count"] field, default 0).
    #   Backoff:    Exponential — delay = 2^retry_count seconds (1s, 2s, 4s).
    #   Retryable:  All exceptions retry up to the cap (retry_count < 3).
    #               aiohttp.ClientError / asyncio.TimeoutError / ConnectionError /
    #               TimeoutError are additionally labelled "transient" in log output.
    #   Non-retryable / Terminal: retry_count >= 3 → dead-lettered (terminal log, NOT re-enqueued).
    #   Budget-hold: Jobs that exceed the crawl budget are re-enqueued unconditionally
    #               (not counted against retry_count — this is a hold, not a failure).
    # ──────────────────────────────────────────────────────────────────────
    async def _vampire_loop(self, vampire_id: int):
        """Greedy consumer loop: Eats URLs from Redis and stores technical ore."""
        logger.info(f"[Vampire-{vampire_id}] Unleashed.")
        _dequeued = 0
        _scraped = 0
        _skipped_lock = 0
        _skipped_existing = 0
        _skipped_filtered = 0
        _failed = 0

        # Domain failure memory: tracks domains with high failure rates
        domain_failures: Dict[str, int] = {}
        DOMAIN_FAILURE_THRESHOLD = 5  # Skip domain after N failures

        def _is_valid_target(url: str) -> bool:
            """Pre-scrape filter: reject known-bad URL patterns."""
            blocked_patterns = [
                "taylorfrancis.com/books",  # paywalled
                "login",
                "signup",
                "register",
                "captcha",
                "javascript:",
                "mailto:",
            ]
            for pattern in blocked_patterns:
                if pattern in url.lower():
                    return False

            # Check if domain has high failure rate
            from urllib.parse import urlparse
            try:
                domain = urlparse(url).netloc.lower()
                if domain_failures.get(domain, 0) >= DOMAIN_FAILURE_THRESHOLD:
                    return False
            except Exception:
                pass

            return True

        while True:
            try:
                # Dequeue next job
                job = await self.adapter.dequeue_job("queue:scraping", timeout_s=10)
                _dequeued += 1
                if not job: continue

                url = job.get("url")
                mission_id = job.get("mission_id")
                if not mission_id:
                    logger.warning(f"[Vampire-{vampire_id}] Job missing mission_id, skipping")
                    continue

                # Pre-scrape filter: reject known-bad URLs before wasting resources
                if not _is_valid_target(url):
                    _skipped_filtered += 1
                    if _dequeued % 100 == 0:
                        console.print(f"[dim][Vampire-{vampire_id}] Stats: dequeued={_dequeued}, scraped={_scraped}, filtered={_skipped_filtered}, failed={_failed}[/dim]")
                    continue  # Don't requeue — URL is known-bad

                # Skip URLs from missions that are no longer tracked by the budget monitor
                # This drains stale URLs from previous/cancelled missions without requeuing
                if not self.budget.get_status(mission_id):
                    _skipped_existing += 1
                    if _dequeued % 500 == 0:
                        console.print(f"[dim][Vampire-{vampire_id}] Draining {mission_id[:8]}... (stale mission, not requeuing)[/dim]")
                    continue  # Don't requeue — let stale URLs drain naturally

                # Check if already processed (Greedy de-duplication)
                existing = await self.adapter.get_source_by_url_hash(
                    mission_id=mission_id,
                    normalized_url_hash=job.get("url_hash", "")
                )
                if existing and existing.get("status") == "fetched":
                    _skipped_existing += 1
                    if _dequeued % 100 == 0:
                        console.print(f"[dim][Vampire-{vampire_id}] Stats: dequeued={_dequeued}, scraped={_scraped}, skipped_existing={_skipped_existing}, skipped_lock={_skipped_lock}, failed={_failed}[/dim]")
                    continue

                # Check budget before eating
                if not self.budget.can_crawl(mission_id):
                    # Re-queue for later
                    await self.adapter.enqueue_job("queue:scraping", job)
                    await asyncio.sleep(30); continue

                # Distributed lock: prevent redundant concurrent scraping of the same URL.
                # Two vampires can both pass get_source_by_url_hash simultaneously (TOCTOU).
                # acquire_lock uses Redis SET NX internally; only one caller proceeds.
                # The other skips without data loss — the DB unique constraint on url_hash
                # would reject the duplicate anyway.
                lock_key = f"lock:scraping:{job.get('url_hash', '')}"
                acquired = await self.adapter.acquire_lock(lock_key, ttl_s=300)
                if not acquired:
                    _skipped_lock += 1
                    logger.debug(f"[Vampire-{vampire_id}] Skipping already-processing URL: {url}")
                    continue

                # Scrape
                result = await self.crawler._scrape_with_retry(url)
                if result:
                    _scraped += 1
                    # Atomic Ingestion via V3 Adapter
                    topic_id = job.get("topic_id", mission_id)
                    source_meta = {
                        "mission_id": mission_id,
                        "topic_id": topic_id,
                        "url": url,
                        "normalized_url": url,
                        "normalized_url_hash": result.checksum,
                        "title": result.title,
                        "source_class": result.source_type,
                        "domain": result.domain,
                        "metadata": result.metadata
                    }
                    await self.adapter.ingest_source(source_meta, result.markdown)

                    # Trigger budget accounting to enable distillation
                    await self.budget.record_bytes(mission_id, result.raw_bytes)

                    logger.info(f"[Vampire-{vampire_id}] Consumed: {url} ({result.raw_bytes} bytes)")
                else:
                    _failed += 1

                    # Track domain failures for pre-scrape filtering
                    from urllib.parse import urlparse
                    try:
                        domain = urlparse(url).netloc.lower()
                        domain_failures[domain] = domain_failures.get(domain, 0) + 1
                        if domain_failures[domain] >= DOMAIN_FAILURE_THRESHOLD:
                            logger.info(f"[Vampire-{vampire_id}] Domain {domain} blocked ({domain_failures[domain]} failures)")
                    except Exception:
                        pass

                    if _dequeued % 50 == 0:
                        console.print(f"[bold red][Vampire-{vampire_id}][/bold red] Stats: dequeued={_dequeued}, scraped={_scraped}, failed={_failed}, filtered={_skipped_filtered}, skipped_lock={_skipped_lock}, skipped_existing={_skipped_existing}")

                    # INFRA-01: Queue depth monitoring every 100 dequeues
                    if _dequeued % 100 == 0:
                        try:
                            queue_depth = await self.adapter.get_queue_depth("queue:scraping")
                            if queue_depth > 8000:
                                logger.error(f"[Backpressure] Queue depth CRITICAL: {queue_depth} (>80%)")
                            elif queue_depth > 5000:
                                logger.warning(f"[Backpressure] Queue depth HIGH: {queue_depth} (>50%)")
                            # TUI-02: Publish status event
                            try:
                                await publish_status(self.redis_client, f"vampire-{vampire_id}", "stats", {
                                    "dequeued": _dequeued, "scraped": _scraped, "failed": _failed,
                                    "queue_depth": queue_depth,
                                })
                            except Exception:
                                pass
                        except Exception:
                            pass
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                # Resolve job reference safely (may not exist if dequeue itself failed)
                _job = job if 'job' in locals() and job else {}
                _url = _job.get("url", "unknown")
                _retry = _job.get("retry_count", 0)

                # Classify for log message only — all exceptions retry up to the cap.
                _retryable = isinstance(e, (
                    aiohttp.ClientError,
                    asyncio.TimeoutError,
                    ConnectionError,
                    TimeoutError,
                ))

                if _job and _retry < 3:
                    _job["retry_count"] = _retry + 1
                    _backoff = 2 ** _retry  # 1s, 2s, 4s
                    _kind = "transient" if _retryable else "non-retryable type"
                    logger.warning(
                        f"[Vampire-{vampire_id}] {_kind.capitalize()} failure on {_url} "
                        f"(attempt {_retry + 1}/3): {e}. Requeueing in {_backoff}s."
                    )
                    await asyncio.sleep(_backoff)
                    await self.adapter.enqueue_job("queue:scraping", _job)
                else:
                    logger.error(
                        f"[DEAD] [Vampire-{vampire_id}] Terminal failure on {_url} "
                        f"after {_retry} attempt(s): {e}. Job dropped."
                    )
                    # Track domain failure even on terminal drop
                    from urllib.parse import urlparse
                    try:
                        domain = urlparse(_url).netloc.lower()
                        domain_failures[domain] = domain_failures.get(domain, 0) + 1
                        if domain_failures[domain] >= DOMAIN_FAILURE_THRESHOLD:
                            logger.info(f"[Vampire-{vampire_id}] Domain {domain} blocked after terminal failure ({domain_failures[domain]} failures)")
                    except Exception:
                        pass

    async def _crawl_and_store(self, mission_id: str, topic_name: str, query: str) -> None:
        """Background task: adaptive frontier research mission."""
        from src.utils.console import console
        try:
            # TUI-02: Publish mission start
            try:
                await publish_status(self.redis_client, "frontier", "mission_start", {
                    "mission_id": mission_id[:8], "topic": topic_name,
                })
            except Exception:
                pass
            # Set mission status to active at start of execution
            await self.adapter.update_mission_status(mission_id, "active")
            console.print(f"\n[bold yellow][System][/bold yellow] Starting Deep Accretive Mission: [cyan]{topic_name}[/cyan]")

            # Pass mission_id to AdaptiveFrontier to use V3 schema
            frontier = AdaptiveFrontier(self, mission_id, topic_name)
            self.active_frontiers[mission_id] = frontier
            total_ingested = await frontier.run()

            console.print(f"[bold blue][DONE][/bold blue] Mission complete. [green]{total_ingested}[/green] total sources ingested.")
            await self.adapter.update_mission_status(mission_id, "completed")

            # Spawn follow-on missions for emergent topics discovered during this mission
            if self.condenser:
                try:
                    emergent = await self.condenser.get_emergent_topics_to_spawn(mission_id)
                    for cand in emergent:
                        concept = cand["concept"]
                        atom_count = cand["atom_count"]
                        try:
                            new_id = await self.learn(topic_name=concept, query=concept)
                            console.print(
                                f"[bold green][Discovery][/bold green] Auto-started follow-on mission: "
                                f"[cyan]{concept}[/cyan] (from {atom_count} emergent atoms)"
                            )
                            logger.info("[System] Spawned emergent mission '%s' → %s", concept, new_id)
                        except Exception as e:
                            logger.warning("[System] Failed to spawn emergent mission for '%s': %s", concept, e)
                except Exception as e:
                    logger.warning("[System] Emergent mission spawn failed: %s", e)

            # TUI-02: Publish mission complete
            try:
                await publish_status(self.redis_client, "frontier", "mission_complete", {
                    "mission_id": mission_id[:8], "total_ingested": total_ingested,
                })
            except Exception:
                pass

        except Exception as e:
            console.print(f"[bold red][FAIL][/bold red] Mission error: {e}")
            logger.error(f"[System] Mission error: {e}", exc_info=True)
            await self.adapter.update_mission_status(mission_id, "failed", stop_reason=str(e))
        finally:
            self._crawl_tasks.pop(mission_id, None)
            self.active_frontiers.pop(mission_id, None)

    async def nudge_mission(self, mission_id: str, instruction: str) -> bool:
        """Apply a human-in-the-loop steering correction to an active mission."""
        frontier = self.active_frontiers.get(mission_id)
        if not frontier:
            return False
        await frontier.apply_nudge(instruction)
        return True

    async def cancel_mission(self, mission_id: str) -> bool:
        """Gracefully stop a running research mission."""
        task = self._crawl_tasks.get(mission_id)
        if not task:
            return False

        # 1. Cancel the task
        task.cancel()

        # 2. Cleanup state
        self._crawl_tasks.pop(mission_id, None)
        self.active_frontiers.pop(mission_id, None)

        # 3. Update DB status
        await self.adapter.update_mission_status(mission_id, "stopped")

        logger.info(f"[System] Mission {mission_id} cancelled by user.")
        return True

    async def generate_report(self, mission_id: str) -> Optional[str]:
        """Trigger Tier 4 Selective Synthesis for a specific mission."""
        if not self.synthesis_service:
            return None
        return await self.synthesis_service.generate_master_brief(mission_id)

    async def _condensation_callback(self, mission_id: str, priority: CondensationPriority) -> None:
        # Register this task so cleanup() can await it instead of cancelling it
        current_task = asyncio.current_task()
        if current_task:
            self._condensation_tasks.add(current_task)
        try:
            console.print(f"[bold magenta][Distillery][/bold magenta] Budget triggered {priority.value} condensation for mission {mission_id[:8]}")
            if not self.condenser:
                console.print(f"[bold red][Distillery][/bold red] Condenser not initialized!")
                return
            # Shield the actual distillation work from external cancellation.
            # CancelledError from event loop shutdown will still propagate after shield completes.
            await asyncio.shield(self.condenser.run(mission_id, priority))
            console.print(f"[bold green][Distillery][/bold green] Condensation pass complete for mission {mission_id[:8]}")
        except asyncio.CancelledError:
            logger.warning(f"[Distillery] Condensation cancelled for mission {mission_id[:8]}")
            console.print(f"[yellow][Distillery][/yellow] Condensation cancelled for {mission_id[:8]}")
        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            logger.error(f"[Distillery] Condensation failed for mission {mission_id[:8]}: {e}\n{tb}")
            console.print(f"[bold red][Distillery][/bold red] ERROR for {mission_id[:8]}: {e}")
        finally:
            # Deregister from tracked tasks
            if current_task:
                self._condensation_tasks.discard(current_task)
            # Always reset budget flag so it can retry
            if self.budget:
                budget = self.budget.get_status(mission_id)
                if budget:
                    budget.condensation_running = False
                    budget.last_trigger = None

    def _build_system_prompt(self, context: str, project: Optional[str]) -> str:
        return (
            "You are Sheppard, a high-fidelity research and engineering assistant. "
            f"{f'You are currently working on the project: {project}.' if project else ''}\n"
            "Use the following retrieved knowledge to ground your response. Cite sources using [Sn] keys.\n"
            f"\n--- KNOWLEDGE ---\n{context}\n--- END KNOWLEDGE ---\n"
            "Be precise, technical, and direct."
        )

    def _check_initialized(self) -> None:
        if not self._initialized:
            raise RuntimeError("System not initialized")

    # ── Ingestion Control Helpers ──

    async def _distill_doc(self, doc: Dict[str, Any]) -> List[Any]:
        """
        Call the existing distillation pipeline on a single document.

        This wraps the current DistillationPipeline to process one doc
        instead of the full batch.
        """
        if not self.condenser or not self.condenser.ollama:
            return []

        from src.utils.distillation_pipeline import extract_technical_atoms
        from src.utils.normalize_atom_schema import normalize_atom_schema
        import uuid

        content = doc.get("content", "")
        if not content:
            return []

        # Extract atoms using existing pipeline
        mission_id = doc.get("mission_id", "ingestion_control")
        atoms_data = await extract_technical_atoms(
            self.condenser.ollama, content, mission_id,
            source_url=doc.get("url", "")
        )

        atoms = []
        for atom_dict in atoms_data:
            if not isinstance(atom_dict, dict):
                continue
            normalized = normalize_atom_schema(atom_dict)
            content_value = normalized.get("text", "")
            if not content_value or not isinstance(content_value, str):
                continue

            atoms.append({
                "id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"{mission_id}:{doc.get('id', '')}:{content_value[:200]}")),
                "content": content_value,
                "type": atom_dict.get("atom_type", atom_dict.get("type", "claim")),
                "confidence": normalized.get("confidence", 0.5),
                "importance": normalized.get("importance", 0.5),
                "novelty": normalized.get("novelty", 0.5),
                "source_id": doc.get("id", ""),
            })

        return atoms

    async def _fetch_doc(self, doc_id: str) -> Optional[Dict[str, Any]]:
        """Fetch document content by source_id — text lives in corpus.chunks, not corpus.sources."""
        if not self.adapter or not self.adapter.pg:
            return None

        try:
            async with self.adapter.pg.pool.acquire() as conn:
                row = await conn.fetchrow(
                    """
                    SELECT s.source_id, s.url, s.mission_id,
                           string_agg(c.inline_text, ' ' ORDER BY c.chunk_index) AS content
                    FROM corpus.sources s
                    JOIN corpus.chunks c ON c.source_id = s.source_id
                    WHERE s.source_id = $1
                      AND c.inline_text IS NOT NULL
                    GROUP BY s.source_id, s.url, s.mission_id
                    """,
                    doc_id,
                )
                if row and row.get("content"):
                    return {
                        "id": doc_id,
                        "url": row.get("url", ""),
                        "content": row["content"],
                        "mission_id": str(row["mission_id"]),
                    }
        except Exception as e:
            logger.debug(f"[IngestionControl] Failed to fetch doc {doc_id}: {e}")

        return None

    async def _store_atoms(self, atoms: List[Any], doc_id: str):
        """Store atoms into Postgres via the existing adapter."""
        if not self.adapter or not atoms:
            return

        try:
            async with self.adapter.pg.pool.acquire() as conn:
                # Resolve true mission_id and domain_profile_id from the source row.
                source_row = await conn.fetchrow(
                    "SELECT mission_id, topic_id FROM corpus.sources WHERE source_id = $1",
                    doc_id,
                )
                if not source_row:
                    logger.warning(f"[IngestionControl] Source {doc_id} not found; skipping atom store")
                    return

                true_mission_id = str(source_row["mission_id"])
                true_topic_id   = str(source_row["topic_id"])

                # Use an existing domain_profile_id for this topic, or fall back to any profile.
                domain_profile_id = await conn.fetchval(
                    "SELECT domain_profile_id FROM knowledge.knowledge_atoms WHERE topic_id = $1 LIMIT 1",
                    true_topic_id,
                )
                if not domain_profile_id:
                    domain_profile_id = await conn.fetchval(
                        "SELECT profile_id FROM config.domain_profiles LIMIT 1"
                    )
                if not domain_profile_id:
                    logger.warning("[IngestionControl] No domain profile found; skipping atom store")
                    return

            for atom in atoms:
                atom_id = atom.get("id", "")
                if not atom_id:
                    continue

                content = atom.get("content", "")
                atom_row = {
                    "atom_id":           atom_id,
                    "topic_id":          true_topic_id,
                    "mission_id":        true_mission_id,
                    "domain_profile_id": domain_profile_id,
                    "atom_type":         atom.get("type", "claim"),
                    "title":             content[:50],
                    "statement":         content,
                    "summary":           content,
                    "confidence":        atom.get("confidence", 0.5),
                    "importance":        atom.get("importance", 0.5),
                    "novelty":           atom.get("novelty", 0.5),
                    "scope_json":        {},
                    "qualifiers_json":   {},
                    "lineage_json":      {
                        "mission_id":       true_mission_id,
                        "extraction_mode":  "ingestion_control_tier2",
                    },
                    "metadata_json":     {"source_id": doc_id},
                }

                evidence_row = {
                    "atom_id":          atom_id,
                    "source_id":        doc_id,
                    "chunk_id":         None,
                    "evidence_strength": 0.7,
                    "supports_statement": True,
                }

                await self.adapter.store_atom_with_evidence(atom_row, [evidence_row])

        except Exception as e:
            logger.error(f"[IngestionControl] Failed to store atoms for {doc_id}: {e}")

# Global singleton
system_manager = SystemManager()

# Legacy aliases for backward compatibility
async def initialize_system() -> Tuple[bool, Optional[str]]:
    """Initialize the system using the global manager."""
    return await system_manager.initialize()

async def cleanup_system() -> None:
    """Clean up the system using the global manager."""
    await system_manager.cleanup()
