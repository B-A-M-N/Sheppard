"""
routes/knowledge.py — Knowledge base REST endpoints.

GET /api/knowledge/graph          — D3 force graph: mission nodes + concept nodes + edges
GET /api/knowledge/atoms          — paginated atom table, filterable by mission/concept
GET /api/knowledge/concepts       — top concepts with atom counts (for sidebar)
GET /api/knowledge/stats          — overall knowledge base stats
"""

import logging
import json

from fastapi import APIRouter, Query, HTTPException
from fastapi.responses import JSONResponse

from src.core.system import system_manager
from src.research.reasoning.trust_state import derive_trust_state

router = APIRouter()
logger = logging.getLogger(__name__)

# Noise patterns for the atom quality filter.
# Stored as LIKE patterns (with % wildcards) so they can be passed as a
# parameterized array to Postgres: NOT (LOWER(statement) LIKE ANY($n::text[]))
_NOISE_PATTERNS: list[str] = [f"%{frag}%" for frag in [
    "click here", "read more", "https://", "http://", "cookie",
    "subscribe", "sign in", "log in", "javascript", "404",
    "unable to load", "access denied", "internet explorer",
    "mozilla firefox", "google chrome", "microsoft edge",
    "403 forbidden", "wikimedia", "a request was made",
    "requires javascript", "please enable", "client certificate",
    "page not found", "portico", "ovid",
    ".gov means", "official website", "encrypted and transmitted",
    "lippincott", "the article is", "the article was",
    "federal government", "end in .gov", "end in .mil",
    "too many requests", "rate limit", "captcha",
    "not-for-profit", "ieee is the world", "ieee ieee",
    "the link you requested", "might be broken",
    "master generative ai", "real-world projects",
    "the thesis is titled", "the chapter is",
    "computer network fundamentals is a chapter",
]]


def _json_dict(value) -> dict:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def _authority_trust_state(status_value, advisory_value=None, reuse_value=None) -> str:
    return derive_trust_state(
        _json_dict(status_value),
        _json_dict(advisory_value),
        _json_dict(reuse_value),
    )


@router.get("/knowledge/stats")
async def knowledge_stats():
    """High-level numbers: total atoms, missions, concepts, sources."""
    try:
        pg = system_manager.adapter.pg
        async with pg.pool.acquire() as conn:
            total_atoms = await conn.fetchval("SELECT COUNT(*) FROM knowledge.knowledge_atoms")
            total_missions = await conn.fetchval("SELECT COUNT(*) FROM mission.research_missions")
            total_concepts = await conn.fetchval(
                "SELECT COUNT(DISTINCT entity_name) FROM knowledge.atom_entities WHERE entity_type='concept'"
            )
            total_sources = await conn.fetchval("SELECT COUNT(*) FROM corpus.sources")
            completed = await conn.fetchval(
                "SELECT COUNT(*) FROM mission.research_missions WHERE status='completed'"
            )
            active = await conn.fetchval(
                "SELECT COUNT(*) FROM mission.research_missions WHERE status='active'"
            )
            trust_rows = await conn.fetch(
                """
                SELECT status_json, advisory_layer_json, reuse_json
                FROM authority.authority_records
                """
            )
        trust_states = {
            "forming": 0,
            "synthesized": 0,
            "contested": 0,
            "stale": 0,
            "reusable": 0,
        }
        for row in trust_rows:
            trust_states[_authority_trust_state(
                row.get("status_json"),
                row.get("advisory_layer_json"),
                row.get("reuse_json"),
            )] += 1
        return JSONResponse({
            "total_atoms": total_atoms,
            "total_missions": total_missions,
            "completed_missions": completed,
            "active_missions": active,
            "total_concepts": total_concepts,
            "total_sources": total_sources,
            "trust_states": trust_states,
        })
    except Exception as e:
        logger.error("[knowledge/stats] %s", e)
        raise HTTPException(500, str(e))


