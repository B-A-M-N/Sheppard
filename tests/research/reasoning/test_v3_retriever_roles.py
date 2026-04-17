import pytest
from unittest.mock import AsyncMock

from src.research.reasoning.retriever import RetrievedItem, RetrievalQuery
from src.research.reasoning.v3_retriever import V3Retriever


class FakeConn:
    async def fetch(self, query, *args):
        if "FROM authority.synthesis_artifacts" in query:
            return [
                {
                    "artifact_id": "artifact-1",
                    "title": "Master Brief: Feature Flags",
                    "abstract": "Project artifact summary",
                    "artifact_type": "master_brief",
                    "authority_record_id": "auth-1",
                    "maturity": "contested",
                }
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
        self.chroma = type("FakeChroma", (), {})()
        self.pg = FakePG()


@pytest.mark.asyncio
async def test_project_artifact_search_returns_project_slot_items():
    retriever = V3Retriever(FakeAdapter())

    items = await retriever._project_artifact_search(
        "feature flags master brief",
        {"topic_id": "topic-1"},
        limit=2,
    )

    assert len(items) == 1
    assert items[0].strategy == "project"
    assert items[0].knowledge_level == "D"
    assert items[0].metadata["artifact_id"] == "artifact-1"
    assert items[0].project_proximity == 1.0


def test_build_unresolved_items_maps_contradictions_to_unresolved_slot():
    retriever = V3Retriever(FakeAdapter())

    contradictions = [
        RetrievedItem(
            content="Conflict summary",
            source="contradiction:contra-1",
            strategy="contradiction",
            item_type="contradiction",
            relevance_score=0.7,
            trust_score=0.6,
            recency_days=9999,
            citation_key="contra-1",
            metadata={"contradiction_set_id": "contra-1"},
        )
    ]

    items = retriever._build_unresolved_items(contradictions, limit=2)

    assert len(items) == 1
    assert items[0].item_type == "unresolved"
    assert items[0].strategy == "unresolved"
    assert items[0].content == "Resolve contradiction contra-1 before reusing this authority."


def test_rerank_prefers_exact_and_authority_bound_items():
    retriever = V3Retriever(FakeAdapter())

    baseline = RetrievedItem(
        content="baseline",
        source="pg",
        strategy="keyword",
        relevance_score=0.85,
        trust_score=0.85,
        recency_days=5,
        metadata={"atom_id": "atom-1"},
    )
    exact_authority = RetrievedItem(
        content="exact authority",
        source="pg",
        strategy="keyword",
        relevance_score=0.82,
        trust_score=0.82,
        recency_days=5,
        metadata={
            "atom_id": "atom-2",
            "authority_record_id": "auth-1",
            "exact_match": True,
            "is_core_atom": True,
        },
    )

    ranked = retriever._rerank([baseline, exact_authority], limit=2)

    assert [item.content for item in ranked] == ["exact authority", "baseline"]


def test_link_context_signals_marks_authority_artifact_and_contradiction_bindings():
    retriever = V3Retriever(FakeAdapter())
    item = RetrievedItem(
        content="feature flags conflict in rollout policy",
        source="pg",
        strategy="semantic",
        relevance_score=0.7,
        trust_score=0.7,
        recency_days=3,
        metadata={"atom_id": "atom-2", "authority_record_id": "auth-1"},
    )
    authority_items = [
        RetrievedItem(
            content="authority summary",
            source="authority",
            strategy="authority",
            metadata={"authority_record_id": "auth-1"},
        )
    ]
    contradiction_items = [
        RetrievedItem(
            content="conflict",
            source="contradiction",
            strategy="contradiction",
            metadata={"atom_a_id": "atom-2", "atom_b_id": "atom-9"},
        )
    ]
    project_artifacts = [
        RetrievedItem(
            content="artifact",
            source="artifact",
            strategy="project",
            metadata={"authority_record_id": "auth-1"},
        )
    ]

    retriever._link_context_signals(
        [item],
        authority_items,
        contradiction_items,
        project_artifacts,
        "feature flags rollout policy",
    )

    assert item.metadata["authority_aligned"] is True
    assert item.metadata["artifact_aligned"] is True
    assert item.metadata["contradiction_bound"] is True
    assert item.metadata["query_overlap"] > 0


@pytest.mark.asyncio
async def test_retrieve_populates_project_artifacts_and_unresolved_slots():
    retriever = V3Retriever(FakeAdapter())
    retriever.adapter.chroma.query = AsyncMock(return_value={"documents": [[]], "metadatas": [[]], "distances": [[]]})
    retriever._postgres_fallback = AsyncMock(return_value=[])
    retriever._authority_search = AsyncMock(return_value=[])
    retriever._contradiction_search = AsyncMock(return_value=[
        RetrievedItem(
            content="Conflict summary",
            source="contradiction:contra-1",
            strategy="contradiction",
            item_type="contradiction",
            relevance_score=0.7,
            trust_score=0.6,
            recency_days=9999,
            citation_key="contra-1",
            metadata={"contradiction_set_id": "contra-1"},
        )
    ])
    retriever._structural_traversal = AsyncMock(return_value=[])
    retriever._project_artifact_search = AsyncMock(return_value=[
        RetrievedItem(
            content="Artifact summary",
            source="artifact:1",
            strategy="project",
            item_type="master_brief",
            relevance_score=0.8,
            trust_score=0.8,
            recency_days=4,
            project_proximity=1.0,
            metadata={"artifact_id": "artifact-1"},
        )
    ])

    ctx = await retriever.retrieve(
        RetrievalQuery(text="feature flags", topic_filter="topic-1", max_results=4)
    )

    assert [item.content for item in ctx.project_artifacts] == ["Artifact summary"]
    assert [item.content for item in ctx.unresolved] == [
        "Resolve contradiction contra-1 before reusing this authority."
    ]
