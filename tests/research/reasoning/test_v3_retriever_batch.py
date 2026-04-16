"""
Batch retrieval coverage for V3Retriever.retrieve_many().
"""

import os
import sys
from unittest.mock import AsyncMock, MagicMock

import pytest

_project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
_src = os.path.join(_project_root, "src")
for _p in (_src, _project_root):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from research.reasoning.retriever import RetrievalQuery, RetrievedItem
from research.reasoning.v3_retriever import V3Retriever


def _make_retriever():
    adapter = MagicMock()
    adapter.chroma = MagicMock()
    adapter.pg = MagicMock()
    return V3Retriever(adapter=adapter)


@pytest.mark.asyncio
async def test_retrieve_many_requires_shared_filter():
    retriever = _make_retriever()

    queries = [
        RetrievalQuery(text="alpha", mission_filter="mission-1"),
        RetrievalQuery(text="beta", mission_filter="mission-2"),
    ]

    with pytest.raises(ValueError, match="share the same filter value"):
        await retriever.retrieve_many(queries)


@pytest.mark.asyncio
async def test_retrieve_many_returns_empty_contexts_when_batch_empty():
    retriever = _make_retriever()
    retriever.adapter.chroma.query = AsyncMock(return_value={"documents": [], "metadatas": [], "distances": []})

    contexts = await retriever.retrieve_many([
        RetrievalQuery(text="alpha", mission_filter="mission-1"),
        RetrievalQuery(text="beta", mission_filter="mission-1"),
    ])

    assert len(contexts) == 2
    assert all(ctx.is_empty for ctx in contexts)


@pytest.mark.asyncio
async def test_retrieve_many_merges_semantic_lexical_and_structural_then_reranks():
    retriever = _make_retriever()
    retriever.adapter.chroma.query = AsyncMock(return_value={
        "documents": [
            ["semantic alpha"],
            ["semantic beta"],
        ],
        "metadatas": [
            [{"atom_id": "sem-1", "atom_type": "claim", "trust_score": 0.30, "captured_at": "2026-04-01T00:00:00+00:00"}],
            [{"atom_id": "sem-2", "atom_type": "claim", "trust_score": 0.20, "captured_at": "2026-03-01T00:00:00+00:00"}],
        ],
        "distances": [
            [0.40],
            [0.50],
        ],
    })

    retriever._postgres_fallback = AsyncMock(side_effect=[
        [
            RetrievedItem(
                content="lexical alpha",
                source="pg",
                strategy="lexical",
                item_type="claim",
                relevance_score=0.95,
                trust_score=0.95,
                recency_days=1,
                metadata={"atom_id": "lex-1"},
            )
        ],
        [
            RetrievedItem(
                content="lexical beta",
                source="pg",
                strategy="lexical",
                item_type="claim",
                relevance_score=0.85,
                trust_score=0.90,
                recency_days=2,
                metadata={"atom_id": "lex-2"},
            )
        ],
    ])
    retriever._structural_traversal = AsyncMock(return_value=[
        RetrievedItem(
            content="structural support",
            source="graph",
            strategy="structural",
            item_type="claim",
            relevance_score=0.70,
            trust_score=0.80,
            recency_days=3,
            metadata={"atom_id": "struct-1"},
        )
    ])
    retriever._authority_search = AsyncMock(return_value=[
        RetrievedItem(
            content="authority summary",
            source="authority:topic",
            strategy="authority",
            item_type="authority",
            relevance_score=0.9,
            trust_score=0.95,
            recency_days=1,
            metadata={"authority_record_id": "auth-1"},
        )
    ])
    retriever._project_artifact_search = AsyncMock(return_value=[
        RetrievedItem(
            content="artifact summary",
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
    retriever._contradiction_search = AsyncMock(return_value=[
        RetrievedItem(
            content="conflict summary",
            source="contradiction:1",
            strategy="contradiction",
            item_type="contradiction",
            relevance_score=0.75,
            trust_score=0.7,
            recency_days=9999,
            metadata={"contradiction_set_id": "contra-1"},
        )
    ])

    contexts = await retriever.retrieve_many([
        RetrievalQuery(text="alpha", mission_filter="mission-1", max_results=2),
        RetrievalQuery(text="beta", mission_filter="mission-1", max_results=2),
    ])

    assert len(contexts) == 2
    assert [item.content for item in contexts[0].definitions] == ["authority summary"]
    assert [item.content for item in contexts[1].definitions] == ["authority summary"]
    assert [item.content for item in contexts[0].evidence] == ["lexical alpha", "structural support"]
    assert [item.content for item in contexts[1].evidence] == ["lexical beta", "structural support"]
    assert [item.content for item in contexts[0].project_artifacts] == ["artifact summary"]
    assert [item.content for item in contexts[0].unresolved] == [
        "Resolve contradiction contra-1 before reusing this authority."
    ]
    retriever._structural_traversal.assert_awaited_once()
    retriever._authority_search.assert_awaited_once()
    retriever._project_artifact_search.assert_awaited_once()
    assert retriever._postgres_fallback.await_count == 2
