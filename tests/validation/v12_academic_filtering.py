"""
V-12: AcademicFilteringEnforced

Verifies that when academic_only=True, non-academic URLs are rejected at the enqueue boundary.
Only URLs matching the academic whitelist are allowed into the queue.
"""
import pytest
from src.research.acquisition.crawler import FirecrawlLocalClient, CrawlerConfig

class MockAdapter:
    """Adapter mock that records enqueued payloads."""
    def __init__(self):
        self.enqueued = []
        self.enqueue_calls = 0

    async def enqueue_job(self, queue_name: str, payload: dict) -> bool:
        self.enqueue_calls += 1
        self.enqueued.append(payload)
        return True  # always succeed

@pytest.mark.asyncio
async def test_v12_academic_filtering(monkeypatch):
    """Test that academic_only=True filters non-academic URLs at enqueue boundary."""

    adapter = MockAdapter()

    # Create FirecrawlLocalClient with academic_only=True
    client = FirecrawlLocalClient(
        config=CrawlerConfig(),
        on_bytes_crawled=lambda x: None,
        academic_only=True,
        enqueue_fn=adapter.enqueue_job,
    )
    # No need to initialize for this test

    # Mock _search to return a mix of academic and non-academic URLs across pages
    async def mock_search(query, pageno):
        # Return different sets per page to ensure pagination works
        if pageno == 1:
            return [
                "https://arxiv.org/abs/1234",  # academic
                "https://example.com/news",    # non-academic
                "https://scholar.google.com/scholar?q=test",  # academic (whitelisted domain scholar.google.com)
            ]
        elif pageno == 2:
            return [
                "https://springer.com/journal/article",  # academic (springer.com in whitelist)
                "https://nytimes.com/2024/01/01/",      # non-academic
            ]
        else:
            return []  # no more pages after 2
    monkeypatch.setattr(client, "_search", mock_search)

    # Call discover_and_enqueue
    total_enqueued = await client.discover_and_enqueue(
        topic_id="test",
        topic_name="Test",
        query="test query",
        mission_id="test-mission-v12",
        visited_urls=set()
    )

    # All payloads should be academic URLs only
    for payload in adapter.enqueued:
        url = payload["url"]
        assert client._is_academic(url), f"Non-academic URL {url} was not filtered"

    # Expected academic URLs: arxiv.org, scholar.google.com, springer.com => 3 total
    expected_academic = 3
    assert total_enqueued == expected_academic, f"Expected {expected_academic} enqueued, got {total_enqueued}"
    assert len(adapter.enqueued) == expected_academic


@pytest.mark.asyncio
async def test_discover_and_enqueue_without_enqueue_fn_returns_zero(monkeypatch):
    client = FirecrawlLocalClient(
        config=CrawlerConfig(),
        on_bytes_crawled=lambda x: None,
        academic_only=False,
    )

    async def mock_search(query, pageno):
        return ["https://example.com/a"] if pageno == 1 else []

    monkeypatch.setattr(client, "_search", mock_search)

    total_enqueued = await client.discover_and_enqueue(
        topic_id="test",
        topic_name="Test",
        query="test query",
        mission_id="test-mission-v12",
        visited_urls=set(),
    )

    assert total_enqueued == 0
