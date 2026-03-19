"""
Enhanced autonomous browser with self-healing capabilities and intelligent navigation.
File: src/research/browser_control.py
"""

from typing import Dict, Any, Optional, List, Set, Tuple, Union, TYPE_CHECKING
from datetime import datetime
from pathlib import Path
import re
from urllib.parse import urljoin, urlparse, parse_qs, urlencode, urlunparse
import json
import tldextract
import random

if TYPE_CHECKING:
    from src.research.browser_manager import BrowserManager
    from src.research.models import SourceType, ValidationLevel

from src.research.exceptions import BrowserError, BrowserNotInitializedError, BrowserTimeout
from src.utils.validation import validate_url

logger = logging.getLogger(__name__)

class AutonomousBrowser(BrowserManager):
    """Advanced browser with autonomous navigation and content extraction capabilities."""
    
    def __init__(
        self,
        headless: bool = True,
        timeout: int = 30,
        max_pages: int = 5,
        screenshot_dir: Optional[Path] = None,
        download_dir: Optional[Path] = None,
        retry_attempts: int = 3,
        retry_delay: float = 1.0,
        window_size: Tuple[int, int] = (1920, 1080),
        config: Optional[Dict[str, Any]] = None,
        options: Dict[str, Any] = None,
        request_headers: Dict[str, str] = None,
        auto_recovery: bool = True,
        max_consecutive_errors: int = 5,
        intelligent_retries: bool = True
    ):
        """Initialize autonomous browser with enhanced capabilities."""
        # Call parent constructor first
        super().__init__(
            headless=headless,
            timeout=timeout,
            max_pages=max_pages,
            screenshot_dir=screenshot_dir,
            download_dir=download_dir,
            retry_attempts=retry_attempts,
            retry_delay=retry_delay,
            window_size=window_size,
            config=config,
            options=options,
            request_headers=request_headers
        )
        
        # Autonomous capabilities
        self.auto_recovery = auto_recovery
        self.max_consecutive_errors = max_consecutive_errors
        self.intelligent_retries = intelligent_retries
        
        # Autonomous state tracking
        self._consecutive_errors = 0
        self._error_timestamps = []
        self._navigated_domains = set()
        self._detected_paywalls = set()
        self._detected_blocking = set()
        self._recovery_attempts = 0
        
        # Intelligent navigation tracking
        self._navigation_history = []
        self._visited_page_types = {
            'article': 0,
            'search': 0,
            'listing': 0,
            'error': 0,
            'paywall': 0
        }
        
        # Content extraction enhancements
        self._content_analyzers = {
            'readability': None,  # Initialized later if needed
            'sentiment': None,    # Initialized later if needed
            'html2md': None       # Initialized later if needed
        }
        
        # Load custom extraction rules
        self._extraction_rules = {
            'news': {
                'content_selectors': ['article', '.entry-content', '.article-content'],
                'date_selectors': ['.publish-date', '.date', 'time'],
                'author_selectors': ['.author', '.byline', '[rel="author"]'],
                'title_selectors': ['h1', '.headline', '.article-title']
            },
            'research': {
                'content_selectors': ['.paper', '.research-content', 'article'],
                'date_selectors': ['.published-date', '.pub-date'],
                'author_selectors': ['.authors', '.researchers'],
                'title_selectors': ['h1.paper-title', '.research-title']
            },
            'blog': {
                'content_selectors': ['.post-content', '.blog-post', 'article'],
                'date_selectors': ['.post-date', '.blog-date', 'time'],
                'author_selectors': ['.post-author', '.blog-author'],
                'title_selectors': ['.post-title', '.blog-title', 'h1']
            }
        }
        
        # Intelligent browsing module
        self._ratelimiting_strategies = {
            'normal': {'delay_range': (1, 3)},
            'aggressive': {'delay_range': (4, 7)},
            'stealth': {'delay_range': (5, 15), 'random_actions': True}
        }
        self._current_strategy = 'normal'
    
    async def initialize(self) -> None:
        """Initialize browser with enhanced setup."""
        try:
            await super().initialize()
            
            # Load dependencies for content extraction if needed
            try:
                import readability
                import html2text
                
                self._content_analyzers['readability'] = readability
                self._content_analyzers['html2md'] = html2text.HTML2Text()
                self._content_analyzers['html2md'].ignore_links = False
                self._content_analyzers['html2md'].ignore_images = False
                self._content_analyzers['html2md'].body_width = 0  # No wrapping
                
                logger.info("Enhanced content analyzers loaded successfully")
            except ImportError:
                logger.warning("Enhanced content analyzers not available")
            
            logger.info("AutonomousBrowser initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize AutonomousBrowser: {str(e)}")
            await self.cleanup()
            raise BrowserError(f"AutonomousBrowser initialization failed: {str(e)}")
    
    async def navigate_intelligently(
        self,
        query: str,
        depth: int = 3,
        source_types: Optional[List[str]] = None,
        progress_callback: Optional[callable] = None
    ) -> Dict[str, Any]:
        """
        Intelligently navigate the web to gather information on a query.
        
        Args:
            query: Search query
            depth: Maximum depth of navigation
            source_types: Optional types of sources to prioritize
            progress_callback: Optional progress callback
            
        Returns:
            Dict[str, Any]: Found content and metadata
        """
        if not self._initialized:
            raise BrowserNotInitializedError("intelligent navigation")
        
        source_types = source_types or ['news', 'research', 'blog']
        results = {
            'query': query,
            'sources': [],
            'content': [],
            'metadata': {
                'pages_visited': 0,
                'domains_visited': set(),
                'errors_encountered': 0,
                'start_time': datetime.now().isoformat(),
                'end_time': None
            }
        }
        
        try:
            # Start with search
            if progress_callback:
                progress_callback(0.1)
                
            search_results = await self.gather_content(query)
            top_urls = search_results.get('results', [])[:self.max_pages]
            
            if progress_callback:
                progress_callback(0.3)
            
            # Navigate to pages and extract content
            for idx, url_data in enumerate(top_urls):
                try:
                    url = url_data.get('url')
                    if not url:
                        continue
                    
                    # Extract content from page
                    page_content = await self.browse_url(url)
                    if not page_content:
                        continue
                    
                    # Convert to markdown if possible
                    markdown_content = await self._extract_markdown(page_content, url)
                    
                    # Determine source type
                    source_type = self._determine_source_type(url, page_content)
                    
                    # Extract metadata
                    metadata = await self._extract_metadata(page_content, url, source_type)
                    
                    # Add to results
                    results['sources'].append({
                        'url': url,
                        'title': url_data.get('title', ''),
                        'source_type': source_type,
                        'metadata': metadata
                    })
                    
                    results['content'].append({
                        'url': url,
                        'html': page_content[:5000],  # Limit size
                        'markdown': markdown_content,
                        'timestamp': datetime.now().isoformat()
                    })
                    
                    # Update metadata
                    results['metadata']['pages_visited'] += 1
                    results['metadata']['domains_visited'].add(urlparse(url).netloc)
                    
                    # Link discovery and follow if depth > 1
                    if depth > 1:
                        await self._follow_relevant_links(
                            page_content, 
                            url, 
                            results, 
                            depth - 1, 
                            source_types
                        )
                    
                    # Update progress
                    if progress_callback:
                        progress_callback(0.3 + (0.7 * (idx + 1) / len(top_urls)))
                    
                except Exception as e:
                    logger.warning(f"Error processing {url}: {str(e)}")
                    results['metadata']['errors_encountered'] += 1
                    
                    # Apply auto-recovery if enabled
                    if self.auto_recovery:
                        await self._attempt_recovery()
            
            # Finalize results
            results['metadata']['end_time'] = datetime.now().isoformat()
            results['metadata']['domains_visited'] = list(results['metadata']['domains_visited'])
            
            if progress_callback:
                progress_callback(1.0)
            
            return results
            
        except Exception as e:
            logger.error(f"Intelligent navigation failed: {str(e)}")
            self._consecutive_errors += 1
            self._error_timestamps.append(datetime.now().isoformat())
            
            # Apply auto-recovery for severe errors
            if self.auto_recovery and self._consecutive_errors >= self.max_consecutive_errors:
                await self._emergency_recovery()
            
            raise BrowserError(f"Intelligent navigation failed: {str(e)}")
    
    async def _extract_markdown(self, html_content: str, url: str) -> str:
        """Extract markdown from HTML content."""
        try:
            if self._content_analyzers['html2md']:
                markdown = self._content_analyzers['html2md'].handle(html_content)
                return markdown
            
            # Fallback to simple extraction if html2text not available
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # Remove script, style elements
            for element in soup(['script', 'style', 'iframe', 'noscript']):
                element.decompose()
            
            # Extract text
            text = soup.get_text(separator='\n\n')
            
            # Basic markdown conversion
            lines = []
            for line in text.split('\n'):
                if line.strip():
                    lines.append(line.strip())
            
            return '\n\n'.join(lines)
            
        except Exception as e:
            logger.warning(f"Markdown extraction failed for {url}: {str(e)}")
            return ""
    
    async def _extract_metadata(
        self,
        html_content: str,
        url: str,
        source_type: str
    ) -> Dict[str, Any]:
        """Extract metadata from HTML content."""
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # Select appropriate extraction rules
            rules = self._extraction_rules.get(
                source_type, 
                self._extraction_rules['blog']  # Default to blog rules
            )
            
            metadata = {
                'title': None,
                'author': None,
                'date': None,
                'word_count': 0,
                'extracted_at': datetime.now().isoformat()
            }
            
            # Extract title
            for selector in rules['title_selectors']:
                element = soup.select_one(selector)
                if element and element.text.strip():
                    metadata['title'] = element.text.strip()
                    break
            
            # Extract author
            for selector in rules['author_selectors']:
                element = soup.select_one(selector)
                if element and element.text.strip():
                    metadata['author'] = element.text.strip()
                    break
            
            # Extract date
            for selector in rules['date_selectors']:
                element = soup.select_one(selector)
                if element and element.text.strip():
                    metadata['date'] = element.text.strip()
                    break
            
            # If date is in an attribute (common for time elements)
            time_elem = soup.find('time')
            if time_elem and time_elem.get('datetime'):
                metadata['date'] = time_elem.get('datetime')
            
            # Extract content and count words
            content_text = ""
            for selector in rules['content_selectors']:
                elements = soup.select(selector)
                for element in elements:
                    content_text += element.text
            
            # Count words
            if content_text:
                metadata['word_count'] = len(content_text.split())
            
            # Get page keywords and description
            meta_keywords = soup.find('meta', {'name': 'keywords'})
            if meta_keywords:
                metadata['keywords'] = meta_keywords.get('content', '')
            
            meta_description = soup.find('meta', {'name': 'description'})
            if meta_description:
                metadata['description'] = meta_description.get('content', '')
            
            return metadata
            
        except Exception as e:
            logger.warning(f"Metadata extraction failed for {url}: {str(e)}")
            return {
                'extracted_at': datetime.now().isoformat(),
                'error': str(e)
            }
    
    def _determine_source_type(self, url: str, content: str) -> str:
        """Determine source type from URL and content patterns."""
        url_lower = url.lower()
        
        # Check URL patterns
        if any(edu in url_lower for edu in ['.edu', 'university', 'academic']):
            return 'research'
        if any(news in url_lower for news in ['news', 'article', 'story']):
            return 'news'
        if any(blog in url_lower for blog in ['blog', 'post']):
            return 'blog'
        
        # Check content patterns
        if content:
            content_lower = content.lower()
            
            # Research indicators
            if (
                re.search(r'\b(?:research|study|paper|journal|doi)\b', content_lower) and
                re.search(r'\b(?:method|methodology|results|conclusion)\b', content_lower)
            ):
                return 'research'
            
            # News indicators
            if (
                re.search(r'\b(?:news|report|reported|article)\b', content_lower) and
                re.search(r'\b(?:today|yesterday|week|month)\b', content_lower)
            ):
                return 'news'
        
        # Default to blog
        return 'blog'
    
    async def _follow_relevant_links(
        self,
        content: str,
        base_url: str,
        results: Dict[str, Any],
        depth: int,
        source_types: List[str]
    ) -> None:
        """Follow relevant links from page content."""
        if depth <= 0:
            return
        
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(content, 'html.parser')
            
            links = []
            base_domain = urlparse(base_url).netloc
            
            # Find all links
            for a_tag in soup.find_all('a', href=True):
                href = a_tag.get('href')
                
                # Skip empty or javascript links
                if not href or href.startswith('javascript:') or href.startswith('#'):
                    continue
                
                # Convert to absolute URL
                absolute_url = urljoin(base_url, href)
                
                # Skip already visited URLs
                if absolute_url in [source['url'] for source in results['sources']]:
                    continue
                
                # Prioritize same-domain links
                link_domain = urlparse(absolute_url).netloc
                is_same_domain = link_domain == base_domain
                
                # Score the link relevance
                link_text = a_tag.text.strip().lower()
                relevance_score = 0
                
                # Higher score for links that match source types
                for source_type in source_types:
                    if source_type in link_text:
                        relevance_score += 2
                
                # Higher score for same domain
                if is_same_domain:
                    relevance_score += 3
                
                # Higher score for "content" paths
                path = urlparse(absolute_url).path.lower()
                if any(p in path for p in ['article', 'research', 'blog', 'paper']):
                    relevance_score += 2
                
                links.append({
                    'url': absolute_url,
                    'text': link_text,
                    'relevance': relevance_score
                })
            
            # Sort by relevance and take top 3
            links.sort(key=lambda x: x['relevance'], reverse=True)
            top_links = links[:3]
            
            # Follow links
            for link in top_links:
                try:
                    # Apply appropriate delay based on current strategy
                    await self._apply_strategy_delay()
                    
                    page_content = await self.browse_url(link['url'])
                    if not page_content:
                        continue
                    
                    # Convert to markdown
                    markdown_content = await self._extract_markdown(page_content, link['url'])
                    
                    # Determine source type
                    source_type = self._determine_source_type(link['url'], page_content)
                    
                    # Extract metadata
                    metadata = await self._extract_metadata(page_content, link['url'], source_type)
                    
                    # Add to results
                    results['sources'].append({
                        'url': link['url'],
                        'title': link['text'] or metadata.get('title', ''),
                        'source_type': source_type,
                        'metadata': metadata
                    })
                    
                    results['content'].append({
                        'url': link['url'],
                        'html': page_content[:5000],  # Limit size
                        'markdown': markdown_content,
                        'timestamp': datetime.now().isoformat()
                    })
                    
                    # Update metadata
                    results['metadata']['pages_visited'] += 1
                    results['metadata']['domains_visited'].add(urlparse(link['url']).netloc)
                    
                    # Recursively follow links with decreased depth
                    await self._follow_relevant_links(
                        page_content, 
                        link['url'], 
                        results, 
                        depth - 1, 
                        source_types
                    )
                    
                except Exception as e:
                    logger.warning(f"Error following link {link['url']}: {str(e)}")
                    results['metadata']['errors_encountered'] += 1
            
        except Exception as e:
            logger.warning(f"Error extracting links from {base_url}: {str(e)}")
    
    async def _attempt_recovery(self) -> None:
        """Attempt to recover from errors."""
        try:
            self._recovery_attempts += 1
            logger.info(f"Attempting recovery ({self._recovery_attempts})")
            
            # Clear browser cache and cookies
            await self.clear_cache()
            
            # Change browsing strategy to be more cautious
            self._update_browsing_strategy('stealth')
            
            # Pause briefly to allow rate limits to reset
            await asyncio.sleep(self.retry_delay * 2)
            
            # If multiple recovery attempts, reinitialize browser
            if self._recovery_attempts >= 3:
                logger.info("Multiple recovery attempts - reinitializing browser")
                await self.cleanup()
                await self.initialize()
                self._recovery_attempts = 0
            
        except Exception as e:
            logger.error(f"Recovery attempt failed: {str(e)}")
    
    async def _emergency_recovery(self) -> None:
        """Emergency recovery for severe error conditions."""
        try:
            logger.warning("Performing emergency recovery")
            
            # Force browser cleanup and restart
            await self.cleanup()
            
            # Wait longer before restart
            await asyncio.sleep(10)
            
            # Reinitialize browser with more conservative settings
            self.headless = True  # Ensure headless
            self.retry_delay *= 2  # Double retry delay
            await self.initialize()
            
            # Reset error counters
            self._consecutive_errors = 0
            self._error_timestamps = []
            self._recovery_attempts = 0
            
            # Use most conservative browsing strategy
            self._update_browsing_strategy('stealth')
            
        except Exception as e:
            logger.error(f"Emergency recovery failed: {str(e)}")
    
    def _update_browsing_strategy(self, strategy: str) -> None:
        """Update browsing strategy."""
        if strategy in self._ratelimiting_strategies:
            self._current_strategy = strategy
            logger.info(f"Switched to '{strategy}' browsing strategy")
    
    async def _apply_strategy_delay(self) -> None:
        """Apply delay according to current strategy."""
        strategy = self._ratelimiting_strategies[self._current_strategy]
        delay_range = strategy.get('delay_range', (1, 3))
        delay = random.uniform(*delay_range)
        
        # Add random actions if in stealth mode
        if strategy.get('random_actions') and self.driver:
            try:
                # Random scroll
                self.driver.execute_script(f"window.scrollTo(0, {random.randint(100, 500)});")
                await asyncio.sleep(random.uniform(0.5, 1.5))
                
                # Random mouse movement simulation
                self.driver.execute_script(
                    f"document.body.dispatchEvent(new MouseEvent('mousemove', "
                    f"{{clientX: {random.randint(10, 500)}, clientY: {random.randint(10, 500)}}}))"
                )
            except Exception:
                pass  # Ignore errors in random actions
        
        await asyncio.sleep(delay)
    
    async def extract_content_intelligent(
        self, 
        url: str,
        extraction_type: str = 'auto',
        validation_level: ValidationLevel = ValidationLevel.MEDIUM
    ) -> Dict[str, Any]:
        """
        Extract content from URL with intelligent processing.
        
        Args:
            url: URL to extract from
            extraction_type: Type of extraction ('auto', 'article', 'research', 'blog')
            validation_level: Validation level to apply
            
        Returns:
            Dict[str, Any]: Extracted content and metadata
        """
        if not self._initialized:
            raise BrowserNotInitializedError("intelligent extraction")
        
        try:
            # Browse URL
            html_content = await self.browse_url(url)
            if not html_content:
                raise BrowserError(f"Failed to load content from {url}")
            
            # Determine content type if auto
            content_type = extraction_type
            if extraction_type == 'auto':
                content_type = self._determine_source_type(url, html_content)
            
            # Extract markdown
            markdown = await self._extract_markdown(html_content, url)
            
            # Extract metadata
            metadata = await self._extract_metadata(html_content, url, content_type)
            
            # Check for paywalls or content blocking
            is_blocked = self._check_for_blocking(html_content, url)
            if is_blocked:
                if urlparse(url).netloc not in self._detected_blocking:
                    self._detected_blocking.add(urlparse(url).netloc)
                
                metadata['is_blocked'] = True
                metadata['blocking_type'] = is_blocked
            
            # Validate content based on level
            validation_results = {}
            if markdown:
                validation_results = await self._validate_content(
                    markdown, 
                    validation_level
                )
            
            return {
                'url': url,
                'content_type': content_type,
                'html': html_content[:5000],  # Limit size
                'markdown': markdown,
                'metadata': metadata,
                'validation': validation_results,
                'extraction_timestamp': datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Intelligent extraction failed for {url}: {str(e)}")
            
            # Record error and attempt recovery
            self._consecutive_errors += 1
            self._error_timestamps.append(datetime.now().isoformat())
            
            if self.auto_recovery and self._consecutive_errors >= 3:
                await self._attempt_recovery()
            
            raise BrowserError(f"Intelligent extraction failed: {str(e)}")
    
    def _check_for_blocking(self, content: str, url: str) -> Optional[str]:
        """Check if content has paywalls or other blocking mechanisms."""
        if not content:
            return None
            
        # Common paywall/blocking indicators
        paywall_patterns = [
            r'subscribe\s+to\s+continue',
            r'subscription\s+required',
            r'premium\s+access',
            r'sign\s+in\s+to\s+continue',
            r'create\s+an\s+account',
            r'plus\s+subscribers\s+only',
            r'article\s+reserved\s+for\s+subscribers',
            r'to\s+continue\s+reading',
            r'subscribe\s+now',
            r'already\s+a\s+subscriber'
        ]
        
        content_lower = content.lower()
        
        # Check for paywall indicators
        for pattern in paywall_patterns:
            if re.search(pattern, content_lower):
                return 'paywall'
        
        # Check for low content volume (possible javascript-based blocking)
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(content, 'html.parser')
        
        # Remove scripts, styles, etc.
        for tag in soup(['script', 'style', 'header', 'footer', 'nav']):
            tag.decompose()
        
        # Extract remaining text
        text = soup.get_text()
        if len(text.split()) < 100:  # Less than 100 words
            return 'low_content'
        
        # Check for CAPTCHAs
        if re.search(r'captcha|recaptcha|cloudflare|ddos', content_lower):
            return 'captcha'
        
        # Check for robots.txt blockers
        if re.search(r'access denied|forbidden|403', content_lower):
            return 'robots_denied'
        
        return None
    
    async def _validate_content(
        self,
        content: str,
        level: ValidationLevel
    ) -> Dict[str, Any]:
        """Validate content quality and relevance."""
        validation = {
            'word_count': len(content.split()),
            'has_urls': bool(re.search(r'https?://\S+', content)),
            'has_citations': bool(re.search(r'\[\d+\]|\(\w+,\s*\d{4}\)', content)),
            'readability_score': self._calculate_readability(content)
        }
        
        # Additional validation for higher levels
        if level in [ValidationLevel.HIGH, ValidationLevel.MEDIUM]:
            # Check for data points (numbers, percentages, etc.)
            data_matches = re.findall(r'\d+(?:\.\d+)?%|\d+\s*(?:million|billion)', content)
            validation['data_points'] = len(data_matches)
            
            # Check for date references
            date_matches = re.findall(
                r'\d{4}-\d{2}-\d{2}|\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]* \d{1,2},? \d{4}\b',
                content
            )
            validation['date_references'] = len(date_matches)
            
            # Check for section structure
            section_matches = re.findall(r'^#{1,3}\s+.+$', content, re.MULTILINE)
            validation['structured_sections'] = len(section_matches)
        
        # Determine quality score based on validation
        quality_score = self._calculate_quality_score(validation)
        validation['quality_score'] = quality_score
        
        # Set pass/fail based on level
        if level == ValidationLevel.HIGH:
            validation['passes_validation'] = quality_score >= 0.8
        elif level == ValidationLevel.MEDIUM:
            validation['passes_validation'] = quality_score >= 0.6
        elif level == ValidationLevel.LOW:
            validation['passes_validation'] = quality_score >= 0.4
        else:
            validation['passes_validation'] = True
        
        return validation
    
    async def extract_with_context(
        self,
        query: str,
        urls: List[str],
        context_type: str = 'research'
    ) -> Dict[str, Any]:
        """
        Extract content from multiple URLs with contextual understanding.
        
        Args:
            query: Research query to provide context
            urls: List of URLs to process
            context_type: Type of context ('research', 'news', 'technical')
            
        Returns:
            Dict[str, Any]: Extracted content with contextual analysis
        """
        if not self._initialized:
            raise BrowserNotInitializedError("contextual extraction")
        
        contextual_results = {
            'query': query,
            'context_type': context_type,
            'sources_processed': 0,
            'sources_succeeded': 0,
            'sources_failed': 0,
            'extracted_content': [],
            'contextual_analysis': {},
            'timestamp': datetime.now().isoformat()
        }
        
        try:
            # Process each URL
            for url in urls:
                try:
                    # Apply delay based on current strategy
                    await self._apply_strategy_delay()
                    
                    # Extract content intelligently
                    extraction_result = await self.extract_content_intelligent(
                        url,
                        extraction_type='auto',
                        validation_level=ValidationLevel.MEDIUM
                    )
                    
                    # Skip if no valid content
                    if not extraction_result.get('markdown'):
                        contextual_results['sources_failed'] += 1
                        continue
                    
                    # Add to results
                    contextual_results['extracted_content'].append(extraction_result)
                    contextual_results['sources_succeeded'] += 1
                    
                except Exception as e:
                    logger.warning(f"Failed to extract from {url}: {str(e)}")
                    contextual_results['sources_failed'] += 1
                
                contextual_results['sources_processed'] += 1
            
            # Generate contextual analysis if we have content
            if contextual_results['extracted_content']:
                contextual_results['contextual_analysis'] = await self._generate_contextual_analysis(
                    contextual_results['extracted_content'],
                    query,
                    context_type
                )
            
            return contextual_results
            
        except Exception as e:
            logger.error(f"Contextual extraction failed: {str(e)}")
            raise BrowserError(f"Contextual extraction failed: {str(e)}")
    
    async def _generate_contextual_analysis(
        self,
        extracted_content: List[Dict[str, Any]],
        query: str,
        context_type: str
    ) -> Dict[str, Any]:
        """Generate contextual analysis of extracted content."""
        analysis = {
            'query': query,
            'content_overview': {
                'total_sources': len(extracted_content),
                'total_words': sum(
                    c.get('metadata', {}).get('word_count', 0) 
                    for c in extracted_content
                ),
                'avg_quality_score': sum(
                    c.get('validation', {}).get('quality_score', 0) 
                    for c in extracted_content
                ) / len(extracted_content) if extracted_content else 0
            },
            'source_types': {},
            'high_quality_sources': [],
            'content_consistency': 'unknown',
            'timestamp': datetime.now().isoformat()
        }
        
        # Count source types
        for content in extracted_content:
            source_type = content.get('content_type', 'unknown')
            if source_type not in analysis['source_types']:
                analysis['source_types'][source_type] = 0
            analysis['source_types'][source_type] += 1
        
        # Identify high-quality sources
        for content in extracted_content:
            quality_score = content.get('validation', {}).get('quality_score', 0)
            if quality_score >= 0.7:
                analysis['high_quality_sources'].append({
                    'url': content.get('url'),
                    'type': content.get('content_type'),
                    'quality_score': quality_score
                })
        
        # Assess content consistency
        if len(extracted_content) >= 2:
            # Very basic consistency check based on word overlaps
            # In a real implementation, you'd use more sophisticated NLP
            common_words = self._find_common_significant_words(
                [c.get('markdown', '') for c in extracted_content]
            )
            
            consistency_score = len(common_words) / 10  # Arbitrary scaling
            
            if consistency_score > 0.7:
                analysis['content_consistency'] = 'high'
            elif consistency_score > 0.4:
                analysis['content_consistency'] = 'medium'
            else:
                analysis['content_consistency'] = 'low'
                
            analysis['common_terms'] = list(common_words)[:10]  # Top 10 common terms
        
        return analysis
    
    def _find_common_significant_words(self, texts: List[str]) -> Set[str]:
        """Find common significant words across texts."""
        try:
            if not texts:
                return set()
                
            # Simple stopwords list
            stopwords = set([
                'and', 'the', 'is', 'in', 'to', 'a', 'of', 'for', 'as', 'on', 'with',
                'by', 'this', 'that', 'it', 'at', 'from', 'be', 'are', 'was', 'were',
                'an', 'or', 'will', 'would', 'could', 'should', 'can', 'not'
            ])
            
            # Get words from each text
            word_sets = []
            for text in texts:
                words = set(
                    word.lower() for word in re.findall(r'\b[a-zA-Z]{3,}\b', text)
                    if word.lower() not in stopwords
                )
                word_sets.append(words)
            
            # Find common words
            if word_sets:
                common_words = set.intersection(*word_sets)
                return common_words
            
            return set()
            
        except Exception:
            return set()
    
    async def search_and_extract(
        self,
        query: str,
        max_results: int = 5,
        research_type: str = 'general',
        validation_level: ValidationLevel = ValidationLevel.MEDIUM
    ) -> Dict[str, Any]:
        """
        Combined search and extraction with intelligent processing.
        
        Args:
            query: Search query
            max_results: Maximum number of results to process
            research_type: Type of research ('general', 'academic', 'news', 'technical')
            validation_level: Validation level to apply
            
        Returns:
            Dict[str, Any]: Search and extraction results
        """
        if not self._initialized:
            raise BrowserNotInitializedError("search and extract")
        
        result = {
            'query': query,
            'research_type': research_type,
            'sources': [],
            'extracted_content': [],
            'metadata': {
                'start_time': datetime.now().isoformat(),
                'end_time': None,
                'urls_searched': 0,
                'successful_extractions': 0,
                'failed_extractions': 0
            }
        }
        
        try:
            # Adjust search engine based on research type
            search_engine = "google"  # Default
            if research_type == 'academic':
                search_engine = "google_scholar"
            elif research_type == 'news':
                search_engine = "news_search"
            
            # Add appropriate keywords based on research type
            enhanced_query = query
            if research_type == 'academic':
                enhanced_query += " research OR study OR paper OR journal"
            elif research_type == 'technical':
                enhanced_query += " tutorial OR documentation OR guide OR how-to"
            elif research_type == 'news':
                enhanced_query += " news OR recent OR latest OR update"
            
            # Perform search
            search_results = await self.gather_content(
                enhanced_query,
                search_engine=search_engine
            )
            
            # Process top results
            top_results = search_results.get('results', [])[:max_results]
            result['metadata']['urls_searched'] = len(top_results)
            
            for url_data in top_results:
                try:
                    url = url_data.get('url')
                    if not url:
                        continue
                    
                    # Apply delay based on current strategy
                    await self._apply_strategy_delay()
                    
                    # Extract content
                    extraction = await self.extract_content_intelligent(
                        url, 
                        extraction_type='auto',
                        validation_level=validation_level
                    )
                    
                    # Add success to results
                    result['sources'].append({
                        'url': url,
                        'title': url_data.get('title', ''),
                        'snippet': url_data.get('snippet', ''),
                        'source_type': extraction.get('content_type', 'unknown'),
                        'quality_score': extraction.get('validation', {}).get('quality_score', 0)
                    })
                    
                    result['extracted_content'].append(extraction)
                    result['metadata']['successful_extractions'] += 1
                    
                except Exception as e:
                    logger.warning(f"Extraction failed for {url}: {str(e)}")
                    result['metadata']['failed_extractions'] += 1
                    
                    # Track failure in sources
                    result['sources'].append({
                        'url': url_data.get('url', ''),
                        'title': url_data.get('title', ''),
                        'error': str(e),
                        'success': False
                    })
                    
                    # Apply recovery if needed
                    if self.auto_recovery and self._consecutive_errors >= 3:
                        await self._attempt_recovery()
            
            # Finalize result
            result['metadata']['end_time'] = datetime.now().isoformat()
            
            return result
            
        except Exception as e:
            logger.error(f"Search and extract failed: {str(e)}")
            
            # Record final time even for errors
            result['metadata']['end_time'] = datetime.now().isoformat()
            
            raise BrowserError(f"Search and extract failed: {str(e)}")
    
    async def cleanup(self) -> None:
        """Enhanced cleanup with state reset."""
        try:
            # Reset autonomous tracking state
            self._consecutive_errors = 0
            self._error_timestamps = []
            self._recovery_attempts = 0
            self._navigated_domains = set()
            self._detected_paywalls = set()
            self._detected_blocking = set()
            self._navigation_history = []
            self._visited_page_types = {
                'article': 0,
                'search': 0,
                'listing': 0,
                'error': 0,
                'paywall': 0
            }
            
            # Call parent cleanup
            await super().cleanup()
            
        except Exception as e:
            logger.error(f"AutonomousBrowser cleanup failed: {str(e)}")
            raise
    
    def _calculate_readability(self, content: str) -> float:
        """Calculate simple readability score."""
        try:
            sentences = re.split(r'[.!?]+', content)
            words = content.split()
            
            if not sentences or not words:
                return 0.0
            
            avg_sentence_length = len(words) / len(sentences)
            avg_word_length = sum(len(word) for word in words) / len(words)
            
            # Simple readability score between 0 and 1
            score = 1.0 - (
                min(max((avg_sentence_length - 10) / 20, 0), 1) * 0.5 +
                min(max((avg_word_length - 4) / 4, 0), 1) * 0.5
            )
            
            return round(score, 2)
            
        except Exception:
            return 0.0
    
    def _calculate_quality_score(self, validation: Dict[str, Any]) -> float:
        """Calculate content quality score from validation data."""
        score = 0.0
        
        # Base score from word count (up to 0.3)
        word_count = validation.get('word_count', 0)
        score += min(word_count / 1000, 1.0) * 0.3
        
        # Score for citations (up to 0.2)
        if validation.get('has_citations'):
            score += 0.2
        
        # Score for data points (up to 0.15)
        data_points = validation.get('data_points', 0)
        score += min(data_points / 5, 1.0) * 0.15
        
        # Score for structured content (up to 0.15)
        structured_sections = validation.get('structured_sections', 0)
        score += min(structured_sections / 3, 1.0) * 0.15
        
        # Score for readability (up to 0.2)
        readability = validation.get('readability_score', 0)
        score += readability * 0.2
        
        # Return final score (max 1.0)
        return round(min(score, 1.0), 2)
        
    async def detect_content_type(self, url: str) -> str:
        """
        Detect content type from URL and page content.
        
        Args:
            url: URL to check
            
        Returns:
            str: Detected content type
        """
        if not self._initialized:
            raise BrowserNotInitializedError("content type detection")
            
        try:
            # Browse URL
            content = await self.browse_url(url)
            if not content:
                raise BrowserError(f"Failed to load content from {url}")
                
            # Check URL patterns first
            url_lower = url.lower()
            
            # Academic patterns
            if any(edu in url_lower for edu in ['.edu', 'university', 'academic']):
                return SourceType.SCHOLARLY.value
                
            # Government patterns
            if '.gov' in url_lower:
                return SourceType.GOVERNMENT.value
                
            # Scientific patterns
            if any(sci in url_lower for sci in ['science', 'research', 'arxiv']):
                return SourceType.SCIENTIFIC.value
                
            # News patterns
            if any(news in url_lower for news in ['news', 'article', 'post']):
                return SourceType.NEWS.value
                
            # Technical patterns
            if any(tech in url_lower for tech in ['docs', 'documentation', 'guide']):
                return SourceType.TECHNICAL.value
                
            # Now check content patterns
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(content, 'html.parser')
            
            # Remove script, style elements
            for element in soup(['script', 'style', 'iframe', 'noscript']):
                element.decompose()
                
            # Get text content
            text_content = soup.get_text().lower()
            
            # Check for scientific indicators
            scientific_terms = ['doi', 'abstract', 'methodology', 'hypothesis', 'experiment']
            scientific_count = sum(1 for term in scientific_terms if term in text_content)
            if scientific_count >= 3:
                return SourceType.SCIENTIFIC.value
                
            # Check for news indicators
            news_terms = ['published', 'reporter', 'editor', 'article', 'reported']
            news_count = sum(1 for term in news_terms if term in text_content)
            if news_count >= 3:
                return SourceType.NEWS.value
                
            # Check for technical indicators
            tech_terms = ['function', 'method', 'class', 'api', 'implementation']
            tech_count = sum(1 for term in tech_terms if term in text_content)
            if tech_count >= 3:
                return SourceType.TECHNICAL.value
                
            # Check for reference indicators
            ref_terms = ['reference', 'dictionary', 'encyclopedia', 'definition']
            ref_count = sum(1 for term in ref_terms if term in text_content)
            if ref_count >= 2:
                return SourceType.REFERENCE.value
                
            # Default to webpage
            return SourceType.WEBPAGE.value
            
        except Exception as e:
            logger.error(f"Content type detection failed: {str(e)}")
            self._consecutive_errors += 1
            
            if self.auto_recovery and self._consecutive_errors >= 3:
                await self._attempt_recovery()
                
            # Default to webpage on error
            return SourceType.WEBPAGE.value
            
    async def check_source_reliability(self, url: str) -> float:
        """
        Check reliability of a source URL.
        
        Args:
            url: URL to check
            
        Returns:
            float: Reliability score (0.0-1.0)
        """
        try:
            # Domain-based reliability
            domain = urlparse(url).netloc.lower()
            
            # High reliability domains
            high_reliability = [
                'wikipedia.org',
                '.edu',
                '.gov',
                'arxiv.org',
                'scholar.google.com',
                'nature.com',
                'science.org',
                'sciencedirect.com',
                'springer.com',
                'acm.org',
                'ieee.org'
            ]
            
            # Medium reliability domains
            medium_reliability = [
                'nytimes.com',
                'bbc.com',
                'reuters.com',
                'bloomberg.com',
                'economist.com',
                'wsj.com',
                'washingtonpost.com',
                'theguardian.com',
                'medium.com',
                'stackoverflow.com',
                'github.com',
                'docs.microsoft.com',
                'developer.mozilla.org'
            ]
            
            # Check high reliability domains
            for rel_domain in high_reliability:
                if rel_domain in domain:
                    return 0.9
                    
            # Check medium reliability domains
            for rel_domain in medium_reliability:
                if rel_domain in domain:
                    return 0.7
                    
            # Default reliability for unknown domains
            return 0.5
            
        except Exception as e:
            logger.error(f"Reliability check failed: {str(e)}")
            return 0.3  # Lower score for errors
    
    async def extract_citations(self, content: str) -> List[Dict[str, Any]]:
        """
        Extract citations from content.
        
        Args:
            content: Content to extract citations from
            
        Returns:
            List[Dict[str, Any]]: Extracted citations
        """
        citations = []
        
        try:
            # Common citation patterns
            patterns = [
                # APA style
                r'\(([A-Za-z]+(?:\s+et\s+al\.)?),\s+(\d{4})[^)]*\)',
                
                # IEEE style
                r'\[(\d+)\]',
                
                # MLA style
                r'\(([A-Za-z]+)\s+(\d+(?:-\d+)?)\)',
                
                # Chicago style
                r'\d+\.\s+([A-Za-z]+(?:\s+et\s+al\.)?),\s+[^,]+,\s+[^,]+,\s+(\d{4})',
                
                # Harvard style
                r'\(([A-Za-z]+),\s+(\d{4})\)'
            ]
            
            for pattern in patterns:
                matches = re.findall(pattern, content)
                for match in matches:
                    citation = {}
                    
                    # Handle different match formats
                    if isinstance(match, tuple):
                        if len(match) >= 2:
                            citation['author'] = match[0]
                            citation['year'] = match[1] if match[1].isdigit() else None
                            
                            # For IEEE style, there's no author in the citation
                            if pattern == patterns[1]:  # IEEE pattern
                                citation['reference_number'] = match[0]
                                citation['author'] = None
                                citation['year'] = None
                    else:
                        # Single string match (like IEEE)
                        if pattern == patterns[1]:  # IEEE pattern
                            citation['reference_number'] = match
                            citation['author'] = None
                            citation['year'] = None
                    
                    # Add citation context (the sentence containing it)
                    sentences = re.split(r'(?<=[.!?])\s+', content)
                    for sentence in sentences:
                        if re.search(pattern, sentence):
                            citation['context'] = sentence.strip()
                            break
                    
                    citations.append(citation)
            
            return citations
            
        except Exception as e:
            logger.error(f"Citation extraction failed: {str(e)}")
            return []
    
    async def find_related_content(
        self,
        url: str,
        max_results: int = 3,
        same_domain_only: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Find content related to a URL.
        
        Args:
            url: Base URL to find related content for
            max_results: Maximum number of results
            same_domain_only: Whether to restrict to same domain
            
        Returns:
            List[Dict[str, Any]]: Related content
        """
        if not self._initialized:
            raise BrowserNotInitializedError("related content")
        
        related_content = []
        
        try:
            # Get base domain
            base_domain = urlparse(url).netloc
            
            # Browse URL to extract links
            content = await self.browse_url(url)
            if not content:
                raise BrowserError(f"Failed to load {url}")
            
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(content, 'html.parser')
            
            # Find all links
            links = []
            for a_tag in soup.find_all('a', href=True):
                href = a_tag.get('href')
                
                # Skip empty, javascript, or anchor links
                if not href or href.startswith('javascript:') or href.startswith('#'):
                    continue
                
                # Convert to absolute URL
                absolute_url = urljoin(url, href)
                
                # Check same domain if required
                if same_domain_only:
                    link_domain = urlparse(absolute_url).netloc
                    if link_domain != base_domain:
                        continue
                
                # Avoid self-links
                if absolute_url == url:
                    continue
                
                # Score link relevance
                link_text = a_tag.text.strip()
                
                # Skip short/empty link text
                if len(link_text) < 3:
                    continue
                
                links.append({
                    'url': absolute_url,
                    'text': link_text,
                    'domain': urlparse(absolute_url).netloc
                })
            
            # Filter for unique URLs
            unique_links = []
            seen_urls = set()
            
            for link in links:
                if link['url'] not in seen_urls:
                    seen_urls.add(link['url'])
                    unique_links.append(link)
            
            # Take top results
            return unique_links[:max_results]
            
        except Exception as e:
            logger.error(f"Related content search failed: {str(e)}")
            self._consecutive_errors += 1
            
            if self.auto_recovery and self._consecutive_errors >= 3:
                await self._attempt_recovery()
                
            return []
            
    async def verify_information(self, claim: str, context: str) -> Dict[str, Any]:
        """
        Verify a claim in context using web search.
        
        Args:
            claim: Claim to verify
            context: Context of the claim
            
        Returns:
            Dict[str, Any]: Verification results
        """
        if not self._initialized:
            raise BrowserNotInitializedError("information verification")
        
        verification = {
            'claim': claim,
            'context': context,
            'verification_status': 'unknown',
            'evidence': [],
            'timestamp': datetime.now().isoformat()
        }
        
        try:
            # Create search query from claim
            search_query = f'"{claim}"'
            
            # Search for claim
            search_results = await self.gather_content(search_query)
            
            if not search_results or not search_results.get('results'):
                verification['verification_status'] = 'insufficient_evidence'
                return verification
            
            # Process top results
            top_results = search_results.get('results', [])[:3]
            
            evidence = []
            supporting_count = 0
            
            for result in top_results:
                try:
                    url = result.get('url')
                    if not url:
                        continue
                    
                    # Apply delay based on current strategy
                    await self._apply_strategy_delay()
                    
                    # Extract content
                    content = await self.browse_url(url)
                    if not content:
                        continue
                    
                    # Parse content
                    from bs4 import BeautifulSoup
                    soup = BeautifulSoup(content, 'html.parser')
                    
                    # Remove script, style elements
                    for element in soup(['script', 'style', 'iframe', 'noscript']):
                        element.decompose()
                    
                    # Get text content
                    text_content = soup.get_text()
                    
                    # Check if claim is present
                    if claim.lower() in text_content.lower():
                        # Find the context around the claim
                        sentences = re.split(r'(?<=[.!?])\s+', text_content)
                        matching_sentences = []
                        
                        for sentence in sentences:
                            if claim.lower() in sentence.lower():
                                matching_sentences.append(sentence.strip())
                        
                        # Determine support level
                        support_level = 'supports' if len(matching_sentences) > 0 else 'no_mention'
                        
                        if support_level == 'supports':
                            supporting_count += 1
                        
                        evidence.append({
                            'url': url,
                            'title': result.get('title', ''),
                            'support_level': support_level,
                            'matching_context': matching_sentences[:3],  # First 3 matches
                            'source_reliability': await self.check_source_reliability(url)
                        })
                        
                except Exception as e:
                    logger.warning(f"Failed to process evidence from {url}: {str(e)}")
                    continue
            
            # Determine verification status
            if not evidence:
                verification['verification_status'] = 'insufficient_evidence'
            elif supporting_count >= 2:
                verification['verification_status'] = 'verified'
            elif supporting_count >= 1:
                verification['verification_status'] = 'partially_verified'
            else:
                verification['verification_status'] = 'unverified'
            
            verification['evidence'] = evidence
            verification['supporting_sources'] = supporting_count
            
            return verification
            
        except Exception as e:
            logger.error(f"Information verification failed: {str(e)}")
            self._consecutive_errors += 1
            
            if self.auto_recovery and self._consecutive_errors >= 3:
                await self._attempt_recovery()
                
            verification['verification_status'] = 'error'
            verification['error'] = str(e)
            return verification
