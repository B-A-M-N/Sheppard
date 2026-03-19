"""
Enhanced Firecrawl client implementation with robust error handling and research integration.
File: src/research/firecrawl_client.py
"""

import logging
import asyncio
from typing import Dict, Any, Optional, List, AsyncGenerator, Union, Tuple
from datetime import datetime
import aiohttp
import json
import websockets
from urllib.parse import urljoin
import backoff
import concurrent.futures

from src.research.exceptions import FirecrawlError
from src.research.config import FirecrawlConfig
from src.utils.validation import validate_url

logger = logging.getLogger(__name__)

class FirecrawlClient:
    """Enhanced wrapper for Firecrawl API with comprehensive error handling."""

    def __init__(self, config: Optional[FirecrawlConfig] = None):
        """
        Initialize Firecrawl client.

        Args:
            config: Optional FirecrawlConfig instance
        """
        self.config = config or FirecrawlConfig()
        self.session: Optional[aiohttp.ClientSession] = None
        self._active_jobs: Dict[str, Dict[str, Any]] = {}
        self._ws_connections: Dict[str, websockets.WebSocketClientProtocol] = {}

        # Configure connection settings
        self.timeout = aiohttp.ClientTimeout(
            total=self.config.timeout,
            connect=30,
            sock_read=30,
            sock_connect=30
        )

        # Configure retry settings
        self.max_retries = self.config.retries
        self.retry_delay = self.config.retry_delay
        self.concurrent_limit = self.config.concurrent_limit

        # Rate limiting state
        self._request_count = 0
        self._last_request_time = None
        self._rate_limit_remaining = None
        self._rate_limit_reset = None

        # Initialize metrics
        self._metrics = {
            'requests_made': 0,
            'successful_requests': 0,
            'failed_requests': 0,
            'retries': 0,
            'rate_limit_hits': 0,
            'avg_response_time': 0.0
        }

    async def initialize(self) -> None:
        """Initialize client session with proper error handling."""
        if not self.session:
            try:
                # Validate API key
                if not self.config.api_key:
                    raise FirecrawlError("API key not configured")

                # Create session with timeout and headers
                self.session = aiohttp.ClientSession(
                    timeout=self.timeout,
                    headers={
                        **self.config.request_headers,
                        'Authorization': f'Bearer {self.config.api_key}'
                    }
                )

                # Verify API connection
                await self._verify_api_connection()
                logger.info("FirecrawlClient initialized successfully")

            except Exception as e:
                logger.error(f"Failed to initialize FirecrawlClient: {str(e)}")
                if self.session:
                    await self.session.close()
                    self.session = None
                raise FirecrawlError(f"Initialization failed: {str(e)}")

    async def cleanup(self) -> None:
        """Clean up client resources with proper error handling."""
        try:
            # Close WebSocket connections
            for ws in self._ws_connections.values():
                try:
                    await ws.close()
                except Exception as e:
                    logger.warning(f"Error closing WebSocket connection: {str(e)}")
            self._ws_connections.clear()

            # Close HTTP session
            if self.session:
                await self.session.close()
                self.session = None

            # Clear state
            self._active_jobs.clear()
            self._request_count = 0
            self._last_request_time = None

            logger.info("FirecrawlClient cleanup completed")

        except Exception as e:
            logger.error(f"Error during cleanup: {str(e)}")
            raise FirecrawlError(f"Cleanup failed: {str(e)}")

    @backoff.on_exception(
        backoff.expo,
        (aiohttp.ClientError, asyncio.TimeoutError),
        max_tries=3
    )
    async def _verify_api_connection(self) -> None:
        """Verify API connectivity."""
        try:
            # Check root endpoint for availability
            endpoint = self.config.base_url
            async with self.session.get(endpoint) as response:
                response.raise_for_status()
                # Local firecrawl might return different messages
                status = await response.json()
                if not status or ('message' not in status and status.get('status') != 'ok'):
                    raise FirecrawlError("API status check failed")
        except Exception as e:
            raise FirecrawlError(f"API connection verification failed: {str(e)}")

    async def scrape_url(
        self,
        url: str,
        options: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Scrape a single URL with Firecrawl API.
        """
        try:
            if not self.session:
                await self.initialize()
            
            # Validate URL
            if not self._validate_url_format(url):
                raise FirecrawlError(f"Invalid URL format: {url}")
            
            # Default options focused on markdown
            default_options = {'formats': ['markdown']}
            scrape_options = {**default_options, **(options or {})}
            
            # Use AsyncV1FirecrawlApp directly
            try:
                from firecrawl import AsyncV1FirecrawlApp
                
                # Pass base_url as api_url to use local instance
                firecrawl_app = AsyncV1FirecrawlApp(
                    api_key=self.config.api_key, 
                    api_url=self.config.base_url
                )
                
                # Use Async SDK's scrape_url
                scrape_result_obj = await firecrawl_app.scrape_url(url, **scrape_options)
                
                # Convert Pydantic model to dictionary
                result = scrape_result_obj.model_dump()
                
                # Wrap in 'data' key if success, to match expected structure
                if result.get('success') and 'data' not in result:
                    # Move content fields to 'data'
                    content_fields = [
                        'markdown', 'html', 'rawHtml', 'links', 'extract', 
                        'json_field', 'screenshot', 'metadata', 'actions', 
                        'title', 'description', 'changeTracking'
                    ]
                    data = {k: result[k] for k in content_fields if k in result}
                    return {
                        'success': True,
                        'data': data,
                        'warning': result.get('warning')
                    }
                
                return result
                
            except Exception as e:
                logger.error(f"Firecrawl API error: {str(e)}")
                raise FirecrawlError(f"API error: {str(e)}")
            
        except Exception as e:
            logger.error(f"URL scraping failed: {str(e)}")
            raise FirecrawlError(f"Failed to scrape URL: {str(e)}")

    async def scrape_urls(
        self,
        urls: List[str],
        options: Optional[Dict[str, Any]] = None
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Scrape multiple URLs concurrently with rate limiting.

        Args:
            urls: List of URLs to scrape
            options: Optional scraping options

        Yields:
            Dict[str, Any]: Scraped content and metadata for each URL
        """
        # Validate input
        if not urls:
            raise FirecrawlError("No URLs provided")

        # Initialize semaphore for concurrency control
        sem = asyncio.Semaphore(self.concurrent_limit)

        async def scrape_with_semaphore(url: str) -> Dict[str, Any]:
            """Scrape URL with semaphore control."""
            async with sem:
                try:
                    return await self.scrape_url(url, options)
                except Exception as e:
                    logger.error(f"Failed to scrape {url}: {str(e)}")
                    return {
                        'url': url,
                        'error': str(e),
                        'timestamp': datetime.now().isoformat()
                    }

        # Create tasks for all URLs
        tasks = [scrape_with_semaphore(url) for url in urls]

        # Process results as they complete
        for completed in asyncio.as_completed(tasks):
            try:
                result = await completed
                if 'error' not in result:
                    yield result
            except Exception as e:
                logger.error(f"Task completion error: {str(e)}")
                continue

    async def start_crawl(
        self,
        url: str,
        options: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Start an asynchronous crawl job.

        Args:
            url: Starting URL for crawl
            options: Optional crawl configuration

        Returns:
            Dict[str, Any]: Crawl job details
        """
        if not self.session:
            await self.initialize()

        try:
            # Validate URL
            if not validate_url(url):
                raise FirecrawlError(f"Invalid URL format: {url}")

            # Merge options with defaults
            crawl_options = {
                'limit': self.config.max_pages,
                'excludePaths': self.config.exclude_paths,
                'scrapeOptions': {
                    **self.config.scrape_options,
                    'formats': ['markdown']
                },
                **(options or {})
            }

            # Prepare request
            endpoint = f"{self.config.base_url}/v1/crawl"
            payload = {
                'url': url,
                'options': crawl_options
            }

            # Execute request
            async with self.session.post(endpoint, json=payload) as response:
                self._update_rate_limit(response)
                response.raise_for_status()
                result = await response.json()

                if 'error' in result:
                    raise FirecrawlError(f"API error: {result['error']}")

                # Track job
                job_id = result.get('jobId')
                if job_id:
                    self._active_jobs[job_id] = {
                        'url': url,
                        'status': 'started',
                        'options': crawl_options,
                        'start_time': datetime.now().isoformat()
                    }

                return result

        except Exception as e:
            logger.error(f"Failed to start crawl: {str(e)}")
            raise FirecrawlError(f"Crawl start failed: {str(e)}")

    async def check_crawl_status(
        self,
        job_id: str
    ) -> Dict[str, Any]:
        """
        Check status of a crawl job.

        Args:
            job_id: ID of crawl job to check

        Returns:
            Dict[str, Any]: Current job status
        """
        if job_id not in self._active_jobs:
            raise FirecrawlError(f"Unknown job ID: {job_id}")

        try:
            endpoint = f"{self.config.base_url}/v1/crawl/{job_id}/status"
            async with self.session.get(endpoint) as response:
                response.raise_for_status()
                result = await response.json()

                # Update job tracking
                self._active_jobs[job_id]['status'] = result.get('status')
                self._active_jobs[job_id]['last_check'] = datetime.now().isoformat()

                return result

        except Exception as e:
            logger.error(f"Failed to check crawl status: {str(e)}")
            raise FirecrawlError(f"Status check failed: {str(e)}")

    async def cancel_crawl(self, job_id: str) -> Dict[str, Any]:
        """
        Cancel an active crawl job.

        Args:
            job_id: ID of crawl job to cancel

        Returns:
            Dict[str, Any]: Cancellation status
        """
        if job_id not in self._active_jobs:
            raise FirecrawlError(f"Unknown job ID: {job_id}")

        try:
            endpoint = f"{self.config.base_url}/v1/crawl/{job_id}/cancel"
            async with self.session.post(endpoint) as response:
                response.raise_for_status()
                result = await response.json()

                if result.get('status') == 'cancelled':
                    self._active_jobs[job_id]['status'] = 'cancelled'

                return result

        except Exception as e:
            logger.error(f"Failed to cancel crawl: {str(e)}")
            raise FirecrawlError(f"Cancellation failed: {str(e)}")

    async def get_crawl_results(
        self,
        job_id: str,
        include_content: bool = True
    ) -> Dict[str, Any]:
        """
        Get results from a completed crawl job.

        Args:
            job_id: ID of completed crawl job
            include_content: Whether to include full content

        Returns:
            Dict[str, Any]: Crawl results and metadata
        """
        if job_id not in self._active_jobs:
            raise FirecrawlError(f"Unknown job ID: {job_id}")

        try:
            endpoint = f"{self.config.base_url}/v1/crawl/{job_id}/results"
            params = {'includeContent': 'true' if include_content else 'false'}

            async with self.session.get(endpoint, params=params) as response:
                response.raise_for_status()
                result = await response.json()

                if not include_content:
                    # Remove full content to reduce memory usage
                    if 'pages' in result:
                        for page in result['pages']:
                            if 'content' in page:
                                del page['content']

                return result

        except Exception as e:
            logger.error(f"Failed to get crawl results: {str(e)}")
            raise FirecrawlError(f"Results retrieval failed: {str(e)}")

    def _validate_url_format(self, url: str) -> bool:
        """Validate URL format."""
        try:
            return validate_url(url)
        except Exception:
            return False

    def _update_rate_limit(self, response: aiohttp.ClientResponse) -> None:
        """Update rate limit tracking from response headers."""
        try:
            if 'X-RateLimit-Remaining' in response.headers:
                self._rate_limit_remaining = int(response.headers['X-RateLimit-Remaining'])
            
            if 'X-RateLimit-Reset' in response.headers:
                self._rate_limit_reset = int(response.headers['X-RateLimit-Reset'])
            
            if self._rate_limit_remaining == 0:
                self._metrics['rate_limit_hits'] += 1
                logger.warning(f"Rate limit reached. Reset in {self._rate_limit_reset} seconds")
        except Exception as e:
            logger.debug(f"Failed to update rate limit info: {str(e)}")
