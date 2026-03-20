
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
                            # A. Corpus Source
                            await conn.execute('''
                                INSERT INTO corpus.sources (
                                    source_id, mission_id, topic_id, url, normalized_url, 
                                    normalized_url_hash, title, source_class, status, domain
                                )
                                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, 'fetched', $9)
                                ON CONFLICT (mission_id, normalized_url_hash) DO UPDATE 
                                SET status = 'fetched'
                            ''', str(uuid.uuid4()), mission_id, topic_id, url, url, 
                                 checksum, title, "web", urlparse(url).netloc)
                            
                            # B. Legacy Source (for refinery support)
                            await conn.execute('''
                                INSERT INTO sources (topic_id, url, title, domain, content_hash, fetch_status)
                                VALUES ($1, $2, $3, $4, $5, 'fetched')
                                ON CONFLICT (topic_id, url) DO UPDATE SET fetch_status = 'fetched'
                            ''', uuid.UUID(topic_id), url, title, urlparse(url).netloc, checksum)
                            
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
