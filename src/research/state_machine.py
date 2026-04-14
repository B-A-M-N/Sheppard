"""
Simple state transition validator for corpus.sources.
DB enforces valid states via CHECK constraint.
Python enforces valid transitions.
"""


VALID_TRANSITIONS: dict[str, set[str]] = {
    "discovered": {"fetched"},
    "fetched": {"extracted", "error", "filtered_out"},
    "extracted": {"condensed", "filtered_out", "rejected"},
    "condensed": {"indexed"},
    "error": {"retrying", "dead_letter"},
    "retrying": {"fetched", "dead_letter"},
    # Terminal states: filtered_out, rejected, dead_letter, indexed
    # have no outgoing transitions.
}


def validate_transition(current: str, target: str) -> bool:
    """Check if a state transition is valid. Returns True if valid."""
    return target in VALID_TRANSITIONS.get(current, set())


async def transition_source_status(
    adapter, source_id: str, target_status: str, current_status: str | None = None
) -> bool:
    """
    Atomically transition a source's status.
    Uses UPDATE ... WHERE status = current_status to prevent races.
    Returns True if transition was applied, False if race lost or source not found.
    """
    if current_status is None:
        row = await adapter.pg.fetch_one(
            "corpus.sources", {"source_id": source_id}
        )
        if not row:
            return False
        current_status = row["status"]

    if not validate_transition(current_status, target_status):
        raise ValueError(
            f"Invalid transition: {current_status} -> {target_status}. "
            f"Valid targets: {VALID_TRANSITIONS.get(current_status, set())}"
        )

    conn = await adapter.pg.pool.acquire()
    try:
        result = await conn.execute(
            "UPDATE corpus.sources SET status = $1 WHERE source_id = $2 AND status = $3",
            target_status, source_id, current_status
        )
        return result == "UPDATE 1"
    finally:
        await adapter.pg.pool.release(conn)
