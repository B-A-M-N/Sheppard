"""
acquisition/budget.py

Pressure-valve storage budget monitor.
Watches raw crawl volume per topic and fires condensation triggers
at thresholds — crawling never stops, condensation runs alongside it.

Thresholds (configurable via env):
  70% → background condensation pass (lowest priority)
  85% → urgent condensation pass (higher priority, more workers)
  95% → aggressive condensation + prune already-condensed raw files

The condensation_callback is injected by the pipeline orchestrator.
"""

import asyncio
import os
import logging
from dataclasses import dataclass, field
from typing import Callable, Awaitable, Dict, Optional
from enum import Enum

logger = logging.getLogger(__name__)


class CondensationPriority(str, Enum):
    LOW = "low"        # 70% threshold — background
    HIGH = "high"      # 85% threshold — urgent
    CRITICAL = "critical"  # 95% threshold — aggressive + prune


@dataclass
class TopicBudget:
    mission_id: str
    topic_name: str
    ceiling_bytes: int          # user-configured max (default 5GB)
    raw_bytes: int = 0
    condensed_bytes: int = 0
    condensation_running: bool = False
    last_trigger: Optional[CondensationPriority] = None

    @property
    def usage_ratio(self) -> float:
        return self.raw_bytes / self.ceiling_bytes if self.ceiling_bytes > 0 else 0.0

    @property
    def headroom_bytes(self) -> int:
        return max(0, self.ceiling_bytes - self.raw_bytes)

    @property
    def is_near_ceiling(self) -> bool:
        return self.usage_ratio >= 0.95


@dataclass
class BudgetConfig:
    default_ceiling_gb: float = float(os.getenv("BUDGET_CEILING_GB", "5"))
    threshold_low: float = float(os.getenv("BUDGET_THRESHOLD_LOW", "0.01"))      # Trigger at 1% (50MB)
    threshold_high: float = float(os.getenv("BUDGET_THRESHOLD_HIGH", "0.05"))    # Trigger at 5% (250MB)
    threshold_critical: float = float(os.getenv("BUDGET_THRESHOLD_CRITICAL", "0.10")) # Trigger at 10% (500MB)
    poll_interval_secs: float = float(os.getenv("BUDGET_POLL_SECS", "10"))
    prune_raw_at: str = os.getenv("BUDGET_PRUNE_RAW_AT", "critical") # low | high | critical | never

    @property
    def default_ceiling_bytes(self) -> int:
        return int(self.default_ceiling_gb * 1024 ** 3)


CondensationCallback = Callable[[str, CondensationPriority], Awaitable[None]]


class BudgetMonitor:
    """
    Central storage budget manager.
    
    The condensation_callback is called with (mission_id, priority) when a
    threshold is crossed. It's the pipeline's responsibility to actually
    run the condensation — the monitor just fires the signal.
    
    Designed to run as a long-lived background task alongside the crawler.
    """

    def __init__(
        self,
        config: Optional[BudgetConfig] = None,
        condensation_callback: Optional[CondensationCallback] = None,
    ):
        self.config = config or BudgetConfig()
        self.condensation_callback = condensation_callback
        self._budgets: Dict[str, TopicBudget] = {}
        self._running = False
        self._lock = asyncio.Lock()

    def register_topic(
        self,
        mission_id: str,
        topic_name: str,
        ceiling_gb: Optional[float] = None,
    ) -> TopicBudget:
        """Register a topic for budget tracking."""
        ceiling_bytes = int((ceiling_gb or self.config.default_ceiling_gb) * 1024 ** 3)
        budget = TopicBudget(
            mission_id=mission_id,
            topic_name=topic_name,
            ceiling_bytes=ceiling_bytes,
        )
        self._budgets[mission_id] = budget
        logger.info(
            f"[Budget] Registered topic '{topic_name}' with {ceiling_gb or self.config.default_ceiling_gb}GB ceiling"
        )
        return budget

    async def record_bytes(self, mission_id: str, raw_bytes: int) -> None:
        """
        Called by the crawler each time a page is ingested.
        Updates raw byte count and checks thresholds immediately.
        """
        async with self._lock:
            if mission_id not in self._budgets:
                logger.warning(f"[Budget] Unknown mission_id: {mission_id}")
                return
            budget = self._budgets[mission_id]
            budget.raw_bytes += raw_bytes

        await self._check_thresholds(mission_id)

    async def record_condensation_result(
        self,
        mission_id: str,
        raw_bytes_freed: int,
        condensed_bytes_added: int,
    ) -> None:
        """
        Called by the condensation pipeline when a pass completes.
        Frees raw budget headroom so crawling can continue.
        """
        async with self._lock:
            if mission_id not in self._budgets:
                return
            budget = self._budgets[mission_id]
            budget.raw_bytes = max(0, budget.raw_bytes - raw_bytes_freed)
            budget.condensed_bytes += condensed_bytes_added
            budget.condensation_running = False
            budget.last_trigger = None # Reset to allow recurring triggers
            logger.info(
                f"[Budget] '{budget.topic_name}' condensation done. "
                f"Freed {raw_bytes_freed / 1024**2:.1f}MB raw → "
                f"{condensed_bytes_added / 1024**2:.1f}MB condensed. "
                f"Effective usage: {budget.usage_ratio:.1%}"
            )

    def get_status(self, mission_id: str) -> Optional[TopicBudget]:
        return self._budgets.get(mission_id)

    def all_statuses(self) -> Dict[str, TopicBudget]:
        return dict(self._budgets)

    def can_crawl(self, mission_id: str) -> bool:
        """
        Returns True unless at 95%+ with condensation already running
        (temporary backpressure to avoid runaway storage).
        """
        budget = self._budgets.get(mission_id)
        if not budget:
            return True
        if budget.is_near_ceiling and budget.condensation_running:
            return False
        return True

    async def _check_thresholds(self, mission_id: str) -> None:
        """
        Evaluate current usage ratio against thresholds.
        Only fires each threshold once per condensation cycle.
        """
        async with self._lock:
            budget = self._budgets[mission_id]

            if budget.condensation_running:
                return  # Already condensing, wait for it to finish

            ratio = budget.usage_ratio
            priority = None

            if ratio >= self.config.threshold_critical:
                if budget.last_trigger != CondensationPriority.CRITICAL:
                    priority = CondensationPriority.CRITICAL
            elif ratio >= self.config.threshold_high:
                if budget.last_trigger not in (CondensationPriority.HIGH, CondensationPriority.CRITICAL):
                    priority = CondensationPriority.HIGH
            elif ratio >= self.config.threshold_low:
                if budget.last_trigger is None:
                    priority = CondensationPriority.LOW

            if priority is None:
                return

            budget.condensation_running = True
            budget.last_trigger = priority
            logger.warning(
                f"[Budget] '{budget.topic_name}' at {ratio:.1%} — "
                f"firing {priority.value} condensation"
            )

        if self.condensation_callback:
            # Fire and forget — condensation runs alongside crawling
            asyncio.create_task(
                self.condensation_callback(mission_id, priority)
            )

    async def run_monitor_loop(self) -> None:
        """
        Background polling loop — secondary check in case
        record_bytes misses a threshold between calls.
        """
        self._running = True
        logger.info("[Budget] Monitor loop started")
        while self._running:
            await asyncio.sleep(self.config.poll_interval_secs)
            for mission_id in list(self._budgets.keys()):
                await self._check_thresholds(mission_id)

    def stop(self) -> None:
        self._running = False
