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
    async def fetch(self, *args, **kwargs):
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
    assert len(ctx.evidence) == 1
    assert ctx.evidence[0].metadata["atom_id"] == "atom-1"
