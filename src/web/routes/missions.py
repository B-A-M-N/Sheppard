"""
routes/missions.py — Mission management REST endpoints.

GET  /api/missions            — list all missions with atom counts
GET  /api/missions/{id}       — single mission detail + events
POST /api/missions            — start a new mission (/learn)
DELETE /api/missions/{id}     — cancel a mission
"""

import logging
from decimal import Decimal

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from src.core.system import system_manager


def _num(v, default=0):
    """Convert Decimal/None to a plain int or float for JSON serialisation."""
    if v is None:
        return default
    if isinstance(v, Decimal):
        return int(v) if v == v.to_integral_value() else float(v)
    return v

router = APIRouter()
logger = logging.getLogger(__name__)


class StartMissionRequest(BaseModel):
    topic: str
    ceiling_gb: float = 5.0
    academic_only: bool = False


@router.get("/missions")
async def list_missions():
    """All missions: live status from system_manager + full DB rows."""
    live = system_manager.status().get("missions", {})

    try:
        pg = system_manager.adapter.pg
        rows = await pg.fetch_many(
            "mission.research_missions",
            order_by="created_at DESC",
            limit=100,
        )
    except Exception as e:
        logger.error("[missions] DB fetch failed: %s", e)
        rows = []

    # Pull atom counts per mission in one query
    atom_counts: dict[str, int] = {}
    try:
        async with pg.pool.acquire() as conn:
            count_rows = await conn.fetch(
                """
                SELECT topic_id, COUNT(*) as cnt
                FROM knowledge.knowledge_atoms
                GROUP BY topic_id
                """
            )
            for r in count_rows:
                atom_counts[r["topic_id"]] = r["cnt"]
    except Exception as e:
        logger.warning("[missions] atom count query failed: %s", e)

    missions = []
    for row in rows:
        mid = row["mission_id"]
        live_info = live.get(mid, {})
        missions.append({
            "mission_id": mid,
            "title": row["title"],
            "objective": row["objective"],
            "status": row["status"],
            "created_at": row["created_at"].isoformat() if row.get("created_at") else None,
            "completed_at": row["completed_at"].isoformat() if row.get("completed_at") else None,
            "atom_count": _num(atom_counts.get(mid), 0),
            "source_count": _num(row.get("source_count"), 0),
            "bytes_ingested": _num(row.get("bytes_ingested"), 0),
            "budget_bytes": _num(row.get("budget_bytes"), 0),
            "crawling": live_info.get("crawling", False),
            "usage": live_info.get("usage", "0.0%"),
        })

    return JSONResponse({"missions": missions})


@router.get("/missions/{mission_id}")
async def get_mission(mission_id: str):
    """Single mission with recent events and sample atoms."""
    try:
        pg = system_manager.adapter.pg
        row = await pg.fetch_one("mission.research_missions", {"mission_id": mission_id})
        if not row:
            raise HTTPException(404, "Mission not found")

        async with pg.pool.acquire() as conn:
            atom_count = await conn.fetchval(
                "SELECT COUNT(*) FROM knowledge.knowledge_atoms WHERE topic_id = $1",
                mission_id,
            )

        events = await pg.fetch_many(
            "mission.mission_events",
            where={"mission_id": mission_id},
            order_by="created_at DESC",
            limit=20,
        )

        atoms = await pg.fetch_many(
            "knowledge.knowledge_atoms",
            where={"topic_id": mission_id},
            order_by="created_at DESC",
            limit=50,
        )

        return JSONResponse({
            "mission": {
                "mission_id": row["mission_id"],
                "title": row["title"],
                "objective": row["objective"],
                "status": row["status"],
                "created_at": row["created_at"].isoformat() if row.get("created_at") else None,
                "completed_at": row["completed_at"].isoformat() if row.get("completed_at") else None,
                "atom_count": _num(atom_count),
                "source_count": _num(row.get("source_count"), 0),
                "bytes_ingested": _num(row.get("bytes_ingested"), 0),
                "budget_bytes": _num(row.get("budget_bytes"), 0),
            },
            "events": [
                {
                    "event_type": e.get("event_type"),
                    "payload": e.get("payload_json"),
                    "created_at": e["created_at"].isoformat() if e.get("created_at") else None,
                }
                for e in events
            ],
            "atoms": [
                {
                    "atom_id": a["atom_id"],
                    "statement": a.get("statement", ""),
                    "atom_type": a.get("atom_type", "claim"),
                    "confidence": _num(a.get("confidence"), 0),
                    "importance": _num(a.get("importance"), 0),
                }
                for a in atoms
            ],
        })
    except HTTPException:
        raise
    except Exception as e:
        logger.error("[missions/%s] error: %s", mission_id, e)
        raise HTTPException(500, str(e))


@router.post("/missions")
async def start_mission(req: StartMissionRequest):
    """Start a new learning mission."""
    try:
        mission_id = await system_manager.learn(
            topic_name=req.topic,
            query=req.topic,
            ceiling_gb=req.ceiling_gb,
            academic_only=req.academic_only,
        )
        return JSONResponse({"mission_id": mission_id, "topic": req.topic}, status_code=201)
    except Exception as e:
        logger.error("[missions] start failed: %s", e)
        raise HTTPException(500, str(e))


@router.delete("/missions/{mission_id}")
async def delete_mission(mission_id: str):
    """
    Cancel an active mission, or delete a completed/failed one from the DB.
    Active missions are cancelled first, then removed.
    """
    try:
        pg = system_manager.adapter.pg

        # Cancel if active (no-op if already done/failed)
        await system_manager.cancel_mission(mission_id)

        # Verify mission exists before deleting
        row = await pg.fetch_one("mission.research_missions", {"mission_id": mission_id})
        if not row:
            raise HTTPException(404, "Mission not found")

        async with pg.pool.acquire() as conn:
            # authority tables use ON DELETE NO ACTION — must be removed before the mission row
            await conn.execute(
                "DELETE FROM authority.synthesis_artifacts WHERE mission_id = $1", mission_id
            )
            await conn.execute(
                "DELETE FROM authority.synthesis_sections WHERE mission_id = $1", mission_id
            )
            # knowledge_atoms uses topic_id (no FK), so cascade from the mission row won't catch it.
            # Delete atoms explicitly; their dependents (atom_entities, embeddings, etc.)
            # all have ON DELETE CASCADE from knowledge_atoms so they go automatically.
            await conn.execute(
                "DELETE FROM knowledge.knowledge_atoms WHERE topic_id = $1", mission_id
            )
            # Deleting the mission cascades to corpus.sources/chunks/clusters,
            # mission_events, mission_frontier_snapshots, mission_mode_runs, mission_nodes.
            await conn.execute(
                "DELETE FROM mission.research_missions WHERE mission_id = $1", mission_id
            )

        return JSONResponse({"deleted": mission_id})
    except HTTPException:
        raise
    except Exception as e:
        logger.error("[missions/%s] delete failed: %s", mission_id, e)
        raise HTTPException(500, str(e))
