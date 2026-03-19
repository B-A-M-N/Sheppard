"""
Enhanced research pipeline with proper task management and staged processing.
File: src/research/pipeline.py
"""

import logging
import asyncio
from typing import Dict, Any, List, Optional, AsyncGenerator
from datetime import datetime
from urllib.parse import urlparse, quote_plus
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException

from src.research.models import (
    ResearchTask,
    TaskStatus,
    SourceType,
    SourceReliability,
    ResearchFinding
)
from src.research.exceptions import ProcessingError, BrowserError
from src.memory.models import Memory
from src.research.browser_manager import BrowserManager
from firecrawl import AsyncV1FirecrawlApp

logger = logging.getLogger(__name__)

class ResearchPipeline:
    """Manages multi-stage research pipeline with proper error handling."""
    
    def __init__(
        self,
        browser_manager: BrowserManager,
        memory_manager: Any,
        firecrawl_config: Optional[Dict[str, Any]] = None
    ):
        """Initialize research pipeline."""
        self.browser = browser_manager
        self.memory_manager = memory_manager
        
        # Initialize Firecrawl if config provided
        if firecrawl_config and firecrawl_config.get('api_key'):
            self.firecrawl = AsyncV1FirecrawlApp(
                api_key=firecrawl_config['api_key'],
                api_url=firecrawl_config.get('base_url')
            )
        else:
            self.firecrawl = None
            
        # Configure source reliability settings
        self.source_reliability = {
            '.edu': SourceReliability.HIGH,    # Educational
            '.gov': SourceReliability.HIGH,    # Government
            '.org': SourceReliability.MEDIUM,  # Non-profit
            'wikipedia.org': SourceReliability.MEDIUM,
            'scholar.google': SourceReliability.HIGH,
            'ncbi.nlm.nih.gov': SourceReliability.HIGH
        }
        
        # Initialize processing state
        self.active_tasks: Dict[str, ResearchTask] = {}
        self._processing_errors: List[Dict[str, Any]] = []
        
    async def process_task(
        self,
        task: ResearchTask,
        progress_callback: Optional[callable] = None
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Process research task through pipeline stages.
        
        Args:
            task: Research task to process
            progress_callback: Optional progress callback
            
        Yields:
            Dict[str, Any]: Stage results
        """
        self.active_tasks[task.id] = task
        task.update_status(TaskStatus.SEARCHING)
        
        try:
            # Stage 1: Search and collect URLs
            if progress_callback:
                progress_callback(0.1)
                
            search_results = await self._perform_search(task.description)
            if not search_results:
                raise ProcessingError("No search results found")
            
            # Stage 2: Filter and validate sources
            if progress_callback:
                progress_callback(0.3)
                
            valid_sources = await self._validate_sources(search_results)
            if not valid_sources:
                raise ProcessingError("No valid sources found")
            
            # Stage 3: Extract content via Firecrawl
            if progress_callback:
                progress_callback(0.5)
                
            findings = await self._extract_content(valid_sources)
            if not findings:
                raise ProcessingError("No content extracted from sources")
                
            # Stage 4: Process and analyze findings
            if progress_callback:
                progress_callback(0.7)
                
            processed_findings = await self._process_findings(findings, task)
            
            # Stage 5: Store in memory
            if progress_callback:
                progress_callback(0.9)
                
            await self._store_findings(processed_findings, task)
            
            # Complete task
            task.update_status(TaskStatus.COMPLETED)
            if progress_callback:
                progress_callback(1.0)
            
            yield {
                'task_id': task.id,
                'status': 'completed',
                'findings': processed_findings,
                'sources_processed': len(valid_sources),
                'findings_count': len(processed_findings)
            }
            
        except Exception as e:
            error_msg = f"Pipeline processing failed: {str(e)}"
            logger.error(error_msg)
            task.update_status(TaskStatus.FAILED)
            task.error = error_msg
            
            # Track error
            self._processing_errors.append({
                'task_id': task.id,
                'error': str(e),
                'timestamp': datetime.now().isoformat()
            })
            
            yield {
                'task_id': task.id,
                'status': 'failed',
                'error': error_msg
            }
            
        finally:
            if task.id in self.active_tasks:
                del self.active_tasks[task.id]

    async def _perform_search(self, query: str) -> List[Dict[str, Any]]:
        """Perform Google search and extract results."""
        try:
            # Ensure browser is initialized
            if not self.browser.is_initialized():
                raise BrowserError("Browser not initialized")
            
            # Encode search query
            encoded_query = quote_plus(query)
            search_url = f"https://www.google.com/search?q={encoded_query}"
            
            # Wait for search results with retry
            retry_count = 0
            max_retries = 3
            
            while retry_count < max_retries:
                try:
                    # Navigate to search
                    self.browser.driver.get(search_url)
                    
                    # Wait for results container
                    results_container = self.browser.wait.until(
                        EC.presence_of_element_located((By.ID, "search"))
                    )
                    
                    # Extract search results
                    results = []
                    for result in results_container.find_elements(By.CSS_SELECTOR, "div.g"):
                        try:
                            # Extract title, URL, and snippet
                            title_elem = result.find_element(By.CSS_SELECTOR, "h3")
                            link_elem = result.find_element(By.CSS_SELECTOR, "a")
                            snippet_elem = result.find_element(By.CSS_SELECTOR, "div.VwiC3b")
                            
                            results.append({
                                'title': title_elem.text,
                                'url': link_elem.get_attribute('href'),
                                'snippet': snippet_elem.text
                            })
                        except Exception as e:
                            logger.debug(f"Failed to extract result: {str(e)}")
                            continue
                    
                    if results:
                        return results
                        
                except TimeoutException:
                    retry_count += 1
                    if retry_count < max_retries:
                        await asyncio.sleep(2 ** retry_count)  # Exponential backoff
                    continue
                    
                except WebDriverException as e:
                    logger.error(f"WebDriver error: {str(e)}")
                    break
            
            raise BrowserError("Failed to get search results after retries")
            
        except Exception as e:
            logger.error(f"Search failed: {str(e)}")
            raise

    async def _validate_sources(
        self,
        search_results: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Validate and filter sources based on reliability."""
        valid_sources = []
        
        for result in search_results:
            try:
                url = result['url']
                domain = urlparse(url).netloc.lower()
                
                # Determine reliability
                reliability = SourceReliability.UNKNOWN
                for pattern, rel in self.source_reliability.items():
                    if pattern in domain:
                        reliability = rel
                        break
                
                # Skip unreliable sources
                if reliability in {SourceReliability.UNKNOWN, SourceReliability.UNRELIABLE}:
                    continue
                
                valid_sources.append({
                    **result,
                    'reliability': reliability,
                    'source_type': self._determine_source_type(url)
                })
                
            except Exception as e:
                logger.debug(f"Source validation failed for {result.get('url')}: {str(e)}")
                continue
        
        return valid_sources

    async def _extract_content(
        self,
        sources: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Extract content using Firecrawl."""
        findings = []
        
        for source in sources:
            try:
                if self.firecrawl:
                    # Use Firecrawl for content extraction
                    scrape_result_obj = await self.firecrawl.scrape_url(
                        source['url'],
                        formats=['markdown'],
                        timeout=30000,
                        removeScripts=True,
                        removeStyles=True
                    )
                    
                    scrape_result = scrape_result_obj.model_dump()
                    
                    if scrape_result and 'markdown' in scrape_result:
                        findings.append({
                            **source,
                            'content': scrape_result['markdown'],
                            'extracted_at': datetime.now().isoformat()
                        })
                else:
                    # Fallback to browser extraction
                    content = await self.browser.extract_content(source['url'])
                    if content:
                        findings.append({
                            **source,
                            'content': content,
                            'extracted_at': datetime.now().isoformat()
                        })
                        
            except Exception as e:
                logger.warning(f"Content extraction failed for {source['url']}: {str(e)}")
                continue
        
        return findings

    async def _process_findings(
        self,
        findings: List[Dict[str, Any]],
        task: ResearchTask
    ) -> List[ResearchFinding]:
        """Process and analyze findings."""
        processed_findings = []
        
        for finding in findings:
            try:
                # Create research finding
                processed = ResearchFinding(
                    content=finding['content'],
                    source=finding['url'],
                    source_type=finding['source_type'],
                    reliability=finding['reliability'],
                    research_source=task.research_type,
                    timestamp=datetime.fromisoformat(finding['extracted_at']),
                    metadata={
                        'title': finding['title'],
                        'snippet': finding['snippet'],
                        'task_id': task.id
                    }
                )
                
                processed_findings.append(processed)
                
            except Exception as e:
                logger.warning(f"Finding processing failed: {str(e)}")
                continue
        
        return processed_findings

    async def _store_findings(
        self,
        findings: List[ResearchFinding],
        task: ResearchTask
    ) -> None:
        """Store findings in memory system."""
        if not self.memory_manager:
            return
            
        try:
            # Create combined memory entry
            memory_content = f"Research findings for: {task.description}\n\n"
            for finding in findings:
                memory_content += f"Source: {finding.source}\n"
                memory_content += f"Title: {finding.metadata['title']}\n"
                memory_content += f"Content:\n{finding.content}\n\n"
            
            memory = Memory(
                content=memory_content,
                metadata={
                    'type': 'research_findings',
                    'task_id': task.id,
                    'sources': [f.source for f in findings],
                    'timestamp': datetime.now().isoformat()
                }
            )
            
            # Generate embedding if available
            if hasattr(self.memory_manager, 'generate_embedding'):
                memory.embedding = await self.memory_manager.generate_embedding(memory_content)
            
            # Store in memory
            await self.memory_manager.store(memory)
            
        except Exception as e:
            logger.error(f"Failed to store findings: {str(e)}")
            raise

    def _determine_source_type(self, url: str) -> SourceType:
        """Determine source type from URL."""
        domain = urlparse(url).netloc.lower()
        
        if any(edu in domain for edu in ['.edu', 'university.', 'academic.']):
            return SourceType.SCHOLARLY
        elif '.gov' in domain:
            return SourceType.GOVERNMENT
        elif any(sci in domain for sci in ['science.', 'research.', 'arxiv.']):
            return SourceType.SCIENTIFIC
        elif any(news in domain for news in ['news.', 'reuters.', 'ap.org']):
            return SourceType.NEWS
        else:
            return SourceType.WEBPAGE

    def get_active_tasks(self) -> List[str]:
        """Get list of active task IDs."""
        return list(self.active_tasks.keys())

    def get_error_count(self) -> int:
        """Get count of processing errors."""
        return len(self._processing_errors)

    def get_last_error(self) -> Optional[Dict[str, Any]]:
        """Get most recent processing error."""
        return self._processing_errors[-1] if self._processing_errors else None
