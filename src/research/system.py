"""
Enhanced research system with Firecrawl and Ollama integration.
File: src/research/system.py
"""

import logging
import asyncio
import json
import re
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple, Union, TypeVar, TYPE_CHECKING
from datetime import datetime
import tldextract
from urllib.parse import urlparse
import uuid
from rich.console import Console
from rich.panel import Panel

# Use TYPE_CHECKING for circular imports
if TYPE_CHECKING:
    from src.research.browser_manager import BrowserManager
    from src.research.task_manager import ResearchTaskManager
    from src.research.content_processor import ContentProcessor

from src.research.models import (
    ResearchType,
    TaskStatus,
    SourceType,
    SourceReliability,
    ValidationLevel,
    ResearchTask,
    ResearchFinding
)
from src.research.exceptions import ResearchError, TaskError, ProcessingError
from src.memory.models import Memory
from src.research.base_system import BaseResearchSystem
from src.research.archivist import run_research
from src.memory.storage_adapter import ChromaSemanticStore

logger = logging.getLogger(__name__)
console = Console()

class ResearchSystem(BaseResearchSystem):
    # Type variable for schema validation
    T = TypeVar('T')
    """Main research system implementation."""
    
    def __init__(
        self,
        memory_manager=None,
        ollama_client=None,
        config=None,
        chroma_store: ChromaSemanticStore = None
    ):
        """Initialize research system with required components."""
        super().__init__(memory_manager, ollama_client, config)
        self.chroma_store = chroma_store
        self.TRUSTED_DOMAINS = {
            "wikipedia.org": 0.9,
            "nationalgeographic.com": 0.85,
            "bbc.com": 0.8,
            "nytimes.com": 0.8,
            "nature.com": 0.95,
            "sciencedirect.com": 0.9,
            "researchgate.net": 0.85,
            "britannica.com": 0.85,
            "nasa.gov": 0.95,
            "nih.gov": 0.95
        }
        
        # Defer browser initialization to avoid circular imports
        self.browser = None
        self.task_manager = None
        self.content_processor = None
        
        # Initialize Firecrawl client conditionally
        self.firecrawl = None
        if config and hasattr(config, 'firecrawl') and config.firecrawl:
            # Import here to avoid circular dependencies
            try:
                from firecrawl import AsyncV1FirecrawlApp
                # Use api_url from config if available (base_url in our config)
                api_url = getattr(config.firecrawl, 'base_url', None)
                self.firecrawl = AsyncV1FirecrawlApp(
                    api_key=config.firecrawl.api_key,
                    api_url=api_url
                )
            except ImportError:
                logger.warning("Firecrawl package not found. Firecrawl integration disabled.")
        
        self.results_dir = config.results_dir if config else None
        if self.results_dir:
            self.results_dir.mkdir(parents=True, exist_ok=True)

    async def initialize(self) -> None:
        """Initialize research system components."""
        if self.initialized:
            return
            
        try:
            # Import components here to avoid circular imports
            from src.research.browser_manager import BrowserManager
            from src.research.task_manager import ResearchTaskManager
            from src.research.content_processor import ContentProcessor
            
            # Initialize components
            # Browser is optional - many operations work via Firecrawl API directly
            try:
                self.browser = BrowserManager(config=self.config.browser if self.config else None)
                await self.browser.initialize()
            except Exception as e:
                logger.warning(f"Browser manager unavailable, continuing without it: {e}")
                self.browser = None

            self.task_manager = ResearchTaskManager(
                memory_manager=self.memory_manager,
                ollama_client=self.ollama_client,
                max_concurrent_tasks=self.config.max_concurrent_tasks if self.config else 5,
                task_timeout=self.config.task_timeout if self.config else 300,
                results_dir=self.config.results_dir if self.config else None
            )
            self.content_processor = ContentProcessor(
                ollama_client=self.ollama_client,
                firecrawl_config=self.config.firecrawl if self.config else None,
                chunk_size=self.config.chunk_size if self.config else 1000,
                chunk_overlap=self.config.chunk_overlap if self.config else 100
            )
            
            # Initialize all components in order
            if self.browser:
                pass  # Already initialized above
            await self.task_manager.initialize()
            await self.content_processor.initialize()
            await super().initialize()
            
            self.initialized = True
            logger.info("Research system initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize research system: {str(e)}")
            await self.cleanup()
            raise

    async def cleanup(self) -> None:
        """Clean up system resources."""
        try:
            if self.browser:
                await self.browser.cleanup()
            if self.task_manager:
                await self.task_manager.cleanup()
            if self.content_processor:
                await self.content_processor.cleanup()
            
            # Clean up firecrawl if available
            if self.firecrawl and hasattr(self.firecrawl, 'cleanup'):
                await self.firecrawl.cleanup()
                
            await super().cleanup()
            self.initialized = False
            logger.info("Research system cleanup completed")
            
        except Exception as e:
            logger.error(f"Error during cleanup: {str(e)}")

    def _ensure_string_content(self, content) -> str:
        """
        Convert any content to a proper string format.
        This is critical for memory storage and embedding generation.
        
        Args:
            content: Content to convert to string
            
        Returns:
            str: String representation of content
        """
        if content is None:
            return ""
        
        # Handle lists by joining elements with newlines
        if isinstance(content, list):
            return "\n".join(self._ensure_string_content(item) for item in content)
        
        # Handle dictionaries by converting to JSON
        if isinstance(content, dict):
            try:
                return json.dumps(content, ensure_ascii=False)
            except Exception:
                # Fallback for non-serializable dicts
                return str(content)
        
        # Convert any other type to string
        return str(content)

    async def safe_generate_embedding(self, content) -> Optional[List[float]]:
        """
        Safely generate embedding from content with robust error handling.
        
        Args:
            content: Content to embed
            
        Returns:
            Optional[List[float]]: Generated embedding or None if failed
        """
        if not self.ollama_client:
            return None
            
        try:
            # Always ensure content is a properly formatted string
            string_content = self._ensure_string_content(content)
            
            # Generate embedding with the string content
            embedding = await self.ollama_client.generate_embedding(string_content)
            return embedding
        except Exception as e:
            logger.warning(f"Failed to generate embedding: {str(e)}")
            return None

    async def research_topic(
        self,
        topic: str,
        research_type: ResearchType = ResearchType.WEB_SEARCH,
        depth: int = 3,
        progress_callback: Optional[callable] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Research a topic with fallback to multiple search engines.
        
        Args:
            topic: Topic to research
            research_type: Type of research
            depth: Depth of research
            progress_callback: Optional progress callback
            metadata: Optional metadata
            
        Returns:
            Dict[str, Any]: Research results
        """
        if not self.initialized:
            await self.initialize()
            
        try:
            if research_type == ResearchType.DEEP_RESEARCH:
                if progress_callback:
                    progress_callback(0.1)

                # Use Archivist for Deep Research (requires chroma_store)
                if not self.chroma_store:
                    raise RuntimeError("DEEP_RESEARCH requires chroma_store to be set on ResearchSystem")

                console.print(Panel(
                    f"[bold green]INITIATING DEEP RESEARCH PROTOCOL:[/bold green] [cyan]{topic}[/cyan]",
                    border_style="green"
                ))

                result = await run_research(
                    objective=f"Objective: {topic}",
                    chroma_store=self.chroma_store,
                    memory_manager=self.memory_manager,
                    ollama_client=self.ollama_client,
                    browser_manager=self.browser,
                    topic=topic
                )

                final_results = {
                    'topic': topic,
                    'report': result['answer'],
                    'sources': result['sources'],
                    'steps': result['steps'],
                    'timestamp': datetime.now().isoformat(),
                    'findings': []  # For compatibility
                }

                final_results['findings'].append({
                    'url': 'internal://archivist-report',
                    'title': f"Deep Research Report: {topic}",
                    'summary': result['answer'][:500] + "...",
                    'key_takeaways': ["See full report for details"]
                })

                if self.memory_manager:
                    memory = Memory(
                        content=result['answer'],
                        metadata={
                            'type': 'deep_research_results',
                            'topic': topic,
                            'sources': result['sources'],
                            'timestamp': datetime.now().isoformat()
                        }
                    )
                    memory.embedding = await self.safe_generate_embedding(result['answer'])
                    await self.memory_manager.store(memory)

                if progress_callback:
                    progress_callback(1.0)

                return final_results

            if progress_callback:
                progress_callback(0.05)
                
            # Use more reliable search engines first
            search_engines = ["bing", "msn", "google"]
            search_results = None
            
            for engine in search_engines:
                try:
                    if not self.browser:
                        raise ResearchError("Browser manager is not available")
                    logger.info(f"Searching on {engine.capitalize()}...")
                    search_results = await self.browser.gather_content(
                        topic,
                        search_engine=engine
                    )
                    if search_results and search_results.get('results'):
                        logger.info(f"Found results from {engine}")
                        break
                except Exception as e:
                    logger.warning(f"Failed to search using {engine}: {str(e)}")
                    continue
            
            if not search_results or not search_results.get('results'):
                raise ResearchError("No search results found from any search engine")
            
            if progress_callback:
                progress_callback(0.30)
            
            # Process URLs directly - simplify by using only top 5 results
            top_urls = search_results['results'][:5]
            
            if progress_callback:
                progress_callback(0.50)
            
            # Process URLs with real-time display
            extracted_content = []
            
            for url_data in top_urls:
                try:
                    url = url_data['url']
                    
                    # Display what we're about to extract
                    console.print(f"[bold cyan]Extracting from:[/bold cyan] {url}")
                    
                    if not self.firecrawl:
                        # Use browser manager as fallback if firecrawl not available
                        if not self.browser:
                            raise ResearchError("Neither Firecrawl nor browser manager is available")
                        console.print("[yellow]Using browser fallback (Firecrawl not available)[/yellow]")
                        content = await self.browser.browse_url(url)
                        if content:
                            extraction_result = {
                                'markdown': content,
                                'timestamp': datetime.now().isoformat()
                            }
                        else:
                            console.print(f"[red]No content extracted from {url}[/red]")
                            continue
                    else:
                        # Use Firecrawl for extraction
                        console.print(f"[cyan]Scraping content with Firecrawl...[/cyan]")
                        extraction_result = await self._safe_scrape_url(url)
                        if not extraction_result or not extraction_result.get('markdown'):
                            console.print(f"[red]Failed to extract content from {url}[/red]")
                            continue
                        else:
                            # Create a cleaner, more readable preview
                            preview_text = extraction_result['markdown'][:300].strip()
                            if len(extraction_result['markdown']) > 300:
                                preview_text += "..."
                                
                            console.print(Panel(
                                preview_text,
                                title=f"[bold green]Content Preview from[/bold green] [blue]{url}[/blue]",
                                border_style="green",
                                padding=(1, 2),
                                expand=False
                            ))
                            console.print(f"[green]Successfully extracted {len(extraction_result['markdown'])} characters[/green]")
                    
                    # Process with LLM if available
                    key_findings = None
                    if self.ollama_client:
                        console.print(f"[cyan]Analyzing content with LLM...[/cyan]")
                        key_findings = await self._extract_key_information(
                            extraction_result['markdown'],
                            topic
                        )
                        if key_findings:
                            console.print(f"[green]✓ Analysis complete[/green]")
                        else:
                            console.print(f"[yellow]⚠ Analysis produced no results[/yellow]")
                    else:
                        console.print(f"[yellow]Skipping analysis (LLM not available)[/yellow]")
                    
                    # Add to extracted content
                    extracted_content.append({
                        'url': url,
                        'title': url_data.get('title', ''),
                        'content': extraction_result['markdown'][:1000],  # Limit content size
                        'key_findings': key_findings,
                        'timestamp': datetime.now().isoformat()
                    })
                    
                    # Display key findings in a more structured and visually appealing way
                    if key_findings:
                        console.print(Panel(
                            f"[bold cyan]Summary:[/bold cyan]\n{key_findings.get('summary', 'No summary available')}\n\n" +
                            f"[bold cyan]Key Takeaways:[/bold cyan]",
                            title=f"[bold green]Analysis Results for[/bold green] [blue]{url}[/blue]",
                            border_style="green",
                            padding=(1, 2),
                            expand=False
                        ))
                        
                        # Display each key takeaway with a bullet point
                        takeaways = key_findings.get('key_takeaways', [])
                        if isinstance(takeaways, list) and takeaways:
                            for point in takeaways:
                                console.print(f"  • [cyan]{point}[/cyan]")
                        elif takeaways:
                            console.print(f"  • [cyan]{takeaways}[/cyan]")
                            
                        console.print(f"[green bold]✓ Completed processing[/green bold] {url}")
                        console.print("=" * 80, style="bright_blue")  # ASCII separator line with color
                    else:
                        console.print(f"[yellow]⚠ No key findings extracted from[/yellow] {url}")
                        console.print("─" * 80)  # Separator line
                    
                except Exception as e:
                    console.print(f"[red]Error processing {url}: {str(e)}[/red]")
                    continue
            
            if progress_callback:
                progress_callback(0.70)
            
            # Format final results
            final_results = {
                'topic': topic,
                'findings': [],
                'sources_analyzed': len(top_urls),
                'successful_extractions': len(extracted_content),
                'timestamp': datetime.now().isoformat()
            }
            
            for finding in extracted_content:
                formatted_finding = {
                    'url': finding['url'],
                    'title': finding['title'],
                    'summary': finding.get('key_findings', {}).get('summary'),
                    'key_takeaways': finding.get('key_findings', {}).get('key_takeaways')
                }
                final_results['findings'].append(formatted_finding)
            
            # Normalize findings to ensure consistent structure
            self._normalize_findings(final_results['findings'])
            
            if progress_callback:
                progress_callback(0.85)
                
            # Store results if memory manager available
            if self.memory_manager and self.config and self.config.embed_findings:
                try:
                    # Create properly sanitized metadata
                    sanitized_metadata = {
                        'type': 'research_results',
                        'task_id': str(uuid.uuid4()),
                        'topic': topic,
                        'timestamp': datetime.now().isoformat()
                    }
                    
                    # Create a proper string for memory content - critical fix
                    memory_content = f"Research results for: {topic}\n\n"
                    
                    # Process each finding to build a proper string
                    for finding in final_results['findings']:  # Use the normalized findings
                        try:
                            # Add source URL
                            memory_content += f"Source: {finding.get('url', '')}\n"
                            
                            # Add title if available
                            if finding.get('title'):
                                memory_content += f"Title: {finding.get('title')}\n"
                            
                            # Add summary with proper string conversion
                            if finding.get('summary'):
                                memory_content += f"Summary: {finding.get('summary')}\n\n"
                            
                            # Add key takeaways with proper string conversion
                            if finding.get('key_takeaways'):
                                memory_content += "Key points:\n"
                                # This will always be a list of strings after normalization
                                for point in finding.get('key_takeaways', []):
                                    memory_content += f"- {point}\n"
                                memory_content += "\n"
                        except Exception as e:
                            logger.warning(f"Error processing finding for memory: {str(e)}")
                            continue
                    
                    # Create memory with properly formatted string content
                    memory = Memory(
                        content=memory_content,
                        metadata=sanitized_metadata
                    )
                    
                    # Generate embedding if available
                    if self.ollama_client:
                        try:
                            # Ensure content is a properly formatted string
                            content_to_embed = self._ensure_string_content(memory_content)
                            # Generate embedding with the string content
                            memory.embedding = await self.ollama_client.generate_embedding(content_to_embed)
                            logger.info("Successfully generated embedding for research results")
                        except Exception as e:
                            logger.warning(f"Failed to generate embedding: {str(e)}")
                            # Don't raise the exception to allow the operation to continue
                    
                    # Store in memory system
                    await self.memory_manager.store(memory)
                    logger.info("Stored research results in memory")
                except Exception as e:
                    logger.warning(f"Failed to store research in memory: {str(e)}")
                
            if progress_callback:
                progress_callback(1.0)
            
            # Return results
            return final_results
            
        except Exception as e:
            logger.error(f"Research failed: {str(e)}")
            raise ResearchError(f"Research failed: {str(e)}")

    def _normalize_findings(self, findings: List[Dict[str, Any]]) -> None:
        """
        Normalize findings to ensure consistent structure.
        This modifies the findings list in-place.
        
        Args:
            findings: List of findings to normalize
        """
        for finding in findings:
            # Ensure summary is a string
            if 'summary' in finding and finding['summary'] is not None:
                if isinstance(finding['summary'], list):
                    finding['summary'] = "\n".join(str(item) for item in finding['summary'])
                elif not isinstance(finding['summary'], str):
                    finding['summary'] = str(finding['summary'])
            
            # Ensure key_takeaways is a list of strings
            if 'key_takeaways' in finding and finding['key_takeaways'] is not None:
                if isinstance(finding['key_takeaways'], list):
                    finding['key_takeaways'] = [
                        str(item) for item in finding['key_takeaways']
                    ]
                elif not isinstance(finding['key_takeaways'], list):
                    # Convert non-list to a single-item list
                    finding['key_takeaways'] = [str(finding['key_takeaways'])]

    async def _safe_scrape_url(self, url: str) -> Optional[Dict[str, Any]]:
        """
        Safely scrape URL with Firecrawl with robust error handling and fallbacks.
        
        Args:
            url: URL to scrape
            
        Returns:
            Optional[Dict[str, Any]]: Scraped content or None
        """
        if not self.firecrawl:
            logger.info(f"Firecrawl not available, using browser for {url}")
            return await self._browser_scrape_fallback(url)
            
        try:
            logger.info(f"Attempting to scrape {url} with Firecrawl")
            
            try:
                # Use AsyncV1FirecrawlApp's scrape_url
                scrape_result_obj = await self.firecrawl.scrape_url(
                    url,
                    formats=['markdown']
                )
                
                # Convert Pydantic model to dictionary
                result = scrape_result_obj.model_dump()
                
                # Validate the result
                if not result:
                    logger.warning(f"Empty result from Firecrawl for {url}")
                    return await self._browser_scrape_fallback(url)
                
                if not isinstance(result, dict):
                    logger.warning(f"Invalid result type from Firecrawl for {url}: {type(result)}")
                    return await self._browser_scrape_fallback(url)
                
                if 'markdown' not in result or not result['markdown']:
                    logger.warning(f"No markdown content from Firecrawl for {url}")
                    return await self._browser_scrape_fallback(url)
                
                logger.info(f"Successfully scraped {url} with Firecrawl")
                return result
                
            except asyncio.TimeoutError:
                logger.warning(f"Firecrawl request timed out for {url}")
                return await self._browser_scrape_fallback(url)
                    
        except Exception as e:
            logger.warning(f"Firecrawl scraping failed for {url}: {str(e)}")
            return await self._browser_scrape_fallback(url)

    async def _browser_scrape_fallback(self, url: str) -> Optional[Dict[str, Any]]:
        """
        Fallback to browser scraping when Firecrawl fails.
        
        Args:
            url: URL to scrape
            
        Returns:
            Optional[Dict[str, Any]]: Scraped content or None
        """
        if not self.browser:
            logger.warning(f"No browser available for fallback scraping of {url}")
            return None
        
        try:
            if not self.browser:
                logger.warning(f"Browser manager not available, cannot scrape {url}")
                return None
            logger.info(f"Attempting to scrape {url} with browser fallback")

            # Try to extract content with browser
            content = await self.browser.browse_url(url)
            
            if not content:
                logger.warning(f"Browser extraction returned no content for {url}")
                return None
            
            # Basic HTML to text conversion
            try:
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(content, 'html.parser')
                
                # Remove script and style elements
                for script in soup(["script", "style", "iframe", "noscript"]):
                    script.extract()
                
                # Get text content
                text = soup.get_text(separator='\n', strip=True)
                
                # Simple markdown conversion
                paragraphs = []
                for para in text.split('\n\n'):
                    if para.strip():
                        paragraphs.append(para.strip())
                
                markdown = '\n\n'.join(paragraphs)
                
                # Verify markdown is a string
                if not isinstance(markdown, str):
                    markdown = str(markdown)
                
                logger.info(f"Successfully scraped {url} with browser fallback")
                return {
                    'markdown': markdown,
                    'timestamp': datetime.now().isoformat(),
                    'source': 'browser_fallback'
                }
                
            except ImportError:
                # If BeautifulSoup not available, use raw content
                if not isinstance(content, str):
                    content = str(content)
                    
                logger.info(f"BeautifulSoup not available, using raw content for {url}")
                return {
                    'markdown': content,
                    'timestamp': datetime.now().isoformat(),
                    'source': 'browser_fallback_raw'
                }
                
        except Exception as e:
            logger.error(f"Browser fallback scraping failed for {url}: {str(e)}")
            return None
            
    async def _extract_key_information(
        self,
        text: str,
        topic: str
    ) -> Dict[str, Any]:
        """
        Uses the LLM to extract and summarize key information from content.
        Implements JSON validation and repair logic to ensure robust parsing.
        
        Args:
            text: Text to analyze
            topic: Research topic
            
        Returns:
            Dict[str, Any]: Extracted key information
        """
        try:
            # Make sure text is a string
            if isinstance(text, list):
                text = "\n".join(str(item) for item in text)
                
            # Import here to avoid circular imports
            from src.utils.json_validator import extract_key_information
            
            # Use the validator to get validated findings
            extracted_result = await extract_key_information(
                llm_client=self.ollama_client,
                text=text,
                topic=topic
            )
            
            # Ensure all elements in the returned dict are strings, not lists
            result = {
                "summary": topic if not extracted_result or not extracted_result.get("summary") else (extracted_result["summary"] if isinstance(extracted_result["summary"], str) else str(extracted_result["summary"])),
                "key_takeaways": [],  # Initialize as empty list
                "detailed_analysis": "",
                "limitations": "",
                "actionable_insights": ""
            }
            
            # Add any content we extracted
            if extracted_result:
                # Convert any list values to strings
                for key, value in extracted_result.items():
                    if isinstance(value, list):
                        if key == "key_takeaways":
                            # Keep key_takeaways as a list with string items
                            result[key] = [str(item) for item in value]
                        else:
                            # Convert other lists to strings
                            result[key] = "\n".join(str(item) for item in value)
                    else:
                        result[key] = str(value) if value is not None else ""
            
            # Ensure key_takeaways is properly formatted
            if 'key_takeaways' in result and isinstance(result['key_takeaways'], list):
                result['key_takeaways'] = [str(item) for item in result['key_takeaways']]
                
            return result
            
        except ImportError:
            # If the validator module isn't available, implement simplified version inline
            try:
                # Build extraction prompt
                prompt = f"""
Analyze this content about "{topic}" and extract the most important information.
Output a valid JSON object with these exact keys:
- "summary": A brief summary of the content
- "key_takeaways": An array of key points (1-5 items)
- "detailed_analysis": A more thorough analysis
- "limitations": Any limitations or cautions
- "actionable_insights": Practical advice based on the content

The response MUST be valid JSON that can be parsed with json.loads().
Format the response as:
{{
  "summary": "...",
  "key_takeaways": ["point 1", "point 2"],
  "detailed_analysis": "...",
  "limitations": "...",
  "actionable_insights": "..."
}}

Content to analyze:
{text[:3000]}
"""
                
                # Get response from LLM
                messages = [{"role": "user", "content": prompt}]
                response = await self.ollama_client.chat(
                    model="llama3.1:latest",
                    messages=messages,
                    temperature=0.3
                )
                
                response_content = response.get('message', {}).get('content', '')
                
                # Try to extract JSON
                import re
                import json
                
                # Look for JSON in code blocks
                json_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', response_content)
                if json_match:
                    try:
                        extracted_result = json.loads(json_match.group(1))
                    except:
                        extracted_result = None
                else:
                    # Look for JSON with brackets
                    json_match = re.search(r'(\{[\s\S]*\})', response_content)
                    if json_match:
                        try:
                            extracted_result = json.loads(json_match.group(1))
                        except:
                            extracted_result = None
                    else:
                        extracted_result = None
                
                # If we can't parse JSON, make a second attempt with clearer instructions
                if not extracted_result:
                    retry_prompt = f"""
The previous response contained invalid JSON. 
I need a valid JSON object with these exact keys:
- "summary"
- "key_takeaways" (array)
- "detailed_analysis"
- "limitations"
- "actionable_insights"

The response must be valid JSON only, with no other text.
"""
                    messages.append({"role": "assistant", "content": response_content})
                    messages.append({"role": "user", "content": retry_prompt})
                    
                    retry_response = await self.ollama_client.chat(
                        model="llama3.1:latest", 
                        messages=messages,
                        temperature=0.2
                    )
                    
                    retry_content = retry_response.get('message', {}).get('content', '')
                    
                    # Try to parse again
                    json_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', retry_content)
                    if json_match:
                        try:
                            extracted_result = json.loads(json_match.group(1))
                        except:
                            extracted_result = None
                    else:
                        json_match = re.search(r'(\{[\s\S]*\})', retry_content)
                        if json_match:
                            try:
                                extracted_result = json.loads(json_match.group(1))
                            except:
                                extracted_result = None
                
                # Ensure all elements in the returned dict are strings, not lists
                result = {
                    "summary": topic if not extracted_result or not extracted_result.get("summary") else (extracted_result["summary"] if isinstance(extracted_result["summary"], str) else str(extracted_result["summary"])),
                    "key_takeaways": [],  # Initialize as empty list
                    "detailed_analysis": "",
                    "limitations": "",
                    "actionable_insights": ""
                }
                
                # Add any content we extracted
                if extracted_result:
                    # Convert any list values to strings
                    for key, value in extracted_result.items():
                        if isinstance(value, list):
                            if key == "key_takeaways":
                                # Keep key_takeaways as a list with string items
                                result[key] = [str(item) for item in value]
                            else:
                                # Convert other lists to strings
                                result[key] = "\n".join(str(item) for item in value)
                        else:
                            result[key] = str(value) if value is not None else ""
                
                # Ensure key_takeaways is properly formatted
                if 'key_takeaways' in result and isinstance(result['key_takeaways'], list):
                    result['key_takeaways'] = [str(item) for item in result['key_takeaways']]
                
                return result
                
            except Exception as e:
                logger.error(f"Error during key information extraction: {str(e)}")
                # Return a minimal valid response as fallback
                return {
                    "summary": f"Information about {topic}",
                    "key_takeaways": [f"Content related to {topic}"],
                    "detailed_analysis": "",
                    "limitations": "",
                    "actionable_insights": ""
                }

    async def _filter_trusted_sources(
        self,
        sources: List[Dict[str, Any]],
        min_reliability: float = 0.7
    ) -> List[Dict[str, Any]]:
        """Filter and prioritize trusted sources."""
        trusted_sources = []
        
        for source in sources:
            url = source.get('url')
            if not url:
                continue
                
            reliability = self._calculate_source_reliability(url)
            if reliability >= min_reliability:
                trusted_sources.append({
                    **source,
                    'reliability': reliability
                })
        
        # Sort by reliability
        trusted_sources.sort(key=lambda x: x['reliability'], reverse=True)
        return trusted_sources

    def _is_trusted_url(self, url: str) -> bool:
        """
        Check if URL is from trusted domain.
        
        Args:
            url: URL to check
            
        Returns:
            bool: True if URL is from trusted domain
        """
        try:
            domain = tldextract.extract(url).registered_domain
            return domain in self.TRUSTED_DOMAINS
        except Exception:
            return False

    def _calculate_source_reliability(self, url: str) -> float:
        """
        Calculate source reliability score.
        
        Args:
            url: URL to check
            
        Returns:
            float: Reliability score (0.0-1.0)
        """
        try:
            domain = tldextract.extract(url).registered_domain
            
            # Check trusted domains
            if domain in self.TRUSTED_DOMAINS:
                return self.TRUSTED_DOMAINS[domain]
            
            # Default reliability for unknown domains
            return 0.5
            
        except Exception:
            return 0.3  # Lower score for unparseable URLs

    async def store_research_results(
        self,
        task_id: str,
        results: Dict[str, Any]
    ) -> None:
        """
        Store research results in memory if available.
        
        Args:
            task_id: Task ID
            results: Research results to store
        """
        if not self.memory_manager:
            return
        
        try:
            # Ensure findings are properly normalized
            if 'findings' in results:
                self._normalize_findings(results['findings'])
            
            # Create memory content as a properly formatted string
            memory_content = f"Research results for: {results.get('topic', 'Unknown topic')}\n\n"
            
            # Process each finding to build memory content
            for finding in results.get('findings', []):
                # Add URL
                memory_content += f"Source: {finding.get('url', '')}\n"
                
                # Add summary with proper string conversion
                if finding.get('summary'):
                    memory_content += f"Summary: {finding.get('summary')}\n\n"
                
                # Add key takeaways if available
                if finding.get('key_takeaways'):
                    memory_content += "Key points:\n"
                    for point in finding.get('key_takeaways', []):
                        memory_content += f"- {point}\n"
                    memory_content += "\n"
            
            # Create memory object
            memory = Memory(
                content=memory_content,
                metadata={
                    'type': 'research_results',
                    'task_id': task_id,
                    'topic': results.get('topic', 'Unknown topic'),
                    'sources': [f.get('url', '') for f in results.get('findings', [])],
                    'timestamp': datetime.now().isoformat()
                }
            )
            
            # Generate embedding if LLM available
            if self.ollama_client:
                try:
                    # Generate embedding with the string content
                    memory.embedding = await self.ollama_client.generate_embedding(memory_content)
                    logger.info("Successfully generated embedding for research results")
                except Exception as e:
                    logger.warning(f"Failed to generate embedding: {str(e)}")
                    # Don't raise the exception to allow the operation to continue
            
            # Store in memory system
            await self.memory_manager.store(memory)
            logger.info(f"Stored research results in memory for task {task_id}")
        except Exception as e:
            logger.warning(f"Failed to store research in memory: {str(e)}")

    async def get_task_results(self, task_id: str) -> Optional[Dict[str, Any]]:
        """
        Get detailed results for a research task.
        
        Args:
            task_id: Task ID
            
        Returns:
            Optional[Dict[str, Any]]: Task results if available
        """
        if not self.task_manager:
            return None
            
        try:
            task = await self.task_manager.get_task(task_id)
            if not task:
                raise TaskError(f"Task not found: {task_id}")
                
            results = {
                'task_id': task_id,
                'description': task.description,
                'status': task.status.value,
                'created_at': task.created_at,
                'completed_at': task.completed_at,
                'findings': [],
                'metrics': {
                    'sources_analyzed': 0,
                    'trusted_sources': 0,
                    'total_findings': 0
                },
                'metadata': task.metadata
            }

            if task.status == TaskStatus.COMPLETED and task.result:
                results['findings'] = task.result.get('findings', [])
                results['metrics'].update({
                    'sources_analyzed': task.result.get('sources_analyzed', 0),
                    'trusted_sources': task.result.get('trusted_sources', 0),
                    'total_findings': len(results['findings'])
                })

                summary = await self.generate_summary(
                    results['findings'], task.description
                )
                if summary:
                    results['summary'] = summary

            return results

        except Exception as e:
            logger.error(f"Failed to get task results: {str(e)}")
            return None

    async def generate_summary(
        self,
        findings: List[Dict[str, Any]],
        topic: str
    ) -> Optional[str]:
        """
        Generate a summary of research findings using Ollama.
        
        Args:
            findings: List of findings to summarize
            topic: Research topic
            
        Returns:
            Optional[str]: Summary if generated
        """
        if not self.ollama_client or not findings:
            return None

        try:
            content_parts = []
            for finding in findings:
                source = finding.get('source', finding.get('url', 'Unknown source'))
                
                # Get content with proper string conversion
                content = finding.get('content', finding.get('summary', ''))
                if isinstance(content, list):
                    content = "\n".join(str(item) for item in content)
                elif not isinstance(content, str):
                    content = str(content)
                    
                if content:
                    content_parts.append(f"From {source}:\n{content}")

            # Join all content parts
            combined_content = "\n\n---\n\n".join(content_parts)

            # Create summary prompt
            prompt = f"""
            Provide a comprehensive summary of the following research findings about '{topic}'.
            Focus on key points, patterns, and conclusions. Organize the summary clearly:

            {combined_content}

            Format the summary with:
            1. Key Findings
            2. Main Conclusions
            3. Notable Sources
            """

            # Get summary from LLM
            messages = [{"role": "user", "content": prompt}]
            response = await self.ollama_client.chat(
                model="llama3.1:latest",
                messages=messages,
                temperature=0.3
            )
            
            summary_text = response.get('message', {}).get('content', '')
            return summary_text.strip()

        except Exception as e:
            logger.warning(f"Failed to generate summary: {str(e)}")
            return None

    async def validate_sources(self, urls: List[str]) -> Dict[str, Any]:
        """
        Validate research sources and calculate trust metrics.
        
        Args:
            urls: List of URLs to validate
            
        Returns:
            Dict[str, Any]: Validation results
        """
        validation_results = {
            'total_urls': len(urls),
            'trusted_urls': 0,
            'untrusted_urls': 0,
            'reliability_scores': {},
            'validation_details': []
        }

        for url in urls:
            try:
                reliability = self._calculate_source_reliability(url)
                is_trusted = self._is_trusted_url(url)

                validation_results['reliability_scores'][url] = reliability
                validation_results['validation_details'].append({
                    'url': url,
                    'is_trusted': is_trusted,
                    'reliability': reliability,
                    'timestamp': datetime.now().isoformat()
                })

                if is_trusted:
                    validation_results['trusted_urls'] += 1
                else:
                    validation_results['untrusted_urls'] += 1

            except Exception as e:
                logger.warning(f"Failed to validate URL {url}: {str(e)}")
                continue

        return validation_results

    async def get_status(self) -> Dict[str, Any]:
        """
        Get detailed system status.
        
        Returns:
            Dict[str, Any]: System status
        """
        try:
            status = {
                'initialized': self.initialized,
                'components': {
                    'browser': bool(self.browser and getattr(self.browser, '_initialized', False)),
                    'task_manager': bool(self.task_manager),
                    'content_processor': bool(self.content_processor),
                    'memory_manager': bool(self.memory_manager),
                    'ollama_client': bool(self.ollama_client),
                    'firecrawl': bool(self.firecrawl)
                },
                'metrics': {
                    'processed_tasks': len(getattr(self.task_manager, 'tasks', {})) if self.task_manager else 0,
                    'active_tasks': len(getattr(self.task_manager, 'active_tasks', set())) if self.task_manager else 0
                },
                'timestamp': datetime.now().isoformat()
            }

            return status

        except Exception as e:
            logger.error(f"Failed to get status: {str(e)}")
            return {
                'error': str(e),
                'timestamp': datetime.now().isoformat()
            }

    async def perform_deep_research(
        self,
        task_id: str,
        validation_level: ValidationLevel = ValidationLevel.HIGH
    ) -> Dict[str, Any]:
        """
        Perform deep research with enhanced validation.
        
        Args:
            task_id: Task ID
            validation_level: Validation strictness level
            
        Returns:
            Dict[str, Any]: Deep research results
        """
        if not self.task_manager:
            await self.initialize()
            
        try:
            task = await self.task_manager.get_task(task_id)
            if not task:
                raise TaskError(f"Task not found: {task_id}")

            # Get initial results
            results = await self.get_task_results(task_id)
            if not results:
                raise ResearchError("No initial results found")

            # Validate sources with enhanced validation
            validation_results = await self.validate_sources(
                [f['url'] for f in results.get('findings', [])]
            )

            # Filter findings based on validation level
            validated_findings = []
            for finding in results.get('findings', []):
                url = finding['url']
                reliability = validation_results['reliability_scores'].get(url, 0.0)
                
                if validation_level == ValidationLevel.HIGH and reliability >= 0.8:
                    validated_findings.append(finding)
                elif validation_level == ValidationLevel.MEDIUM and reliability >= 0.6:
                    validated_findings.append(finding)
                elif validation_level == ValidationLevel.LOW and reliability >= 0.4:
                    validated_findings.append(finding)
            
            # Get content from validated sources
            deep_findings = []
            for finding in validated_findings:
                try:
                    # Get content using Firecrawl or browser
                    content = None
                    if self.firecrawl:
                        result = await self._safe_scrape_url(finding['url'])
                        if result and result.get('markdown'):
                            content = result['markdown']
                    
                    if not content and self.browser:
                        html_content = await self.browser.browse_url(finding['url'])
                        if html_content:
                            # Get HTML content as string
                            if not isinstance(html_content, str):
                                html_content = str(html_content)
                            content = html_content
                    
                    if content:
                        # Process content if content processor is available
                        processed = None
                        if self.content_processor:
                            processed = await self.content_processor.process_content(
                                content,
                                task=task,
                                metadata={'source_url': finding['url']}
                            )
                        
                        deep_findings.append({
                            **finding,
                            'full_content': content[:5000],  # Limit content length
                            'processed_content': processed,
                            'validation_info': next(
                                (v for v in validation_results['validation_details'] 
                                if v['url'] == finding['url']),
                                {'reliability': 0.5}
                            )
                        })
                                
                except Exception as e:
                    logger.warning(f"Failed to process deep content from {finding['url']}: {str(e)}")
                    continue
            
            # Generate comprehensive analysis
            analysis = None
            if deep_findings and self.ollama_client:
                try:
                    content_parts = []
                    for finding in deep_findings:
                        content = finding.get('full_content', '')
                        if content:
                            content_parts.append(
                                f"Source: {finding['url']}\n"
                                f"Reliability: {finding['validation_info']['reliability']}\n"
                                f"Content:\n{content[:1000]}"  # First 1000 chars only
                            )
                    
                    combined_content = "\n\n---\n\n".join(content_parts)
                    
                    prompt = f"""
                    Perform a comprehensive analysis of the following research findings about '{task.description}'.
                    Focus on:
                    1. Key themes and patterns across sources
                    2. Main arguments and evidence
                    3. Contradictions or disagreements between sources
                    4. Reliability assessment of the information
                    5. Gaps in the research
                    
                    Sources:
                    {combined_content}
                    
                    Provide a structured analysis with clear sections.
                    """
                    
                    messages = [{"role": "user", "content": prompt}]
                    response = await self.ollama_client.chat(
                        model="llama3.1:latest",
                        messages=messages,
                        temperature=0.3
                    )
                    
                    analysis_text = response.get('message', {}).get('content', '')
                    
                    analysis = {
                        'text': analysis_text.strip(),
                        'sources_analyzed': len(deep_findings),
                        'avg_reliability': sum(
                            f['validation_info']['reliability'] 
                            for f in deep_findings
                        ) / len(deep_findings) if deep_findings else 0,
                        'timestamp': datetime.now().isoformat()
                    }
                    
                except Exception as e:
                    logger.warning(f"Failed to generate analysis: {str(e)}")
            
            deep_results = {
                'task_id': task_id,
                'validation_level': validation_level.value,
                'original_findings': len(results.get('findings', [])),
                'validated_findings': len(validated_findings),
                'deep_findings': len(deep_findings),
                'analysis': analysis,
                'validation_results': validation_results,
                'timestamp': datetime.now().isoformat()
            }
            
            # Store results if configured
            if self.results_dir:
                try:
                    results_file = self.results_dir / f"deep_research_{task_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
                    with open(results_file, 'w', encoding='utf-8') as f:
                        json.dump(deep_results, f, indent=2)
                except Exception as e:
                    logger.warning(f"Failed to store deep research results: {str(e)}")
            
            return deep_results
            
        except Exception as e:
            logger.error(f"Deep research failed: {str(e)}")
            raise ResearchError(f"Deep research failed: {str(e)}")

    def _calculate_readability(self, content: str) -> float:
        """
        Calculate readability score.
        
        Args:
            content: Content to analyze
            
        Returns:
            float: Readability score (0.0-1.0)
        """
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

    def _assess_technical_depth(self, content: str) -> float:
        """
        Assess technical depth of content.
        
        Args:
            content: Content to analyze
            
        Returns:
            float: Technical depth score (0.0-1.0)
        """
        try:
            # Technical indicators
            indicators = {
                'code_blocks': r'```[\s\S]*?```',
                'equations': r'\$[^$]+\$|\\\(.*?\\\)',
                'technical_terms': r'\b(?:algorithm|implementation|framework|architecture|protocol)\b',
                'data_structures': r'\b(?:array|list|tree|graph|queue|stack)\b',
                'measurements': r'\d+(?:\.\d+)?\s*(?:bytes?|kb|mb|gb|ms|ns|fps)',
                'variables': r'\b(?:var|let|const|function|class|method)\b'
            }
            
            scores = []
            for pattern in indicators.values():
                matches = re.findall(pattern, content, re.IGNORECASE)
                score = min(len(matches) / 5, 1.0)  # Cap at 1.0
                scores.append(score)
            
            return round(sum(scores) / len(indicators), 2) if scores else 0.0
            
        except Exception:
            return 0.0

    def __str__(self) -> str:
        """
        Get string representation.
        
        Returns:
            str: String representation
        """
        return f"ResearchSystem(initialized={self.initialized})"
