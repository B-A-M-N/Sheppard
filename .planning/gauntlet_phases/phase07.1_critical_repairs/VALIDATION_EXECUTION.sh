#!/usr/bin/env bash
#
# Phase 07.1 — Validation Execution Script
# This script performs the definitive validation of the critical repairs.
#
# Exit codes:
#   0 = all validation passed
#   1 = migration not applied or column missing
#   2 = test suite failed
#   3 = test suite could not be executed
#
# Usage: ./VALIDATION_EXECUTION.sh
# Requirements: psql, pytest, database connectivity

set -e  # Exit on any error

echo "=== Phase 07.1: Validation Execution ==="
echo ""

# Color helpers
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
DB_CONN="postgresql://sheppard:1234@localhost:5432/sheppard_v3"
# If using remote DB, override:
# DB_CONN="postgresql://sheppard:1234@10.9.66.198:5432/sheppard_v3"

# ============================================
# STEP 1: Check database connectivity
# ============================================
echo "Step 1: Checking database connectivity..."
if command -v psql &> /dev/null; then
    if echo "SELECT 1" | PGPASSWORD=1234 psql -h localhost -p 5432 -U sheppard -d sheppard_v3 -c "SELECT 1" &>/dev/null; then
        echo -e "${GREEN}✓${NC} Database connection OK"
    else
        echo -e "${RED}✗${NC} Cannot connect to database"
        echo "  Check that PostgreSQL is running and credentials are correct."
        exit 1
    fi
else
    echo -e "${RED}✗${NC} psql not found in PATH"
    exit 1
fi

# ============================================
# STEP 2: Verify exhausted_modes_json column exists
# ============================================
echo ""
echo "Step 2: Verifying exhausted_modes_json column in mission_nodes..."

COLUMN_CHECK=$(PGPASSWORD=1234 psql -h localhost -p 5432 -U sheppard -d sheppard_v3 -tAc \
    "SELECT column_name FROM information_schema.columns WHERE table_name='mission_nodes' AND column_name='exhausted_modes_json';")

if [ -z "$COLUMN_CHECK" ]; then
    echo -e "${RED}✗${NC} Column 'exhausted_modes_json' does NOT exist in mission_nodes"
    echo ""
    echo "ACTION REQUIRED:"
    echo "  Apply the migration:"
    echo "    \\i .planning/gauntlet_phases/phase07.1_critical_repairs/MIGRATION_add_exhausted_modes_json.sql"
    echo ""
    echo "  Or run manually:"
    echo "    PGPASSWORD=1234 psql -h localhost -p 5432 -U sheppard -d sheppard_v3 -c \"ALTER TABLE mission.mission_nodes ADD COLUMN IF NOT EXISTS exhausted_modes_json JSONB NOT NULL DEFAULT '[]'::jsonb;\""
    exit 1
else
    echo -e "${GREEN}✓${NC} Column exists: $COLUMN_CHECK"
fi

# ============================================
# STEP 3: Optional — Backfill existing rows (safe)
# ============================================
echo ""
echo "Step 3: Ensuring existing rows have non-null values (if any)..."
PGPASSWORD=1234 psql -h localhost -p 5432 -U sheppard -d sheppard_v3 -c \
    "UPDATE mission.mission_nodes SET exhausted_modes_json = '[]' WHERE exhausted_modes_json IS NULL;" 2>/dev/null || true
echo -e "${GREEN}✓${NC} Backfill complete (no rows affected means column was already populated)"

# ============================================
# STEP 4: Check pytest availability
# ============================================
echo ""
echo "Step 4: Checking pytest installation..."
if ! command -v pytest &> /dev/null; then
    echo -e "${RED}✗${NC} pytest not found"
    echo "  Install: pip install pytest pytest-asyncio"
    exit 3
fi
echo -e "${GREEN}✓${NC} pytest available"

# ============================================
# STEP 5: Run validation test suite
# ============================================
echo ""
echo "Step 5: Running validation test suite..."
echo "Command: pytest tests/validation/ -v --tb=short"
echo ""

# Run tests with verbose output
if pytest tests/validation/ -v --tb=short; then
    echo ""
    echo -e "${GREEN}========================================${NC}"
    echo -e "${GREEN}✓ ALL VALIDATION TESTS PASSED${NC}"
    echo -e "${GREEN}========================================${NC}"
    echo ""
    echo "The system is now validated for milestone v1.0."
    echo "Next: Run final milestone audit with 'gsd:audit-milestone'"
    exit 0
else
    echo ""
    echo -e "${RED}========================================${NC}"
    echo -e "${RED}✗ VALIDATION TESTS FAILED${NC}"
    echo -e "${RED}========================================${NC}"
    echo ""
    echo "FAILURE ANALYSIS:"
    echo "- Review the pytest output above for specific test failures"
    echo "- Common issues:"
    echo "  1. Missing exhausted_modes_json column → re-apply migration"
    echo "  2. V09 failure with real frontier → check DB interactions"
    echo "  3. V10 integration failure → verify backpressure logic"
    echo "  4. V11 failure → check JSON serialization/deserialization"
    echo "  5. V12 failure → verify academic_only flag propagation"
    echo ""
    echo "ACTION: Return to Phase 07.1, debug the failures, and repeat validation."
    exit 2
fi
