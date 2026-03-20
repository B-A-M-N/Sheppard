#!/bin/bash

# Configuration
SHEPPARD_DIR="/home/bamn/Sheppard"
FIRECRAWL_DIR="/home/bamn/Progeny/firecrawl-local"
SEARXNG_DIR="/home/bamn/Progeny/ai-companion/searxng_server"
LOG_DIR="$SHEPPARD_DIR/logs"

mkdir -p "$LOG_DIR"

echo "[Stability] Stopping existing services..."
pkill -9 -f "searx/webapp.py"
pkill -9 -f "dist/api.js"
pkill -9 -f "dist/src/index.js"
pkill -9 -f "dist/src/services/queue-worker.js"
sleep 3

echo "[Stability] Starting SearXNG (8080)..."
cd "$SEARXNG_DIR"
export SEARXNG_SETTINGS_PATH="$SEARXNG_DIR/settings.yml"
export SEARXNG_SECRET="sheppard_secret"
export PORT=8080
setsid nohup ./venv/bin/python searx/webapp.py > "$LOG_DIR/searxng.log" 2>&1 &
sleep 10

echo "[Stability] Starting Playwright Service (3003)..."
cd "$FIRECRAWL_DIR/apps/playwright-service-ts"
export NODE_ENV=production
export PORT=3003
setsid nohup node dist/api.js > "$LOG_DIR/playwright.log" 2>&1 &
sleep 5

echo "[Stability] Starting Firecrawl API (3002)..."
cd "$FIRECRAWL_DIR/apps/api"
export PORT=3002
export HOST=0.0.0.0
export REDIS_URL=redis://localhost:6379
export REDIS_RATE_LIMIT_URL=redis://localhost:6379
export PLAYWRIGHT_MICROSERVICE_URL=http://localhost:3003/scrape
export USE_DB_AUTHENTICATION=false
export SEARXNG_ENDPOINT=http://127.0.0.1:8080
setsid nohup node dist/src/index.js > "$LOG_DIR/firecrawl_api.log" 2>&1 &
sleep 5

echo "[Stability] Starting Firecrawl Worker..."
# Load worker count from .env if available
WORKER_COUNT=$(grep NUM_WORKERS_PER_QUEUE "$SHEPPARD_DIR/.env" | cut -d'=' -f2)
export NUM_WORKERS_PER_QUEUE=${WORKER_COUNT:-12}
setsid nohup node dist/src/services/queue-worker.js > "$LOG_DIR/firecrawl_worker.log" 2>&1 &

echo "Research stack started with high-stability setsid sessions!"
ss -tulpn | grep -E "8888|3002|3003"
