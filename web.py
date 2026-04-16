#!/usr/bin/env python3
"""
web.py — Sheppard Web UI entry point.

Usage:
  python web.py              # default: 0.0.0.0:8000
  python web.py --port 9000
"""

import sys
import argparse
from pathlib import Path

# Ensure project root is on path
sys.path.insert(0, str(Path(__file__).parent))

import uvicorn


def main():
    parser = argparse.ArgumentParser(description="Sheppard Web UI")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--reload", action="store_true", help="Dev mode: auto-reload on changes")
    args = parser.parse_args()

    uvicorn.run(
        "src.web.server:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level="info",
    )


if __name__ == "__main__":
    main()
