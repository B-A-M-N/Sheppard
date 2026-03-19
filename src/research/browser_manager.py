"""
Enhanced browser manager with robust error handling and automatic driver management.
File: src/research/browser_manager.py
"""

import logging
import asyncio
from typing import Dict, Any, Optional, List, Set, Tuple
from datetime import datetime
from pathlib import Path
import re
from urllib.parse import urlparse, quote_plus, parse_qs, urlencode, urlunparse
import json
import sys
import os
import subprocess
import shutil

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException,
    WebDriverException,
    InvalidArgumentException,
    SessionNotCreatedException
)

from src.research.exceptions import (
    BrowserError,
    BrowserNotInitializedError,
    BrowserTimeout
)
from src.research.models import BrowserConfig

logger = logging.getLogger(__name__)

class URLFilter:
    """Filters and cleans URLs to remove tracking parameters and standardize formats."""
    
    def __init__(self):
        """Initialize URL filter."""
        # Patterns for URLs to exclude
        self.excluded_patterns = [
            r'(?:advertisement|banner|ad)\.',  # Ad-related
            r'(?:track|analytic)\.',           # Tracking
            r'(?:pop(?:up|over))\.',           # Popups
            r'\.(exe|zip|rar|7z|tar|gz)'       # Downloads
        ]
        
        # Tracking parameters to remove
        self.tracking_params = [
            'utm_source', 'utm_medium', 'utm_campaign', 'utm_term', 'utm_content',
            'fbclid', 'gclid', 'msclkid', 'ref', 'source', 'mc_cid', 'mc_eid',
            'yclid', 'dclid'
        ]
    
    def clean_url(self, url: str) -> Optional[str]:
        """
        Extracts the actual destination URL from tracking or redirect URLs.
        
        Args:
            url: URL to clean
            
        Returns:
            Optional[str]: Cleaned URL or None if URL should be excluded
        """
        if not url:
            return None

        try:
            # Parse URL
            parsed = urlparse(url)
            
            # Extract real URL from Google tracking links
            if parsed.netloc.endswith("google.com") and "/url" in parsed.path:
                query_params = parse_qs(parsed.query)
                if 'q' in query_params:
                    return query_params['q'][0]  # Extract actual URL from the "q" parameter
            
            # Ignore unwanted search tracking domains
            if any(bad in parsed.netloc for bad in ["goo.gl", "search.app.goo.gl"]):
                return None
            
            # Remove tracking parameters from query
            if parsed.query:
                query_dict = parse_qs(parsed.query)
                # Remove known tracking parameters
                for param in self.tracking_params:
                    query_dict.pop(param, None)
                
                # Rebuild query string
                new_query = urlencode(query_dict, doseq=True) if query_dict else ''
                
                # Rebuild URL without tracking parameters
                url = urlunparse((
                    parsed.scheme,
                    parsed.netloc,
                    parsed.path,
                    parsed.params,
                    new_query,
                    parsed.fragment
                ))
            
            return url
            
        except Exception:
            # If any error occurs, return the original URL
            return url


