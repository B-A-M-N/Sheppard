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
import logging
import os
import re
from typing import AsyncGenerator, List, Optional, Dict, Any, Tuple

# V2 Acquisitions
from src.research.acquisition.budget import BudgetMonitor, BudgetConfig, CondensationPriority
from src.research.acquisition.crawler import FirecrawlLocalClient, CrawlerConfig
from src.research.acquisition.frontier import AdaptiveFrontier
# V2 Condensation
from src.research.condensation.pipeline import DistillationPipeline
# V2 Reasoning (deprecated — not used in V3)
# from src.research.reasoning.retriever import HybridRetriever, RetrievalQuery
from src.research.reasoning.retriever import RetrievalQuery  # Shared types only
from src.research.reasoning.v3_retriever import V3Retriever
# from src.research.reasoning.assembler import EvidenceAssembler  # disabled — V2 dependency
# from src.research.reasoning.synthesis_service import SynthesisService  # disabled — V2 dependency
# LLM & Memory
from src.llm.client import OllamaClient
from src.llm.model_router import ModelRouter, TaskType
# NOTE: MemoryManager is deprecated; V3 uses SheppardStorageAdapter exclusively.
from src.research.system import ResearchSystem

# V3 Storage
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
        self.research_system: Optional[ResearchSystem] = None
        # V2 MemoryManager removed — canonical truth is V3 adapter only
        self.memory = None

        self._crawl_tasks: Dict[str, asyncio.Task] = {}
        self.active_frontiers: Dict[str, AdaptiveFrontier] = {}
        self._monitor_task: Optional[asyncio.Task] = None
        self._vampire_tasks: List[asyncio.Task] = []
        self._initialized = False

    async def initialize(self) -> Tuple[bool, Optional[str]]:
        """Boot all subsystems. Returns (success, error_message)."""
        if self._initialized:
            return True, None

        try:
            logger.info("[System] Initializing Sheppard Infrastructure...")

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

            # 4. Condensation pipeline (V3-only, memory=None)
            self.condenser = DistillationPipeline(
                ollama=self.ollama,
                memory=None,  # MemoryManager removed
                budget=self.budget,
                adapter=self.adapter
            )

            # 5. Crawler
            self.crawler = FirecrawlLocalClient(
                config=CrawlerConfig(),
                on_bytes_crawled=self.budget.record_bytes,
            )
            await self.crawler.initialize()

            # 6. Retriever (V3 only)
            self.retriever = V3Retriever(adapter=self.adapter)

            # NOTE: Assembler and SynthesisService are disabled pending V3-only implementations
            # self.assembler = None
            # self.synthesis_service = None

            # 7. Research system (V3 deep research)
            self.research_system = ResearchSystem(
                chroma_store=self.adapter.chroma,
                ollama_client=self.ollama,
                memory_manager=None  # V2 memory deprecated; intermediate storage disabled
            )
            await self.research_system.initialize()

            # 8. Start background tasks
            self._monitor_task = asyncio.create_task(self.budget.run_monitor_loop())
            
            # 8. Unleash Local Vampires
            num_vampires = 8 # Balanced greed for Ryzen 9
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

        # 3. Register with Budget Monitor (will be migrated to mission_id in Phase 03)
        self.budget.register_topic(
            topic_id=mission_id,  # Bridge: use mission_id as topic_id until BudgetMonitor migrates
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
        """Run hybrid retrieval and return formatted context."""
        self._check_initialized()
        
        q = RetrievalQuery(
            text=text,
            project_filter=project_filter,
            topic_filter=topic_filter,
            max_results=max_results
        )
        ctx = await self.retriever.retrieve(q)
        return self.retriever.build_context_block(ctx, project_name=project_filter)

    async def chat(
        self,
        messages: List[dict],
        project_context: Optional[str] = None,
    ) -> AsyncGenerator[str, None]:
        """Conversational turn with hybrid RAG context."""
        self._check_initialized()

        user_msg = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
        
        context_block = ""
        if user_msg:
            context_block = await self.query(text=user_msg, project_filter=project_context)

        system_prompt = self._build_system_prompt(context_block, project_context)

        async for token in self.ollama.chat_stream(
            model=self.model_router.get_model_name(TaskType.CHAT),
            messages=messages,
            system_prompt=system_prompt,
        ):
            yield token

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
            
        logger.info("[System] Sheppard shut down cleanly")

    # ──────────────────────────────────────────────────
    # Internal Helpers
    # ──────────────────────────────────────────────────

    async def _vampire_loop(self, vampire_id: int):
        """Greedy consumer loop: Eats URLs from Redis and stores technical ore."""
        logger.info(f"[Vampire-{vampire_id}] Unleashed.")
        while True:
            try:
                # Dequeue next job
                job = await self.adapter.dequeue_job("queue:scraping", timeout_s=10)
                if not job: continue
                
                url = job.get("url")
                mission_id = job.get("mission_id")
                if not mission_id:
                    logger.warning(f"[Vampire-{vampire_id}] Job missing mission_id, skipping")
                    continue

                # Check if already processed (Greedy de-duplication)
                existing = await self.adapter.get_source_by_url_hash(job.get("url_hash", ""))
                if existing and existing.get("status") == "fetched":
                    logger.debug(f"[Vampire-{vampire_id}] Already fetched: {url}")
                    continue

                # Check budget before eating
                if not self.budget.can_crawl(mission_id):
                    # Re-queue for later
                    await self.adapter.enqueue_job("queue:scraping", job)
                    await asyncio.sleep(30); continue

                # Scrape
                result = await self.crawler._scrape_with_retry(url)
                if result:
                    # Atomic Ingestion via V3 Adapter
                    source_meta = {
                        "mission_id": mission_id,
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

                    logger.info(f"[Vampire-{vampire_id}] Consumed: {url}")
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[Vampire-{vampire_id}] Indigestion on {job.get('url') if 'job' in locals() else 'unknown'}: {e}")
                await asyncio.sleep(2)

    async def _crawl_and_store(self, mission_id: str, topic_name: str, query: str) -> None:
        """Background task: adaptive frontier research mission."""
        from src.utils.console import console
        try:
            console.print(f"\n[bold yellow][System][/bold yellow] Starting Deep Accretive Mission: [cyan]{topic_name}[/cyan]")

            # Pass mission_id to AdaptiveFrontier to use V3 schema
            frontier = AdaptiveFrontier(self, mission_id, topic_name)
            self.active_frontiers[mission_id] = frontier
            total_ingested = await frontier.run()

            console.print(f"[bold blue][DONE][/bold blue] Mission complete. [green]{total_ingested}[/green] total sources ingested.")
            await self.adapter.update_mission_status(mission_id, "completed")

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
        await self.condenser.run(mission_id, priority)

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

# Global singleton
system_manager = SystemManager()

# Legacy aliases for backward compatibility
async def initialize_system() -> Tuple[bool, Optional[str]]:
    """Initialize the system using the global manager."""
    return await system_manager.initialize()

async def cleanup_system() -> None:
    """Clean up the system using the global manager."""
    await system_manager.cleanup()
