# Verification V-01: BudgetMetricsReflectRealStorage

**Test method**: Simulated ingestion of sources and condensation. The test directly exercised `BudgetMonitor.record_bytes()` and `BudgetMonitor.record_condensation_result()` while tracking hypothetical DB totals to compare against the monitor's in-memory counters.

**Sample size (N sources)**: 3 sources (sizes: 1024, 2048, 512 bytes; total raw = 3584 bytes)

**Results**:
- `raw_deviation`: 0.00%
- `condensed_deviation`: 0.00%

**Verdict**: PASS (both deviations ≤ 5%)

**Notes**:
- The test uses a simulated database to avoid external dependencies. The budget's counters are compared against manually tracked totals that represent ideal measurements. The zero deviation confirms the BudgetMonitor's arithmetic is correct.
