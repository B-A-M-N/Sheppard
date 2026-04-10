
import asyncio
import os
import json
import hashlib
import uuid
from typing import Optional
from urllib.parse import urlparse
import aiohttp
import asyncpg
import redis.asyncio as redis

# Scout Node Configuration (Flexible)
MAIN_PC_IP = os.getenv("MAIN_PC_IP", "10.9.66.198")
POSTGRES_DSN = f"postgresql://sheppard:1234@{MAIN_PC_IP}:5432/semantic_memory"
REDIS_URL = f"redis://{MAIN_PC_IP}:6379"
FIRECRAWL_URL = os.getenv("FIRECRAWL_URL", "http://localhost:3002")

# Chunking configuration
CHUNK_SIZE = 1000  # tokens per chunk
CHUNK_OVERLAP = 200  # token overlap between chunks


async def _create_chunks_for_source(conn, source_id, mission_id, topic_id, text, text_ref):
    """Create chunks for a source so the distillery pipeline can bind evidence."""
    try:
        # Lazy import chunker
        from src.research.archivist.chunker import chunk_text
        chunk_strings = chunk_text(text)

        for idx, chunk_text_content in enumerate(chunk_strings):
            chunk_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{source_id}:chunk:{idx}"))
            await conn.execute('''
                INSERT INTO corpus.chunks (
                    chunk_id, source_id, mission_id, topic_id, chunk_index,
                    inline_text, text_ref, token_count
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                ON CONFLICT (chunk_id) DO UPDATE SET inline_text = EXCLUDED.inline_text
            ''', chunk_id, source_id, mission_id, topic_id, idx,
                 chunk_text_content, text_ref, len(chunk_text_content.split()))
    except ImportError:
        # Fallback: create a single chunk with the full text
        chunk_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{source_id}:chunk:0"))
        await conn.execute('''
            INSERT INTO corpus.chunks (
                chunk_id, source_id, mission_id, topic_id, chunk_index,
                inline_text, text_ref, token_count
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            ON CONFLICT (chunk_id) DO UPDATE SET inline_text = EXCLUDED.inline_text
        ''', chunk_id, source_id, mission_id, topic_id, 0,
             text, text_ref, len(text.split()))
    except Exception as e:
        print(f"[!] [Chunker] Failed to create chunks for {source_id}: {e}")
        # Fallback: create a single chunk
        chunk_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{source_id}:chunk:0"))
        try:
            await conn.execute('''
                INSERT INTO corpus.chunks (
                    chunk_id, source_id, mission_id, topic_id, chunk_index,
                    inline_text, text_ref, token_count
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                ON CONFLICT (chunk_id) DO UPDATE SET inline_text = EXCLUDED.inline_text
            ''', chunk_id, source_id, mission_id, topic_id, 0,
                 text, text_ref, len(text.split()))
        except Exception as e2:
            print(f"[!] [Chunker] Fallback chunk creation also failed: {e2}")

