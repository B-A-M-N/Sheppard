"""
Source and content validation for research system.
"""

import logging
import re
from typing import Dict, Any, List, Optional, Tuple, Union
from datetime import datetime
from urllib.parse import urlparse
from enum import Enum, auto

# Import from core exceptions instead of research exceptions
from src.core.base_exceptions import ChatSystemError

class ValidationError(ChatSystemError):
    """Base exception for validation errors."""
    def __init__(self, message: str = "Validation failed"):
        super().__init__(f"Validation error: {message}")

class ValidationLevel(Enum):
    """Validation strictness levels."""
    NONE = auto()
    LOW = auto()
    MEDIUM = auto()
    HIGH = auto()
    FULL = auto()

# Import research models after ValidationError definition
from src.research.models import (
    ResearchSource,
    SourceType,
    SourceReliability
)

logger = logging.getLogger(__name__)

class SourceValidator:
    """Validates research sources and their content."""
    
    def __init__(self):
        """Initialize source validator."""
        # Domain reliability patterns
        self.reliable_domains = {
            r'\.edu$': 0.9,  # Educational institutions
            r'\.gov$': 0.9,  # Government sites
            r'\.org$': 0.8,  # Non-profit organizations
            r'wikipedia\.org$': 0.8,  # Wikipedia
            r'arxiv\.org$': 0.9,  # arXiv
            r'github\.com$': 0.8,  # GitHub
            r'medium\.com$': 0.6,  # Medium
            r'stackexchange\.com$': 0.8,  # Stack Exchange
            r'stackoverflow\.com$': 0.8  # Stack Overflow
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
        
        # Initialize state
        self._initialized = False
        self._session = None

    async def initialize(self) -> None:
        """Initialize validator."""
        if self._initialized:
            return
            
        try:
            # Initialize any required resources
            # In this case, we don't need external resources
            # but the method is required for system initialization
            self._initialized = True
            logger.info("Source validator initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize source validator: {str(e)}")
            raise
    
    async def cleanup(self) -> None:
        """Clean up validator resources."""
        try:
            # Clean up any resources
            # In this case, we don't have external resources to clean up
            # but the method is required for system cleanup
            self._initialized = False
            logger.info("Source validator cleanup completed")
            
        except Exception as e:
            logger.error(f"Error during source validator cleanup: {str(e)}")
    
    async def validate_source(
        self,
        source: Union[ResearchSource, Dict[str, Any]]
    ) -> Tuple[bool, Optional[str]]:
        """
        Validate a research source.
        
        Args:
            source: Source to validate
            
        Returns:
            Tuple[bool, Optional[str]]: (is_valid, error_message)
        """
        try:
            # Convert dict to ResearchSource if needed
            if isinstance(source, dict):
                source = ResearchSource(**source)
            
            # Validate URL
            if not self._validate_url(source.url):
                return False, f"Invalid URL: {source.url}"
            
            # Validate source type
            if not isinstance(source.source_type, SourceType):
                return False, f"Invalid source type: {source.source_type}"
            
            # Validate reliability
            if not isinstance(source.reliability, SourceReliability):
                return False, f"Invalid reliability: {source.reliability}"
            
            # Validate dates if present
            if source.published_date:
                try:
                    datetime.fromisoformat(source.published_date.replace('Z', '+00:00'))
                except ValueError:
                    return False, f"Invalid published date format: {source.published_date}"
            
            # Additional metadata validation
            if source.metadata:
                if not isinstance(source.metadata, dict):
                    return False, "Metadata must be a dictionary"
            
            return True, None
            
        except Exception as e:
            logger.error(f"Source validation failed: {str(e)}")
            return False, str(e)
    
    def _validate_url(self, url: str) -> bool:
        """Validate URL format."""
        if not url:
            return False
            
        try:
            result = urlparse(url)
            return all([result.scheme, result.netloc])
        except Exception:
            return False
    
    def calculate_reliability(self, source: ResearchSource) -> float:
        """Calculate overall source reliability score."""
        base_score = source.reliability.get_score()
        domain_score = self._get_domain_reliability(source.url)
        
        # Adjust score based on validation level
        validation_modifier = {
            ValidationLevel.HIGH: 1.0,
            ValidationLevel.MEDIUM: 0.8,
            ValidationLevel.LOW: 0.6,
            ValidationLevel.NONE: 0.4
        }.get(source.validation_level, 0.5)
        
        # Calculate weighted score
        weighted_score = (base_score * 0.4 + domain_score * 0.4 + validation_modifier * 0.2)
        return round(min(1.0, max(0.0, weighted_score)), 2)
    
    def _get_domain_reliability(self, url: str) -> float:
        """Get reliability score based on domain patterns."""
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

class ContentValidator:
    """Validates research content."""
    
    def __init__(self):
        """Initialize content validator."""
        self.min_content_length = 50  # Minimum meaningful content length
        self.max_content_length = 100000  # Maximum content length
        
        # Content quality indicators
        self.quality_indicators = {
            'references': r'\[\d+\]|\[(?:[A-Za-z]+\s*(?:et al\.)?,\s*\d{4})\]',
            'citations': r'\(\w+(?:\s*et al\.)?,\s*\d{4}\)',
            'urls': r'https?://\S+',
            'equations': r'\$[^$]+\$|\\\(.*?\\\)',
            'code_blocks': r'```[\s\S]*?```'
        }

        # Initialize state
        self._initialized = False
        self._llm_client = None
    
    async def initialize(self, llm_client=None) -> None:
        """Initialize validator with optional LLM client."""
        if self._initialized:
            return
            
        try:
            self._llm_client = llm_client
            self._initialized = True
            logger.info("Content validator initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize content validator: {str(e)}")
            raise
    
    async def cleanup(self) -> None:
        """Clean up validator resources."""
        try:
            self._llm_client = None
            self._initialized = False
            logger.info("Content validator cleanup completed")
            
        except Exception as e:
            logger.error(f"Error during content validator cleanup: {str(e)}")
    
    async def validate_content(
        self,
        content: str,
        validation_level: ValidationLevel = ValidationLevel.MEDIUM,
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
            
            # Look for quality indicators
            for indicator, pattern in self.quality_indicators.items():
                matches = re.findall(pattern, content)
                validation_results['indicators_found'][indicator] = len(matches)
            
            # Calculate quality score
            quality_score = self._calculate_quality_score(
                content,
                validation_results['indicators_found']
            )
            validation_results['score'] = quality_score
            
            # Validate based on level
            if validation_level == ValidationLevel.HIGH:
                if quality_score < 0.8:
                    return False, "Content quality below threshold for high validation", validation_results
            elif validation_level == ValidationLevel.MEDIUM:
                if quality_score < 0.6:
                    return False, "Content quality below threshold for medium validation", validation_results
            elif validation_level == ValidationLevel.LOW:
                if quality_score < 0.4:
                    return False, "Content quality below threshold for low validation", validation_results
            
            return True, None, validation_results
            
        except Exception as e:
            logger.error(f"Content validation failed: {str(e)}")
            return False, str(e), {}
    
    def _calculate_quality_score(
        self,
        content: str,
        indicators: Dict[str, int]
    ) -> float:
        """Calculate content quality score."""
        score = 0.0
        content_length = len(content)
        
        # Length score (0.0 - 0.2)
        length_score = min(content_length / 1000, 1.0) * 0.2
        score += length_score
        
        # Indicators score (0.0 - 0.6)
        if indicators:
            # References and citations (0.0 - 0.3)
            ref_count = indicators.get('references', 0) + indicators.get('citations', 0)
            ref_score = min(ref_count / 5, 1.0) * 0.3
            score += ref_score
            
            # URLs and external links (0.0 - 0.2)
            url_count = indicators.get('urls', 0)
            url_score = min(url_count / 3, 1.0) * 0.2
            score += url_score
            
            # Technical content (0.0 - 0.1)
            tech_count = indicators.get('equations', 0) + indicators.get('code_blocks', 0)
            tech_score = min(tech_count / 2, 1.0) * 0.1
            score += tech_score
        
        # Content diversity score (0.0 - 0.2)
        unique_words = len(set(content.lower().split()))
        diversity_score = min(unique_words / 200, 1.0) * 0.2
        score += diversity_score
        
        return round(min(1.0, score), 2)

class ReferenceValidator:
    """Validates research references and citations."""
    
    def __init__(self):
        """Initialize reference validator."""
        # Citation format patterns
        self.citation_patterns = {
            'apa': r'\((?:[A-Za-z]+(?:\s*et al\.?)?,\s*\d{4}(?:,\s*(?:p\.|pp\.)?\s*\d+(?:-\d+)?)?\))',
            'mla': r'\([A-Za-z]+\s+\d+(?:-\d+)?\)',
            'chicago': r'\d+\.\s*[A-Za-z]+',
            'ieee': r'\[\d+\]',
            'harvard': r'\([A-Za-z]+,\s*\d{4}\)'
        }
        
        # DOI pattern
        self.doi_pattern = r'10\.\d{4,}/[-._;()/:\w]+'

        # Initialize state
        self._initialized = False
        self._llm_client = None

    async def initialize(self, llm_client=None) -> None:
        """Initialize validator with optional LLM client."""
        if self._initialized:
            return
            
        try:
            self._llm_client = llm_client
            self._initialized = True
            logger.info("Reference validator initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize reference validator: {str(e)}")
            raise
    
    async def cleanup(self) -> None:
        """Clean up validator resources."""
        try:
            self._llm_client = None
            self._initialized = False
            logger.info("Reference validator cleanup completed")
            
        except Exception as e:
            logger.error(f"Error during reference validator cleanup: {str(e)}")

    async def validate_reference(
        self,
        reference: str,
        expected_format: Optional[str] = None
    ) -> Tuple[bool, Optional[str], Dict[str, Any]]:
        """
        Validate a reference string.
        
        Args:
            reference: Reference string to validate
            expected_format: Expected citation format
            
        Returns:
            Tuple[bool, Optional[str], Dict[str, Any]]:
                (is_valid, error_message, validation_results)
        """
        validation_results = {
            'detected_format': None,
            'has_doi': False,
            'has_year': False,
            'has_authors': False,
            'confidence': 0.0
        }
        
        try:
            # Check for empty reference
            if not reference or not reference.strip():
                return False, "Empty reference", validation_results
            
            # Detect citation format
            detected_format = None
            max_confidence = 0.0
            
            for format_name, pattern in self.citation_patterns.items():
                if re.search(pattern, reference):
                    confidence = self._calculate_format_confidence(
                        reference,
                        format_name,
                        pattern
                    )
                    if confidence > max_confidence:
                        max_confidence = confidence
                        detected_format = format_name
            
            validation_results['detected_format'] = detected_format
            validation_results['confidence'] = max_confidence
            
            # Check for DOI
            doi_match = re.search(self.doi_pattern, reference)
            validation_results['has_doi'] = bool(doi_match)
            
            # Check for year
            year_match = re.search(r'\d{4}', reference)
            validation_results['has_year'] = bool(year_match)
            
            # Check for authors
            authors_match = re.search(r'[A-Za-z]+(?:\s*et al\.?)?', reference)
            validation_results['has_authors'] = bool(authors_match)
            
            # Validate against expected format
            if expected_format:
                if detected_format != expected_format:
                    return (
                        False,
                        f"Reference format mismatch: expected {expected_format}, "
                        f"detected {detected_format}",
                        validation_results
                    )
            
            # Consider valid if we have a format and reasonable confidence
            is_valid = detected_format is not None and max_confidence >= 0.7
            error_message = None if is_valid else "Invalid reference format"
            
            return is_valid, error_message, validation_results
            
        except Exception as e:
            logger.error(f"Reference validation failed: {str(e)}")
            return False, str(e), validation_results
    
    def _calculate_format_confidence(
        self,
        reference: str,
        format_name: str,
        pattern: str
    ) -> float:
        """Calculate confidence score for citation format match."""
        try:
            # Base confidence from pattern match
            if not re.search(pattern, reference):
                return 0.0
                
            confidence = 0.6  # Start with base confidence for pattern match
            
            # Format-specific checks
            if format_name == 'apa':
                # Check for author-year format
                if re.search(r'[A-Za-z]+(?:\s*et al\.?)?,\s*\d{4}', reference):
                    confidence += 0.2
                # Check for page numbers
                if re.search(r'p\.|pp\.\s*\d+', reference):
                    confidence += 0.1
            
            elif format_name == 'mla':
                # Check for author-page format
                if re.search(r'[A-Za-z]+\s+\d+', reference):
                    confidence += 0.2
            
            elif format_name == 'chicago':
                # Check for footnote format
                if re.search(r'^\d+\.\s*', reference):
                    confidence += 0.2
            
            elif format_name == 'ieee':
                # Check for bracketed number format
                if re.search(r'^\[\d+\]$', reference):
                    confidence += 0.3
            
            elif format_name == 'harvard':
                # Check for author-year in parentheses
                if re.search(r'\([A-Za-z]+,\s*\d{4}\)', reference):
                    confidence += 0.2
                # Check for page numbers
                if re.search(r'\d+(?:-\d+)?', reference):
                    confidence += 0.1

            # Additional checks for all formats
            
            # Check for multiple references
            if re.search(r';|\sand\s', reference):
                confidence += 0.1
            
            # Check for volume/issue numbers
            if re.search(r'vol\.|volume|issue|\(\d+\)', reference.lower()):
                confidence += 0.1
            
            return min(1.0, confidence)
            
        except Exception as e:
            logger.error(f"Format confidence calculation failed: {str(e)}")
            return 0.0

    async def validate_references(
        self,
        references: List[str],
        expected_format: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Validate a list of references.
        
        Args:
            references: List of references to validate
            expected_format: Expected citation format
            
        Returns:
            Dict[str, Any]: Validation results
        """
        results = {
            'valid_count': 0,
            'invalid_count': 0,
            'format_mismatches': 0,
            'validation_details': [],
            'formats_detected': set()
        }
        
        for ref in references:
            is_valid, error, ref_results = await self.validate_reference(
                ref,
                expected_format
            )
            
            if is_valid:
                results['valid_count'] += 1
            else:
                results['invalid_count'] += 1
                
            if ref_results['detected_format']:
                results['formats_detected'].add(ref_results['detected_format'])
                
            if (expected_format and ref_results['detected_format'] and 
                expected_format != ref_results['detected_format']):
                results['format_mismatches'] += 1
                
            results['validation_details'].append({
                'reference': ref,
                'is_valid': is_valid,
                'error': error,
                'details': ref_results
            })
        
        # Convert set to list for JSON serialization
        results['formats_detected'] = list(results['formats_detected'])
        
        return results

class DataValidator:
    """Validates research data and metrics."""
    
    def __init__(self):
        """Initialize data validator."""
        self.numeric_types = (int, float)
        self.allowed_types = {
            'numeric': self.numeric_types,
            'string': (str,),
            'boolean': (bool,),
            'list': (list,),
            'dict': (dict,)
        }
    
    async def validate_data(
        self,
        data: Any,
        schema: Dict[str, Any],
        validation_level: ValidationLevel = ValidationLevel.MEDIUM
    ) -> Tuple[bool, Optional[str], Dict[str, Any]]:
        """
        Validate research data against a schema.
        
        Args:
            data: Data to validate
            schema: Validation schema
            validation_level: Level of validation to apply
            
        Returns:
            Tuple[bool, Optional[str], Dict[str, Any]]:
                (is_valid, error_message, validation_results)
        """
        validation_results = {
            'type_checks': {},
            'range_checks': {},
            'constraint_checks': {},
            'missing_fields': [],
            'invalid_fields': []
        }
        
        try:
            # Check required fields
            required_fields = schema.get('required', [])
            if isinstance(data, dict):
                for field in required_fields:
                    if field not in data:
                        validation_results['missing_fields'].append(field)
            
            # Validate fields against schema
            for field_name, field_schema in schema.get('properties', {}).items():
                if field_name in data:
                    field_value = data[field_name]
                    
                    # Type validation
                    expected_type = field_schema.get('type')
                    if expected_type:
                        type_valid = self._validate_type(
                            field_value,
                            expected_type
                        )
                        validation_results['type_checks'][field_name] = type_valid
                        if not type_valid:
                            validation_results['invalid_fields'].append(field_name)
                    
                    # Range validation for numeric fields
                    if expected_type == 'numeric' and isinstance(field_value, self.numeric_types):
                        range_valid = self._validate_range(
                            field_value,
                            field_schema.get('minimum'),
                            field_schema.get('maximum')
                        )
                        validation_results['range_checks'][field_name] = range_valid
                        if not range_valid:
                            validation_results['invalid_fields'].append(field_name)
                    
                    # Custom constraints
                    constraints = field_schema.get('constraints', {})
                    if constraints:
                        constraint_valid = self._validate_constraints(
                            field_value,
                            constraints
                        )
                        validation_results['constraint_checks'][field_name] = constraint_valid
                        if not constraint_valid:
                            validation_results['invalid_fields'].append(field_name)
            
            # Determine overall validity based on validation level
            if validation_level == ValidationLevel.HIGH:
                is_valid = (not validation_results['missing_fields'] and 
                          not validation_results['invalid_fields'] and
                          all(validation_results['type_checks'].values()) and
                          all(validation_results['range_checks'].values()) and
                          all(validation_results['constraint_checks'].values()))
            elif validation_level == ValidationLevel.MEDIUM:
                is_valid = (not validation_results['missing_fields'] and
                          all(validation_results['type_checks'].values()) and
                          all(validation_results['range_checks'].values()))
            else:  # LOW or NONE
                is_valid = not validation_results['missing_fields']
            
            error_message = None if is_valid else "Data validation failed"
            return is_valid, error_message, validation_results
            
        except Exception as e:
            logger.error(f"Data validation failed: {str(e)}")
            return False, str(e), validation_results
    
    def _validate_type(
        self,
        value: Any,
        expected_type: str
    ) -> bool:
        """Validate value type."""
        if expected_type in self.allowed_types:
            return isinstance(value, self.allowed_types[expected_type])
        return False
    
    def _validate_range(
        self,
        value: Union[int, float],
        minimum: Optional[Union[int, float]] = None,
        maximum: Optional[Union[int, float]] = None
    ) -> bool:
        """Validate numeric range."""
        if minimum is not None and value < minimum:
            return False
        if maximum is not None and value > maximum:
            return False
        return True
    
    def _validate_constraints(
        self,
        value: Any,
        constraints: Dict[str, Any]
    ) -> bool:
        """Validate custom constraints."""
        try:
            for constraint_type, constraint_value in constraints.items():
                if constraint_type == 'regex' and isinstance(value, str):
                    if not re.match(constraint_value, value):
                        return False
                        
                elif constraint_type == 'enum':
                    if value not in constraint_value:
                        return False
                        
                elif constraint_type == 'length':
                    if len(value) != constraint_value:
                        return False
                        
                elif constraint_type == 'min_length':
                    if len(value) < constraint_value:
                        return False
                        
                elif constraint_type == 'max_length':
                    if len(value) > constraint_value:
                        return False
                        
                elif constraint_type == 'custom':
                    if callable(constraint_value) and not constraint_value(value):
                        return False
            
            return True
            
        except Exception:
            return False
