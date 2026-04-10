"""
acquisition/crawler.py

Firecrawl-local client wrapper with Asynchronous Dual-Lane Metabolism.
- Fast Lane (Host): Direct, high-priority Playwright scrapes.
- Slow Lane (Laptop): Non-blocking, pull-based background tasks (PDFs, static, retries).
"""

import asyncio
import hashlib
import os

# INFRA-01: Configurable Firecrawl concurrency with clamped range
FIRECRAWL_MAX_CONCURRENT = int(os.environ.get("FIRECRAWL_MAX_CONCURRENT", "8"))
FIRECRAWL_MAX_CONCURRENT = max(1, min(FIRECRAWL_MAX_CONCURRENT, 32))  # Clamp 1-32
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import AsyncGenerator, Callable, List, Optional, Set, Dict, Any, Union
from urllib.parse import urlparse

import aiohttp
from src.utils.console import console

logger = logging.getLogger(__name__)

# Archivist's "Ivory Tower" whitelist
ACADEMIC_WHITELIST_DOMAINS: Set[str] = {
    # Traditional academic TLDs
    ".edu", ".gov",
    # Major academic publishers & repositories
    "arxiv.org", "pubmed.ncbi.nlm.nih.gov",
    "scholar.google.com", "semanticscholar.org",
    "acm.org", "ieee.org", "nature.com", "science.org",
    "springer.com", "researchgate.net", "ssrn.com",
    # General reference
    "wikipedia.org",
    # University presses
    "cambridge.org", "oxfordjournals.org", "academic.oup.com",
    # Museums & societies (paleo/geo relevant)
    "amnh.org", "fieldmuseum.org", "paleontology.org", "dinosauria.org",
    "berkeley.edu", "mit.edu", "harvard.edu", "stanford.edu",
    # UK academic institutions
    "ac.uk",
    # Government science agencies & research institutes
    "usgs.gov", "nps.gov", "si.edu", "nasa.gov",
    # Data/code archives
    "github.com", "gitlab.com", "osf.io", "zenodo.org",
    "figshare.com", "dryad.org",
    # Additional educational / reference sites
    "archive.org", "britannica.com", "nationalgeographic.com",
    "opengeology.org", "paleoportal.org", "academia.edu",
    # Journal aggregators
    "journals.elsevier.com", "pubs.acs.org", "pnas.org",
    "bioone.org", "frontiersin.org", "peerj.com",
}

@dataclass
class CrawlResult:
    url: str
    title: str
    markdown: str
    raw_bytes: int
    checksum: str
    domain: str
    source_type: str = "web"
    raw_file_path: Optional[str] = None
    metadata: dict = field(default_factory=dict)

@dataclass
class CrawlerConfig:
    firecrawl_url: str = os.getenv("FIRECRAWL_BASE_URL", "http://127.0.0.1:3002")
    searxng_urls: List[str] = field(default_factory=lambda: [
        "http://127.0.0.1:8080"
    ])
    # Redis queues for Two-Lane Pipeline
    fast_lane_queue: str = "firecrawl:fast"
    slow_lane_queue: str = "firecrawl:slow"

    firecrawl_api_key: str = os.getenv("FIRECRAWL_API_KEY", "local")
    raw_data_dir: str = os.getenv("RAW_DATA_DIR", "./data/raw_docs")
    max_retries: int = 3
    retry_base_delay: float = 1.0
    request_timeout: int = 60
    max_depth: int = 5
    rate_limit_delay: float = 0.5
    slow_lane_domains: Set[str] = field(default_factory=set)

