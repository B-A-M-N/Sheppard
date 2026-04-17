from datetime import datetime, timezone

import pytest

from src.core.memory.cmk.belief_graph import BeliefGraph


class FakeConn:
    def __init__(self, node_rows, edge_rows=None, error=None):
        self.node_rows = node_rows
        self.edge_rows = edge_rows or []
        self.error = error
        self.calls = 0

    async def fetch(self, _query):
        if self.error is not None:
            raise self.error
        self.calls += 1
        return self.node_rows if self.calls == 1 else self.edge_rows


class _Acquire:
    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, exc_type, exc, tb):
        return False


class FakePool:
    def __init__(self, conn):
        self.conn = conn

    def acquire(self):
        return _Acquire(self.conn)


@pytest.mark.asyncio
async def test_load_from_db_populates_nodes_and_edges():
    now = datetime.now(timezone.utc)
    conn = FakeConn(
        node_rows=[
            {
                "id": "n1",
                "canonical_id": None,
                "claim": "claim one",
                "domain": "d1",
                "authority_score": 0.8,
                "stability_score": 0.7,
                "contradiction_pressure": 0.1,
                "revision_count": 2,
                "embedding": "[1.0, 2.0]",
                "created_at": now,
                "updated_at": now,
            },
            {
                "id": "n2",
                "canonical_id": "c2",
                "claim": "claim two",
                "domain": "d2",
                "authority_score": 0.6,
                "stability_score": 0.5,
                "contradiction_pressure": 0.0,
                "revision_count": 0,
                "embedding": None,
                "created_at": now,
                "updated_at": now,
            },
        ],
        edge_rows=[
            {
                "id": "e1",
                "from_node": "n1",
                "to_node": "n2",
                "relation_type": "supports",
                "strength": 0.9,
                "evidence_atom_ids": ["a1"],
                "reason": "reason",
                "created_at": now,
            },
            {
                "id": "e2",
                "from_node": "n1",
                "to_node": "missing",
                "relation_type": "supports",
                "strength": 0.5,
                "evidence_atom_ids": [],
                "reason": "",
                "created_at": now,
            },
        ],
    )
    graph = BeliefGraph(pg_pool=FakePool(conn))

    count = await graph.load_from_db()

    assert count == 2
    assert set(graph._nodes) == {"n1", "n2"}
    assert set(graph._edges) == {"e1"}
    assert graph._nodes["n1"].embedding == [1.0, 2.0]
    assert graph._nodes["n1"].neighbor_count == 1
    assert graph._nodes["n2"].neighbor_count == 1
    assert graph._outgoing["n1"] == ["e1"]
    assert graph._incoming["n2"] == ["e1"]


@pytest.mark.asyncio
async def test_load_from_db_returns_zero_when_tables_missing():
    graph = BeliefGraph(pg_pool=FakePool(FakeConn([], error=Exception('relation "belief_nodes" does not exist'))))

    count = await graph.load_from_db()

    assert count == 0
    assert graph._nodes == {}
    assert graph._edges == {}
