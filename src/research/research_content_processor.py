"""
Enhanced research content processor with Firecrawl integration.
File: src/research/research_content_processor.py
"""

import logging
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime

from src.research.models import ResearchTask, SourceType, TaskStatus
from src.research.exceptions import ProcessingError
from src.research.firecrawl_client import FirecrawlClient
from src.research.result_processor import ResearchResultProcessor
from src.memory.models import Memory

logger = logging.getLogger(__name__)

class ContentProcessor:
    """Processes research content with Firecrawl and LLM analysis."""
    
    def __init__(
        self,
        ollama_client=None,
        firecrawl_config=None,
        chunk_size: int = 1000,
        chunk_overlap: int = 100
    ):
        """Initialize content processor."""
        self.client = ollama_client
        self.firecrawl = FirecrawlClient(config=firecrawl_config)
        self.result_processor = ResearchResultProcessor(ollama_client)
        
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        
        # Track processed content
        self._processed_urls: Dict[str, Dict[str, Any]] = {}
    
    async def process_research_content(
        self,
        urls: List[Dict[str, Any]],
        task: ResearchTask,
        progress_callback: Optional[callable] = None
    ) -> List[Dict[str, Any]]:
        """
        Process a batch of research URLs.
        
        Args:
            urls: List of URLs to process
            task: Associated research task
            progress_callback: Optional progress callback
            
        Returns:
            List[Dict[str, Any]]: Processed research findings
        """
        try:
            findings = []
            total_urls = len(urls)
            
            # Update task status
            task.update_status(TaskStatus.SCRAPING)
            
            for idx, url_data in enumerate(urls):
                try:
                    url = url_data['url']
                    
                    # Skip if already processed
                    if url in self._processed_urls:
                        findings.append(self._processed_urls[url])
                        continue
                    
                    # Use Firecrawl to get markdown
                    scrape_result = await self.firecrawl.scrape_url(url)
                    
                    if not scrape_result.get('markdown'):
                        logger.warning(f"No markdown content for {url}")
                        continue
                    
                    # Process markdown content
                    processed = await self.result_processor.process_markdown(
                        scrape_result['markdown'],
                        task,
                        url
                    )
                    
                    # Create memory from processed content
                    memory = await self.result_processor.create_memory(processed, task)
                    
                    # Generate embedding if LLM available
                    if self.client:
                        try:
                            memory.embedding = await self.client.generate_embedding(memory.content)
                        except Exception as e:
                            logger.warning(f"Failed to generate embedding: {str(e)}")
                    
                    # Add to findings
                    finding = {
                        'content': memory.content,
                        'url': url,
                        'title': url_data.get('title', ''),
                        'source_type': processed['metadata']['source_type'],
                        'reliability': url_data.get('reliability', 0.5),
                        'has_citations': processed['metadata']['has_citations'],
                        'word_count': processed['metadata']['word_count'],
                        'extracted_info': processed['extracted_info'],
                        'timestamp': datetime.now().isoformat()
                    }
                    
                    findings.append(finding)
                    self._processed_urls[url] = finding
                    
                    # Update progress
                    if progress_callback:
                        progress_callback((idx + 1) / total_urls)
                    
                except Exception as e:
                    logger.error(f"Failed to process {url}: {str(e)}")
    
                except Exception as e:
                    logger.error(f"Failed to process {url}: {str(e)}")
                    continue
            
            # Update task status
            task.update_status(TaskStatus.ANALYZING)
            
            # Generate combined analysis if we have findings
            if findings and self.client:
                combined_analysis = await self._generate_combined_analysis(
                    findings,
                    task.description
                )
                if combined_analysis:
                    task.metadata['combined_analysis'] = combined_analysis
            
            return findings
            
        except Exception as e:
            logger.error(f"Content processing failed: {str(e)}")
            raise ProcessingError(f"Content processing failed: {str(e)}")
    
    async def _generate_combined_analysis(
        self,
        findings: List[Dict[str, Any]],
        topic: str
    ) -> Optional[Dict[str, Any]]:
        """Generate combined analysis of all findings."""
        try:
            # Prepare content for analysis
            content_parts = []
            for finding in findings:
                content_parts.append(f"Source: {finding['url']}\n{finding['content']}")
            
            combined_content = "\n\n---\n\n".join(content_parts)
            
            # Create analysis prompt
            prompt = f"""
            Analyze the following research findings related to: {topic}

            Sources:
            {combined_content}

            Provide a comprehensive analysis including:
            1. Key themes and patterns across sources
            2. Main conclusions supported by multiple sources
            3. Any contradictions or disagreements between sources
            4. Notable statistics and data points
            5. Gaps in the research or areas needing more investigation

            Structure the analysis clearly with sections.
            """
            
            # Get analysis from LLM
            messages = [{"role": "user", "content": prompt}]
            analysis_text = ""
            
            async for response in self.client.chat(
                messages=messages,
                stream=True,
                temperature=0.3
            ):
                if response and response.content:
                    analysis_text += response.content
            
            # Extract sections from analysis
            sections = await self._extract_analysis_sections(analysis_text)
            
            return {
                'text': analysis_text,
                'sections': sections,
                'source_count': len(findings),
                'timestamp': datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.warning(f"Failed to generate combined analysis: {str(e)}")
            return None
    
    async def _extract_analysis_sections(self, text: str) -> Dict[str, str]:
        """Extract sections from analysis text."""
        sections = {}
        current_section = 'main'
        current_content = []
        
        for line in text.split('\n'):
            if line.strip() and any(char.isdigit() for char in line[:2]):
                # Looks like a numbered section
                if current_content:
                    sections[current_section] = '\n'.join(current_content).strip()
                current_section = line.strip()
                current_content = []
            else:
                current_content.append(line)
        
        # Add final section
        if current_content:
            sections[current_section] = '\n'.join(current_content).strip()
        
        return sections
    
    async def process_url(
        self,
        url: str,
        task: ResearchTask
    ) -> Optional[Dict[str, Any]]:
        """
        Process a single URL.
        
        Args:
            url: URL to process
            task: Associated research task
            
        Returns:
            Optional[Dict[str, Any]]: Processed content if successful
        """
        try:
            # Check if already processed
            if url in self._processed_urls:
                return self._processed_urls[url]
            
            # Use Firecrawl to get markdown
            scrape_result = await self.firecrawl.scrape_url(url)
            
            if not scrape_result.get('markdown'):
                return None
            
            # Process markdown content
            processed = await self.result_processor.process_markdown(
                scrape_result['markdown'],
                task,
                url
            )
            
            # Create memory
            memory = await self.result_processor.create_memory(processed, task)
            
            # Generate embedding if LLM available
            if self.client:
                try:
                    memory.embedding = await self.client.generate_embedding(memory.content)
                except Exception as e:
                    logger.warning(f"Failed to generate embedding: {str(e)}")
            
            # Create finding
            finding = {
                'content': memory.content,
                'url': url,
                'source_type': processed['metadata']['source_type'],
                'reliability': processed.get('reliability', 0.5),
                'has_citations': processed['metadata']['has_citations'],
                'word_count': processed['metadata']['word_count'],
                'extracted_info': processed['extracted_info'],
                'timestamp': datetime.now().isoformat()
            }
            
            self._processed_urls[url] = finding
            return finding
            
        except Exception as e:
            logger.error(f"Failed to process URL {url}: {str(e)}")
            return None
    
    async def cleanup(self) -> None:
        """Clean up processor resources."""
        try:
            if self.firecrawl:
                await self.firecrawl.cleanup()
            self._processed_urls.clear()
            
        except Exception as e:
            logger.error(f"Cleanup failed: {str(e)}")
    
    def __str__(self) -> str:
        """Get string representation."""
        return (
            f"ContentProcessor("
            f"processed_urls={len(self._processed_urls)}, "
            f"has_llm={bool(self.client)})"
        )
