"""
Enhanced validation models for research content with markdown support.
File: src/research/model_validation.py
"""

from enum import Enum, auto
from typing import Dict, Any, List, Optional, Tuple, Set
from datetime import datetime
import re
from urllib.parse import urlparse

class ValidationLevel(Enum):
    """Validation strictness levels."""
    STRICT = auto()
    NORMAL = auto()
    LENIENT = auto()

class SourceValidator:
    """Validates research sources and their content."""
    
    def __init__(self):
        """Initialize source validator."""
        # Domain reliability patterns
        self.reliable_domains = {
            r'\.edu$': 0.9,  # Educational institutions
            r'\.gov$': 0.9,  # Government sites
            r'\.org$': 0.8,  # Non-profit organizations
            r'\.mil$': 0.9,  # Military sites
            r'wikipedia\.org$': 0.8,  # Wikipedia
            r'arxiv\.org$': 0.9,  # arXiv
            r'github\.com$': 0.8,  # GitHub
            r'science\.(org|com)$': 0.85,  # Science publications
            r'nature\.com$': 0.9,  # Nature
            r'scholar\.google\.com$': 0.9  # Google Scholar
        }
        
        # Content quality indicators
        self.quality_indicators = {
            'references': r'\[\d+\]|\[(?:[A-Za-z]+\s*(?:et al\.)?,\s*\d{4})\]',
            'citations': r'\((?:[A-Za-z]+\s*(?:et al\.)?,\s*\d{4})\)',
            'data_points': r'\d+(?:\.\d+)?%|\d+(?:\.\d+)?\s*(?:million|billion|trillion)',
            'academic_terms': r'study|research|analysis|methodology|hypothesis|conclusion',
            'technical_terms': r'algorithm|implementation|framework|architecture|protocol'
        }
        
        # Markdown structure validation
        self.markdown_patterns = {
            'headers': r'^#{1,6}\s+.+$',
            'lists': r'^\s*[-*+]\s+.+$',
            'code_blocks': r'```[\s\S]*?```',
            'tables': r'\|.*\|.*\n\|[-\s|]+\|',
            'blockquotes': r'^\s*>\s+.+'
        }
        
        # URL validation patterns
        self.url_pattern = re.compile(
            r'^https?://'  # http:// or https://
            r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|'  # domain...
            r'localhost|'  # localhost...
            r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'  # ...or ip
            r'(?::\d+)?'  # optional port
            r'(?:/?|[/?]\S+)$', re.IGNORECASE
        )
    
    async def validate_content(
        self,
        content: str,
        source_url: str,
        validation_level: ValidationLevel = ValidationLevel.NORMAL
    ) -> Tuple[bool, Optional[str], Dict[str, Any]]:
        """
        Validate research content with markdown support.
        
        Args:
            content: Content to validate
            source_url: Source URL of content
            validation_level: Validation strictness level
            
        Returns:
            Tuple[bool, Optional[str], Dict[str, Any]]: 
                (is_valid, error_message, validation_results)
        """
        validation_results = {
            'url_reliability': self._calculate_url_reliability(source_url),
            'content_quality': self._assess_content_quality(content),
            'markdown_quality': self._validate_markdown_structure(content),
            'indicators_found': self._find_quality_indicators(content),
            'timestamp': datetime.now().isoformat()
        }
        
        # Calculate overall score based on validation level
        score = self._calculate_validation_score(validation_results, validation_level)
        validation_results['score'] = score
        
        # Determine validity based on validation level
        if validation_level == ValidationLevel.STRICT:
            is_valid = score >= 0.8
        elif validation_level == ValidationLevel.NORMAL:
            is_valid = score >= 0.6
        else:  # LENIENT
            is_valid = score >= 0.4
        
        error_message = None if is_valid else f"Content validation failed (score: {score:.2f})"
        return is_valid, error_message, validation_results
    
    def _calculate_url_reliability(self, url: str) -> float:
        """Calculate URL reliability score."""
        try:
            domain = urlparse(url).netloc.lower()
            
            # Check domain patterns
            for pattern, score in self.reliable_domains.items():
                if re.search(pattern, domain):
                    return score
            
            # Default score for unknown domains
            return 0.5
            
        except Exception:
            return 0.3  # Lower score for unparseable URLs
    
    def _assess_content_quality(self, content: str) -> Dict[str, float]:
        """Assess various aspects of content quality."""
        assessment = {
            'length_score': min(len(content) / 1000, 1.0),
            'structure_score': 0.0,
            'readability_score': 0.0,
            'information_density': 0.0
        }
        
        # Assess structure (paragraphs, sections)
        paragraphs = content.split('\n\n')
        assessment['structure_score'] = min(len(paragraphs) / 10, 1.0)
        
        # Assess readability (simple approximation)
        words = content.split()
        if words:
            avg_word_length = sum(len(word) for word in words) / len(words)
            assessment['readability_score'] = 1.0 - min(max(avg_word_length - 4, 0) / 8, 1.0)
        
        # Assess information density
        info_patterns = {
            'numbers': r'\d+(?:\.\d+)?',
            'dates': r'\d{4}-\d{2}-\d{2}',
            'percentages': r'\d+(?:\.\d+)?%',
            'measurements': r'\d+(?:\.\d+)?\s*(?:kg|km|m|ft|mi|lb)'
        }
        
        total_matches = 0
        for pattern in info_patterns.values():
            total_matches += len(re.findall(pattern, content))
        
        assessment['information_density'] = min(total_matches / (len(words) / 100), 1.0)
        
        return assessment
    
    def _validate_markdown_structure(self, content: str) -> Dict[str, Any]:
        """Validate markdown document structure."""
        structure = {
            'has_headers': False,
            'has_lists': False,
            'has_code_blocks': False,
            'has_tables': False,
            'has_quotes': False,
            'hierarchy_score': 0.0
        }
        
        # Check for markdown elements
        for element, pattern in self.markdown_patterns.items():
            matches = re.findall(pattern, content, re.MULTILINE)
            structure[f'has_{element}'] = bool(matches)
        
        # Analyze header hierarchy
        headers = re.findall(r'^(#{1,6})\s+(.+)$', content, re.MULTILINE)
        if headers:
            # Check if headers follow proper hierarchy
            current_level = 0
            valid_transitions = 0
            total_transitions = 0
            
            for header in headers:
                level = len(header[0])
                if current_level == 0 or level <= current_level + 1:
                    valid_transitions += 1
                total_transitions += 1
                current_level = level
            
            structure['hierarchy_score'] = valid_transitions / total_transitions if total_transitions else 0.0
        
        return structure
    
    def _find_quality_indicators(self, content: str) -> Dict[str, int]:
        """Find quality indicators in content."""
        indicators = {}
        for name, pattern in self.quality_indicators.items():
            matches = re.findall(pattern, content, re.IGNORECASE)
            indicators[name] = len(matches)
        return indicators
    
    def _calculate_validation_score(
        self,
        results: Dict[str, Any],
        validation_level: ValidationLevel
    ) -> float:
        """Calculate overall validation score."""
        weights = {
            ValidationLevel.STRICT: {
                'url_reliability': 0.3,
                'content_quality': 0.3,
                'markdown_quality': 0.2,
                'indicators': 0.2
            },
            ValidationLevel.NORMAL: {
                'url_reliability': 0.25,
                'content_quality': 0.35,
                'markdown_quality': 0.15,
                'indicators': 0.25
            },
            ValidationLevel.LENIENT: {
                'url_reliability': 0.2,
                'content_quality': 0.4,
                'markdown_quality': 0.1,
                'indicators': 0.3
            }
        }
        
        weight = weights[validation_level]
        
        # Calculate weighted scores
        url_score = results['url_reliability'] * weight['url_reliability']
        
        # Content quality score
        quality_scores = results['content_quality']
        content_score = sum(quality_scores.values()) / len(quality_scores) * weight['content_quality']
        
        # Markdown structure score
        markdown_results = results['markdown_quality']
        markdown_score = (
            sum(1 for v in markdown_results.values() if v is True) / 
            len(markdown_results) * 
            weight['markdown_quality']
        )
        
        # Indicators score
        indicators = results['indicators_found']
        max_indicators = max(sum(indicators.values()), 1)
        indicators_score = min(sum(indicators.values()) / max_indicators, 1.0) * weight['indicators']
        
        return round(url_score + content_score + markdown_score + indicators_score, 2)