class BrowserManager:
    """Enhanced browser manager with robust fallback mechanisms."""
    
    def __init__(
        self,
        headless: bool = True,
        timeout: int = 60,
        max_pages: int = 5,
        screenshot_dir: Optional[Path] = None,
        download_dir: Optional[Path] = None,
        retry_attempts: int = 3,
        retry_delay: float = 1.0,
        window_size: Tuple[int, int] = (1920, 1080),
        config: Optional[BrowserConfig] = None,
        options: Dict[str, Any] = None,
        request_headers: Dict[str, str] = None
    ):
        """Initialize browser manager with fallback options."""
        # Use config if provided, otherwise use default parameters
        if config:
            self.headless = config.headless
            self.window_size = config.window_size
            self.timeout = config.timeout
            self.retry_attempts = config.retry_attempts
            self.retry_delay = config.retry_delay
            self.screenshot_dir = config.screenshot_dir
            self.download_dir = config.download_dir
        else:
            self.headless = headless
            self.window_size = window_size
            self.timeout = timeout
            self.retry_attempts = retry_attempts
            self.retry_delay = retry_delay
            self.screenshot_dir = screenshot_dir
            self.download_dir = download_dir

        # Max pages is not part of BrowserConfig
        self.max_pages = max_pages
        
        # Initialize browser components
        self.driver = None
        self.wait = None
        self._research_active = False
        self._initialized = False
        self._session = None
        
        # Initialize tracking sets
        self.visited_urls: Set[str] = set()
        self._active_tasks: Dict[str, Dict[str, Any]] = {}
        
        # Initialize metrics
        self._metrics = {
            'pages_processed': 0,
            'successful_extractions': 0,
            'failed_extractions': 0,
            'total_bytes_processed': 0
        }
        
        # Initialize error tracking
        self._error_count = 0
        self._last_error = None
        self._last_error_time = None

        # Add URL filter
        self._url_filter = URLFilter()

        # Create directories if needed
        if self.screenshot_dir:
            self.screenshot_dir.mkdir(parents=True, exist_ok=True)
        if self.download_dir:
            self.download_dir.mkdir(parents=True, exist_ok=True)
            
        # Chrome/driver compatibility tracking
        self._driver_attempts = []
        self._initialization_attempts = 0
        self._fallback_mode = False
    
    async def initialize(self) -> None:
        """Initialize browser with multiple fallback strategies and auto-driver matching."""
        if self._initialized:
            return
        
        self._initialization_attempts += 1
        logger.info(f"Initializing browser (attempt {self._initialization_attempts})")
        
        try:
            # Set up Chrome options
            options = Options()
            
            # Add anti-detection measures
            options.add_argument("--disable-blink-features=AutomationControlled")
            options.add_argument("--disable-dev-shm-usage")
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-gpu")
            
            # Use a random user-agent for better evasion
            try:
                from fake_useragent import UserAgent
                ua = UserAgent()
                user_agent = ua.random
                options.add_argument(f"--user-agent={user_agent}")
            except Exception:
                user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
                options.add_argument(f"--user-agent={user_agent}")
            
            # Set headless mode
            if self.headless:
                options.add_argument("--headless=new")
            
            # Try initialization methods in sequence until one works
            methods = [
                self._initialize_with_playwright,
                self._initialize_with_undetected_chromedriver,
                self._initialize_with_webdriver_manager,
                self._initialize_with_fallback_methods
            ]
            
            exception = None
            for method in methods:
                try:
                    await method(options)
                    # If we reach here, initialization was successful
                    self._initialized = True
                    logger.info(f"Browser manager initialized successfully using {method.__name__}")
                    return
                except Exception as e:
                    logger.warning(f"Method {method.__name__} failed: {str(e)}")
                    exception = e
                    # Continue to next method
            
            # If we're here, all methods failed
            raise BrowserError(f"All initialization methods failed: {str(exception)}")

        except Exception as e:
            logger.error(f"Failed to initialize browser manager: {str(e)}")
            await self.cleanup()
            raise BrowserError(f"Browser initialization failed: {str(e)}")
    
    async def _initialize_with_playwright(self, options: Any) -> None:
        """Initialize browser with Playwright as the primary driver."""
        try:
            from playwright.async_api import async_playwright
            
            # We don't initialize a persistent browser instance here to avoid keeping it open unnecessarily.
            # Instead, we set fallback mode to true so all operations use playwright internally.
            self._fallback_mode = True
            self.driver = None # No persistent Selenium driver
            self._driver_attempts.append({"method": "playwright", "success": True})
            logger.info("Playwright initialized as primary browser manager")
            
        except ImportError:
            self._driver_attempts.append({"method": "playwright", "success": False, "error": "Playwright not installed"})
            raise ImportError("Playwright is not installed. Please install it with 'pip install playwright'")

    async def _initialize_with_undetected_chromedriver(self, options: Options) -> None:
        """Initialize browser with undetected_chromedriver."""
        try:
            import undetected_chromedriver as uc
            self.driver = uc.Chrome(options=options)
            self.wait = WebDriverWait(self.driver, self.timeout)
            
            # Set window size
            if self.headless:
                self.driver.set_window_size(*self.window_size)
            else:
                self.driver.maximize_window()
                
            self._driver_attempts.append({"method": "undetected_chromedriver", "success": True})
        except Exception as e:
            self._driver_attempts.append({"method": "undetected_chromedriver", "success": False, "error": str(e)})
            raise
    
    async def _initialize_with_webdriver_manager(self, options: Options) -> None:
        """Initialize browser with webdriver_manager."""
        try:
            from webdriver_manager.chrome import ChromeDriverManager
            
            # Get browser version
            browser_version = self._get_chrome_version()
            
            # Request compatible driver
            driver_path = ChromeDriverManager(chrome_version=browser_version).install()
            service = Service(executable_path=driver_path)
            
            self.driver = webdriver.Chrome(service=service, options=options)
            self.wait = WebDriverWait(self.driver, self.timeout)
            
            # Set window size
            if self.headless:
                self.driver.set_window_size(*self.window_size)
            else:
                self.driver.maximize_window()
                
            self._driver_attempts.append({"method": "webdriver_manager", "success": True})
        except Exception as e:
            self._driver_attempts.append({"method": "webdriver_manager", "success": False, "error": str(e)})
            raise
    
    async def _initialize_with_fallback_methods(self, options: Options) -> None:
        """Initialize browser with various fallback methods."""
        # Try multiple approaches for browser initialization
        exceptions = []
        
        # Approach 1: Try system ChromeDriver
        try:
            path = await self._find_system_chromedriver()
            if path:
                service = Service(executable_path=path)
                self.driver = webdriver.Chrome(service=service, options=options)
                self.wait = WebDriverWait(self.driver, self.timeout)
                self._driver_attempts.append({"method": "system_chromedriver", "success": True})
                return
        except Exception as e:
            exceptions.append(f"System ChromeDriver failed: {str(e)}")
            self._driver_attempts.append({"method": "system_chromedriver", "success": False, "error": str(e)})
        
        # Approach 2: Try with playwright if available
        try:
            # Only attempt importing if not already failed in this session
            if not any(d["method"] == "playwright" for d in self._driver_attempts):
                from playwright.async_api import async_playwright
                self._fallback_mode = True
                
                # We'll initialize playwright in the gather_content method as needed
                logger.info("Using Playwright as a fallback for browser automation")
                self._driver_attempts.append({"method": "playwright", "success": True})
                return
        except ImportError as e:
            exceptions.append(f"Playwright not available: {str(e)}")
            self._driver_attempts.append({"method": "playwright", "success": False, "error": str(e)})
        
        # Approach 3: Setup minimal browser for basic text extraction
        try:
            # We'll use requests for basic content fetching
            import requests
            from bs4 import BeautifulSoup
            
            # Setup minimal browser replacement that will be called in gather_content
            self._fallback_mode = True
            logger.info("Using requests/BeautifulSoup as a minimal fallback")
            self._driver_attempts.append({"method": "requests_fallback", "success": True})
            return
        except ImportError as e:
            exceptions.append(f"Requests/BeautifulSoup fallback failed: {str(e)}")
            self._driver_attempts.append({"method": "requests_fallback", "success": False, "error": str(e)})
        
        # If we get here, all approaches failed
        raise BrowserError(f"All fallback initialization methods failed: {', '.join(exceptions)}")
    
    def _get_chrome_version(self) -> Optional[str]:
        """Get installed Chrome version."""
        try:
            # Different commands for different platforms
            if sys.platform.startswith('linux'):
                # Try multiple commands for Linux
                commands = [
                    ['google-chrome', '--version'],
                    ['google-chrome-stable', '--version'],
                    ['chromium-browser', '--version'],
                    ['chromium', '--version']
                ]
                
                for cmd in commands:
                    try:
                        version = subprocess.check_output(cmd, stderr=subprocess.STDOUT).decode('utf-8')
                        match = re.search(r'[\d\.]+', version)
                        if match:
                            return match.group(0)
                    except (subprocess.SubprocessError, FileNotFoundError):
                        continue
                
            elif sys.platform == 'darwin':  # macOS
                try:
                    cmd = ['/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', '--version']
                    version = subprocess.check_output(cmd).decode('utf-8')
                    match = re.search(r'[\d\.]+', version)
                    if match:
                        return match.group(0)
                except:
                    pass
                    
            elif sys.platform == 'win32':  # Windows
                try:
                    import winreg
                    key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Software\Google\Chrome\BLBeacon')
                    version, _ = winreg.QueryValueEx(key, 'version')
                    return version
                except:
                    pass
                    
            logger.warning("Could not determine Chrome version")
            return None
            
        except Exception as e:
            logger.warning(f"Error detecting Chrome version: {str(e)}")
            return None
    
    async def _find_system_chromedriver(self) -> Optional[str]:
        """Find ChromeDriver in system path."""
        try:
            if sys.platform.startswith('win'):
                cmd = ['where', 'chromedriver']
            else:
                cmd = ['which', 'chromedriver']
                
            output = subprocess.check_output(cmd, text=True).strip()
            if output:
                logger.info(f"Found system ChromeDriver at: {output}")
                return output
        except subprocess.SubprocessError:
            logger.info("ChromeDriver not found in system path")
            
        return None

    async def gather_content(
        self,
        query: str,
        search_engine: str = "google",
        progress_callback: Optional[callable] = None
    ) -> Dict[str, Any]:
        """Gather content with SearXNG as primary and other engines as fallback."""
        if not self._initialized:
            await self.initialize()

        # Try SearXNG first if configured
        searxng_url = os.getenv('SEARXNG_ENDPOINT')
        if searxng_url:
            try:
                logger.info(f"Searching on SearXNG: {query}")
                import requests
                # Format: query, format=json
                response = requests.get(
                    f"{searxng_url}/search",
                    params={'q': query, 'format': 'json'},
                    timeout=self.timeout
                )
                response.raise_for_status()
                data = response.json()
                
                results = []
                for res in data.get('results', [])[:self.max_pages]:
                    results.append({
                        'url': res.get('url'),
                        'title': res.get('title'),
                        'snippet': res.get('content', '')
                    })
                
                if results:
                    logger.info(f"Found {len(results)} results from SearXNG")
                    return {
                        'query': query,
                        'search_engine': 'searxng',
                        'results': results,
                        'timestamp': datetime.now().isoformat()
                    }
            except Exception as e:
                logger.warning(f"SearXNG search failed, falling back: {str(e)}")

        # If we're in fallback mode (no Selenium driver),
        # use alternative content gathering methods
        if self._fallback_mode:
            return await self._fallback_gather_content(query, search_engine, progress_callback)
        
        try:
            if progress_callback:
                progress_callback(0.1)
            
            # Sanitize query
            sanitized_query = self._sanitize_query(query)
            if not sanitized_query:
                raise ValueError("Invalid search query")
            
            # Build search URL based on engine
            search_url = {
                "google": f"https://www.google.com/search?q={quote_plus(sanitized_query)}",
                "bing": f"https://www.bing.com/search?q={quote_plus(sanitized_query)}",
                "msn": f"https://www.msn.com/en-us/search?q={quote_plus(sanitized_query)}"
            }.get(search_engine.lower(), f"https://www.google.com/search?q={quote_plus(sanitized_query)}")
            
            # Navigate to search
            try:
                logger.info(f"Searching on {search_engine.capitalize()}: {sanitized_query}")
                self.driver.get(search_url)
                
                # Add random delay to mimic human behavior
                import random, time
                time.sleep(random.uniform(2, 4))
                
                # Extract search results based on engine
                if search_engine.lower() == "google":
                    css_selector = "div.g"
                    title_selector = "h3"
                    url_selector = "a"
                    snippet_selector = "div.VwiC3b"
                elif search_engine.lower() == "bing":
                    css_selector = "li.b_algo"
                    title_selector = "h2"
                    url_selector = "a"
                    snippet_selector = "p"
                elif search_engine.lower() == "msn":
                    css_selector = "div.algocore"
                    title_selector = "h2"
                    url_selector = "a"
                    snippet_selector = "p.b_paractl"
                else:
                    css_selector = "div.g"
                    title_selector = "h3"
                    url_selector = "a"
                    snippet_selector = "div.VwiC3b"
                
                # Wait for search results
                search_results = self.wait.until(
                    EC.presence_of_all_elements_located((By.CSS_SELECTOR, css_selector))
                )
                
                if progress_callback:
                    progress_callback(0.5)
                
                # Extract results
                results = []
                for result in search_results[:self.max_pages]:
                    try:
                        # Find required elements
                        title_elem = result.find_element(By.CSS_SELECTOR, title_selector)
                        link_elem = result.find_element(By.CSS_SELECTOR, url_selector)
                        
                        try:
                            snippet_elem = result.find_element(By.CSS_SELECTOR, snippet_selector)
                            snippet = snippet_elem.text.strip()
                        except:
                            snippet = ""
                        
                        # Get URL and clean it
                        raw_url = link_elem.get_attribute("href")
                        cleaned_url = self._url_filter.clean_url(raw_url)
                        
                        if cleaned_url and cleaned_url not in self.visited_urls:
                            results.append({
                                'url': cleaned_url,
                                'title': title_elem.text.strip(),
                                'snippet': snippet
                            })
                            self.visited_urls.add(cleaned_url)
                            
                    except Exception as e:
                        logger.debug(f"Error extracting search result: {str(e)}")
                        continue
                
                if progress_callback:
                    progress_callback(1.0)
                
                return {
                    'query': query,
                    'search_engine': search_engine,
                    'results': results,
                    'timestamp': datetime.now().isoformat()
                }
                
            except TimeoutException:
                raise BrowserTimeout("search results", timeout=self.timeout)
            except WebDriverException as e:
                raise BrowserError(f"Browser automation failed: {str(e)}")
            
        except Exception as e:
            logger.error(f"Content gathering failed: {str(e)}")
            # If standard method fails, try fallback
            try:
                return await self._fallback_gather_content(query, search_engine, progress_callback)
            except Exception as fallback_error:
                logger.error(f"Fallback method also failed: {str(fallback_error)}")
                raise BrowserError(f"Content gathering failed: {str(e)}")
    
    async def _fallback_gather_content(
        self,
        query: str,
        search_engine: str = "google",
        progress_callback: Optional[callable] = None
    ) -> Dict[str, Any]:
        """Gather content using fallback methods when Selenium is unavailable."""
        try:
            if progress_callback:
                progress_callback(0.1)
            
            # Try to use playwright if available
            try:
                # Check if playwright is available
                from playwright.async_api import async_playwright
                return await self._playwright_gather_content(query, search_engine, progress_callback)
            except ImportError:
                # Playwright not available, try requests
                pass
                
            # Sanitize query
            sanitized_query = self._sanitize_query(query)
            if not sanitized_query:
                raise ValueError("Invalid search query")
                
            # Build search URL
            search_url = {
                "google": f"https://www.google.com/search?q={quote_plus(sanitized_query)}",
                "bing": f"https://www.bing.com/search?q={quote_plus(sanitized_query)}",
                "msn": f"https://www.msn.com/en-us/search?q={quote_plus(sanitized_query)}"
            }.get(search_engine.lower(), f"https://www.google.com/search?q={quote_plus(sanitized_query)}")
            
            # Use requests to fetch content
            import requests
            from bs4 import BeautifulSoup
            
            # Use a more browser-like User-Agent
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/110.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
            }
            
            if progress_callback:
                progress_callback(0.3)
                
            response = requests.get(search_url, headers=headers, timeout=self.timeout)
            soup = BeautifulSoup(response.text, 'html.parser')
            
            if progress_callback:
                progress_callback(0.5)
            
            # Extract results based on engine
            results = []
            
            if search_engine.lower() == "google":
                # For Google
                search_results = soup.select('div.g')
                for result in search_results[:self.max_pages]:
                    try:
                        title_elem = result.select_one('h3')
                        if not title_elem:
                            continue
                            
                        link_elem = result.select_one('a')
                        if not link_elem or not link_elem.get('href'):
                            continue
                            
                        snippet_elem = result.select_one('div.VwiC3b') or result.select_one('.aCOpRe')
                        snippet = snippet_elem.get_text(strip=True) if snippet_elem else ""
                        
                        url = link_elem['href']
                        if url.startswith('/url?q='):
                            url = url.split('/url?q=')[1].split('&')[0]
                            
                        if url and url not in self.visited_urls:
                            results.append({
                                'url': url,
                                'title': title_elem.get_text(strip=True),
                                'snippet': snippet
                            })
                            self.visited_urls.add(url)
                    except Exception as e:
                        logger.debug(f"Error extracting Google result: {str(e)}")
                        continue
            
            elif search_engine.lower() == "bing":
                # For Bing
                search_results = soup.select('li.b_algo')
                for result in search_results[:self.max_pages]:
                    try:
                        title_elem = result.select_one('h2')
                        if not title_elem:
                            continue
                            
                        link_elem = result.select_one('a')
                        if not link_elem or not link_elem.get('href'):
                            continue
                            
                        snippet_elem = result.select_one('p')
                        snippet = snippet_elem.get_text(strip=True) if snippet_elem else ""
                        
                        url = link_elem['href']
                        if url and url not in self.visited_urls:
                            results.append({
                                'url': url,
                                'title': title_elem.get_text(strip=True),
                                'snippet': snippet
                            })
                            self.visited_urls.add(url)
                    except Exception as e:
                        logger.debug(f"Error extracting Bing result: {str(e)}")
                        continue
            
            else:
                # Generic extraction as fallback
                for link_elem in soup.select('a[href^="http"]')[:self.max_pages]:
                    try:
                        url = link_elem['href']
                        if (url and 
                            url not in self.visited_urls and 
                            not url.startswith('javascript:') and
                            not url.endswith('.jpg') and
                            not url.endswith('.png') and
                            not url.endswith('.css') and
                            not url.endswith('.js')):
                            
                            title = link_elem.get_text(strip=True)
                            if not title:
                                title = url
                                
                            results.append({
                                'url': url,
                                'title': title[:100],  # Limit title length
                                'snippet': ""
                            })
                            self.visited_urls.add(url)
                    except Exception:
                        continue
            
            if progress_callback:
                progress_callback(1.0)
                
            return {
                'query': query,
                'search_engine': search_engine,
                'results': results,
                'timestamp': datetime.now().isoformat(),
                'fallback_method': 'requests'
            }
            
        except Exception as e:
            logger.error(f"Fallback content gathering failed: {str(e)}")
            # Return minimal results as last resort
            return {
                'query': query,
                'search_engine': search_engine,
                'results': [
                    {
                        'url': 'https://en.wikipedia.org/wiki/' + query.replace(' ', '_'),
                        'title': f'{query} - Wikipedia',
                        'snippet': f"Information about {query} from Wikipedia, the free encyclopedia."
                    }
                ],
                'timestamp': datetime.now().isoformat(),
                'fallback_method': 'minimal'
            }
    
    async def _playwright_gather_content(
        self,
        query: str,
        search_engine: str = "google",
        progress_callback: Optional[callable] = None
    ) -> Dict[str, Any]:
        """Gather content using playwright as a fallback."""
        from playwright.async_api import async_playwright
        
        if progress_callback:
            progress_callback(0.1)
            
        # Sanitize query
        sanitized_query = self._sanitize_query(query)
        if not sanitized_query:
            raise ValueError("Invalid search query")
            
        # Build search URL
        search_url = {
            "google": f"https://www.google.com/search?q={quote_plus(sanitized_query)}",
            "bing": f"https://www.bing.com/search?q={quote_plus(sanitized_query)}",
            "msn": f"https://www.msn.com/en-us/search?q={quote_plus(sanitized_query)}"
        }.get(search_engine.lower(), f"https://www.google.com/search?q={quote_plus(sanitized_query)}")
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            
            # Navigate to search page
            await page.goto(search_url, wait_until="domcontentloaded")
            
            if progress_callback:
                progress_callback(0.3)
                
            # Wait for results to load
            if search_engine.lower() == "google":
                await page.wait_for_selector('div.g', timeout=30000)
            elif search_engine.lower() == "bing":
                await page.wait_for_selector('li.b_algo', timeout=30000)
            else:
                # Generic wait
                await page.wait_for_timeout(5000)
                
            if progress_callback:
                progress_callback(0.5)
                
            # Extract results based on engine
            results = []
            
            if search_engine.lower() == "google":
                # For Google
                search_results = await page.query_selector_all('div.g')
                for result in search_results[:self.max_pages]:
                    try:
                        title_elem = await result.query_selector('h3')
                        if not title_elem:
                            continue
                            
                        link_elem = await result.query_selector('a')
                        if not link_elem:
                            continue
                            
                        snippet_elem = await result.query_selector('div.VwiC3b')
                        
                        title = await title_elem.inner_text()
                        url = await link_elem.get_attribute('href')
                        snippet = await snippet_elem.inner_text() if snippet_elem else ""
                        
                        if url and url not in self.visited_urls:
                            results.append({
                                'url': url,
                                'title': title,
                                'snippet': snippet
                            })
                            self.visited_urls.add(url)
                    except Exception as e:
                        logger.debug(f"Error extracting Google result: {str(e)}")
                        continue
            
            elif search_engine.lower() == "bing":
                # For Bing
                search_results = await page.query_selector_all('li.b_algo')
                for result in search_results[:self.max_pages]:
                    try:
                        title_elem = await result.query_selector('h2')
                        if not title_elem:
                            continue
                            
                        link_elem = await result.query_selector('a')
                        if not link_elem:
                            continue
                            
                        snippet_elem = await result.query_selector('p')
                        
                        title = await title_elem.inner_text()
                        url = await link_elem.get_attribute('href')
                        snippet = await snippet_elem.inner_text() if snippet_elem else ""
                        
                        if url and url not in self.visited_urls:
                            results.append({
                                'url': url,
                                'title': title,
                                'snippet': snippet
                            })
                            self.visited_urls.add(url)
                    except Exception as e:
                        logger.debug(f"Error extracting Bing result: {str(e)}")
                        continue
            
            else:
                # Generic extraction as fallback
                link_elems = await page.query_selector_all('a[href^="http"]')
                for link_elem in link_elems[:self.max_pages]:
                    try:
                        url = await link_elem.get_attribute('href')
                        if (url and 
                            url not in self.visited_urls and 
                            not url.startswith('javascript:') and
                            not url.endswith('.jpg') and
                            not url.endswith('.png') and
                            not url.endswith('.css') and
                            not url.endswith('.js')):
                            
                            title = await link_elem.inner_text()
                            if not title:
                                title = url
                                
                            results.append({
                                'url': url,
                                'title': title[:100],  # Limit title length
                                'snippet': ""
                            })
                            self.visited_urls.add(url)
                    except Exception:
                        continue
            
            await browser.close()
            
            if progress_callback:
                progress_callback(1.0)
                
            return {
                'query': query,
                'search_engine': search_engine,
                'results': results,
                'timestamp': datetime.now().isoformat(),
                'fallback_method': 'playwright'
            }

    def _sanitize_query(self, query: str) -> Optional[str]:
        """Sanitize search query."""
        if not query or not query.strip():
            return None
            
        # Remove potentially harmful characters
        sanitized = re.sub(r'[^a-zA-Z0-9\s\-_\.,]', '', query)
        
        # Limit query length
        max_length = 100
        if len(sanitized) > max_length:
            sanitized = sanitized[:max_length]
        
        return sanitized.strip()
    
    async def take_screenshot(
        self,
        url: str,
        filepath: str
    ) -> bool:
        """
        Take screenshot of webpage with fallback methods.
        
        Args:
            url: URL to capture
            filepath: Path to save screenshot
            
        Returns:
            bool: True if successful
        """
        if not self._initialized:
            await self.initialize()
        
        try:
            # Clean URL before processing
            url = self._url_filter.clean_url(url)
            
            if not self._fallback_mode:
                # Use selenium if available
                self.driver.get(url)
                
                # Wait for page load
                self.wait.until(
                    lambda d: d.execute_script('return document.readyState') == 'complete'
                )
                
                # Take screenshot
                self.driver.save_screenshot(filepath)
                logger.info(f"Screenshot saved to {filepath}")
                return True
            else:
                # Try playwright if available
                try:
                    from playwright.async_api import async_playwright
                    async with async_playwright() as p:
                        browser = await p.chromium.launch(headless=True)
                        page = await browser.new_page()
                        
                        # Navigate to URL
                        await page.goto(url, wait_until="domcontentloaded")
                        
                        # Take screenshot
                        await page.screenshot(path=filepath)
                        await browser.close()
                        
                        logger.info(f"Screenshot saved to {filepath} with playwright")
                        return True
                except ImportError:
                    logger.warning("Playwright not available for screenshots")
                    return False
                
        except Exception as e:
            logger.error(f"Screenshot failed: {str(e)}")
            return False
    
    async def browse_url(
        self,
        url: str,
        headless: bool = True,
        progress_callback: Optional[callable] = None
    ) -> Optional[str]:
        """
        Browse to a specific URL and extract content with fallback mechanisms.
        
        Args:
            url: URL to browse
            headless: Whether to use headless mode
            progress_callback: Optional progress callback
            
        Returns:
            Optional[str]: Extracted content if successful
        """
        if not self._initialized:
            await self.initialize()
        
        # If we're in fallback mode, use alternative content methods
        if self._fallback_mode:
            return await self._fallback_browse_url(url, progress_callback)
        
        try:
            if progress_callback:
                progress_callback(0.1)
            
            # Validate and clean URL
            url = self._url_filter.clean_url(url)
            if not url or not url.startswith('http'):
                raise ValueError(f"Invalid URL: {url}")
            
            # Update headless mode if needed
            if headless != self.headless:
                self.headless = headless
                await self.cleanup()
                await self.initialize()
            
            if progress_callback:
                progress_callback(0.3)
            
            # Navigate to URL
            self.driver.get(url)
            
            # Wait for page load
            self.wait.until(
                lambda d: d.execute_script('return document.readyState') == 'complete'
            )
            
            if progress_callback:
                progress_callback(0.7)
            
            # Get page content
            content = self.driver.page_source
            
            # Take screenshot if enabled
            if self.screenshot_dir:
                filename = f"screenshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
                filepath = self.screenshot_dir / filename
                self.driver.save_screenshot(str(filepath))
            
            if progress_callback:
                progress_callback(1.0)
            
            return content
            
        except TimeoutException:
            logger.warning(f"Timeout loading URL: {url}, trying fallback method")
            return await self._fallback_browse_url(url, progress_callback)
        except WebDriverException as e:
            logger.warning(f"Browser error: {str(e)}, trying fallback method")
            return await self._fallback_browse_url(url, progress_callback)
        except Exception as e:
            logger.error(f"URL browsing failed: {str(e)}")
            # Try fallback as last resort
            return await self._fallback_browse_url(url, progress_callback)
    
    async def _fallback_browse_url(
        self,
        url: str,
        progress_callback: Optional[callable] = None
    ) -> Optional[str]:
        """Browse URL using fallback methods when Selenium is unavailable."""
        try:
            if progress_callback:
                progress_callback(0.1)
                
            # Validate and clean URL
            url = self._url_filter.clean_url(url)
            if not url or not url.startswith('http'):
                raise ValueError(f"Invalid URL: {url}")
                
            # Try to use playwright if available
            try:
                # Check if playwright is available
                from playwright.async_api import async_playwright
                return await self._playwright_browse_url(url, progress_callback)
            except ImportError:
                # Playwright not available, try requests
                pass
                
            if progress_callback:
                progress_callback(0.3)
                
            # Use requests to fetch content
            import requests
            from bs4 import BeautifulSoup
            
            # Use a more browser-like User-Agent
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/110.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
            }
            
            response = requests.get(url, headers=headers, timeout=self.timeout)
            
            if progress_callback:
                progress_callback(0.7)
                
            # Convert HTML to usable content
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Clean up content by removing scripts, styles, etc.
            for tag in soup(['script', 'style', 'meta', 'noscript']):
                tag.decompose()
                
            if progress_callback:
                progress_callback(1.0)
                
            return soup.prettify()
            
        except Exception as e:
            logger.error(f"Fallback URL browsing failed: {str(e)}")
            return None
            
    async def _playwright_browse_url(
        self,
        url: str,
        progress_callback: Optional[callable] = None
    ) -> Optional[str]:
        """Browse URL using playwright as a fallback."""
        from playwright.async_api import async_playwright
        
        try:
            if progress_callback:
                progress_callback(0.2)
                
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page()
                
                # Navigate to URL
                await page.goto(url, wait_until="domcontentloaded", timeout=self.timeout * 1000)
                
                if progress_callback:
                    progress_callback(0.6)
                    
                # Get page content
                content = await page.content()
                
                # Take screenshot if enabled
                if self.screenshot_dir:
                    filename = f"screenshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
                    filepath = self.screenshot_dir / filename
                    await page.screenshot(path=str(filepath))
                
                await browser.close()
                
                if progress_callback:
                    progress_callback(1.0)
                    
                return content
                
        except Exception as e:
            logger.error(f"Playwright fallback failed: {str(e)}")
            return None
    
    def get_driver_status(self) -> Dict[str, Any]:
        """Get detailed status of browser driver."""
        return {
            'initialized': self._initialized,
            'fallback_mode': self._fallback_mode,
            'driver_attempts': self._driver_attempts,
            'initialization_attempts': self._initialization_attempts,
            'chrome_version': self._get_chrome_version(),
            'timestamp': datetime.now().isoformat()
        }
            
    async def cleanup(self) -> None:
        """Clean up browser resources."""
        try:
            if self.driver:
                try:
                    # Close all windows
                    for handle in self.driver.window_handles[1:]:
                        self.driver.switch_to.window(handle)
                        self.driver.close()
                    
                    # Quit browser
                    self.driver.quit()
                    logger.info("Browser cleanup completed")
                    
                except Exception as e:
                    logger.warning(f"Error during browser cleanup: {str(e)}")
                finally:
                    self.driver = None
                    self.wait = None
            
            # Clear state
            self._initialized = False
            self._research_active = False
            self.visited_urls.clear()
            
        except Exception as e:
            logger.error(f"Error during cleanup: {str(e)}")
    
    def __str__(self) -> str:
        """Get string representation."""
        status = "initialized" if self._initialized else "not initialized"
        mode = "headless" if self.headless else "visible"
        urls = len(self.visited_urls)
        tasks = len(self._active_tasks)
        fallback = "fallback" if self._fallback_mode else "standard"
        return f"BrowserManager({status}, {mode}, {fallback}, urls={urls}, tasks={tasks})"
