"""
V-01: Budget metrics reflect real storage

This test uses simulated data to verify that the BudgetMonitor's raw_bytes
and condensed_bytes accurately reflect hypothetical stored data within 5% tolerance.
"""
import pytest
import asyncio
from src.research.acquisition.budget import BudgetMonitor, BudgetConfig

@pytest.mark.asyncio
async def test_v01_budget_metrics():
    mission_id = "test-mission-v01"
    config = BudgetConfig(default_ceiling_gb=1.0)
    monitor = BudgetMonitor(config=config)
    monitor.register_topic(mission_id, "test-topic", ceiling_gb=1.0)

    # --- Raw bytes consistency ---
    # Simulate ingestion of 3 sources with known byte sizes
    source_sizes = [1024, 2048, 512]  # total 3584
    simulated_db_raw_total = 0
    for size in source_sizes:
        await monitor.record_bytes(mission_id, size)
        simulated_db_raw_total += size

    status = monitor.get_status(mission_id)
    assert status is not None
    budget_raw = status.raw_bytes
    raw_deviation = abs(budget_raw - simulated_db_raw_total) / simulated_db_raw_total if simulated_db_raw_total > 0 else 0.0
    print(f"Simulated DB raw total: {simulated_db_raw_total}")
    print(f"Budget raw bytes: {budget_raw}")
    print(f"raw_deviation: {raw_deviation*100:.2f}%")

    # --- Condensed bytes consistency ---
    # Simulate condensation producing atoms with a known total size
    condensed_added = 1000  # hypothetical total size of atoms created
    simulated_db_condensed_total = 0
    await monitor.record_condensation_result(
        mission_id,
        raw_bytes_freed=0,
        condensed_bytes_added=condensed_added
    )
    simulated_db_condensed_total += condensed_added

    budget_condensed = status.condensed_bytes
    condensed_deviation = abs(budget_condensed - simulated_db_condensed_total) / simulated_db_condensed_total if simulated_db_condensed_total > 0 else 0.0
    print(f"Simulated DB condensed total: {simulated_db_condensed_total}")
    print(f"Budget condensed bytes: {budget_condensed}")
    print(f"condensed_deviation: {condensed_deviation*100:.2f}%")

    # Both deviations must be <= 5%
    assert raw_deviation <= 0.05, f"Raw deviation {raw_deviation*100:.2f}% exceeds 5%"
    assert condensed_deviation <= 0.05, f"Condensed deviation {condensed_deviation*100:.2f}% exceeds 5%"