@router.get("/knowledge/graph")
async def knowledge_graph(mission_id: str = Query(None)):
    """
    D3-ready graph payload.
    Nodes: missions (type='mission') + concepts (type='concept')
    Links: mission → concept edges weighted by atom count
    """
    try:
        pg = system_manager.adapter.pg
        async with pg.pool.acquire() as conn:
            if mission_id:
                rows = await conn.fetch(
                    """
                    SELECT ae.entity_name, COUNT(*) as cnt, ka.topic_id
                    FROM knowledge.atom_entities ae
                    JOIN knowledge.knowledge_atoms ka ON ka.atom_id = ae.atom_id
                    WHERE ae.entity_type = 'concept'
                      AND ka.topic_id = $1
                    GROUP BY ae.entity_name, ka.topic_id
                    ORDER BY cnt DESC
                    LIMIT 80
                    """,
                    mission_id,
                )
            else:
                rows = await conn.fetch(
                    """
                    SELECT ae.entity_name, COUNT(*) as cnt, ka.topic_id
                    FROM knowledge.atom_entities ae
                    JOIN knowledge.knowledge_atoms ka ON ka.atom_id = ae.atom_id
                    WHERE ae.entity_type = 'concept'
                    GROUP BY ae.entity_name, ka.topic_id
                    ORDER BY cnt DESC
                    LIMIT 150
                    """,
                )

            missions_raw = await conn.fetch(
                "SELECT mission_id, title, status FROM mission.research_missions"
            )

        mission_map = {r["mission_id"]: r for r in missions_raw}

        nodes = {}
        links = []

        if rows:
            # Concept graph — atom_entities populated
            for r in rows:
                topic_id = r["topic_id"]
                concept = r["entity_name"]
                cnt = r["cnt"]

                if topic_id not in nodes:
                    m = mission_map.get(topic_id, {})
                    trust_row = m.get("status_json") if isinstance(m, dict) else None
                    nodes[topic_id] = {
                        "id": topic_id,
                        "label": m.get("title", topic_id[:8]),
                        "type": "mission",
                        "status": m.get("status", "unknown"),
                        "trust_state": m.get("trust_state", "forming"),
                    }

                cid = f"concept:{concept}"
                if cid not in nodes:
                    nodes[cid] = {"id": cid, "label": concept, "type": "concept", "weight": 0}
                nodes[cid]["weight"] = nodes[cid].get("weight", 0) + cnt
                links.append({"source": topic_id, "target": cid, "value": cnt})
        else:
            # Fallback: deduplicated topic graph — one node per unique topic title,
            # sized by total atoms across all runs, no meaningless same-title links.
            async with pg.pool.acquire() as conn:
                topic_rows = await conn.fetch(
                    """
                    SELECT LOWER(TRIM(m.title)) as norm_title,
                           MAX(m.title) as display_title,
                           MAX(m.status) as status,
                           SUM(ka_count.cnt) as total_atoms,
                           COUNT(DISTINCT m.mission_id) as run_count,
                           MAX(ka_count.avg_conf) as avg_conf,
                           MAX(ar.status_json) as status_json,
                           MAX(ar.advisory_layer_json) as advisory_layer_json,
                           MAX(ar.reuse_json) as reuse_json
                    FROM mission.research_missions m
                    JOIN (
                        SELECT topic_id,
                               COUNT(*) as cnt,
                               AVG(confidence) as avg_conf
                        FROM knowledge.knowledge_atoms
                        GROUP BY topic_id
                    ) ka_count ON ka_count.topic_id = m.mission_id
                    LEFT JOIN authority.authority_records ar ON ar.topic_id = m.mission_id
                    GROUP BY LOWER(TRIM(m.title))
                    ORDER BY total_atoms DESC
                    LIMIT 60
                    """
                )

            for r in topic_rows:
                if not r["total_atoms"]:
                    continue
                nid = f"topic:{r['norm_title']}"
                nodes[nid] = {
                    "id": nid,
                    "label": r["display_title"],
                    "type": "mission",
                    "status": r["status"] or "unknown",
                    "weight": int(r["total_atoms"]),
                    "run_count": int(r["run_count"]),
                    "avg_conf": round(float(r["avg_conf"] or 0), 2),
                    "trust_state": _authority_trust_state(
                        r.get("status_json"),
                        r.get("advisory_layer_json"),
                        r.get("reuse_json"),
                    ),
                }

        return JSONResponse({
            "nodes": list(nodes.values()),
            "links": links,
        })
    except Exception as e:
        logger.error("[knowledge/graph] %s", e)
        raise HTTPException(500, str(e))