class ContentValidator:
    """Validates research content."""
    
    def __init__(self):
        """Initialize content validator."""
        self.min_content_length = 50  # Minimum meaningful content length
        self.max_content_length = 100000  # Maximum content length
        
        # Markdown patterns for content checking
        self.markdown_elements = {
            'headers': r'^#{1,6}\s.+$',
            'lists': r'^\s*[-*+]\s.+$',
            'tables': r'\|.+\|',
            'code_blocks': r'```[\s\S]*?```',
            'blockquotes': r'^\s*>.+$',
            'links': r'\[([^\]]+)\]\(([^)]+)\)',
            'images': r'!\[([^\]]*)\]\(([^)]+)\)',
            'emphasis': r'[*_]{1,2}[^*_]+[*_]{1,2}'
        }
        
        # Content quality indicators
        self.quality_indicators = {
            'citations': r'\[\d+\]|\[[A-Za-z]+\s+\d{4}\]',
            'quotes': r'(?<!")(?<!\')"([^"]+)"(?!")|\'([^\']+)\'',
            'statistics': r'\d+(?:\.\d+)?%|\d+(?:\.\d+)?\s*(?:million|billion|trillion)',
            'dates': r'\b(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+\d{1,2},?\s+\d{4}\b|\d{4}-\d{2}-\d{2}',
            'urls': r'https?://\S+'
        }
    
    async def validate_content(
        self,
        content: str,
        validation_level: ValidationLevel = ValidationLevel.NORMAL,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Tuple[bool, Optional[str], Dict[str, Any]]:
        """
        Validate research content.
        
        Args:
            content: Content to validate
            validation_level: Level of validation to apply
            metadata: Optional metadata about the content
            
        Returns:
            Tuple[bool, Optional[str], Dict[str, Any]]: 
                (is_valid, error_message, validation_results)
        """
        try:
            validation_results = {
                'length': len(content),
                'markdown_elements': {},
                'indicators_found': {},
                'score': 0.0,
                'validation_level': validation_level.value
            }
            
            # Check length
            if len(content) < self.min_content_length:
                return False, "Content too short", validation_results
            if len(content) > self.max_content_length:
                return False, "Content too long", validation_results
            
            # Check for empty or whitespace content
            if not content.strip():
                return False, "Empty content", validation_results
            
            # Check markdown elements
            for element, pattern in self.markdown_elements.items():
                matches = re.findall(pattern, content, re.MULTILINE)
                validation_results['markdown_elements'][element] = len(matches)
            
            # Check quality indicators
            for indicator, pattern in self.quality_indicators.items():
                matches = re.findall(pattern, content)
                validation_results['indicators_found'][indicator] = len(matches)
            
            # Calculate quality score
            quality_score = self._calculate_quality_score(
                content,
                validation_results['markdown_elements'],
                validation_results['indicators_found']
            )
            validation_results['score'] = quality_score
            
            # Validate based on level
            if validation_level == ValidationLevel.STRICT:
                is_valid = quality_score >= 0.8
            elif validation_level == ValidationLevel.NORMAL:
                is_valid = quality_score >= 0.6
            else:  # LENIENT
                is_valid = quality_score >= 0.4
            
            error_message = None if is_valid else f"Content quality below threshold ({quality_score:.2f})"
            return is_valid, error_message, validation_results
            
        except Exception as e:
            return False, str(e), {}

    def _calculate_quality_score(
        self,
        content: str,
        markdown_elements: Dict[str, int],
        indicators: Dict[str, int]
    ) -> float:
        """Calculate content quality score."""
        score = 0.0
        
        # Length score (0.0 - 0.2)
        length_score = min(len(content) / 1000, 1.0) * 0.2
        score += length_score
        
        # Markdown structure score (0.0 - 0.3)
        if markdown_elements:
            # Headers score
            if markdown_elements.get('headers', 0) > 0:
                score += 0.1
            
            # Lists and tables score
            if markdown_elements.get('lists', 0) > 0 or markdown_elements.get('tables', 0) > 0:
                score += 0.1
            
            # Code blocks and formatting score
            if (markdown_elements.get('code_blocks', 0) > 0 or 
                markdown_elements.get('emphasis', 0) > 0):
                score += 0.1
        
        # Content indicators score (0.0 - 0.5)
        if indicators:
            # Citations and references (0.0 - 0.2)
            citations_count = indicators.get('citations', 0)
            if citations_count > 0:
                score += min(citations_count / 5, 1.0) * 0.2
            
            # Statistics and data (0.0 - 0.2)
            stats_count = indicators.get('statistics', 0)
            if stats_count > 0:
                score += min(stats_count / 3, 1.0) * 0.2
            
            # URLs and external references (0.0 - 0.1)
            urls_count = indicators.get('urls', 0)
            if urls_count > 0:
                score += min(urls_count / 2, 1.0) * 0.1
        
        return round(min(1.0, score), 2)

class MarkdownValidator:
    """Validates markdown structure and formatting."""
    
    def __init__(self):
        """Initialize markdown validator."""
        # Header patterns
        self.header_patterns = {
            'atx': r'^#{1,6}\s+.+$',  # ATX-style headers
            'setext': r'^.+\n[=\-]+$'  # Setext-style headers
        }
        
        # List patterns
        self.list_patterns = {
            'unordered': r'^\s*[-*+]\s+.+$',  # Unordered lists
            'ordered': r'^\s*\d+\.\s+.+$',     # Ordered lists
            'task': r'^\s*[-*+]\s+\[[ x]\]\s+.+$'  # Task lists
        }
        
        # Table patterns
        self.table_patterns = {
            'header': r'^\|.+\|$',  # Table header
            'separator': r'^\|[-:\s|]+\|$',  # Table separator
            'row': r'^\|.+\|$'  # Table row
        }
        
        # Code block patterns
        self.code_patterns = {
            'fenced': r'```[a-z]*\n[\s\S]*?```',  # Fenced code blocks
            'indented': r'(?:^(?: {4}|\t).+\n?)+'  # Indented code blocks
        }
        
        # Link patterns
        self.link_patterns = {
            'inline': r'\[([^\]]+)\]\(([^)]+)\)',  # Inline links
            'reference': r'\[([^\]]+)\]\[([^\]]+)\]',  # Reference links
            'definition': r'^\[([^\]]+)\]:\s+(\S+)(?:\s+"([^"]+)")?\s*$'  # Link definitions
        }
    
    async def validate_markdown(
        self,
        content: str,
        validation_level: ValidationLevel = ValidationLevel.NORMAL
    ) -> Tuple[bool, Optional[str], Dict[str, Any]]:
        """
        Validate markdown content structure.
        
        Args:
            content: Markdown content to validate
            validation_level: Level of validation to apply
            
        Returns:
            Tuple[bool, Optional[str], Dict[str, Any]]:
                (is_valid, error_message, validation_results)
        """
        validation_results = {
            'structure': await self._validate_structure(content),
            'formatting': await self._validate_formatting(content),
            'links': await self._validate_links(content),
            'hierarchy': await self._validate_hierarchy(content),
            'timestamp': datetime.now().isoformat()
        }
        
        # Calculate overall score
        score = self._calculate_markdown_score(validation_results, validation_level)
        validation_results['score'] = score
        
        # Determine validity based on level
        if validation_level == ValidationLevel.STRICT:
            is_valid = (
                score >= 0.8 and
                validation_results['structure']['valid'] and
                validation_results['hierarchy']['valid']
            )
        elif validation_level == ValidationLevel.NORMAL:
            is_valid = (
                score >= 0.6 and
                validation_results['structure']['valid']
            )
        else:  # LENIENT
            is_valid = score >= 0.4
        
        error_message = None if is_valid else "Markdown validation failed"
        return is_valid, error_message, validation_results
    
    async def _validate_structure(self, content: str) -> Dict[str, Any]:
        """Validate basic markdown structure."""
        results = {
            'valid': True,
            'headers': [],
            'lists': [],
            'tables': [],
            'code_blocks': [],
            'errors': []
        }
        
        # Validate headers
        for style, pattern in self.header_patterns.items():
            headers = re.findall(pattern, content, re.MULTILINE)
            results['headers'].extend(headers)
        
        if not results['headers']:
            results['valid'] = False
            results['errors'].append("No headers found")
        
        # Validate lists
        for style, pattern in self.list_patterns.items():
            lists = re.findall(pattern, content, re.MULTILINE)
            results['lists'].extend(lists)
        
        # Validate tables
        table_lines = []
        current_table = []
        for line in content.split('\n'):
            if any(re.match(pattern, line) for pattern in self.table_patterns.values()):
                current_table.append(line)
            elif current_table:
                if len(current_table) >= 3:  # Valid table needs header, separator, and data
                    table_lines.extend(current_table)
                current_table = []
        results['tables'] = table_lines
        
        # Validate code blocks
        for style, pattern in self.code_patterns.items():
            code_blocks = re.findall(pattern, content, re.DOTALL)
            results['code_blocks'].extend(code_blocks)
        
        return results
    
    async def _validate_formatting(self, content: str) -> Dict[str, Any]:
        """Validate markdown formatting."""
        results = {
            'emphasis': [],
            'strong': [],
            'inline_code': [],
            'blockquotes': [],
            'horizontal_rules': []
        }
        
        # Find emphasis (*italic* or _italic_)
        results['emphasis'] = re.findall(r'[*_](?!\s)([^*_]+)(?!\s)[*_]', content)
        
        # Find strong (**bold** or __bold__)
        results['strong'] = re.findall(r'[*_]{2}(?!\s)([^*_]+)(?!\s)[*_]{2}', content)
        
        # Find inline code (`code`)
        results['inline_code'] = re.findall(r'`([^`]+)`', content)
        
        # Find blockquotes
        results['blockquotes'] = re.findall(r'^\s*>[ ].+$', content, re.MULTILINE)
        
        # Find horizontal rules
        results['horizontal_rules'] = re.findall(r'^\s*[-*_]{3,}\s*$', content, re.MULTILINE)
        
        return results
    
    async def _validate_links(self, content: str) -> Dict[str, Any]:
        """Validate markdown links."""
        results = {
            'valid': True,
            'inline_links': [],
            'reference_links': [],
            'link_definitions': {},
            'errors': []
        }
        
        # Find inline links
        inline_links = re.findall(self.link_patterns['inline'], content)
        results['inline_links'] = [
            {'text': text, 'url': url}
            for text, url in inline_links
        ]
        
        # Find reference links
        reference_links = re.findall(self.link_patterns['reference'], content)
        results['reference_links'] = [
            {'text': text, 'ref': ref}
            for text, ref in reference_links
        ]
        
        # Find link definitions
        definitions = re.findall(self.link_patterns['definition'], content, re.MULTILINE)
        for ref, url, title in definitions:
            results['link_definitions'][ref] = {
                'url': url,
                'title': title if title else None
            }
        
        # Validate reference links
        for link in results['reference_links']:
            if link['ref'] not in results['link_definitions']:
                results['valid'] = False
                results['errors'].append(f"Missing definition for reference: {link['ref']}")
        
        return results
    
    async def _validate_hierarchy(self, content: str) -> Dict[str, Any]:
        """Validate markdown heading hierarchy."""
        results = {
            'valid': True,
            'levels': [],
            'errors': []
        }
        
        current_level = 0
        for line in content.split('\n'):
            # Check ATX headers
            if line.startswith('#'):
                level = len(re.match(r'^#+', line).group())
                
                # Headers should only increment by one level
                if level > current_level + 1 and current_level > 0:
                    results['valid'] = False
                    results['errors'].append(
                        f"Invalid header level increment: {current_level} to {level}"
                    )
                
                current_level = level
                results['levels'].append(level)
        
        # Should start with h1
        if results['levels'] and results['levels'][0] != 1:
            results['valid'] = False
            results['errors'].append("Document should start with h1")
        
        return results
    
    def _calculate_markdown_score(
        self,
        results: Dict[str, Any],
        validation_level: ValidationLevel
    ) -> float:
        """Calculate overall markdown quality score."""
        score = 0.0
        
        # Structure score (0.0 - 0.4)
        structure = results['structure']
        if structure['headers']:
            score += 0.1
        if structure['lists']:
            score += 0.1
        if structure['tables']:
            score += 0.1
        if structure['code_blocks']:
            score += 0.1
        
        # Formatting score (0.0 - 0.2)
        formatting = results['formatting']
        format_elements = sum(
            1 for elements in formatting.values()
            if elements
        )
        score += (format_elements / len(formatting)) * 0.2
        
        # Links score (0.0 - 0.2)
        links = results['links']
        if links['valid']:
            link_count = len(links['inline_links']) + len(links['reference_links'])
            score += min(link_count / 5, 1.0) * 0.2
        
        # Hierarchy score (0.0 - 0.2)
        if results['hierarchy']['valid']:
            score += 0.2
        
        return round(min(1.0, score), 2)

# Initialize validators
source_validator = SourceValidator()
content_validator = ContentValidator()
markdown_validator = MarkdownValidator()
