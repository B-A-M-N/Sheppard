"""
Enhanced content processor with research workflow integration.
File: src/research/content_processor.py
"""

import logging
import re
from typing import Dict, Any, List, Optional, Tuple, TYPE_CHECKING
from datetime import datetime

# Import model types directly
from src.research.models import ResearchTask, TaskStatus, SourceType
from src.research.exceptions import ProcessingError
from src.utils.text_processing import sanitize_text

# Use TYPE_CHECKING for circular imports
if TYPE_CHECKING:
    from src.memory.manager import MemoryManager
    from src.memory.models import Memory

logger = logging.getLogger(__name__)

class ContentProcessor:
    """Processes research content with Firecrawl and LLM integration."""
    
    def __init__(
        self,
        ollama_client=None,
        firecrawl_config=None,
        chunk_size: int = 1000,
        chunk_overlap: int = 100
    ):
        """Initialize content processor."""
        self.client = ollama_client
        self.firecrawl = None
        if firecrawl_config:
            from firecrawl import AsyncV1FirecrawlApp
            # Use api_url from config if available (base_url in our config)
            api_url = getattr(firecrawl_config, 'base_url', None)
            self.firecrawl = AsyncV1FirecrawlApp(
                api_key=firecrawl_config.api_key,
                api_url=api_url
            )
        
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        
        # Track processed content
        self._processed_urls: Dict[str, Dict[str, Any]] = {}
        self._initialized = False
        # Initialize patterns for content extraction
        self.patterns = {
            'citations': r'\[\d+\]|\[[A-Za-z]+\s+\d{4}\]',
            'dates': r'\b\d{4}-\d{2}-\d{2}\b|\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]* \d{1,2},? \d{4}\b',
            'metrics': r'\d+(?:\.\d+)?%|\d+(?:\.\d+)?\s*(?:million|billion|trillion)',
            'quotes': r'(?<!")(?<!\')"([^"]+)"(?!")|\'([^\']+)\'',
            'equations': r'\$[^$]+\$|\\\(.*?\\\)',
            'headers': r'^#{1,6}\s+.+$',
            'lists': r'^\s*[-*+]\s+.+$',
            'code_blocks': r'```[\s\S]*?```',
            'tables': r'\|.*\|.*\n\|[-\s|]+\|',
            'urls': r'https?://[^\s<>"]+|www\.[^\s<>"]+',
            'email': r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
        }
        
        # Content validation thresholds
        self.validation_thresholds = {
            'min_content_length': 50,
            'max_content_length': 100000,
            'min_quote_length': 10,
            'min_citation_count': 1,
            'max_url_count': 50
        }
    
    def set_firecrawl_client(self, firecrawl_client: Any) -> None:
        """Set the Firecrawl client instance."""
        self.firecrawl = firecrawl_client
        logger.info("Firecrawl client set in ContentProcessor")
    async def initialize(self) -> None:
        """Initialize processor components."""
        if self._initialized:
            return
        
        try:
            # Initialize Firecrawl only if it has the method
            if self.firecrawl and hasattr(self.firecrawl, "initialize"):
                await self.firecrawl.initialize()
            
            self._initialized = True
            logger.info("Content processor initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize content processor: {str(e)}")
            await self.cleanup()
            raise
    
    async def cleanup(self) -> None:
        """Clean up processor resources."""
        try:
            # Clean up Firecrawl only if it has the method
            if self.firecrawl and hasattr(self.firecrawl, "cleanup"):
                await self.firecrawl.cleanup()
            
            # Clear processed URLs
            self._processed_urls.clear()
            
            # Reset initialization flag
            self._initialized = False

            logger.info("Content processor cleanup completed")

        except Exception as e:
            logger.error(f"Error during cleanup: {str(e)}")
    async def process_content(
        self,
        content: str,
        task: Optional[ResearchTask] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Process content with extraction and analysis.
        """
        try:
            if not self._validate_content_length(content):
                raise ProcessingError("Content length outside allowed range")
            
            content = sanitize_text(content)
            extracted = await self._extract_patterns(content)
            structure_analysis = await self._analyze_structure(content)
            
            summary = None
            if self.client and task:
                try:
                    summary = await self._generate_summary(content, task.description)
                except Exception as e:
                    logger.warning(f"Failed to generate summary: {str(e)}")
            
            relevance_analysis = None
            if self.client and task:
                try:
                    relevance_analysis = await self._analyze_relevance(content, task.description)
                except Exception as e:
                    logger.warning(f"Failed to analyze relevance: {str(e)}")
            
            result = {
                'content': content,
                'extracted_patterns': extracted,
                'structure_analysis': structure_analysis,
                'summary': summary,
                'relevance_analysis': relevance_analysis,
                'metadata': {
                    'word_count': len(content.split()),
                    'char_count': len(content),
                    'has_citations': bool(extracted.get('citations')),
                    'has_metrics': bool(extracted.get('metrics')),
                    'readability_score': self._calculate_readability(content),
                    'processing_timestamp': datetime.now().isoformat(),
                    **(metadata or {})
                }
            }
            
            return result
            
        except Exception as e:
            logger.error(f"Content processing failed: {str(e)}")
            raise ProcessingError(f"Content processing failed: {str(e)}")
    async def _extract_patterns(self, content: str) -> Dict[str, List[str]]:
        """Extract patterns from content."""
        extracted = {}
        
        for pattern_name, pattern in self.patterns.items():
            matches = re.findall(pattern, content, re.MULTILINE)
            
            if pattern_name == 'quotes':
                cleaned = []
                for match in matches:
                    if isinstance(match, tuple):
                        quote = match[0] or match[1]
                    else:
                        quote = match
                    if quote and len(quote.strip()) >= self.validation_thresholds['min_quote_length']:
                        cleaned.append(quote.strip())
                matches = cleaned
            else:
                matches = [m.strip() for m in matches if m.strip()]
            
            if matches:
                extracted[pattern_name] = matches
        
        return extracted
    
    async def _analyze_structure(self, content: str) -> Dict[str, Any]:
        """Analyze content structure."""
        structure = {
            'paragraphs': len(re.split(r'\n\s*\n', content)),
            'sentences': len(re.split(r'[.!?]+', content)),
            'sections': {},
            'formatting': {
                'headers': False,
                'lists': False,
                'tables': False,
                'code_blocks': False
            },
            'hierarchy_score': 0.0
        }
        
        headers = re.findall(r'^(#{1,6})\s+(.+)$', content, re.MULTILINE)
        if headers:
            level_counts = {}
            current_level = 0
            valid_transitions = 0
            total_transitions = 0
            
            for header in headers:
                level = len(header[0])
                level_counts[level] = level_counts.get(level, 0) + 1
                
                if current_level == 0 or level <= current_level + 1:
                    valid_transitions += 1
                total_transitions += 1
                current_level = level
            
            structure['sections'] = {
                'total_headers': len(headers),
                'level_distribution': level_counts
            }
            
            if total_transitions > 0:
                structure['hierarchy_score'] = valid_transitions / total_transitions
        
        return structure
    async def _generate_summary(self, content: str, topic: str) -> Optional[str]:
        """Generate content summary using LLM."""
        if not self.client:
            return None
        
        try:
            prompt = f"""
            Generate a concise summary of the following content, focusing on information relevant to: {topic}
            
            Content:
            {content[:4000]}  # Limit content length
            
            Provide:
            1. Main points and key findings
            2. Relevant statistics or data
            3. Important conclusions
            
            Format as a clear, well-structured summary.
            """
            
            messages = [{"role": "user", "content": prompt}]
            summary_text = ""
            
            async for response in self.client.chat(
                messages=messages,
                stream=True,
                temperature=0.3  
            ):
                if response and response.content:
                    summary_text += response.content
            
            return summary_text.strip()
            
        except Exception as e:
            logger.warning(f"Failed to generate summary: {str(e)}")
            return None
    
    async def _analyze_relevance(
        self,
        content: str,
        topic: str
    ) -> Optional[Dict[str, Any]]:
        """Analyze content relevance to topic."""
        if not self.client:
            return None
        
        try:
            prompt = f"""
            Analyze the relevance of the following content to the topic: {topic}
            
            Content:
            {content[:4000]}
            
            Provide:
            1. Relevance score (0.0 to 1.0)
            2. Key relevant points
            3. Missing aspects
            
            Format as JSON.
            """
            
            messages = [{"role": "user", "content": prompt}]
            analysis_text = ""
            
            async for response in self.client.chat(
                messages=messages,
                stream=True,
                temperature=0.2
            ):
                if response and response.content:
                    analysis_text += response.content
            
            import json
            return json.loads(analysis_text)
            
        except Exception as e:
            logger.warning(f"Failed to analyze relevance: {str(e)}")
            return None
    async def process_research_content(
        self,
        urls: List[Dict[str, Any]],
        task: ResearchTask,
        progress_callback: Optional[callable] = None
    ) -> List[Dict[str, Any]]:
        """Process a batch of research URLs."""
        if not self._initialized:
            await self.initialize()

        try:
            findings = []
            total_urls = len(urls)
            
            task.update_status(TaskStatus.SCRAPING)
            
            for idx, url_data in enumerate(urls):
                try:
                    url = url_data['url']
                    
                    if url in self._processed_urls:
                        findings.append(self._processed_urls[url])
                        continue
                    
                    scrape_result_obj = await self.firecrawl.scrape_url(
                        url,
                        formats=['markdown']
                    )
                    
                    scrape_result = scrape_result_obj.model_dump()
                    
                    if not scrape_result.get('markdown'):
                        logger.warning(f"No markdown content for {url}")
                        continue
                    
                    processed = await self.process_content(
                        scrape_result['markdown'],
                        task=task,
                        metadata={'source_url': url}
                    )
                    
                    memory = await self._create_memory(processed, task)
                    
                    if self.client:
                        try:
                            memory.embedding = await self.client.generate_embedding(
                                memory.content,
                                model="mxbai-embed-large"
                            )
                        except Exception as e:
                            logger.warning(f"Failed to generate embedding: {str(e)}")
                    
                    finding = {
                        'content': memory.content,
                        'url': url,
                        'title': url_data.get('title', ''),
                        'source_type': self._determine_source_type(url, processed),
                        'reliability': self._calculate_reliability(url_data, processed),
                        'extracted_info': processed['extracted_patterns'],
                        'structure_info': processed['structure_analysis'],
                        'relevance': processed.get('relevance_analysis'),
                        'summary': processed.get('summary'),
                        'metadata': {
                            'word_count': processed['metadata']['word_count'],
                            'has_citations': processed['metadata']['has_citations'],
                            'readability_score': processed['metadata']['readability_score'],
                            'processing_timestamp': datetime.now().isoformat()
                        }
                    }
                    
                    findings.append(finding)
                    self._processed_urls[url] = finding
                    
                    if progress_callback:
                        progress_callback((idx + 1) / total_urls)
                    
                except Exception as e:
                    logger.error(f"Failed to process {url}: {str(e)}")
                    continue
            
            task.update_status(TaskStatus.ANALYZING)
            
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
            content_parts = []
            for finding in findings:
                content_parts.append(f"Source: {finding['url']}\n{finding['content']}")
            
            combined_content = "\n\n---\n\n".join(content_parts)
            
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
            
            messages = [{"role": "user", "content": prompt}]
            analysis_text = ""
            
            async for response in self.client.chat(
                messages=messages,
                stream=True,
                temperature=0.3
            ):
                if response and response.content:
                    analysis_text += response.content
            
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
                if current_content:
                    sections[current_section] = '\n'.join(current_content).strip()
                current_section = line.strip()
                current_content = []
            else:
                current_content.append(line)
        
        if current_content:
            sections[current_section] = '\n'.join(current_content).strip()
        
        return sections
    async def _create_memory(
        self,
        processed_content: Dict[str, Any],
        task: ResearchTask
    ) -> 'Memory':
        """Create memory from processed content."""
        # Import Memory at runtime to avoid circular imports
        from src.memory.models import Memory
        
        content_parts = []
        
        if processed_content.get('summary'):
            content_parts.append(f"Summary:\n{processed_content['summary']}")
        
        extracted = processed_content.get('extracted_patterns', {})
        if extracted:
            if extracted.get('metrics'):
                content_parts.append("\nKey Metrics:")
                content_parts.extend(f"- {stat}" for stat in extracted['metrics'])
            
            if extracted.get('quotes'):
                content_parts.append("\nRelevant Quotes:")
                content_parts.extend(f"- {quote}" for quote in extracted['quotes'][:3])
        
        # Ensure all content parts are strings
        string_content_parts = []
        for part in content_parts:
            if isinstance(part, list):
                string_content_parts.append("\n".join(str(item) for item in part))
            else:
                string_content_parts.append(str(part))
        memory = Memory(
            content="\n\n".join(string_content_parts),
            metadata={
                'type': 'research_finding',
                'task_id': task.id,
                'source_url': processed_content['metadata'].get('source_url'),
                'word_count': processed_content['metadata']['word_count'],
                'has_citations': processed_content['metadata']['has_citations'],
                'readability_score': processed_content['metadata']['readability_score'],
                'timestamp': datetime.now().isoformat()
            }
        )
        
        return memory
    def _validate_content_length(self, content: str) -> bool:
        """Validate content length."""
        length = len(content)
        return (length >= self.validation_thresholds['min_content_length'] and 
                length <= self.validation_thresholds['max_content_length'])
    
    def _calculate_readability(self, content: str) -> float:
        """Calculate simple readability score."""
        try:
            sentences = re.split(r'[.!?]+', content)
            words = content.split()
            
            if not sentences or not words:
                return 0.0
            
            avg_sentence_length = len(words) / len(sentences)
            avg_word_length = sum(len(word) for word in words) / len(words)
            
            score = 1.0 - (min(max((avg_sentence_length - 10) / 20, 0), 1) * 0.5 +
                          min(max((avg_word_length - 4) / 4, 0), 1) * 0.5)
            
            return round(score, 2)
            
        except Exception:
            return 0.0
    def _determine_source_type(
        self,
        url: str,
        processed_content: Dict[str, Any]
    ) -> str:
        """Determine source type from URL and content."""
        url_lower = url.lower()
        
        if any(edu in url_lower for edu in ['.edu', 'university.', 'academic.']):
            return SourceType.SCHOLARLY.value
        elif '.gov' in url_lower:
            return SourceType.GOVERNMENT.value
        elif any(sci in url_lower for sci in ['science.', 'research.', 'arxiv.', 'nature.']):
            return SourceType.SCIENTIFIC.value
        
        extracted = processed_content.get('extracted_patterns', {})
        structure = processed_content.get('structure_analysis', {})
        
        if (len(extracted.get('citations', [])) >= 3 and
            len(extracted.get('equations', [])) >= 1):
            return SourceType.SCIENTIFIC.value
        
        if (len(extracted.get('code_blocks', [])) >= 2 or
            structure.get('formatting', {}).get('code_blocks', False)):
            return SourceType.TECHNICAL.value
        
        if (any('news.' in url_lower for url in extracted.get('urls', [])) or
            len(extracted.get('dates', [])) >= 3):
            return SourceType.NEWS.value
        
        return SourceType.WEBPAGE.value
    
    def _calculate_reliability(
        self,
        url_data: Dict[str, Any],
        processed_content: Dict[str, Any]
    ) -> float:
        """Calculate source reliability score."""
        base_score = url_data.get('reliability', 0.5)
        
        adjustments = []
        
        citations = len(processed_content.get('extracted_patterns', {}).get('citations', []))
        if citations >= 5:
            adjustments.append(0.2)
        elif citations >= 2:
            adjustments.append(0.1)
        
        structure = processed_content.get('structure_analysis', {})
        if structure.get('hierarchy_score', 0) >= 0.8:
            adjustments.append(0.1)
        
        metrics = len(processed_content.get('extracted_patterns', {}).get('metrics', []))
        if metrics >= 3:
            adjustments.append(0.1)
        
        final_score = base_score + sum(adjustments)
        return round(min(1.0, max(0.0, final_score)), 2)
    
    def __str__(self) -> str:
        """Get string representation."""
        return (
            f"ContentProcessor("
            f"processed_urls={len(self._processed_urls)}, "
            f"has_llm={bool(self.client)}, "
            f"initialized={self._initialized})"
        )
