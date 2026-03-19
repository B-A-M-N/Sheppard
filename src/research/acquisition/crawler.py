"""
acquisition/crawler.py

Firecrawl-local client wrapper.
Wraps your self-hosted firecrawl instance with:
  - Per-page byte tracking (feeds BudgetMonitor)
  - Semantic dedup pre-check before expensive crawl
  - Retry logic with exponential backoff
  - Academic whitelist mode (Archivist's Ivory Tower filter)
  - Raw file persistence to disk for condensation pipeline
"""

import asyncio
import hashlib
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import AsyncGenerator, Callable, List, Optional, Set
from urllib.parse import urlparse

import aiohttp

logger = logging.getLogger(__name__)

# Archivist's "Ivory Tower" whitelist — academic & high-fidelity sources
ACADEMIC_WHITELIST_DOMAINS: Set[str] = {
    ".edu", ".gov", "arxiv.org", "pubmed.ncbi.nlm.nih.gov",
    "scholar.google.com", "semanticscholar.org", "acm.org",
    "ieee.org", "nature.com", "science.org", "springer.com",
    "researchgate.net", "ssrn.com",
}


@dataclass
class CrawlResult:
    url: str
    title: str
    markdown: str
    raw_bytes: int
    checksum: str
    domain: str
    source_type: str = "web"   # web | academic | pdf
    raw_file_path: Optional[str] = None
    metadata: dict = field(default_factory=dict)


@dataclass
class CrawlerConfig:
    firecrawl_url: str = os.getenv("FIRECRAWL_BASE_URL", "http://localhost:3002")
    firecrawl_api_key: str = os.getenv("FIRECRAWL_API_KEY", "local")
    raw_data_dir: str = os.getenv("RAW_DATA_DIR", "./data/raw_docs")
    max_retries: int = 3
    retry_base_delay: float = 1.0
    request_timeout: int = 60
    max_depth: int = 5          # Increased from 3 to 5 for deeper discovery
    rate_limit_delay: float = 0.5  # seconds between requests


