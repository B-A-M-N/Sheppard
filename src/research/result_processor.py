"""
Research result processor for handling Firecrawl output.
File: src/research/result_processor.py
"""

import logging
import re
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime

from src.research.models import ResearchTask, SourceType
from src.research.exceptions import ProcessingError
from src.memory.models import Memory

logger = logging.getLogger(__name__)

class ResearchResultProcessor:
    """Processes research results from Firecrawl and prepares them for storage."""
    
    def __init__(self, ollama_client=None):
        """Initialize processor with optional LLM client."""
        self.client = ollama_client
        
        # Section identification patterns
        self.section_patterns = {
            'abstract': r'(?i)abstract|summary|overview',
            'introduction': r'(?i)introduction|background|context',
            'methodology': r'(?i)method|methodology|approach',
            'results': r'(?i)results|findings|data',
            'discussion': r'(?i)discussion|analysis|interpretation',
            'conclusion': r'(?i)conclusion|summary|final'
        }
        
        # Content extraction patterns
        self.extraction_patterns = {
            'citations': r'\[\d+\]|\[[A-Za-z]+\s+\d{4}\]',
            'quotes': r'(?<!")(?<!\')"([^"]+)"(?!")|\'([^\']+)\'',
            'statistics': r'\d+(?:\.\d+)?%|\d+(?:\.\d+)?\s*(?:million|billion|trillion)',
            'dates': r'\b(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+\d{1,2},?\s+\d{4}\b|\d{4}-\d{2}-\d{2}',
            'urls': r'https?://\S+'
        }
    
    async def process_markdown(
        self,
        content: str,
        task: ResearchTask,
        source_url: str
    ) -> Dict[str, Any]:
        """
        Process markdown content from Firecrawl.
        
        Args:
            content: Markdown content to process
            task: Associated research task
            source_url: Source URL of content
            
        Returns:
            Dict[str, Any]: Processed content and metadata
        """
        try:
            # Split content into sections
            sections = await self._split_into_sections(content)
            
            # Extract key information
            extracted = await self._extract_key_information(content)
            
            # Get content summary if LLM available
            summary = None
            if self.client:
                summary = await self._generate_summary(content, task.description)
            
            # Process extracted information
            processed = {
                'source_url': source_url,
                'sections': sections,
                'extracted_info': extracted,
                'summary': summary,
                'metadata': {
                    'timestamp': datetime.now().isoformat(),
                    'word_count': len(content.split()),
                    'has_citations': bool(extracted.get('citations')),
                    'source_type': self._determine_source_type(source_url, content)
                }
            }
            
            return processed
            
        except Exception as e:
            logger.error(f"Failed to process markdown from {source_url}: {str(e)}")
            raise ProcessingError(f"Markdown processing failed: {str(e)}")
    
    async def _split_into_sections(self, content: str) -> Dict[str, str]:
        """Split markdown content into logical sections."""
        sections = {}
        
        # Split by headers
        current_section = 'main'
        current_content = []
        
        for line in content.split('\n'):
            # Check if line is a header
            if line.startswith('#'):
                # Store previous section
                if current_content:
                    sections[current_section] = '\n'.join(current_content).strip()
                    current_content = []
                
                # Determine new section type
                header_text = line.lstrip('#').strip().lower()
                section_found = False
                
                for section_type, pattern in self.section_patterns.items():
                    if re.search(pattern, header_text):
                        current_section = section_type
                        section_found = True
                        break
                
                if not section_found:
                    current_section = header_text
                
            else:
                current_content.append(line)
        
        # Store final section
        if current_content:
            sections[current_section] = '\n'.join(current_content).strip()
        
        return sections
    
    async def _extract_key_information(self, content: str) -> Dict[str, List[str]]:
        """Extract key information using patterns."""
        extracted = {}
        
        for info_type, pattern in self.extraction_patterns.items():
            matches = re.findall(pattern, content)
            
            # Clean matches
            if info_type == 'quotes':
                # Handle both single and double quote matches
                cleaned = []
                for match in matches:
                    if isinstance(match, tuple):
                        quote = match[0] or match[1]  # Take whichever quote was matched
                    else:
                        quote = match
                    if quote and len(quote.strip()) > 10:  # Minimum quote length
                        cleaned.append(quote.strip())
                matches = cleaned
            else:
                matches = [m.strip() for m in matches if m.strip()]
            
            extracted[info_type] = matches
        
        return extracted
    
    async def _generate_summary(self, content: str, topic: str) -> Optional[str]:
        """Generate content summary using LLM."""
        if not self.client:
            return None
            
        try:
            # Create summary prompt
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
            
            # Get summary from LLM
            messages = [{"role": "user", "content": prompt}]
            summary_text = ""
            
            async for response in self.client.chat(
                messages=messages,
                stream=True,
                temperature=0.3  # Lower temperature for more focused summary
            ):
                if response and response.content:
                    summary_text += response.content
            
            return summary_text.strip()
            
        except Exception as e:
            logger.warning(f"Failed to generate summary: {str(e)}")
            return None
    
    def _determine_source_type(self, url: str, content: str) -> str:
        """Determine source type from URL and content."""
        # First check URL
        url_lower = url.lower()
        
        if any(edu in url_lower for edu in ['.edu', 'university.', 'academic.']):
            return SourceType.SCHOLARLY.value
        elif '.gov' in url_lower:
            return SourceType.GOVERNMENT.value
        elif any(sci in url_lower for sci in ['science.', 'research.', 'arxiv.', 'nature.']):
            return SourceType.SCIENTIFIC.value
        
        # Check content characteristics
        content_lower = content.lower()
        
        # Check for academic/scientific indicators
        academic_indicators = [
            r'\b(?:study|research|experiment)\b',
            r'\b(?:methodology|hypothesis|conclusion)\b',
            r'\b(?:data|analysis|results)\b',
            r'\bcite[ds]?\b',
            r'\breferences?\b'
        ]
        
        academic_count = sum(
            1 for pattern in academic_indicators
            if re.search(pattern, content_lower)
        )
        
        if academic_count >= 3:
            return SourceType.SCHOLARLY.value
        
        # Check for technical content
        technical_indicators = [
            r'\b(?:code|algorithm|implementation)\b',
            r'\b(?:function|method|api)\b',
            r'\b(?:documentation|tutorial|guide)\b',
            r'```[a-z]*\n'  # Code blocks
        ]
        
        technical_count = sum(
            1 for pattern in technical_indicators
            if re.search(pattern, content_lower)
        )
        
        if technical_count >= 2:
            return SourceType.TECHNICAL.value
        
        # Check for news content
        news_indicators = [
            r'\b(?:reported|announced|stated)\b',
            r'\b(?:today|yesterday|this week)\b',
            r'\b(?:according to|sources say)\b'
        ]
        
        news_count = sum(
            1 for pattern in news_indicators
            if re.search(pattern, content_lower)
        )
        
        if news_count >= 2:
            return SourceType.NEWS.value
        
        return SourceType.WEBPAGE.value
    
    async def create_memory(
        self,
        processed_content: Dict[str, Any],
        task: ResearchTask
    ) -> Memory:
        """Create memory from processed content."""
        # Prepare memory content
        content_parts = []
        
        if processed_content.get('summary'):
            content_parts.append(f"Summary:\n{processed_content['summary']}")
        
        # Add key information
        extracted = processed_content.get('extracted_info', {})
        if extracted:
            if extracted.get('statistics'):
                content_parts.append("\nKey Statistics:")
                content_parts.extend(f"- {stat}" for stat in extracted['statistics'])
            
            if extracted.get('quotes'):
                content_parts.append("\nRelevant Quotes:")
                content_parts.extend(f"- {quote}" for quote in extracted['quotes'][:3])
        
        # Create memory
        memory = Memory(
            content="\n\n".join(content_parts),
            metadata={
                'type': 'research_result',
                'task_id': task.id,
                'source_url': processed_content['source_url'],
                'source_type': processed_content['metadata']['source_type'],
                'has_citations': processed_content['metadata']['has_citations'],
                'word_count': processed_content['metadata']['word_count'],
                'timestamp': datetime.now().isoformat()
            }
        )
        
        return memory
    
    def __str__(self) -> str:
        """Get string representation."""
        return f"ResearchResultProcessor(has_llm={bool(self.client)})"
