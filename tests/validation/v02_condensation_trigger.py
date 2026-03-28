"""
V-02: CondensationTriggerCorrectness

Tests that the BudgetMonitor fires a HIGH-priority condensation trigger exactly once
when raw_bytes crosses the HIGH threshold (85%) and does not trigger prematurely.
"""
import pytest
import asyncio
from src.research.acquisition.budget import BudgetMonitor, BudgetConfig, CondensationPriority

@pytest.mark.asyncio
async def test_v02_condensation_trigger():
    # Configure thresholds: HIGH=85%, CRITICAL=95%
    # Set LOW threshold > 90% to avoid interference during test
    config = BudgetConfig(threshold_low=0.90, threshold_high=0.85, threshold_critical=0.95)
    monitor = BudgetMonitor(config=config)
    mission_id = "test-mission-v02"
    ceiling = 1000  # bytes
    monitor.register_topic(mission_id, "test-topic", ceiling_gb=ceiling / (1024**3))
    # Ensure exact ceiling value
    monitor._budgets[mission_id].ceiling_bytes = ceiling

    # Track condensation invocations
    calls = []
    async def callback(mid, priority):
        status = monitor.get_status(mid)
        calls.append({"raw": status.raw_bytes, "priority": priority})
    monitor.condensation_callback = callback

    # --- Ingestion simulation ---
    # Step 1: Ingestion below threshold (80%)
    await monitor.record_bytes(mission_id, 800)
    await asyncio.sleep(0)  # allow callback to execute
    assert len(calls) == 0, "Condensation should not trigger before HIGH threshold"

    # Step 2: Cross HIGH threshold (add 50 -> total 850, exactly 85%)
    await monitor.record_bytes(mission_id, 50)
    await asyncio.sleep(0)
    assert len(calls) == 1, "Exactly one HIGH trigger expected at threshold crossing"
    trigger = calls[0]
    assert trigger["raw"] >= 850, f"Trigger raw {trigger['raw']} should be >= 850"
    assert trigger["raw"] <= 900, f"Trigger raw {trigger['raw']} should be <= 900 (before 90%)"
    assert trigger["priority"] == CondensationPriority.HIGH

    # Step 3: Continue ingestion past 90% but before condensation completes
    await monitor.record_bytes(mission_id, 50)  # total 900
    await asyncio.sleep(0)
    assert len(calls) == 1, "No additional triggers while condensation is running"

    # PASS: single trigger between 85% and 90%, none before