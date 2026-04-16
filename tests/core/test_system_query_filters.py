import pytest

from src.core.system import SystemManager


class FakeRetriever:
    def __init__(self):
        self.query = None

    async def retrieve(self, query):
        self.query = query
        return type("Ctx", (), {"is_empty": True})()

    def build_context_block(self, ctx, project_name=None):
        return ""


@pytest.mark.asyncio
async def test_query_maps_project_filter_to_mission_filter():
    sm = SystemManager()
    sm._initialized = True
    sm.chat_bridge = None
    sm.retriever = FakeRetriever()

    await sm.query("find atoms", project_filter="mission-123", topic_filter="topic-456")

    assert sm.retriever.query is not None
    assert sm.retriever.query.project_filter == "mission-123"
    assert sm.retriever.query.mission_filter == "mission-123"
    assert sm.retriever.query.topic_filter == "topic-456"
