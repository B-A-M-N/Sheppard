"""
V-12: AcademicFilteringEnforced

Verifies that when academic_only=True, non-academic URLs are rejected at the enqueue boundary.
Only URLs matching the academic whitelist are allowed into the queue.
"""
import pytest
import asyncio
from src.research.acquisition.crawler import FirecrawlLocalClient, CrawlerConfig
from src.core.system import SystemManager

class MockAdapter:
    """Adapter mock that records enqueued payloads."""
    def __init__(self):
        self.enqueued = []
        self.enqueue_calls = 0

    async def enqueue_job(self, queue_name: str, payload: dict) -> bool:
        self.enqueue_calls += 1
        self.enqueued.append(payload)
        return True  # always succeed

class MockSystemManager:
    def __init__(self):
        self.adapter = MockAdapter()

@pytest.mark.asyncio
async def test_v12_academic_filtering(monkeypatch):
    """Test that academic_only=True filters non-academic URLs at enqueue boundary."""

    # Create a mock system_manager with adapter
    mock_sm = MockSystemManager()
    # Patch the module-level system_manager used by discover_and_enqueue
    monkeypatch.setattr("src.research.acquisition.crawler.system_manager", mock_sm)

    # Create FirecrawlLocalClient with academic_only=True
    client = FirecrawlLocalClient(
        config=CrawlerConfig(),
        on_bytes_crawled=lambda x: None,
        academic_only=True
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
    for payload in mock_sm.adapter.enqueued:
        url = payload["url"]
        assert client._is_academic(url), f"Non-academic URL {url} was not filtered"

    # Expected academic URLs: arxiv.org, scholar.google.com, springer.com => 3 total
    expected_academic = 3
    assert total_enqueued == expected_academic, f"Expected {expected_academic} enqueued, got {total_enqueued}"
    assert len(mock_sm.adapter.enqueued) == expected_academic
