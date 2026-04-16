#!/bin/bash
# start_research_stack.sh — Sheppard research service launcher with health checks
# Starts SearXNG, Playwright, and Firecrawl. Safe to re-run: skips already-running services.

set -euo pipefail

SHEPPARD_DIR="/home/bamn/Sheppard"
FIRECRAWL_DIR="/home/bamn/firecrawl-local"
SEARXNG_DIR="/home/bamn/Progeny/ai-companion/searxng_server"
LOG_DIR="$SHEPPARD_DIR/logs"
TIMEOUT=30  # seconds to wait for each service to come up

mkdir -p "$LOG_DIR"

# ── helpers ────────────────────────────────────────────────────────────────────

port_listening() {
    ss -tulpn 2>/dev/null | grep -q ":$1 "
}

wait_for_port() {
    local port=$1 name=$2 elapsed=0
    while ! port_listening "$port"; do
        if [ "$elapsed" -ge "$TIMEOUT" ]; then
            echo "[ERROR] $name did not start on port $port within ${TIMEOUT}s — check $LOG_DIR"
            return 1
        fi
        sleep 2
        elapsed=$((elapsed + 2))
    done
    echo "[OK] $name is up on port $port"
}

# ── SearXNG (port 8080) ────────────────────────────────────────────────────────

if port_listening 8080; then
    echo "[SKIP] SearXNG already running on port 8080"
else
    echo "[START] SearXNG (port 8080)..."
    cd "$SEARXNG_DIR"
    SEARXNG_SETTINGS_PATH="$SEARXNG_DIR/settings.yml" \
    SEARXNG_SECRET="sheppard_secret" \
    PORT=8080 \
    setsid nohup ./venv/bin/python searx/webapp.py > "$LOG_DIR/searxng.log" 2>&1 &
    wait_for_port 8080 "SearXNG"
fi

# ── Playwright service (port 3003) ─────────────────────────────────────────────

if port_listening 3003; then
    echo "[SKIP] Playwright service already running on port 3003"
else
    echo "[START] Playwright service (port 3003)..."
    # Install browser binaries if missing
    if [ ! -f "$HOME/.cache/ms-playwright/chromium_headless_shell-1208/chrome-headless-shell-linux64/chrome-headless-shell" ]; then
        echo "[SETUP] Installing Playwright browser binaries..."
        cd "$FIRECRAWL_DIR/apps/playwright-service-ts"
        npx playwright install chromium >> "$LOG_DIR/playwright_install.log" 2>&1
    fi
    cd "$FIRECRAWL_DIR/apps/playwright-service-ts"
    REDIS_URL=redis://127.0.0.1:6379 \
    PORT=3003 \
    NODE_ENV=production \
    setsid nohup node dist/api.js > "$LOG_DIR/playwright.log" 2>&1 &
    wait_for_port 3003 "Playwright"
fi

# ── Firecrawl API + workers (managed by harness on port 3002) ──────────────────
# The harness at firecrawl-local/apps/api manages the API + worker pool together.

if port_listening 3002; then
    echo "[SKIP] Firecrawl API already running on port 3002"
else
    echo "[START] Firecrawl API via harness (port 3002)..."
    cd "$FIRECRAWL_DIR/apps/api"
    REDIS_URL=redis://127.0.0.1:6379 \
    REDIS_RATE_LIMIT_URL=redis://127.0.0.1:6379 \
    PLAYWRIGHT_MICROSERVICE_URL=http://127.0.0.1:3003/scrape \
    USE_DB_AUTHENTICATION=false \
    PORT=3002 \
    HOST=0.0.0.0 \
    SEARXNG_ENDPOINT=http://127.0.0.1:8080 \
    setsid nohup node dist/src/index.js > "$LOG_DIR/firecrawl_api.log" 2>&1 &
    wait_for_port 3002 "Firecrawl API"
fi

# ── Final status ───────────────────────────────────────────────────────────────

echo ""
echo "=== Research Stack Status ==="
ss -tulpn | grep -E ":(8080|3002|3003) " || true
echo "All required services are running."