class FirecrawlLocalClient:
    def __init__(
        self,
        config: Optional[CrawlerConfig] = None,
        on_bytes_crawled: Optional[Callable[[str, int], None]] = None,
        academic_only: bool = False,
    ):
        self.config = config or CrawlerConfig()
        self.on_bytes_crawled = on_bytes_crawled
        self.academic_only = academic_only
        self._session: Optional[aiohttp.ClientSession] = None
        self._seen_checksums: Set[str] = set()
        self._queue_size = 0
        self._search_index = 0
        
        # Domains that are fast/stable enough for the i5 "Slow Lane"
        self.slow_lane_domains = {
            "wikipedia.org", "arxiv.org", "github.com", "nature.com", 
            "science.org", "ieee.org", "docs.python.org"
        }

        Path(self.config.raw_data_dir).mkdir(parents=True, exist_ok=True)

    @property
    def queue_size(self) -> int:
        return self._queue_size

    @property
    def current_searxng_url(self) -> str:
        url = self.config.searxng_urls[self._search_index % len(self.config.searxng_urls)]
        self._search_index += 1
        return url

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

    def _route_url(self, url: str) -> str:
        """Architecture decision: Is this Fast Lane or Slow Lane?"""
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        
        # 1. Heavy files (PDFs) -> Slow Lane
        if url.lower().endswith(".pdf"): return "slow"
        
        # 2. Known static/low-complexity or high-latency domains -> Slow Lane
        generic_domains = [
            "dictionary.com", "merriam-webster.com", "wiktionary.org", 
            "definitions.net", "oxfordlearnersdictionaries.com",
            "support.google.com", "stackexchange.com", "stackoverflow.com",
            "wikipedia.org", "britannica.com"
        ]
        # Convert set to list before concatenation
        slow_list = list(self.slow_lane_domains) if isinstance(self.slow_lane_domains, set) else self.slow_lane_domains
        if any(d in domain for d in generic_domains + slow_list): return "slow"
        
        # 3. Everything else (JS-heavy, technical docs, unknowns) -> Fast Lane
        return "fast"

    async def crawl_topic(
        self,
        topic_id: str,
        topic_name: str,
        seed_query: str,
        can_crawl_fn: Optional[Callable[[str], bool]] = None,
        visited_urls: Optional[Set[str]] = None,
        mission_id: str = None
    ) -> AsyncGenerator[CrawlResult, None]:
        """Parallel researcher: Fetches high-value data using multiple concurrent workers."""
        if not self._session: await self.initialize()
        
        discovery_queue = asyncio.Queue()
        results_queue = asyncio.Queue()
        if visited_urls is None: visited_urls = set()

        # Initial discovery
        seed_urls = await self._search(seed_query)
        for url in seed_urls: await discovery_queue.put((url, 0))
        
        self._queue_size = discovery_queue.qsize()
        
        num_workers = 8  # Balanced for Ryzen 9
        active_workers = 0
        
        async def worker():
            nonlocal active_workers
            active_workers += 1
            try:
                while not discovery_queue.empty() or active_workers > 1:
                    if can_crawl_fn and not can_crawl_fn(topic_id):
                        await asyncio.sleep(5); continue

                    try:
                        url, depth = await asyncio.wait_for(discovery_queue.get(), timeout=2)
                    except asyncio.TimeoutError:
                        if discovery_queue.empty(): break
                        continue

                    if url in visited_urls or depth > self.config.max_depth:
                        discovery_queue.task_done(); continue
                    
                    visited_urls.add(url)

                    # --- ROUTING ---
                    lane = self._route_url(url)
                    if lane == "slow":
                        await self._offload_to_slow_lane(topic_id, url, mission_id)
                        discovery_queue.task_done(); continue

                    # --- FAST LANE SCRAPE ---
                    if self.academic_only and not self._is_academic(url): 
                        discovery_queue.task_done(); continue

                    result = await self._scrape_with_retry(url)
                    if result:
                        if result.checksum not in self._seen_checksums:
                            self._seen_checksums.add(result.checksum)
                            
                            # Recursive link discovery
                            if depth < self.config.max_depth:
                                new_links = self._extract_links(result.metadata.get('html', ''), url)
                                for link in new_links:
                                    if link not in visited_urls:
                                        await discovery_queue.put((link, depth + 1))
                            
                            result.raw_file_path = await self._persist_raw(topic_id, url, result.markdown)
                            if self.on_bytes_crawled:
                                await self.on_bytes_crawled(topic_id, result.raw_bytes)
                            
                            await results_queue.put(result)
                    
                    discovery_queue.task_done()
                    await asyncio.sleep(self.config.rate_limit_delay)
            finally:
                active_workers -= 1

        # Start workers
        worker_tasks = [asyncio.create_task(worker()) for _ in range(num_workers)]

        # Generator loop
        while active_workers > 0 or not results_queue.empty():
            try:
                # Polling results queue
                res = await asyncio.wait_for(results_queue.get(), timeout=0.5)
                yield res
                results_queue.task_done()
            except asyncio.TimeoutError:
                continue

        # Ensure all workers are cleaned up
        for t in worker_tasks:
            if not t.done(): t.cancel()
        await asyncio.gather(*worker_tasks, return_exceptions=True)

    async def _offload_to_slow_lane(self, topic_id: str, url: str, mission_id: str = None):
        """Asynchronous handoff to the Slow Lane (Laptop) worker via Redis Queue."""
        try:
            from src.core.system import system_manager
            payload = {
                "topic_id": topic_id,
                "mission_id": mission_id or topic_id,
                "url": url,
                "priority": 0,
                "requires_js": False
            }
            await system_manager.adapter.enqueue_job("queue:scraping", payload)
            logger.info(f"[Crawler] Offloaded to SLOW-LANE queue: {url}")
        except Exception as e:
            logger.debug(f"[Crawler] Slow-lane offload failed: {e}")

    async def _search(self, query: str, pageno: int = 1) -> List[str]:
        """Discovery Race: Hits all SearXNG nodes in parallel. First success wins.
        
        Searches across both academic engines (Google Scholar, arXiv, PubMed, 
        Semantic Scholar, CrossRef, CORE, BASE) and general engines (Bing, Qwant, 
        Brave, DuckDuckGo) simultaneously. Academic URLs are classified on ingestion 
        via ACADEMIC_WHITELIST_DOMAINS — general results never taint academic sources.
        """
        import aiohttp
        import random
        from src.config.settings_v2 import settings

        engines_str = settings.searxng_all_engines

        async def fetch_one(url):
            try:
                payload = {
                    "q": query,
                    "format": "json",
                    "pageno": pageno,
                    "engines": engines_str
                }
                async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=8)) as session:
                    async with session.get(f"{url}/search", params=payload) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            results = data.get("results", [])
                            return [r["url"] for r in results if isinstance(r, dict) and "url" in r]
            except:
                pass
            return None

        urls = list(self.config.searxng_urls)
        random.shuffle(urls)
        tasks = [asyncio.create_task(fetch_one(url)) for url in urls]
        
        for task in asyncio.as_completed(tasks):
            res = await task
            if res and len(res) > 0:
                for t in tasks:
                    if not t.done(): t.cancel()
                return res
        return []

    async def discover_and_enqueue(
        self,
        topic_id: str,
        topic_name: str,
        query: str,
        mission_id: str = None,
        visited_urls: Optional[Set[str]] = None
    ) -> int:
        """Producer: Finds URLs and dumps them into the global Redis queue.
        Deep Mines up to Page 5 if no new URLs are found.
        """
        from src.core.system import system_manager
        total_enqueued = 0

        # Pre-filter patterns — reject before enqueuing
        _blocked_patterns = [
            "taylorfrancis.com/books",  # paywalled
            "login",
            "signup",
            "register",
            "captcha",
        ]

        def _is_valid_url(url: str) -> bool:
            for pattern in _blocked_patterns:
                if pattern in url.lower():
                    return False
            return True

        for page in range(1, 6): # Deep Mine: Page 1 to 5
            urls = await self._search(query, pageno=page)
            if not urls:
                break
                
            page_new_count = 0
            backpressure_triggered = False
            for url in urls:
                if visited_urls is not None and url in visited_urls:
                    continue

                # Apply pre-filter: reject known-bad URL patterns
                if not _is_valid_url(url):
                    continue

                # Apply academic_only filter if enabled
                if self.academic_only and not self._is_academic(url):
                    continue

                lane = self._route_url(url)
                payload = {
                    "topic_id": topic_id,
                    "mission_id": mission_id or topic_id,
                    "url": url,
                    "url_hash": hashlib.md5(url.encode()).hexdigest(),
                    "lane": lane,
                    "priority": 1 if lane == "fast" else 0
                }
                success = await system_manager.adapter.enqueue_job("queue:scraping", payload)
                if success:
                    if visited_urls is not None:
                        visited_urls.add(url)
                    page_new_count += 1
                    total_enqueued += 1
                else:
                    # Backpressure: queue depth limit reached; stop enqueuing further URLs for this node
                    backpressure_triggered = True
                    break

            if backpressure_triggered:
                break

            # Deep mining: continue through all pages regardless of new URL count.
            # Removed break-on-first-success to explore pages 1-5 fully.

        return total_enqueued

    _search_lock = asyncio.Lock()

    async def _scrape_with_retry(self, url: str) -> Optional[CrawlResult]:
        for attempt in range(self.config.max_retries):
            try:
                async with self._session.post(
                    f"{self.config.firecrawl_url}/v1/scrape",
                    json={"url": url, "formats": ["markdown", "html"], "onlyMainContent": True},
                    # FIRE-01: Uses scrape (not /v2/extract) — avoids Firecrawl's internal schema wrapping
                ) as resp:
                    if resp.status != 200: return None
                    data = await resp.json()
                    if not data.get("success"): return None
                    doc = data.get("data", {})
                    markdown = doc.get("markdown", "")
                    if not markdown: return None

                    return CrawlResult(
                        url=url, title=doc.get("metadata", {}).get("title", ""),
                        markdown=markdown, raw_bytes=len(markdown.encode("utf-8")),
                        checksum=hashlib.md5(markdown.encode()).hexdigest(),
                        domain=urlparse(url).netloc,
                        source_type="academic" if self._is_academic(url) else "web",
                        metadata=doc.get("metadata", {}),
                    )
            except:
                await asyncio.sleep(self.config.retry_base_delay * (2 ** attempt))
        return None

    def _extract_links(self, html: str, base_url: str) -> List[str]:
        if not html: return []
        from bs4 import BeautifulSoup
        from urllib.parse import urljoin
        soup = BeautifulSoup(html, 'html.parser')
        base_domain = urlparse(base_url).netloc
        links = []
        for a in soup.find_all('a', href=True):
            url = urljoin(base_url, a['href'])
            parsed = urlparse(url)
            if parsed.netloc == base_domain and parsed.scheme in ['http', 'https']:
                if not any(x in url.lower() for x in ['/tag/', '/category/', '/login', '/signup']):
                    links.append(url)
        return list(set(links))[:5]

    async def _persist_raw(self, topic_id: str, url: str, content: str) -> str:
        topic_dir = Path(self.config.raw_data_dir) / topic_id
        topic_dir.mkdir(parents=True, exist_ok=True)
        url_hash = hashlib.md5(url.encode()).hexdigest()[:12]
        file_path = topic_dir / f"{url_hash}.md"
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(f"<!-- SOURCE: {url} -->\n\n{content}")
        return str(file_path)

    def _is_academic(self, url: str) -> bool:
        domain = urlparse(url).netloc.lower()
        return any(domain.endswith(whitelist) or whitelist in domain for whitelist in ACADEMIC_WHITELIST_DOMAINS)

import uuid
