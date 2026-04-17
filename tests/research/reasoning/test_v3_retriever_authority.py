import pytest

from src.research.reasoning.v3_retriever import V3Retriever
from src.research.reasoning.retriever import RetrievalQuery


class FakeChroma:
    async def query(self, collection, query_text=None, where=None, limit=20, query_texts=None):
        if collection == "knowledge_atoms":
            return {
                "documents": [["Atom evidence."]],
                "metadatas": [[{
                    "atom_id": "atom-1",
                    "atom_type": "claim",
                    "trust_score": 0.8,
                    "source_url": "https://example.com",
                    "captured_at": None,
                    "citation_key": "[A1]",
                }]],
                "distances": [[0.1]],
            }
        if collection == "authority_records":
            assert where == {"topic_id": "topic-1"}
            return {
                "documents": [["Authority summary line."]],
                "metadatas": [[{
                    "authority_record_id": "auth-1",
                    "topic_id": "topic-1",
                    "confidence": 0.92,
                    "maturity": "synthesized",
                }]],
                "distances": [[0.05]],
            }
        raise AssertionError(f"Unexpected collection: {collection}")


class FakeConn:
    async def fetchrow(self, *args, **kwargs):
        query = args[0]
        if "FROM authority.authority_records" in query:
            return {
                "authority_record_id": "auth-1",
                "core_ids": ["atom-core"],
            }
        return None

    async def fetch(self, *args, **kwargs):
        query = args[0]
        if "FROM knowledge.contradiction_sets" in query:
            return [{
                "contradiction_set_id": "contra-1",
                "summary": "Conflict on method",
                "atom_a_id": "atom-a",
                "atom_a_statement": "Method A is best.",
                "atom_b_id": "atom-b",
                "atom_b_statement": "Method B is best.",
            }]
        if "FROM knowledge.atom_relationships" in query:
            return [{"related_atom_id": "atom-related"}]
        if "FROM knowledge.knowledge_atoms" in query:
            return [
                {
                    "atom_id": "atom-core",
                    "statement": "Core authority atom.",
                    "atom_type": "claim",
                    "confidence": 0.97,
                    "importance": 0.92,
                    "topic_id": "topic-1",
                    "created_at": None,
                    "mission_title": "Topic 1",
                },
                {
                    "atom_id": "atom-related",
                    "statement": "Related authority atom.",
                    "atom_type": "claim",
                    "confidence": 0.74,
                    "importance": 0.55,
                    "topic_id": "topic-1",
                    "created_at": None,
                    "mission_title": "Topic 1",
                },
            ]
        return []


class FakeAcquire:
    async def __aenter__(self):
        return FakeConn()

    async def __aexit__(self, exc_type, exc, tb):
        return False


class FakePGPool:
    def acquire(self):
        return FakeAcquire()


class FakePG:
    pool = FakePGPool()


class FakeAdapter:
    def __init__(self):
        self.chroma = FakeChroma()
        self.pg = FakePG()


@pytest.mark.asyncio
async def test_retrieve_includes_authority_hits_in_definitions():
    retriever = V3Retriever(FakeAdapter())

    ctx = await retriever.retrieve(
        RetrievalQuery(text="authority query", topic_filter="topic-1", max_results=5)
    )

    assert len(ctx.definitions) == 1
    assert ctx.definitions[0].item_type == "authority"
    assert ctx.definitions[0].metadata["authority_record_id"] == "auth-1"
    assert len(ctx.contradictions) == 1
    assert ctx.contradictions[0].item_type == "contradiction"
    assert ctx.contradictions[0].metadata["contradiction_set_id"] == "contra-1"
    evidence_ids = {item.metadata["atom_id"] for item in ctx.evidence}
    assert "atom-1" in evidence_ids
    assert "atom-core" in evidence_ids
    assert "atom-related" in evidence_ids


@pytest.mark.asyncio
async def test_retrieve_maps_mission_filter_to_authority_topic_scope():
    retriever = V3Retriever(FakeAdapter())

    ctx = await retriever.retrieve(
        RetrievalQuery(text="authority query", mission_filter="topic-1", max_results=5)
    )

    assert len(ctx.definitions) == 1
    assert ctx.definitions[0].metadata["authority_record_id"] == "auth-1"


@pytest.mark.asyncio
async def test_structural_traversal_marks_core_and_related_atoms():
    retriever = V3Retriever(FakeAdapter())

    items = await retriever._structural_traversal({"topic_id": "topic-1"}, limit=4)

    assert [item.metadata["atom_id"] for item in items] == ["atom-core", "atom-related"]
    assert items[0].metadata["is_core_atom"] is True
    assert items[0].knowledge_level == "A"
    assert items[1].metadata["is_core_atom"] is False
    assert items[1].knowledge_level == "B"


@pytest.mark.asyncio
async def test_contradiction_search_returns_bound_atom_ids():
    retriever = V3Retriever(FakeAdapter())

    items = await retriever._contradiction_search({"topic_id": "topic-1"}, limit=3)

    assert len(items) == 1
    assert items[0].item_type == "contradiction"
    assert {
        key: items[0].metadata[key]
        for key in ("contradiction_set_id", "atom_a_id", "atom_b_id")
    } == {
        "contradiction_set_id": "contra-1",
        "atom_a_id": "atom-a",
        "atom_b_id": "atom-b",
    }
    assert items[0].metadata["type"] == "direct"
    assert "Method A is best." in items[0].content
    assert "Method B is best." in items[0].content
