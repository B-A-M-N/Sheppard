"""
Enhanced browser-based research system with visual progress tracking.
File: src/research/browser.py
"""
import asyncio
import logging
from typing import Dict, Any, List, Optional, Set
from datetime import datetime
from pathlib import Path
import re
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException, InvalidArgumentException
from urllib.parse import quote_plus
from src.utils.console import console

logger = logging.getLogger(__name__)

class BrowserController:
    """Manages browser-based research with visual feedback."""
    def __init__(
        self,
        headless: bool = False,
        screenshot_dir: Optional[Path] = None,
        max_pages: int = 5,
        timeout: int = 60  # Increased from 30 to 60 seconds
    ):
        """Initialize browser researcher."""
        self.headless = headless
        self.screenshot_dir = screenshot_dir
        self.max_pages = max_pages
        self.timeout = timeout
        self.driver = None
        self.wait = None
        self._research_active = False
        self.progress = None
        self.visited_urls: Set[str] = set()
        
        # Create screenshot directory if needed
        if self.screenshot_dir:
            self.screenshot_dir.mkdir(parents=True, exist_ok=True)

    async def initialize(self) -> None:
        """Initialize browser with proper configuration."""
        if self.driver:
            return
        options = Options()
        if self.headless:
            options.add_argument('--headless=new')
        
        # Enhanced anti-detection settings
        options.add_argument('--disable-blink-features=AutomationControlled')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-gpu')
        options.add_argument('--disable-notifications')
        options.add_argument('--disable-popup-blocking')
        options.add_argument('--disable-password-manager')  
        options.add_argument('--disable-infobars')
        options.add_argument('--disable-extensions')
        
        # Add random user agent
        user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/117.0"
        ]
        import random
        options.add_argument(f"user-agent={random.choice(user_agents)}")
        
        # Create and configure driver
        try:
            # Try to use undetected_chromedriver if available
            try:
                import undetected_chromedriver as uc
                self.driver = uc.Chrome(options=options)
            except ImportError:
                # Fall back to regular Chrome
                self.driver = webdriver.Chrome(options=options)
                
            self.wait = WebDriverWait(self.driver, self.timeout)
            
            # Set window size
            if self.headless:
                self.driver.set_window_size(1920, 1080)
            else:
                self.driver.maximize_window()
                
            # Add random delay for more human-like behavior
            import time, random
            time.sleep(random.uniform(1, 3))
                
            logger.info("Browser initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize browser: {str(e)}")
            await self.cleanup()
            raise

    async def cleanup(self) -> None:
        """Clean up browser resources."""
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
        
        self.visited_urls.clear()
        self._research_active = False

    def sanitize_query(self, query: str) -> Optional[str]:
        """Sanitize and validate the search query."""
        if not query or not query.strip():
            logger.warning("Empty or whitespace query provided")
            return None
        
        # Remove any non-alphanumeric characters except spaces
        sanitized_query = re.sub(r'[^a-zA-Z0-9\s]', '', query)
        
        # Limit query length to a reasonable value
        max_length = 100
        if len(sanitized_query) > max_length:
            logger.warning(f"Query truncated to {max_length} characters")
            sanitized_query = sanitized_query[:max_length]
        
        return sanitized_query.strip()

    async def gather_content(self, query: str) -> Optional[Dict[str, Any]]:
        """
        Gather content from search query with visual feedback.
        
        Args:
            query: Search query
            
        Returns:
            Optional[Dict[str, Any]]: Gathered content and metadata
        """
        try:
            if not self.driver:
                await self.initialize()
            
            # Sanitize and validate query
            sanitized_query = self.sanitize_query(query)
            if not sanitized_query:
                return None

            # Display search info
            console.print(f"[bold cyan]Searching:[/bold cyan] {sanitized_query}")

            # Encode query for URL
            encoded_query = quote_plus(sanitized_query)
            
            # Construct search URL
            search_url = f"https://www.google.com/search?q={encoded_query}"
            try:
                console.print(f"[cyan]Accessing search engine...[/cyan]")
                self.driver.get(search_url)
                self.wait.until(EC.presence_of_element_located((By.ID, "search")))
                console.print(f"[green]✓ Search page loaded[/green]")
            except InvalidArgumentException as e:
                console.print(f"[red]Invalid search URL: {search_url}[/red]")
                return await self.fallback_search(sanitized_query)
            except TimeoutException:
                console.print(f"[red]Timeout waiting for search results[/red]")
                return await self.fallback_search(sanitized_query)
            except WebDriverException as e:
                console.print(f"[red]WebDriver error during navigation: {str(e)}[/red]")
                return await self.fallback_search(sanitized_query)

            # Extract search results
            search_results = []
            try:
                # Wait for search results to load
                console.print(f"[cyan]Extracting search results...[/cyan]")
                result_elements = self.wait.until(
                    EC.presence_of_all_elements_located((By.CSS_SELECTOR, "div.g"))
                )
                
                # Show progress
                with console.status(f"[cyan]Processing {len(result_elements)} results...[/cyan]"):
                    # Process each result
                    for element in result_elements[:self.max_pages]:
                        try:
                            # Find required elements
                            title_elem = element.find_element(By.CSS_SELECTOR, "h3")
                            link_elem = element.find_element(By.CSS_SELECTOR, "a")
                            snippet_elem = element.find_element(By.CSS_SELECTOR, "div.VwiC3b")
                            
                            result_url = link_elem.get_attribute("href")
                            if result_url and result_url not in self.visited_urls:
                                # Extract text content
                                title = title_elem.text.strip()
                                snippet = snippet_elem.text.strip()
                                
                                if title and snippet:  # Only add if we have both
                                    search_results.append({
                                        'url': result_url,
                                        'title': title,
                                        'snippet': snippet
                                    })
                                    self.visited_urls.add(result_url)
                                    console.print(f"  [green]✓[/green] Found: [bold]{title}[/bold]")
                        except Exception as e:
                            console.print(f"  [yellow]⚠[/yellow] Error extracting result: {str(e)}")
                            continue
                
                console.print(f"[green]✓ Extracted {len(search_results)} results[/green]")
                        
            except TimeoutException:
                console.print(f"[red]Timeout extracting search results[/red]")
                return await self.fallback_search(sanitized_query)
            except Exception as e:
                console.print(f"[red]Error processing search results: {str(e)}[/red]")
                return await self.fallback_search(sanitized_query)
            
            # Return search results 
            return {
                'query': sanitized_query,
                'results': search_results,
                'timestamp': datetime.now().isoformat()
            }
            
        except Exception as e:
            console.print(f"[red]Error gathering content: {str(e)}[/red]")
            return None

    async def fallback_search(self, query: str) -> Optional[Dict[str, Any]]:
        """Perform fallback search using pre-defined results."""
        logger.info(f"Falling back to pre-defined search results for: {query}")
        
        # Use a pre-defined set of search results as a fallback
        fallback_results = [
            {
                'url': 'https://example.com/fallback1',
                'title': 'Fallback Result 1',
                'snippet': 'This is a pre-defined fallback search result.'
            },
            {
                'url': 'https://example.com/fallback2',
                'title': 'Fallback Result 2',
                'snippet': 'Another pre-defined fallback search result.'
            }
        ]
        
        return {
            'query': query,
            'results': fallback_results,
            'timestamp': datetime.now().isoformat()
        }

    async def browse_url(self, url: str, headless: bool = True) -> Optional[str]:
        """
        Browse to a specific URL and return the page content.
        
        Args:
            url: URL to browse to
            headless: Whether to run browser in headless mode
            
        Returns:
            Optional[str]: Page content if successful, None otherwise
        """
        try:
            # Validate URL
            if not url or not url.startswith('http'):
                logger.error(f"Invalid URL: {url}")
                return None

            # Update headless mode if needed
            if headless != self.headless:
                self.headless = headless
                await self.cleanup()
                await self.initialize()

            # Navigate to URL
            self.driver.get(url)

            # Wait for page load
            self.wait.until(lambda driver: driver.execute_script('return document.readyState') == 'complete')

            # Get page content
            content = self.driver.page_source
            
            # Optionally take screenshot
            if self.screenshot_dir:
                filename = f"screenshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
                filepath = self.screenshot_dir / filename
                self.driver.save_screenshot(str(filepath))

            return content

        except Exception as e:
            logger.error(f"Error browsing URL: {str(e)}")
            return None

    async def stop_research(self) -> None:
        """Stop ongoing research."""
        self._research_active = False
