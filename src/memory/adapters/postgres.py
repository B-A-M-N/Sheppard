"""
memory/adapters/postgres.py

Concrete Postgres backend implementation for Sheppard Storage Adapter.
"""
import asyncpg
import json
from typing import Any, Dict, List, Optional, Sequence, Union

JsonDict = dict[str, Any]

class PostgresStoreImpl:
    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    def _prepare_values(self, row: JsonDict) -> List[Any]:
        """Convert dict values to asyncpg-friendly types."""
        from datetime import datetime
        prepared = []
        for v in row.values():
            if isinstance(v, (dict, list)):
                prepared.append(json.dumps(v))
            elif isinstance(v, str):
                # Try to parse ISO datetime if it looks like one
                if len(v) > 19 and v[10] == 'T':
                    try:
                        prepared.append(datetime.fromisoformat(v.replace('Z', '+00:00')))
                    except:
                        prepared.append(v)
                else:
                    prepared.append(v)
            else:
                prepared.append(v)
        return prepared

    async def upsert_row(self, table: str, key_fields: Union[str, Sequence[str]], row: JsonDict) -> None:
        if isinstance(key_fields, str):
            key_fields = [key_fields]

        async with self.pool.acquire() as conn:
            columns = list(row.keys())
            values = self._prepare_values(row)

            col_str = ", ".join(columns)
            val_str = ", ".join(f"${i+1}" for i in range(len(values)))

            update_parts = [f"{col} = EXCLUDED.{col}" for col in columns if col not in key_fields]
            update_str = ", ".join(update_parts)

            query = f"INSERT INTO {table} ({col_str}) VALUES ({val_str})"
            key_str = ", ".join(key_fields)
            if update_parts:
                query += f" ON CONFLICT ({key_str}) DO UPDATE SET {update_str}"
            else:
                query += f" ON CONFLICT ({key_str}) DO NOTHING"

            await conn.execute(query, *values)

    async def insert_row(self, table: str, row: JsonDict) -> None:
        async with self.pool.acquire() as conn:
            columns = list(row.keys())
            values = self._prepare_values(row)
            
            col_str = ", ".join(columns)
            val_str = ", ".join(f"${i+1}" for i in range(len(values)))
            
            query = f"INSERT INTO {table} ({col_str}) VALUES ({val_str})"
            await conn.execute(query, *values)

    async def update_row(self, table: str, key_field: str, row: JsonDict) -> None:
        async with self.pool.acquire() as conn:
            columns = [c for c in row.keys() if c != key_field]
            values = [v for k, v in row.items() if k != key_field]
            
            # Add the key field value at the end for the WHERE clause
            values.append(row[key_field])
            
            set_parts = [f"{col} = ${i+1}" for i, col in enumerate(columns)]
            set_str = ", ".join(set_parts)
            
            query = f"UPDATE {table} SET {set_str} WHERE {key_field} = ${len(values)}"
            await conn.execute(query, *values)

    async def bulk_insert(self, table: str, rows: Sequence[JsonDict]) -> None:
        if not rows: return
        async with self.pool.acquire() as conn:
            columns = list(rows[0].keys())
            col_str = ", ".join(columns)
            
            query = f"INSERT INTO {table} ({col_str}) VALUES ({', '.join(f'${i+1}' for i in range(len(columns)))})"
            values = [self._prepare_values(r) for r in rows]
            await conn.executemany(query, values)

    async def bulk_upsert(self, table: str, key_fields: Sequence[str], rows: Sequence[JsonDict]) -> None:
        if not rows: return
        async with self.pool.acquire() as conn:
            columns = list(rows[0].keys())
            col_str = ", ".join(columns)
            
            update_parts = [f"{col} = EXCLUDED.{col}" for col in columns if col not in key_fields]
            update_str = ", ".join(update_parts)
            
            query = f"INSERT INTO {table} ({col_str}) VALUES ({', '.join(f'${i+1}' for i in range(len(columns)))})"
            key_str = ", ".join(key_fields)
            if update_parts:
                query += f" ON CONFLICT ({key_str}) DO UPDATE SET {update_str}"
            else:
                query += f" ON CONFLICT ({key_str}) DO NOTHING"
                
            values = [self._prepare_values(r) for r in rows]
            await conn.executemany(query, values)

    async def fetch_one(self, table: str, where: JsonDict) -> JsonDict | None:
        async with self.pool.acquire() as conn:
            where_parts = [f"{k} = ${i+1}" for i, k in enumerate(where.keys())]
            query = f"SELECT * FROM {table} WHERE {' AND '.join(where_parts)} LIMIT 1"
            row = await conn.fetchrow(query, *where.values())
            return dict(row) if row else None

    async def fetch_many(
        self,
        table: str,
        where: JsonDict | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> list[JsonDict]:
        async with self.pool.acquire() as conn:
            query = f"SELECT * FROM {table}"
            values = []
            if where:
                where_parts = [f"{k} = ${i+1}" for i, k in enumerate(where.keys())]
                query += f" WHERE {' AND '.join(where_parts)}"
                values = list(where.values())
            
            if order_by:
                query += f" ORDER BY {order_by}"
            if limit:
                query += f" LIMIT {limit}"
                
            rows = await conn.fetch(query, *values)
            return [dict(r) for r in rows]

    async def delete_where(self, table: str, where: JsonDict) -> None:
        if not where: raise ValueError("delete_where requires conditions")
        async with self.pool.acquire() as conn:
            where_parts = [f"{k} = ${i+1}" for i, k in enumerate(where.keys())]
            query = f"DELETE FROM {table} WHERE {' AND '.join(where_parts)}"
            await conn.execute(query, *where.values())
