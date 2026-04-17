from types import MethodType

import pytest

from src.core.system import SystemManager
from src.core.memory.cmk.session_runtime import SessionResult
from src.core.memory.cmk.working_state import WorkingState


class FakeOllama:
    def __init__(self):
        self.calls = []

    async def chat_stream(self, model, messages, system_prompt=None, temperature=None):
        self.calls.append(
            {
                "model": model,
                "messages": messages,
                "system_prompt": system_prompt,
                "temperature": temperature,
            }
        )
        for token in ["analysis", " response"]:
            yield token


class EscalatingBridge:
    async def process_session_turn(self, user_query, session_id, mission_id=None, topic_id=None):
        return SessionResult(
            route="analysis",
            working_state=WorkingState(session_id=session_id, mission_id=mission_id, topic_id=topic_id),
            analysis_brief="### ESCALATED ANALYSIS\n- DIAGNOSIS: Queue contention\n- RECOMMENDATION: Reduce contention",
        )


@pytest.mark.asyncio
async def test_chat_consumes_analysis_brief_and_skips_canonical_query():
    sm = SystemManager()
    sm._initialized = True
    sm.ollama = FakeOllama()
    sm.chat_bridge = EscalatingBridge()

    async def fail_query(self, *args, **kwargs):
        raise AssertionError("canonical query path should be skipped for escalated analysis")

    async def stop_reflection(self, response, user_input, context_used):
        return {"expand": False, "topics": []}

    sm.query = MethodType(fail_query, sm)
    sm._reflect_on_response = MethodType(stop_reflection, sm)

    chunks = []
    async for token in sm.chat(
        messages=[{"role": "user", "content": "diagnose the latency spike"}],
        project_context="mission-1",
        session_id="session-1",
    ):
        chunks.append(token)

    assert "".join(chunks) == "analysis response"
    assert sm.ollama.calls
    assert "ESCALATED ANALYSIS" in sm.ollama.calls[0]["system_prompt"]
    assert "Queue contention" in sm.ollama.calls[0]["system_prompt"]
    assert "--- KNOWLEDGE ---\n\n--- END KNOWLEDGE ---" in sm.ollama.calls[0]["system_prompt"]
