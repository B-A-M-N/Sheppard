
import asyncio
import os
import signal
import sys
import uuid
import logging
import asyncpg
import traceback
from src.core.system import system_manager
from src.research.acquisition.budget import CondensationPriority

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("Refinery")

async def refinery_loop():
    # 1. Initialize System
    print("[*] Initializing System Components...")
    success, err = await system_manager.initialize()
    if not success:
        print(f"[!] System Init Failed: {err}")
        return

    print("[*] Global V3 Refinery Online. Smelting technical ore...")
    
    # 2. Setup Database Connection
    from src.config.database import DatabaseConfig
    pg_dsn = DatabaseConfig.DB_URLS.get("semantic_memory")
    pool = await asyncpg.create_pool(pg_dsn, min_size=1, max_size=5)

    try:
        while True:
            try:
                # 3. Find work via V3 Tables
                async with pool.acquire() as conn:
                    # Find a mission with fetched but uncondensed sources
                    mission = await conn.fetchrow('''
                        SELECT m.mission_id, m.title, COUNT(s.source_id) as backlog
                        FROM mission.research_missions m
                        JOIN corpus.sources s ON s.mission_id = m.mission_id
                        WHERE s.status = 'fetched'
                        GROUP BY m.mission_id, m.title
                        ORDER BY backlog DESC
                        LIMIT 1
                    ''')
                    
                    if not mission or mission['backlog'] == 0:
                        # No work found, sleep longer
                        await asyncio.sleep(15)
                        continue
                        
                    mission_id = mission['mission_id']
                    title = mission['title']
                    backlog = mission['backlog']
                    
                    print(f"[*] Batch Found: '{title}' ({backlog} sources pending)")
                    
                    # 4. Process Batch (Uses the adapter inside system_manager)
                    # This marks sources as 'condensed' inside corpus.sources
                    await system_manager.condenser.run(mission_id, CondensationPriority.LOW)
                    
                    # 5. Progress Report
                    atom_count = await conn.fetchval(
                        "SELECT count(*) FROM knowledge.knowledge_atoms WHERE mission_id = $1", 
                        mission_id
                    )
                    print(f"[✓] Extracted {atom_count or 0} atoms for Mission {mission_id[:8]}...")
                
                # Small breather between batches
                await asyncio.sleep(2)
                
            except Exception as loop_err:
                print(f"[!] Loop Error: {loop_err}")
                traceback.print_exc()
                await asyncio.sleep(5)
            
    except asyncio.CancelledError:
        print("[*] Refinery shutdown signal received.")
    finally:
        print("[*] Closing Refinery Database Pool...")
        await pool.close()

async def main():
    # Handle graceful exit
    stop_event = asyncio.Event()
    
    def shutdown_handler():
        print("\n[*] Stopping refinery...")
        stop_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, shutdown_handler)

    refinery_task = asyncio.create_task(refinery_loop())
    
    # Block until shutdown signal
    await stop_event.wait()
    
    # Trigger cancellation
    refinery_task.cancel()
    try:
        await refinery_task
    except asyncio.CancelledError:
        pass
    
    # Final system cleanup
    print("[*] Performing final system cleanup...")
    await system_manager.cleanup()
    print("[*] Refinery offline.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(f"Fatal Startup Error: {e}")
        traceback.print_exc()
