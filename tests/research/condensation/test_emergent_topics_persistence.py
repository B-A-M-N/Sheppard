import pytest

from src.research.condensation.pipeline import DistillationPipeline, _is_low_signal_atom


class FakeAdapter:
    def __init__(self):
        self.snapshots = {}

    async def get_latest_frontier_checkpoint(self, mission_id):
        return self.snapshots.get(mission_id)

    async def checkpoint_frontier(self, mission_id, snapshot):
        self.snapshots[mission_id] = snapshot

    class pg:
        @staticmethod
        async def fetch_many(*args, **kwargs):
            return []


@pytest.mark.asyncio
async def test_record_emergent_topics_uses_checkpoint_snapshot():
    adapter = FakeAdapter()
    pipeline = DistillationPipeline(ollama=None, memory=None, budget=None, adapter=adapter)

    await pipeline._record_emergent_topics(
        mission_id="mission-1",
        mission_title="AI Agents",
        concept_counts={
            "authentication and authorization": 6,
            "ai agents": 8,
            "overview": 9,
        },
    )

    snapshot = adapter.snapshots["mission-1"]
    assert snapshot["emergent_topics"] == [
        {
            "concept": "authentication and authorization",
            "atom_count": 6,
            "source_mission": "mission-1",
        }
    ]


def test_low_signal_atom_rejects_boilerplate():
    assert _is_low_signal_atom(
        {"text": "The https:// ensures that you are connecting to the official website and that any information you provide is encrypted and transmitted securely."},
        "AI Agents",
    ) is True


def test_low_signal_atom_accepts_mission_relevant_content():
    assert _is_low_signal_atom(
        {"text": "Authentication and authorization mechanisms are critical for coordinating AI agents across multi-tenant systems."},
        "AI Agents",
    ) is False
