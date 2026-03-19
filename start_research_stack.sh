#!/bin/bash

# Configuration
SHEPPARD_DIR="/home/bamn/Sheppard"
FIRECRAWL_DIR="/home/bamn/Progeny/firecrawl-local"
SEARXNG_DIR="/home/bamn/Progeny/ai-companion/searxng_server"
LOG_DIR="$SHEPPARD_DIR/logs"

mkdir -p "$LOG_DIR"

echo "Stopping existing services..."
pkill -f "searx/webapp.py"
pkill -f "dist/api.js"
pkill -f "dist/src/index.js"
pkill -f "dist/src/services/queue-worker.js"
sleep 2

echo "Starting SearXNG..."
cd "$SEARXNG_DIR"
export SEARXNG_SETTINGS_PATH="$SEARXNG_DIR/settings.yml"
export SEARXNG_SECRET="sheppard_secret"
# Add engine rotation via env if supported, or ensure settings.yml is broad
./venv/bin/python searx/webapp.py > "$LOG_DIR/searxng.log" 2>&1 &

echo "Starting Playwright Service..."
cd "$FIRECRAWL_DIR/apps/playwright-service-ts"
export NODE_ENV=production
export PORT=3003
node dist/api.js > "$LOG_DIR/playwright.log" 2>&1 &

echo "Starting Firecrawl API..."
cd "$FIRECRAWL_DIR/apps/api"
export PORT=3002
export HOST=0.0.0.0
export REDIS_URL=redis://localhost:6379
export REDIS_RATE_LIMIT_URL=redis://localhost:6379
export PLAYWRIGHT_MICROSERVICE_URL=http://localhost:3003/scrape
export USE_DB_AUTHENTICATION=false
export SEARXNG_ENDPOINT=http://127.0.0.1:8080
node dist/src/index.js > "$LOG_DIR/firecrawl_api.log" 2>&1 &

echo "Starting Firecrawl Worker..."
node dist/src/services/queue-worker.js > "$LOG_DIR/firecrawl_worker.log" 2>&1 &

echo "Research stack started!"
echo "SearXNG: http://localhost:8080"
echo "Firecrawl: http://localhost:3002"
echo "Logs available in $LOG_DIR"
