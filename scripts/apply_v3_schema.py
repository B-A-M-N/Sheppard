#!/usr/bin/env python3
"""
Apply V3 schema to PostgreSQL database.

This script creates the V3 database (if not exists) and applies src/memory/schema_v3.sql.
"""

import asyncio
import asyncpg
import sys
from pathlib import Path

# Configuration
# Use the same host/credentials as in DatabaseConfig but create a new DB
HOST = "10.9.66.198"
PORT = 5432
USER = "sheppard"
PASSWORD = "1234"
NEW_DB = "sheppard_v3"  # Dedicated DB for V3

SCHEMA_SQL_PATH = Path(__file__).parent.parent / "src" / "memory" / "schema_v3.sql"


async def create_database():
    """Connect to postgres and create sheppard_v3 database if not exists."""
    # Connect to 'postgres' maintenance DB
    conn = await asyncpg.connect(
        host=HOST,
        port=PORT,
        user=USER,
        password=PASSWORD,
        database="postgres"
    )
    try:
        # Check if DB exists
        exists = await conn.fetchval(
            "SELECT 1 FROM pg_database WHERE datname = $1",
            NEW_DB
        )
        if not exists:
            print(f"Creating database {NEW_DB}...")
            await conn.execute(f'CREATE DATABASE "{NEW_DB}"')
            print(f"Database {NEW_DB} created.")
        else:
            print(f"Database {NEW_DB} already exists.")
    finally:
        await conn.close()


async def apply_schema():
    """Connect to sheppard_v3 and apply schema.sql."""
    dsn = f"postgresql://{USER}:{PASSWORD}@{HOST}:{PORT}/{NEW_DB}"
    conn = await asyncpg.connect(dsn)

    try:
        # Read schema file
        sql = SCHEMA_SQL_PATH.read_text()
        print(f"Applying schema from {SCHEMA_SQL_PATH}...")

        # Execute (supports multiple statements)
        await conn.execute(sql)
        print("Schema applied successfully.")

        # Verify tables
        rows = await conn.fetch(
            """
            SELECT table_schema, table_name
            FROM information_schema.tables
            WHERE table_schema IN ('config','mission','corpus','knowledge','authority','application')
            ORDER BY table_schema, table_name;
            """
        )
        print(f"\nV3 tables created: {len(rows)}")
        for row in rows:
            print(f"  {row['table_schema']}.{row['table_name']}")

        # Count total tables expected? Roughly 40+ from schema_v3.sql
        if len(rows) < 30:
            print("\nWARNING: Expected more tables. Check schema file for errors.")
        else:
            print("\nSchema verification PASSED.")

    finally:
        await conn.close()


async def main():
    print("=" * 60)
    print("Sheppard V3 — Apply Schema")
    print("=" * 60)

    try:
        await create_database()
        await apply_schema()
        print("\n✅ V3 database and schema ready.")
        return 0
    except Exception as e:
        print(f"\n❌ Failed: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
