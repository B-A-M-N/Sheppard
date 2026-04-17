import pytest

from src.core.system import SystemManager


class FakeRetriever:
    async def retrieve(self, query):
        return type("Ctx", (), {"is_empty": False})()

    def build_context_block(self, ctx, project_name=None):
        return "### Supporting Evidence\n- V3 evidence"


class FakeBridge:
    async def extract_reasoning_overlay(self, user_query):
        return {
            "supporting_beliefs": [{"claim": "Belief graph support", "confidence": 0.81}],
            "contradicting_beliefs": [],
        }

    def format_reasoning_overlay(self, reasoning_context):
        return "### Cross-Document Reasoning\n- Belief graph support (81%)"


@pytest.mark.asyncio
async def test_query_keeps_v3_as_canonical_and_appends_cmk_overlay():
    sm = SystemManager()
    sm._initialized = True
    sm.retriever = FakeRetriever()
    sm.chat_bridge = FakeBridge()

    result = await sm.query("find atoms", project_filter="mission-123")

    assert "### Supporting Evidence" in result
    assert "### Cross-Document Reasoning" in result
