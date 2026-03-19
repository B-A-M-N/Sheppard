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
# V2 Reasoning
from src.research.reasoning.retriever import HybridRetriever, RetrievalQuery
# LLM & Memory
from src.llm.client import OllamaClient
from src.llm.model_router import ModelRouter, TaskType
from src.memory.manager import MemoryManager

from src.config.settings import settings

logger = logging.getLogger(__name__)

class SystemManager:
    """
    Unified system manager for Sheppard.
    Orchestrates legacy research tasks and V2 accretive learning missions.
    """

    def __init__(self):
        self.memory: Optional[MemoryManager] = None
        self.ollama: Optional[OllamaClient] = None
        self.model_router = ModelRouter()
        self.budget: Optional[BudgetMonitor] = None
        self.crawler: Optional[FirecrawlLocalClient] = None
        self.condenser: Optional[DistillationPipeline] = None
        self.retriever: Optional[HybridRetriever] = None

        self._crawl_tasks: Dict[str, asyncio.Task] = {}
        self._monitor_task: Optional[asyncio.Task] = None
        self._initialized = False

    async def initialize(self) -> Tuple[bool, Optional[str]]:
        """Boot all subsystems. Returns (success, error_message)."""
        if self._initialized:
            return True, None

        try:
            logger.info("[System] Initializing Sheppard Infrastructure...")

            # 1. Memory (ChromaDB + Postgres V2)
            self.memory = MemoryManager()
            await self.memory.initialize()

            # 2. LLM Client
            self.ollama = OllamaClient(model_router=self.model_router)
            await self.ollama.initialize()
            self.memory.set_ollama_client(self.ollama)

            # 3. Budget monitor
            self.budget = BudgetMonitor(
                config=BudgetConfig(),
                condensation_callback=self._condensation_callback,
            )

            # 4. Condensation pipeline
            self.condenser = DistillationPipeline(
                ollama=self.ollama,
                memory=self.memory,
                budget=self.budget,
            )

            # 5. Crawler
            self.crawler = FirecrawlLocalClient(
                config=CrawlerConfig(),
                on_bytes_crawled=self.budget.record_bytes,
            )
            await self.crawler.initialize()

            # 6. Retriever
            self.retriever = HybridRetriever(memory_manager=self.memory)

            # 7. Start background tasks
            self._monitor_task = asyncio.create_task(self.budget.run_monitor_loop())

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

        topic_id = await self.memory.create_topic(name=topic_name, description=query)
        await self.memory.update_topic_status(topic_id, "active")
        
        self.budget.register_topic(
            topic_id=topic_id,
            topic_name=topic_name,
            ceiling_gb=ceiling_gb,
        )

        self.crawler.academic_only = academic_only

        task = asyncio.create_task(self._crawl_and_store(topic_id, topic_name, query))
        self._crawl_tasks[topic_id] = task
        
        logger.info(f"[System] Learning mission '{topic_name}' started (ID: {topic_id})")
        return topic_id

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
        """Graceful shutdown of all tasks."""
        if self._monitor_task:
            self._monitor_task.cancel()
        for task in self._crawl_tasks.values():
            if not task.done():
                task.cancel()
        if self.crawler:
            await self.crawler.cleanup()
        if self.memory:
            await self.memory.cleanup()
        logger.info("[System] Sheppard shut down cleanly")

    # ──────────────────────────────────────────────────
    # Internal Helpers
    # ──────────────────────────────────────────────────

    async def _crawl_and_store(self, topic_id: str, topic_name: str, query: str) -> None:
        """Background task: adaptive frontier research mission."""
        from src.utils.console import console
        try:
            console.print(f"\n[bold yellow][System][/bold yellow] Starting Deep Accretive Mission: [cyan]{topic_name}[/cyan]")
            
            frontier = AdaptiveFrontier(self, topic_id, topic_name)
            total_ingested = await frontier.run()
            
            console.print(f"[bold blue][DONE][/bold blue] Mission complete. [green]{total_ingested}[/green] total sources ingested.")
            await self.memory.update_topic_status(topic_id, "done")

        except Exception as e:
            console.print(f"[bold red][FAIL][/bold red] Mission error: {e}")
            logger.error(f"[System] Mission error: {e}", exc_info=True)
            await self.memory.update_topic_status(topic_id, "failed")
        finally:
            self._crawl_tasks.pop(topic_id, None)

    async def _condensation_callback(self, topic_id: str, priority: CondensationPriority) -> None:
        await self.condenser.run(topic_id, priority)

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