class FirecrawlLocalClient:
    """
    Async wrapper for the self-hosted firecrawl-local API.
    
    Yields CrawlResult objects as pages are scraped.
    Calls on_bytes_crawled after each page so BudgetMonitor
    can track storage and trigger condensation as needed.
    """

    def __init__(
        self,
        config: Optional[CrawlerConfig] = None,
        on_bytes_crawled: Optional[Callable[[str, int], None]] = None,
        academic_only: bool = False,
    ):
        self.config = config or CrawlerConfig()
        self.on_bytes_crawled = on_bytes_crawled  # (topic_id, bytes) callback
        self.academic_only = academic_only
        self._session: Optional[aiohttp.ClientSession] = None
        self._seen_checksums: Set[str] = set()
        self._queue_size = 0 # Track discovery queue size

        Path(self.config.raw_data_dir).mkdir(parents=True, exist_ok=True)

    @property
    def queue_size(self) -> int:
        return self._queue_size

    async def initialize(self) -> None:
        self._session = aiohttp.ClientSession(
            headers={
                "Authorization": f"Bearer {self.config.firecrawl_api_key}",
                "Content-Type": "application/json",
            },
            timeout=aiohttp.ClientTimeout(total=self.config.request_timeout),
        )
        logger.info(f"[Crawler] Connected to firecrawl-local at {self.config.firecrawl_url}")

    async def cleanup(self) -> None:
        if self._session:
            await self._session.close()

    async def crawl_topic(
        self,
        topic_id: str,
        topic_name: str,
        seed_query: str,
        can_crawl_fn: Optional[Callable[[str], bool]] = None,
        visited_urls: Optional[Set[str]] = None,
    ) -> AsyncGenerator[CrawlResult, None]:
        """
        Recursive Accretive Crawler. 
        Follows links and maintains a discovery queue until budget is reached.
        """
        if not self._session:
            await self.initialize()

        from src.utils.console import console
        logger.info(f"[Crawler] Starting accretive mission for '{topic_name}'")
        
        # 1. Discovery Queue
        discovery_queue = asyncio.Queue()
        if visited_urls is None:
            visited_urls = set()

        # 2. Initial Search
        seed_urls = await self._search(seed_query)
        for url in seed_urls:
            await discovery_queue.put((url, 0)) # (url, depth)
        
        self._queue_size = discovery_queue.qsize()

        while not discovery_queue.empty():
            # Check budget
            if can_crawl_fn and not can_crawl_fn(topic_id):
                console.print("[yellow][Crawler] Budget backpressure — waiting...[/yellow]")
                await asyncio.sleep(30)
                continue

            url, depth = await discovery_queue.get()
            self._queue_size = discovery_queue.qsize()
            
            if url in visited_urls or depth > self.config.max_depth:
                continue
            
            visited_urls.add(url)

            # Apply academic filter
            if self.academic_only and not self._is_academic(url):
                continue

            result = await self._scrape_with_retry(url)
            if result is None:
                continue

            # Dedup by content
            if result.checksum in self._seen_checksums:
                continue
            self._seen_checksums.add(result.checksum)

            # Extract new links for deeper crawling
            if depth < self.config.max_depth:
                new_links = self._extract_links(result.metadata.get('html', ''), url)
                for link in new_links:
                    if link not in visited_urls:
                        await discovery_queue.put((link, depth + 1))
                self._queue_size = discovery_queue.qsize()

            # Persist and yield
            result.raw_file_path = await self._persist_raw(topic_id, url, result.markdown)
            if self.on_bytes_crawled:
                await self.on_bytes_crawled(topic_id, result.raw_bytes)

            yield result
            await asyncio.sleep(self.config.rate_limit_delay)

    def _extract_links(self, html: str, base_url: str) -> List[str]:
        """Surgically extract high-quality links to follow."""
        if not html: return []
        from bs4 import BeautifulSoup
        from urllib.parse import urljoin
        
        soup = BeautifulSoup(html, 'html.parser')
        base_domain = urlparse(base_url).netloc
        links = []
        
        for a in soup.find_all('a', href=True):
            url = urljoin(base_url, a['href'])
            parsed = urlparse(url)
            # Only follow links on the same domain or relevant subdomains
            if parsed.netloc == base_domain and parsed.scheme in ['http', 'https']:
                # Skip common junk paths
                if not any(x in url.lower() for x in ['/tag/', '/category/', '/login', '/signup', '/search']):
                    links.append(url)
        
        return list(set(links))[:5] # Limit per page to avoid spider traps

    async def crawl_url(
        self,
        url: str,
        topic_id: str,
        can_crawl_fn: Optional[Callable[[str], bool]] = None,
    ) -> Optional[CrawlResult]:
        """Crawl a single specific URL."""
        if not self._session:
            await self.initialize()

        if can_crawl_fn and not can_crawl_fn(topic_id):
            logger.warning(f"[Crawler] Budget full, cannot crawl {url}")
            return None

        return await self._scrape_with_retry(url)

    async def _search(self, query: str) -> List[str]:
        """Use firecrawl's /v1/search to get seed URLs."""
        from src.utils.console import console
        console.print(f"[dim][Crawler] Searching for: {query}...[/dim]")
        logger.info(f"[Crawler] Sending search request for: '{query}'")
        try:
            async with self._session.post(
                f"{self.config.firecrawl_url}/v1/search",
                json={"query": query, "limit": 20},
            ) as resp:
                logger.info(f"[Crawler] Search response status: {resp.status}")
                if resp.status != 200:
                    console.print(f"[bold red][Crawler] Search failed (HTTP {resp.status})[/bold red]")
                    return []
                
                data = await resp.json()
                # Local Firecrawl returns list directly in 'data'
                results = data.get("data", [])
                
                if not isinstance(results, list):
                    # Fallback for cloud structure
                    results = results.get("web", [])
                
                urls = [r["url"] for r in results if isinstance(r, dict) and "url" in r]
                console.print(f"[dim][Crawler] Found {len(urls)} results.[/dim]")
                logger.info(f"[Crawler] Extracted {len(urls)} valid URLs")
                return urls
        except Exception as e:
            console.print(f"[bold red][Crawler] Search error: {e}[/bold red]")
            logger.error(f"[Crawler] Search failed for '{query}': {e}")
            return []

    async def _scrape_with_retry(self, url: str) -> Optional[CrawlResult]:
        """Scrape a URL with exponential backoff retry."""
        for attempt in range(self.config.max_retries):
            try:
                async with self._session.post(
                    f"{self.config.firecrawl_url}/v1/scrape",
                    json={
                        "url": url,
                        "formats": ["markdown", "html"],
                        "onlyMainContent": True,
                    },
                ) as resp:
                    if resp.status != 200:
                        logger.warning(f"[Crawler] HTTP {resp.status} for {url}")
                        return None

                    data = await resp.json()
                    if not data.get("success"):
                        return None

                    doc = data.get("data", {})
                    markdown = doc.get("markdown", "")
                    if not markdown:
                        return None

                    raw_bytes = len(markdown.encode("utf-8"))
                    checksum = hashlib.md5(markdown.encode()).hexdigest()
                    domain = urlparse(url).netloc
                    source_type = "academic" if self._is_academic(url) else "web"
                    if url.endswith(".pdf"):
                        source_type = "pdf"

                    return CrawlResult(
                        url=url,
                        title=doc.get("metadata", {}).get("title", ""),
                        markdown=markdown,
                        raw_bytes=raw_bytes,
                        checksum=checksum,
                        domain=domain,
                        source_type=source_type,
                        metadata=doc.get("metadata", {}),
                    )

            except aiohttp.ClientError as e:
                wait = self.config.retry_base_delay * (2 ** attempt)
                logger.warning(f"[Crawler] Attempt {attempt+1} failed for {url}: {e}. Retrying in {wait}s")
                await asyncio.sleep(wait)

        logger.error(f"[Crawler] All retries exhausted for {url}")
        return None

    async def _persist_raw(
        self,
        topic_id: str,
        url: str,
        content: str,
    ) -> str:
        """Save raw markdown to disk for condensation pipeline."""
        topic_dir = Path(self.config.raw_data_dir) / topic_id
        topic_dir.mkdir(parents=True, exist_ok=True)

        # Use URL hash as filename to avoid path issues
        url_hash = hashlib.md5(url.encode()).hexdigest()[:12]
        file_path = topic_dir / f"{url_hash}.md"

        with open(file_path, "w", encoding="utf-8") as f:
            f.write(f"<!-- SOURCE: {url} -->\n\n{content}")

        return str(file_path)

    def _is_academic(self, url: str) -> bool:
        """Check if URL belongs to a whitelisted academic domain."""
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        return any(
            domain.endswith(whitelist) or whitelist in domain
            for whitelist in ACADEMIC_WHITELIST_DOMAINS
        )