async def vampire_worker(worker_id: int = 0):
    print(f"[*] [Vampire-{worker_id}] Scout Node linked to Main PC ({MAIN_PC_IP})")
    
    # 1. Connect to Main PC triad
    try:
        # Use a shared pool if we spawn multiple local workers
        pg_pool = await asyncpg.create_pool(POSTGRES_DSN, min_size=1, max_size=5)
        redis_client = redis.Redis.from_url(REDIS_URL, decode_responses=True)
        print(f"[✓] [Vampire-{worker_id}] Connected to Postgres and Redis.")
    except Exception as e:
        print(f"[!] [Vampire-{worker_id}] Connection failed: {e}")
        return

    session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=60))
    
    while True:
        try:
            # 2. Dequeue from global queue
            result = await redis_client.blpop("queue:scraping", timeout=10)
            if not result:
                continue
                
            job = json.loads(result[1])
            url = job.get("url")
            topic_id = job.get("topic_id")
            mission_id = job.get("mission_id")
            
            print(f"[*] [Vampire-{worker_id}] Eating: {url}")
            
            # 3. Scrape via local Firecrawl
            async with session.post(f"{FIRECRAWL_URL}/v1/scrape", json={
                "url": url, "formats": ["markdown", "html"], "onlyMainContent": True
            }) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get("success"):
                        doc = data.get("data", {})
                        markdown = doc.get("markdown", "")
                        title = doc.get("metadata", {}).get("title", "")
                        checksum = hashlib.md5(markdown.encode()).hexdigest()
                        
                        # 4. Store result in Main PC Postgres (V3 Triad Logic)
                        async with pg_pool.acquire() as conn:
                            source_id = str(uuid.uuid4())
                            url_hash = hashlib.md5(url.encode()).hexdigest()

                            try:
                                # A. Store text content in corpus.text_refs (inline_text)
                                blob_id = f"blob:{source_id}"
                                await conn.execute('''
                                    INSERT INTO corpus.text_refs (
                                        blob_id, inline_text, metadata_json
                                    ) VALUES ($1, $2, $3)
                                    ON CONFLICT (blob_id) DO UPDATE SET inline_text = EXCLUDED.inline_text
                                ''', blob_id, markdown, json.dumps({
                                    "title": title,
                                    "source_url": url,
                                }))

                                # B. Corpus Source — WITH canonical_text_ref
                                await conn.execute('''
                                    INSERT INTO corpus.sources (
                                        source_id, mission_id, topic_id, url, normalized_url,
                                        normalized_url_hash, title, source_class, status, domain,
                                        canonical_text_ref, content_hash
                                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, 'fetched', $9, $10, $11)
                                    ON CONFLICT (mission_id, normalized_url_hash) DO UPDATE
                                    SET status = 'fetched', canonical_text_ref = $10, content_hash = $11
                                ''', source_id, mission_id, topic_id, url, url,
                                     url_hash, title, "web", urlparse(url).netloc, blob_id, checksum)

                                # C. Legacy Source (for refinery support)
                                await conn.execute('''
                                    INSERT INTO sources (topic_id, url, title, domain, content_hash, fetch_status)
                                    VALUES ($1, $2, $3, $4, $5, 'fetched')
                                    ON CONFLICT (topic_id, url) DO UPDATE SET fetch_status = 'fetched'
                                ''', uuid.UUID(topic_id), url, title, urlparse(url).netloc, checksum)

                                # D. Create chunks for the source (needed by distillery pipeline)
                                await _create_chunks_for_source(conn, source_id, mission_id, topic_id, markdown, blob_id)

                            except Exception as inner_e:
                                import traceback as tb
                                # Dead-letter: log failure to audit.pipeline_runs
                                scrape_run_id = f"scrape-{hashlib.sha256(url.encode()).hexdigest()[:8]}"
                                try:
                                    await conn.execute('''
                                        INSERT INTO audit.pipeline_runs (
                                            run_id, mission_id, topic_id, pipeline_type, pipeline_version,
                                            status, error_stage, error_class, error_detail, error_traceback
                                        ) VALUES ($1, $2, $3, 'scraping', 'v1.3.0-phase13',
                                                  'failed', 'source_ingest', $4, $5, $6)
                                        ON CONFLICT (run_id) DO UPDATE SET
                                            status = 'failed',
                                            error_stage = 'source_ingest',
                                            error_class = EXCLUDED.error_class,
                                            error_detail = EXCLUDED.error_detail,
                                            error_traceback = EXCLUDED.error_traceback
                                    ''', scrape_run_id, mission_id, topic_id,
                                        type(inner_e).__name__, str(inner_e), tb.format_exc())
                                except Exception:
                                    pass  # Don't let audit failure hide the original exception
                                raise

                        print(f"[✓] [Vampire-{worker_id}] Consumed: {url}")
                    else:
                        print(f"[!] [Vampire-{worker_id}] Firecrawl failed for {url}")
                else:
                    print(f"[!] [Vampire-{worker_id}] HTTP {resp.status} for {url}")
                    
        except Exception as e:
            print(f"[!] [Vampire-{worker_id}] Indigestion on {url if 'url' in locals() else 'unknown'}: {e}")
            await asyncio.sleep(2)

async def main():
    # Scale workers based on cores if running on the 20c node
    num_workers = int(os.getenv("VAMPIRE_WORKERS", "4"))
    tasks = [vampire_worker(i) for i in range(num_workers)]
    await asyncio.gather(*tasks)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
