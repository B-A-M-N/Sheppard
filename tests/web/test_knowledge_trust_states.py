import pytest

from src.web.routes import knowledge


class _FakeConn:
    def __init__(self):
        self.calls = 0

    async def fetchval(self, query, *args):
        if "knowledge.knowledge_atoms" in query:
            return 10
        if "mission.research_missions" in query and "completed" in query:
            return 1
        if "mission.research_missions" in query and "active" in query:
            return 2
        if "mission.research_missions" in query:
            return 3
        if "knowledge.atom_entities" in query:
            return 4
        if "corpus.sources" in query:
            return 5
        return 0

    async def fetch(self, query, *args):
        if "FROM authority.authority_records" in query:
            return [
                {
                    "status_json": {"maturity": "synthesized", "successful_application_count": 1},
                    "advisory_layer_json": {},
                    "reuse_json": {"application_history": [{"id": 1}]},
                },
                {
                    "status_json": {"maturity": "contested"},
                    "advisory_layer_json": {"major_contradictions": ["x"]},
                    "reuse_json": {},
                },
            ]
        raise AssertionError(query)


class _Acquire:
    async def __aenter__(self):
        return _FakeConn()

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _Pool:
    def acquire(self):
        return _Acquire()


class _PG:
    pool = _Pool()


class _Adapter:
    pg = _PG()


@pytest.mark.asyncio
async def test_knowledge_stats_returns_trust_state_counts(monkeypatch):
    monkeypatch.setattr(knowledge.system_manager, "adapter", _Adapter())

    response = await knowledge.knowledge_stats()

    assert response.status_code == 200
    payload = response.body.decode()
    assert '"reusable":1' in payload
    assert '"contested":1' in payload
