"""
Text processing and extraction utilities.
File: src/research/extractors.py
"""

import re
import logging
import json
from typing import Dict, Any, List, Optional, Union, Tuple
from datetime import datetime
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

class ContentExtractor:
    """Base extractor for content types."""
    
    def __init__(self):
        """Initialize content extractor."""
        # Initialize extraction patterns
        self.extraction_patterns = {
            'url': r'https?://[^\s<>"]+|www\.[^\s<>"]+',
            'email': r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
            'date': r'\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{2,4}',
            'phone': r'\+?1?\d{9,15}|\(\d{3}\)\s*\d{3}[-\s]?\d{4}',
            'citation': r'\[[^\]]+\]|\([^)]+\)',
            'heading': r'^#+\s+.+$|^[A-Za-z0-9\s]+\n[=\-]{2,}$'
        }
        
        self.valid_content_types = {
            'text/html',
            'text/plain',
            'application/json',
            'text/markdown',
            'text/csv',
            'application/xml'
        }

    def _clean_content(self, content: str) -> str:
        """Clean and normalize content with improved handling."""
        if not content or not isinstance(content, str):
            return ""
            
        # Remove technical artifacts
        content = re.sub(
            r'fill-rule=".*?"|clip-rule=".*?"|<path.*?>|</path>|<g.*?>|</g>|'
            r'<defs>.*?</defs>|<clipPath.*?>.*?</clipPath>|<svg.*?>.*?</svg>',
            '',
            content,
            flags=re.DOTALL
        )
        
        # Remove HTML
        content = BeautifulSoup(content, 'html.parser').get_text()
        
        # Normalize whitespace
        content = ' '.join(content.split())
        
        return content.strip()

    async def extract(
        self,
        content: str,
        content_type: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Extract content based on type.
        
        Args:
            content: Raw content to extract from
            content_type: Optional content type hint
            metadata: Optional extraction metadata
            
        Returns:
            Dict[str, Any]: Extracted content and metadata
        """
        try:
            # Determine content type if not provided
            if not content_type:
                content_type = self._detect_content_type(content)
            
            # Validate content type
            if content_type not in self.valid_content_types:
                raise ValueError(f"Unsupported content type: {content_type}")
            
            # Extract based on type
            if content_type == 'text/html':
                extracted = await self._extract_html(content)
            elif content_type == 'application/json':
                extracted = await self._extract_json(content)
            elif content_type == 'text/csv':
                extracted = await self._extract_csv(content)
            elif content_type == 'application/xml':
                extracted = await self._extract_xml(content)
            else:
                extracted = await self._extract_text(content)
            
            # Add metadata
            if metadata:
                extracted['metadata'] = {
                    **extracted.get('metadata', {}),
                    **metadata
                }
            
            # Add extraction statistics
            extracted['extraction_stats'] = {
                'content_type': content_type,
                'original_length': len(content),
                'extracted_length': len(extracted.get('content', '')),
                'timestamp': datetime.now().isoformat()
            }
            
            return extracted
            
        except Exception as e:
            logger.error(f"Content extraction failed: {str(e)}")
            raise
    
    def _detect_content_type(self, content: str) -> str:
        """Detect content type from content."""
        content = content.strip()
        
        # Check for HTML
        if content.startswith('<!DOCTYPE html>') or re.search(r'<html\b', content):
            return 'text/html'
        
        # Check for JSON
        if content.startswith('{') or content.startswith('['):
            try:
                json.loads(content)
                return 'application/json'
            except json.JSONDecodeError:
                pass
        
        # Check for CSV
        if ',' in content and '\n' in content:
            return 'text/csv'
        
        # Check for XML
        if content.startswith('<?xml') or re.match(r'<\w+[^>]*>', content):
            return 'text/xml'
        
        # Check for Markdown
        if re.search(r'(?m)^#{1,6}\s', content) or '```' in content:
            return 'text/markdown'
        
        return 'text/plain'

    async def _extract_html(
        self,
        content: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Extract content from HTML."""
        try:
            soup = BeautifulSoup(content, 'html.parser')
            
            # Remove script and style elements
            for element in soup(['script', 'style', 'iframe', 'noscript']):
                element.decompose()
            
            # Extract metadata
            page_metadata = {
                'title': soup.title.string if soup.title else None,
                'meta_description': (
                    soup.find('meta', {'name': 'description'})['content']
                    if soup.find('meta', {'name': 'description'}) 
                    else None
                ),
                'links': [
                    {'text': a.get_text(strip=True), 'href': a.get('href')}
                    for a in soup.find_all('a', href=True)
                ],
                **(metadata or {})
            }
            
            # Get main content
            content_selectors = [
                'article', 'main', '[role="main"]',
                '.content', '#content', '.post-content',
                '.entry-content', '.article-content'
            ]
            
            main_content = None
            for selector in content_selectors:
                element = soup.select_one(selector)
                if element:
                    main_content = element.get_text(separator='\n', strip=True)
                    break
            
            if not main_content:
                main_content = soup.get_text(separator='\n', strip=True)
            
            return {
                'content': main_content,
                'metadata': page_metadata,
                'content_type': 'text/html'
            }
            
        except Exception as e:
            logger.error(f"HTML extraction failed: {str(e)}")
            raise

    async def _extract_text(
        self,
        content: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Extract text content."""
        try:
            # Extract patterns
            extracted_patterns = {}
            for pattern_name, pattern in self.extraction_patterns.items():
                matches = re.findall(pattern, content)
                if matches:
                    extracted_patterns[pattern_name] = matches
            
            return {
                'content': content,
                'patterns': extracted_patterns,
                'metadata': metadata or {},
                'content_type': 'text/plain'
            }
            
        except Exception as e:
            logger.error(f"Text extraction failed: {str(e)}")
            raise

    async def _extract_json(
        self,
        content: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Extract content from JSON."""
        try:
            # Parse JSON
            data = json.loads(content)
            
            # Extract text content recursively
            text_content = []
            
            def extract_text(obj):
                if isinstance(obj, str):
                    text_content.append(obj)
                elif isinstance(obj, list):
                    for item in obj:
                        extract_text(item)
                elif isinstance(obj, dict):
                    for value in obj.values():
                        extract_text(value)
            
            extract_text(data)
            
            return {
                'content': '\n'.join(text_content),
                'raw_data': data,
                'metadata': metadata or {},
                'content_type': 'application/json'
            }
            
        except Exception as e:
            logger.error(f"JSON extraction failed: {str(e)}")
            raise

    async def _extract_csv(
        self,
        content: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Extract content from CSV."""
        try:
            # Split into lines
            lines = [line.strip() for line in content.split('\n') if line.strip()]
            if not lines:
                raise ValueError("Empty CSV content")
            
            # Parse headers and data
            headers = [col.strip() for col in lines[0].split(',')]
            rows = []
            
            for line in lines[1:]:
                values = [val.strip() for val in line.split(',')]
                if len(values) == len(headers):
                    rows.append(dict(zip(headers, values)))
            
            return {
                'content': '\n'.join(str(row) for row in rows),
                'headers': headers,
                'rows': rows,
                'metadata': metadata or {},
                'content_type': 'text/csv'
            }
            
        except Exception as e:
            logger.error(f"CSV extraction failed: {str(e)}")
            raise

    async def _extract_xml(
        self,
        content: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Extract content from XML."""
        try:
            soup = BeautifulSoup(content, 'xml')
            
            # Extract text content
            text_content = soup.get_text(separator='\n', strip=True)
            
            # Get structure info
            structure = {
                'root_tag': soup.find().name,
                'child_tags': list(set(child.name for child in soup.find_all()))
            }
            
            return {
                'content': text_content,
                'structure': structure,
                'metadata': metadata or {},
                'content_type': 'application/xml'
            }
            
        except Exception as e:
            logger.error(f"XML extraction failed: {str(e)}")
            raise

class DataExtractor:
    """Extracts structured data from various content types."""
    
    def __init__(self):
        """Initialize data extractor."""
        # Common data patterns
        self.patterns = {
            'number': r'-?\d*\.?\d+',
            'date': r'\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{2,4}',
            'email': r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
            'url': r'https?://[^\s<>"]+|www\.[^\s<>"]+',
            'table_row': r'\|.*\|',
            'json_object': r'\{[^{}]*\}'
        }

    async def extract_data(
        self,
        content: Union[str, Dict[str, Any]],
        data_type: str = 'auto',
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Extract data from content based on type.
        
        Args:
            content: Content to extract from
            data_type: Type of data to extract ('auto', 'json', 'table', 'text')
            metadata: Optional extraction metadata
            
        Returns:
            Dict[str, Any]: Extracted data
        """
        try:
            # Auto-detect type if not specified
            if data_type == 'auto':
                data_type = self._detect_data_type(content)
            
            # Extract based on type
            if data_type == 'json':
                extracted = await self._extract_json(content)
            elif data_type == 'table':
                extracted = await self._extract_table(content)
            else:  # text
                extracted = await self._extract_text(content)
            
            # Add metadata
            if metadata:
                extracted['metadata'] = metadata
                
            return extracted
            
        except Exception as e:
            logger.error(f"Data extraction failed: {str(e)}")
            return {
                'error': str(e),
                'type': data_type,
                'timestamp': datetime.now().isoformat()
            }

    def _detect_data_type(
        self,
        content: Union[str, Dict[str, Any]]
    ) -> str:
        """Detect content data type."""
        if isinstance(content, dict):
            return 'json'
            
        if isinstance(content, str):
            # Check for JSON
            if content.strip().startswith('{') or content.strip().startswith('['):
                try:
                    json.loads(content)
                    return 'json'
                except json.JSONDecodeError:
                    pass
            
            # Check for table
            if re.search(r'\|.*\|.*\n\|[-\s|]+\|', content):
                return 'table'
            
            # Default to text
            return 'text'
            
        return 'text'  # Default

    async def _extract_json(
        self,
        content: Union[str, Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Extract data from JSON content."""
        try:
            # Parse if string
            if isinstance(content, str):
                data = json.loads(content)
            else:
                data = content
            
            # Extract nested values
            extracted = {
                'type': 'json',
                'timestamp': datetime.now().isoformat(),
                'data': data,
                'structure': self._analyze_json_structure(data)
            }
            
            return extracted
            
        except Exception as e:
            logger.error(f"JSON extraction failed: {str(e)}")
            raise

    async def _extract_table(self, content: str) -> Dict[str, Any]:
        """Extract data from table content."""
        try:
            lines = content.strip().split('\n')
            
            # Parse headers
            headers = [
                cell.strip() for cell in lines[0].strip('|').split('|')
            ]
            
            # Skip separator line
            data_lines = lines[2:] if len(lines) > 2 else []
            
            # Parse rows
            rows = []
            for line in data_lines:
                cells = [cell.strip() for cell in line.strip('|').split('|')]
                if len(cells) == len(headers):
                    row_dict = dict(zip(headers, cells))
                    rows.append(row_dict)
            
            return {
                'type': 'table',
                'timestamp': datetime.now().isoformat(),
                'headers': headers,
                'rows': rows,
                'stats': {
                    'row_count': len(rows),
                    'column_count': len(headers)
                }
            }
            
        except Exception as e:
            logger.error(f"Table extraction failed: {str(e)}")
            raise

    async def _extract_text(self, content: str) -> Dict[str, Any]:
        """Extract structured data from text content."""
        try:
            extracted = {
                'type': 'text',
                'timestamp': datetime.now().isoformat(),
                'patterns_found': {}
            }
            
            # Extract patterns
            for pattern_name, pattern in self.patterns.items():
                matches = re.findall(pattern, content)
                if matches:
                    extracted['patterns_found'][pattern_name] = matches
            
            # Add text stats
            extracted['stats'] = {
                'length': len(content),
                'word_count': len(content.split()),
                'pattern_matches': {
                    k: len(v) for k, v in extracted['patterns_found'].items()
                }
            }
            
            return extracted
            
        except Exception as e:
            logger.error(f"Text extraction failed: {str(e)}")
            raise

    def _analyze_json_structure(
        self,
        data: Any,
        max_depth: int = 5,
        current_depth: int = 0
    ) -> Dict[str, Any]:
        """Analyze JSON data structure recursively."""
        if current_depth >= max_depth:
            return {'type': 'max_depth_reached'}
        
        if isinstance(data, dict):
            return {
                'type': 'object',
                'keys': list(data.keys()),
                'children': {
                    k: self._analyze_json_structure(v, max_depth, current_depth + 1)
                    for k, v in data.items()
                }
            }
        elif isinstance(data, list):
            return {
                'type': 'array',
                'length': len(data),
                'sample': self._analyze_json_structure(
                    data[0], max_depth, current_depth + 1
                ) if data else None
            }
        else:
            return {'type': type(data).__name__}

class TableExtractor:
    """Extracts and processes table data from various formats."""
    
    def __init__(self):
        """Initialize table extractor."""
        self.table_patterns = {
            'markdown': r'\|.*\|.*\n\|[-\s|]+\|',
            'html': r'<table[^>]*>.*?</table>',
            'csv': r'(?:^|\n)(?:[^,\n]*,){2,}[^,\n]*(?:$|\n)'
        }

    async def extract_tables(
        self,
        content: str,
        format_type: str = 'auto',
        metadata: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Extract tables from content.
        
        Args:
            content: Content to extract tables from
            format_type: Format of the tables ('auto', 'markdown', 'html', 'csv')
            metadata: Optional extraction metadata
            
        Returns:
            List[Dict[str, Any]]: Extracted tables
        """
        try:
            # Auto-detect format if not specified
            if format_type == 'auto':
                format_type = self._detect_table_format(content)
            
            # Extract based on format
            if format_type == 'markdown':
                tables = await self._extract_markdown_tables(content)
            elif format_type == 'html':
                tables = await self._extract_html_tables(content)
            elif format_type == 'csv':
                tables = await self._extract_csv_tables(content)
            else:
                tables = []
            
            # Add metadata to each table
            if metadata:
                for table in tables:
                    table['metadata'] = {
                        **table.get('metadata', {}),
                        **metadata
                    }
            
            return tables
            
        except Exception as e:
            logger.error(f"Table extraction failed: {str(e)}")
            return []

    def _detect_table_format(self, content: str) -> str:
        """Detect table format from content."""
        for format_type, pattern in self.table_patterns.items():
            if re.search(pattern, content, re.DOTALL | re.IGNORECASE):
                return format_type
        return 'unknown'

    async def _extract_markdown_tables(self, content: str) -> List[Dict[str, Any]]:
        """Extract tables from Markdown content."""
        tables = []
        # Find table blocks
        table_blocks = re.finditer(r'(\|.*\|.*\n\|[-\s|]+\|.*(?:\n\|.*\|.*)*)', content)
        
        for block in table_blocks:
            table_content = block.group(1)
            lines = table_content.strip().split('\n')
            
            # Parse headers
            headers = [cell.strip() for cell in lines[0].strip('|').split('|')]
            
            # Skip separator line
            rows = []
            for line in lines[2:]:
                cells = [cell.strip() for cell in line.strip('|').split('|')]
                if len(cells) == len(headers):
                    rows.append(dict(zip(headers, cells)))
            
            tables.append({
                'format': 'markdown',
                'headers': headers,
                'rows': rows,
                'timestamp': datetime.now().isoformat()
            })
        
        return tables

    async def _extract_html_tables(self, content: str) -> List[Dict[str, Any]]:
        """Extract tables from HTML content."""
        tables = []
        soup = BeautifulSoup(content, 'html.parser')
        
        for table in soup.find_all('table'):
            # Extract headers
            headers = []
            header_row = table.find('tr')
            if header_row:
                headers = [
                    cell.get_text(strip=True)
                    for cell in header_row.find_all(['th', 'td'])
                ]
            
            # Extract rows
            rows = []
            for row in table.find_all('tr')[1:]:
                cells = [cell.get_text(strip=True) for cell in row.find_all('td')]
                if len(cells) == len(headers):
                    rows.append(dict(zip(headers, cells)))
            
            tables.append({
                'format': 'html',
                'headers': headers,
                'rows': rows,
                'timestamp': datetime.now().isoformat()
            })
        
        return tables

    async def _extract_csv_tables(self, content: str) -> List[Dict[str, Any]]:
        """Extract tables from CSV content."""
        tables = []
        # Split content into potential CSV blocks
        blocks = re.split(r'\n\s*\n', content)
        
        for block in blocks:
            if ',' not in block:
                continue
                
            lines = [line.strip() for line in block.split('\n') if line.strip()]
            if not lines:
                continue
            
            # Parse headers and rows
            headers = [cell.strip() for cell in lines[0].split(',')]
            rows = []
            
            for line in lines[1:]:
                cells = [cell.strip() for cell in line.split(',')]
                if len(cells) == len(headers):
                    rows.append(dict(zip(headers, cells)))
            
            if rows:
                tables.append({
                    'format': 'csv',
                    'headers': headers,
                    'rows': rows,
                    'timestamp': datetime.now().isoformat()
                })
        
        return tables

class ListExtractor:
    """Extracts and processes list data from various formats."""
    
    def __init__(self):
        """Initialize list extractor."""
        self.list_patterns = {
            'bullet': r'(?m)^\s*[-*•]\s+.+',
            'numbered': r'(?m)^\s*\d+\.\s+.+',
            'checkbox': r'(?m)^\s*\[[ x]\]\s+.+',
        }

    async def extract_lists(
        self,
        content: str,
        list_types: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Extract lists from content.
        
        Args:
            content: Content to extract lists from
            list_types: Optional specific list types to extract
            metadata: Optional extraction metadata
            
        Returns:
            Dict[str, List[Dict[str, Any]]]: Extracted lists by type
        """
        try:
            result = {
                'timestamp': datetime.now().isoformat(),
                'lists': {}
            }
            
            # Determine which patterns to use
            patterns = {
                k: v for k, v in self.list_patterns.items()
                if not list_types or k in list_types
            }
            
            # Extract lists by type
            for list_type, pattern in patterns.items():
                extracted = await self._extract_list_type(content, pattern, list_type)
                if extracted:
                    result['lists'][list_type] = extracted
            
            # Add metadata
            if metadata:
                result['metadata'] = metadata
            
            return result
            
        except Exception as e:
            logger.error(f"List extraction failed: {str(e)}")
            return {'timestamp': datetime.now().isoformat(), 'lists': {}}

    async def _extract_list_type(
        self,
        content: str,
        pattern: str,
        list_type: str
    ) -> List[Dict[str, Any]]:
        """Extract specific type of list."""
        extracted = []
        matches = re.finditer(pattern, content, re.MULTILINE)
        
        for match in matches:
            item_text = match.group(0).strip()
            
            # Process based on list type
            if list_type == 'bullet':
                item_text = re.sub(r'^\s*[-*•]\s+', '', item_text)
            elif list_type == 'numbered':
                item_text = re.sub(r'^\s*\d+\.\s+', '', item_text)
            elif list_type == 'checkbox':
                checked = '[x]' in item_text.lower()
                item_text = re.sub(r'^\s*\[[ x]\]\s+', '', item_text)
                extracted.append({
                    'text': item_text,
                    'checked': checked
                })
                continue
            
            extracted.append({'text': item_text})
        
        return extracted

class CodeExtractor:
    """Extracts and processes code snippets from various formats."""
    
    def __init__(self):
        """Initialize code extractor."""
        self.code_patterns = {
            'markdown': r'```[\w]*\n[\s\S]*?```',
            'inline': r'`[^`]+`',
            'html': r'<code[^>]*>[\s\S]*?</code>',
            'xml': r'<\?[\s\S]*?\?>'
        }
        
        self.language_markers = {
            'python': ['python', 'py'],
            'javascript': ['javascript', 'js'],
            'typescript': ['typescript', 'ts'],
            'html': ['html', 'htm'],
            'css': ['css', 'scss', 'sass'],
            'sql': ['sql'],
            'shell': ['bash', 'sh', 'shell'],
            'json': ['json'],
            'xml': ['xml']
        }

    async def extract_code(
        self,
        content: str,
        languages: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Extract code snippets from content.
        
        Args:
            content: Content to extract code from
            languages: Optional specific languages to extract
            metadata: Optional extraction metadata
            
        Returns:
            Dict[str, Any]: Extracted code snippets
        """
        try:
            result = {
                'timestamp': datetime.now().isoformat(),
                'snippets': [],
                'stats': {'total_snippets': 0, 'by_language': {}}
            }
            
            # Extract all code blocks
            for format_type, pattern in self.code_patterns.items():
                matches = re.finditer(pattern, content, re.MULTILINE | re.DOTALL)
                
                for match in matches:
                    snippet = await self._process_code_snippet(
                        match.group(0),
                        format_type,
                        languages
                    )
                    
                    if snippet:
                        result['snippets'].append(snippet)
                        lang = snippet['language']
                        result['stats']['total_snippets'] += 1
                        result['stats']['by_language'][lang] = \
                            result['stats']['by_language'].get(lang, 0) + 1
            
            # Add metadata
            if metadata:
                result['metadata'] = metadata
            
            return result
            
        except Exception as e:
            logger.error(f"Code extraction failed: {str(e)}")
            return {
                'timestamp': datetime.now().isoformat(),
                'snippets': [],
                'stats': {'total_snippets': 0, 'by_language': {}}
            }

    async def _process_code_snippet(
        self,
        snippet: str,
        format_type: str,
        languages: Optional[List[str]] = None
    ) -> Optional[Dict[str, Any]]:
        """Process and clean code snippet."""
        try:
            if format_type == 'markdown':
                # Extract language and code
                first_line = snippet[3:].split('\n')[0].strip().lower()
                language = 'unknown'
                
                # Determine language
                for lang, markers in self.language_markers.items():
                    if first_line in markers:
                        language = lang
                        break
                
                # Skip if not in requested languages
                if languages and language not in languages:
                    return None
                
                # Clean code
                code = '\n'.join(snippet.split('\n')[1:-1])
                
            elif format_type == 'inline':
                code = snippet.strip('`')
                language = 'inline'
                
            elif format_type == 'html':
                code = BeautifulSoup(snippet, 'html.parser').get_text()
                language = 'html'
                
            elif format_type == 'xml':
                code = snippet
                language = 'xml'
            
            else:
                return None
            
            return {
                'code': code.strip(),
                'language': language,
                'format': format_type,
                'timestamp': datetime.now().isoformat(),
                'length': len(code.strip())
            }
            
        except Exception as e:
            logger.error(f"Code snippet processing failed: {str(e)}")
            return None
