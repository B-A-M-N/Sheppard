import pytest

from src.core.memory.cmk.runtime import CMKRuntime
from src.core.memory.cmk.types import CMKAtom, Concept


@pytest.mark.asyncio
async def test_load_concepts_backfills_atoms_from_store():
    runtime = CMKRuntime()

    concept = Concept(
        id="concept-1",
        name="concept",
        summary="summary",
        atom_ids=["a1", "a2"],
        centroid=[1.0, 0.0],
        reliability=0.9,
        centrality=0.8,
        topic_id="topic-1",
        mission_id="mission-1",
    )
    atoms = [
        CMKAtom(id="a1", content="alpha", topic_id="topic-1", mission_id="mission-1"),
        CMKAtom(id="a2", content="beta", topic_id="topic-1", mission_id="mission-1"),
    ]

    async def _load_concepts(topic_id=None):
        assert topic_id == "topic-1"
        return [concept]

    async def _load_atoms(atom_ids=None, topic_id=None, mission_id=None, limit=500):
        assert atom_ids == ["a1", "a2"]
        assert topic_id == "topic-1"
        assert mission_id is None
        return atoms

    runtime.store.load_concepts = _load_concepts
    runtime.store.load_atoms = _load_atoms

    count = await runtime.load_concepts(topic_filter="topic-1")

    assert count == 1
    assert set(runtime.atoms) == {"a1", "a2"}
    assert runtime.concept_retriever is not None
    expanded = runtime.concept_retriever.expand_concept(concept)
    assert [atom.id for atom in expanded] == ["a1", "a2"]


@pytest.mark.asyncio
async def test_query_with_concepts_respects_filters_and_falls_back():
    runtime = CMKRuntime()
    runtime.embedder.embed = lambda _: [1.0, 0.0]

    matching = CMKAtom(id="a1", content="match", topic_id="topic-1", mission_id="mission-1", reliability=0.9)
    non_matching = CMKAtom(id="a2", content="miss", topic_id="topic-2", mission_id="mission-2", reliability=0.8)
    concept = Concept(
        id="concept-1",
        name="concept",
        summary="summary",
        atom_ids=["a1", "a2"],
        centroid=[1.0, 0.0],
        reliability=0.9,
        centrality=0.8,
    )
    runtime.atoms = {"a1": matching, "a2": non_matching}

    class FakeRetriever:
        def retrieve_and_expand(self, query_vec, top_k=5):
            return ([(concept, 0.9)], [matching, non_matching])

    runtime.concept_retriever = FakeRetriever()

    async def _fallback(user_query, topic_filter=None, mission_filter=None):
        return {
            "user_query": user_query,
            "topic_filter": topic_filter,
            "mission_filter": mission_filter,
        }

    runtime.query = _fallback

    pack = await runtime.query_with_concepts(
        "question",
        top_k_concepts=3,
        topic_filter="topic-1",
        mission_filter="mission-1",
    )

    assert [atom.id for atom in pack.usable_atoms] == ["a1"]

    fallback = await runtime.query_with_concepts(
        "question",
        top_k_concepts=3,
        topic_filter="missing-topic",
        mission_filter="missing-mission",
    )

    assert fallback == {
        "user_query": "question",
        "topic_filter": "missing-topic",
        "mission_filter": "missing-mission",
    }