@router.get("/knowledge/atoms")
async def list_atoms(
    mission_id: str = Query(None),
    concept: str = Query(None),
    min_confidence: float = Query(0.3, ge=0.0, le=1.0),
    min_importance: float = Query(0.55, ge=0.0, le=1.0),  # excludes default-scored 0.5 atoms
    sort: str = Query("importance"),
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
):
    """Paginated atom table. Filtered by confidence + importance, sortable, filterable by mission/concept."""
    sort_col = {
        "confidence": "ka.confidence DESC, ka.importance DESC",
        "importance": "ka.importance DESC, ka.confidence DESC",
        "created_at": "ka.created_at DESC",
    }.get(sort, "ka.importance DESC, ka.confidence DESC")

    try:
        pg = system_manager.adapter.pg
        async with pg.pool.acquire() as conn:
            # Fixed params: $1=min_confidence, $2=min_importance, $3=noise patterns array
            # Dynamic params start at $4
            conditions = [
                "ka.confidence >= $1",
                "ka.importance >= $2",
                "NOT (LOWER(ka.statement) LIKE ANY($3::text[]))",
                "LENGTH(ka.statement) >= 40",
                # Real factual claims end with sentence-terminating punctuation.
                # Paper titles, headings, and navigation text almost never do.
                "(ka.statement LIKE '%.') OR (ka.statement LIKE '%!') OR "
                "(ka.statement LIKE '%?') OR (ka.statement LIKE '%)') OR "
                "(ka.statement LIKE '%.]')",
            ]
            params: list = [min_confidence, min_importance, _NOISE_PATTERNS]
            p = 4

            if mission_id:
                conditions.append(f"ka.topic_id = ${p}")
                params.append(mission_id)
                p += 1

            where = " AND ".join(conditions)

            if concept:
                rows = await conn.fetch(
                    f"""
                    SELECT ka.atom_id, ka.statement, ka.atom_type, ka.confidence,
                           ka.importance, ka.created_at, ka.topic_id,
                           m.title as mission_title,
                           ar.status_json,
                           ar.advisory_layer_json,
                           ar.reuse_json
                    FROM knowledge.knowledge_atoms ka
                    JOIN knowledge.atom_entities ae ON ae.atom_id = ka.atom_id
                    JOIN mission.research_missions m ON m.mission_id = ka.topic_id
                    LEFT JOIN authority.authority_records ar ON ar.topic_id = ka.topic_id
                    WHERE {where}
                      AND ae.entity_name ILIKE ${p}
                      AND ae.entity_type = 'concept'
                    ORDER BY {sort_col}
                    LIMIT ${p+1} OFFSET ${p+2}
                    """,
                    *params, concept, limit, offset,
                )
                total = await conn.fetchval(
                    f"""
                    SELECT COUNT(*)
                    FROM knowledge.knowledge_atoms ka
                    JOIN knowledge.atom_entities ae ON ae.atom_id = ka.atom_id
                    WHERE {where}
                      AND ae.entity_name ILIKE ${p}
                      AND ae.entity_type = 'concept'
                    """,
                    *params, concept,
                )
            else:
                rows = await conn.fetch(
                    f"""
                    SELECT ka.atom_id, ka.statement, ka.atom_type, ka.confidence,
                           ka.importance, ka.created_at, ka.topic_id,
                           m.title as mission_title,
                           ar.status_json,
                           ar.advisory_layer_json,
                           ar.reuse_json
                    FROM knowledge.knowledge_atoms ka
                    JOIN mission.research_missions m ON m.mission_id = ka.topic_id
                    LEFT JOIN authority.authority_records ar ON ar.topic_id = ka.topic_id
                    WHERE {where}
                    ORDER BY {sort_col}
                    LIMIT ${p} OFFSET ${p+1}
                    """,
                    *params, limit, offset,
                )
                total = await conn.fetchval(
                    f"SELECT COUNT(*) FROM knowledge.knowledge_atoms ka WHERE {where}",
                    *params,
                )

        return JSONResponse({
            "total": total,
            "offset": offset,
            "limit": limit,
            "min_confidence": min_confidence,
            "atoms": [
                {
                    "atom_id": r["atom_id"],
                    "statement": r["statement"],
                    "atom_type": r["atom_type"],
                    "confidence": round(float(r["confidence"]), 3) if r["confidence"] is not None else None,
                    "importance": round(float(r["importance"]), 3) if r["importance"] is not None else None,
                    "created_at": r["created_at"].isoformat() if r.get("created_at") else None,
                    "mission_title": r.get("mission_title", ""),
                    "topic_id": r["topic_id"],
                    "trust_state": _authority_trust_state(
                        r.get("status_json"),
                        r.get("advisory_layer_json"),
                        r.get("reuse_json"),
                    ),
                }
                for r in rows
            ],
        })
    except Exception as e:
        logger.error("[knowledge/atoms] %s", e)
        raise HTTPException(500, str(e))


@router.get("/knowledge/concepts")
async def list_concepts(
    mission_id: str = Query(None),
    limit: int = Query(60, le=200),
):
    """Top concepts with atom counts, optionally filtered to a mission."""
    try:
        pg = system_manager.adapter.pg
        async with pg.pool.acquire() as conn:
            if mission_id:
                rows = await conn.fetch(
                    """
                    SELECT ae.entity_name, COUNT(*) as cnt
                    FROM knowledge.atom_entities ae
                    JOIN knowledge.knowledge_atoms ka ON ka.atom_id = ae.atom_id
                    WHERE ae.entity_type = 'concept' AND ka.topic_id = $1
                    GROUP BY ae.entity_name
                    ORDER BY cnt DESC
                    LIMIT $2
                    """,
                    mission_id, limit,
                )
            else:
                rows = await conn.fetch(
                    """
                    SELECT ae.entity_name, COUNT(*) as cnt
                    FROM knowledge.atom_entities ae
                    WHERE ae.entity_type = 'concept'
                    GROUP BY ae.entity_name
                    ORDER BY cnt DESC
                    LIMIT $1
                    """,
                    limit,
                )

        return JSONResponse({
            "concepts": [{"name": r["entity_name"], "count": r["cnt"]} for r in rows]
        })
    except Exception as e:
        logger.error("[knowledge/concepts] %s", e)
        raise HTTPException(500, str(e))
