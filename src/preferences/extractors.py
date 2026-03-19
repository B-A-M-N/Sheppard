"""
Extractors for identifying and extracting preferences from different sources.
File: src/preferences/extractors.py
"""

import re
import logging
from typing import Dict, Any, List, Optional, Set
from datetime import datetime

from src.preferences.models import (
    Preference,
    PreferenceCategory,
    PreferenceType,
    PreferenceValue,
    PreferenceMetadata
)
from src.preferences.exceptions import ValidationError

logger = logging.getLogger(__name__)

class PreferenceExtractor:
    """Base class for preference extraction."""
    
    def __init__(self):
        """Initialize base extractor."""
        self.preference_patterns = {
            "appearance": {
                "keywords": ["theme", "color", "display", "font", "style"],
                "patterns": [
                    r"prefer\s+(light|dark)\s+theme",
                    r"like\s+(?:the\s+)?(light|dark)\s+mode",
                    r"font\s+size\s+(small|medium|large)"
                ]
            },
            "behavior": {
                "keywords": ["auto", "save", "confirm", "default", "behavior"],
                "patterns": [
                    r"auto[\-\s]save\s+(on|off|enabled|disabled)",
                    r"confirm\s+actions?\s+(yes|no|true|false)",
                    r"default\s+view\s+as\s+(\w+)"
                ]
            },
            "communication": {
                "keywords": ["response", "style", "formal", "casual", "detail"],
                "patterns": [
                    r"prefer\s+(formal|casual|detailed|brief)\s+responses?",
                    r"(more|less)\s+detailed\s+responses?",
                    r"communicate\s+in\s+a\s+(formal|casual)\s+way"
                ]
            }
        }
        
        self.confidence_modifiers = {
            "explicit": {
                "keywords": ["prefer", "want", "like", "need", "must"],
                "boost": 0.3
            },
            "strong": {
                "keywords": ["always", "never", "definitely", "absolutely"],
                "boost": 0.2
            },
            "weak": {
                "keywords": ["maybe", "might", "could", "possibly"],
                "reduction": 0.2
            }
        }
    
    async def extract_preferences(
        self,
        content: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> List[Preference]:
        """
        Extract preferences from content.
        
        Args:
            content: Content to extract from
            metadata: Optional additional metadata
            
        Returns:
            List[Preference]: Extracted preferences
            
        Raises:
            ValidationError: If extraction validation fails
        """
        try:
            preferences = []
            timestamp = datetime.now().isoformat()
            
            # Extract preferences for each category
            for category, patterns in self.preference_patterns.items():
                category_prefs = self._extract_category_preferences(
                    content,
                    category,
                    patterns,
                    timestamp,
                    metadata
                )
                preferences.extend(category_prefs)
            
            return preferences
            
        except Exception as e:
            logger.error(f"Preference extraction failed: {str(e)}")
            raise ValidationError(f"Failed to extract preferences: {str(e)}")
    
    def _extract_category_preferences(
        self,
        content: str,
        category: str,
        patterns: Dict[str, List[str]],
        timestamp: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> List[Preference]:
        """Extract preferences for a specific category."""
        preferences = []
        content_lower = content.lower()
        
        # Check for category keywords
        if not any(kw in content_lower for kw in patterns["keywords"]):
            return preferences
        
        # Extract using patterns
        for pattern in patterns["patterns"]:
            matches = re.finditer(pattern, content_lower)
            for match in matches:
                try:
                    # Get matched value
                    value = match.group(1)
                    
                    # Calculate confidence
                    confidence = self._calculate_confidence(
                        content_lower,
                        match.start(),
                        match.end()
                    )
                    
                    # Create preference
                    preference = self._create_preference(
                        category,
                        pattern,
                        value,
                        confidence,
                        timestamp,
                        metadata
                    )
                    
                    if preference:
                        preferences.append(preference)
                        
                except (IndexError, AttributeError) as e:
                    logger.warning(
                        f"Failed to extract preference from match: {str(e)}"
                    )
        
        return preferences
    
    def _calculate_confidence(
        self,
        content: str,
        start: int,
        end: int,
        base_confidence: float = 0.5
    ) -> float:
        """Calculate confidence score for extraction."""
        confidence = base_confidence
        
        # Get context around match
        context_start = max(0, start - 50)
        context_end = min(len(content), end + 50)
        context = content[context_start:context_end]
        
        # Apply confidence modifiers
        for modifier_type, modifier in self.confidence_modifiers.items():
            if any(kw in context for kw in modifier["keywords"]):
                if "boost" in modifier:
                    confidence = min(1.0, confidence + modifier["boost"])
                if "reduction" in modifier:
                    confidence = max(0.0, confidence - modifier["reduction"])
        
        return round(confidence, 2)
    
    def _create_preference(
        self,
        category: str,
        pattern: str,
        value: str,
        confidence: float,
        timestamp: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Optional[Preference]:
        """Create a preference object from extracted data."""
        try:
            # Determine preference key from pattern
            key = self._get_preference_key(pattern, category)
            
            # Determine value type and normalize value
            value_type, normalized_value = self._normalize_value(value)
            
            # Create preference object
            return Preference(
                id=f"pref_{category}_{key}_{timestamp}",
                category=PreferenceCategory(category),
                key=key,
                value=PreferenceValue(
                    type=value_type,
                    value=normalized_value
                ),
                metadata=PreferenceMetadata(
                    source="text_extraction",
                    confidence=confidence,
                    timestamp=timestamp,
                    context=metadata or {}
                )
            )
            
        except Exception as e:
            logger.warning(f"Failed to create preference: {str(e)}")
            return None
    
    def _get_preference_key(self, pattern: str, category: str) -> str:
        """Determine preference key from pattern."""
        # Extract key term from pattern
        key_match = re.search(r'\(([^)]+)\)', pattern)
        if key_match:
            options = key_match.group(1).split('|')
            base_key = options[0]  # Use first option as base
            return f"{category}_{base_key}"
        
        # Fallback to first keyword
        pattern_words = pattern.split(r'\s+')
        return f"{category}_{pattern_words[0]}"
    
    def _normalize_value(self, value: str) -> tuple[PreferenceType, Any]:
        """Normalize extracted value and determine its type."""
        value_lower = value.lower()
        
        # Check for boolean values
        if value_lower in {'true', 'yes', 'on', 'enabled'}:
            return PreferenceType.BOOLEAN, True
        if value_lower in {'false', 'no', 'off', 'disabled'}:
            return PreferenceType.BOOLEAN, False
        
        # Check for numeric values
        try:
            if '.' in value:
                return PreferenceType.FLOAT, float(value)
            return PreferenceType.INTEGER, int(value)
        except ValueError:
            pass
        
        # Default to string
        return PreferenceType.STRING, value

class TextPreferenceExtractor(PreferenceExtractor):
    """Extracts preferences from text content."""
    
    def __init__(self):
        """Initialize text extractor with additional patterns."""
        super().__init__()
        self.text_patterns = {
            "direct_statement": [
                r"i (?:prefer|want|like|need) (.+)",
                r"set (?:the\s+)?(.+?) to (.+)",
                r"change (?:the\s+)?(.+?) to (.+)",
                r"use (?:the\s+)?(.+) (?:mode|setting|option)"
            ],
            "comparative": [
                r"(?:prefer|like) (.+) (?:over|rather than|instead of) (.+)",
                r"(.+) (?:is better than|works better than) (.+)",
                r"don't (?:like|want|prefer) (.+)"
            ]
        }
    
    async def extract_preferences(
        self,
        content: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> List[Preference]:
        """Extract preferences from text content."""
        preferences = await super().extract_preferences(content, metadata)
        
        # Add text-specific extraction
        text_preferences = self._extract_from_text_patterns(
            content,
            metadata
        )
        preferences.extend(text_preferences)
        
        return preferences
    
    def _extract_from_text_patterns(
        self,
        content: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> List[Preference]:
        """Extract preferences using text-specific patterns."""
        preferences = []
        timestamp = datetime.now().isoformat()
        
        for pattern_type, patterns in self.text_patterns.items():
            for pattern in patterns:
                matches = re.finditer(pattern, content.lower())
                for match in matches:
                    try:
                        if pattern_type == "direct_statement":
                            preference = self._handle_direct_statement(
                                match,
                                timestamp,
                                metadata
                            )
                        else:  # comparative
                            preference = self._handle_comparative(
                                match,
                                timestamp,
                                metadata
                            )
                        
                        if preference:
                            preferences.append(preference)
                            
                    except Exception as e:
                        logger.warning(
                            f"Failed to extract text preference: {str(e)}"
                        )
        
        return preferences
    
    def _handle_direct_statement(
        self,
        match: re.Match,
        timestamp: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Optional[Preference]:
        """Handle direct preference statements."""
        try:
            if len(match.groups()) == 1:
                value = match.group(1)
                key = self._infer_preference_key(value)
            else:
                key = match.group(1)
                value = match.group(2)
            
            confidence = self._calculate_confidence(
                match.string,
                match.start(),
                match.end(),
                base_confidence=0.7  # Higher base for direct statements
            )
            
            return self._create_preference(
                "text_direct",
                key,
                value,
                confidence,
                timestamp,
                metadata
            )
            
        except Exception as e:
            logger.warning(f"Failed to handle direct statement: {str(e)}")
            return None
    
    def _handle_comparative(
        self,
        match: re.Match,
        timestamp: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Optional[Preference]:
        """Handle comparative preference statements."""
        try:
            preferred = match.group(1)
            alternative = match.group(2) if len(match.groups()) > 1 else None
            
            confidence = self._calculate_confidence(
                match.string,
                match.start(),
                match.end(),
                base_confidence=0.6  # Slightly lower for comparative
            )
            
            return self._create_preference(
                "text_comparative",
                self._infer_preference_key(preferred),
                preferred,
                confidence,
                timestamp,
                {
                    **(metadata or {}),
                    "alternative": alternative
                }
            )
            
        except Exception as e:
            logger.warning(f"Failed to handle comparative: {str(e)}")
            return None
    
    def _infer_preference_key(self, value: str) -> str:
        """Infer preference key from value."""
        # Clean and normalize value
        key = re.sub(r'[^\w\s-]', '', value.lower())
        key = re.sub(r'[\s-]+', '_', key.strip())
        return key[:50]  # Limit length

class ContextPreferenceExtractor(PreferenceExtractor):
    """Extracts preferences from interaction context."""
    
    def __init__(self):
        """Initialize context extractor."""
        super().__init__()
        self.context_indicators = {
            "action_based": {
                "keywords": ["always", "never", "whenever", "every time"],
                "confidence": 0.8
            },
            "repeated": {
                "keywords": ["again", "once more", "like before", "same as"],
                "confidence": 0.7
            },
            "consistent": {
                "keywords": ["usually", "normally", "typically", "generally"],
                "confidence": 0.6
            }
        }
    
    async def extract_preferences(
        self,
        content: str,
        context: Dict[str, Any],
        metadata: Optional[Dict[str, Any]] = None
    ) -> List[Preference]:
        """
        Extract preferences from interaction context.
        
        Args:
            content: Current content
            context: Interaction context
            metadata: Optional additional metadata
            
        Returns:
            List[Preference]: Extracted preferences
        """
        preferences = []
        
        # Get base preferences
        base_preferences = await super().extract_preferences(
            content,
            metadata
        )
        preferences.extend(base_preferences)
        
        # Add context-based preferences
        context_preferences = self._extract_from_context(
            content,
            context,
            metadata
        )
        preferences.extend(context_preferences)
        
        return preferences
    
    def _extract_from_context(
        self,
        content: str,
        context: Dict[str, Any],
        metadata: Optional[Dict[str, Any]] = None
    ) -> List[Preference]:
        """Extract preferences from context."""
        preferences = []
        timestamp = datetime.now().isoformat()
        
        # Check context indicators
        for indicator_type, config in self.context_indicators.items():
            if self._matches_context_indicator(
                content,
                context,
                config["keywords"]
            ):
                extracted = self._handle_context_match(
                    content,
                    context,
                    config["confidence"],
                    indicator_type,
                    metadata
                )
                preferences.extend(extracted)
        
        return preferences
    
    def _matches_context_indicator(
        self,
        content: str,
        context: Dict[str, Any],
        keywords: List[str]
    ) -> bool:
        """Check if content matches context indicator."""
        content_lower = content.lower()
        
        # Check direct keyword matches
        if any(kw in content_lower for kw in keywords):
            return True
        
        # Check context history if available
        history = context.get('history', [])
        if history:
            # Check for repeated patterns
            return self._check_repeated_patterns(history, keywords)
        
        return False
    
    def _check_repeated_patterns(
        self,
        history: List[Dict[str, Any]],
        keywords: List[str]
    ) -> bool:
        """Check for repeated patterns in history."""
        if len(history) < 2:
            return False
            
        # Check last few interactions
        recent_history = history[-3:]  # Look at last 3 interactions
        pattern_count = 0
        
        for interaction in recent_history:
            content = interaction.get('content', '').lower()
            if any(kw in content for kw in keywords):
                pattern_count += 1
        
        return pattern_count >= 2  # Return True if pattern appears multiple times
    
    def _handle_context_match(
        self,
        content: str,
        context: Dict[str, Any],
        base_confidence: float,
        indicator_type: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> List[Preference]:
        """Handle context-based preference match."""
        preferences = []
        timestamp = datetime.now().isoformat()
        
        try:
            # Extract key terms from context
            key_terms = self._extract_key_terms(content, context)
            
            for term in key_terms:
                category = self._infer_category(term, context)
                if not category:
                    continue
                
                # Calculate confidence based on context
                confidence = self._adjust_confidence(
                    base_confidence,
                    context,
                    indicator_type
                )
                
                # Create preference
                preference = self._create_preference(
                    category,
                    term,
                    self._extract_value(term, content, context),
                    confidence,
                    timestamp,
                    {
                        **(metadata or {}),
                        "context_type": indicator_type,
                        "extraction_source": "context"
                    }
                )
                
                if preference:
                    preferences.append(preference)
                    
        except Exception as e:
            logger.warning(f"Failed to handle context match: {str(e)}")
        
        return preferences
    
    def _extract_key_terms(
        self,
        content: str,
        context: Dict[str, Any]
    ) -> Set[str]:
        """Extract key terms from content and context."""
        terms = set()
        
        # Extract from current content
        content_terms = self._extract_terms_from_text(content)
        terms.update(content_terms)
        
        # Extract from recent history
        history = context.get('history', [])
        for interaction in history[-3:]:  # Last 3 interactions
            hist_terms = self._extract_terms_from_text(
                interaction.get('content', '')
            )
            terms.update(hist_terms)
        
        return terms
    
    def _extract_terms_from_text(self, text: str) -> Set[str]:
        """Extract potential preference terms from text."""
        terms = set()
        text_lower = text.lower()
        
        # Look for terms near preference indicators
        indicators = [
            "prefer", "want", "like", "need",
            "always", "never", "use", "set"
        ]
        
        for indicator in indicators:
            matches = re.finditer(
                f"{indicator}\\s+([\\w\\s]+?)(?:\\s+(?:to|as|with|in)\\b|$)",
                text_lower
            )
            for match in matches:
                term = match.group(1).strip()
                if term:
                    terms.add(term)
        
        return terms
    
    def _infer_category(
        self,
        term: str,
        context: Dict[str, Any]
    ) -> Optional[str]:
        """Infer preference category from term and context."""
        term_lower = term.lower()
        
        # Check each category's keywords
        for category, patterns in self.preference_patterns.items():
            if any(kw in term_lower for kw in patterns["keywords"]):
                return category
            
        # Check context for category hints
        recent_categories = self._get_recent_categories(context)
        if recent_categories:
            return recent_categories[0]  # Use most recent category
        
        return None
    
    def _get_recent_categories(
        self,
        context: Dict[str, Any]
    ) -> List[str]:
        """Get recently used preference categories from context."""
        categories = []
        
        history = context.get('history', [])
        for interaction in reversed(history):  # Most recent first
            metadata = interaction.get('metadata', {})
            if 'preference_category' in metadata:
                categories.append(metadata['preference_category'])
                
        return list(dict.fromkeys(categories))  # Remove duplicates
    
    def _extract_value(
        self,
        term: str,
        content: str,
        context: Dict[str, Any]
    ) -> Any:
        """Extract preference value for term."""
        content_lower = content.lower()
        term_lower = term.lower()
        
        # Look for explicit value assignments
        value_patterns = [
            f"{term_lower}\\s+(?:to|as)\\s+([\\w\\s]+)",
            f"{term_lower}\\s+(?:is|should be)\\s+([\\w\\s]+)",
            f"set\\s+{term_lower}\\s+to\\s+([\\w\\s]+)"
        ]
        
        for pattern in value_patterns:
            match = re.search(pattern, content_lower)
            if match:
                return match.group(1).strip()
        
        # Check context for recent values
        history = context.get('history', [])
        for interaction in reversed(history):
            hist_content = interaction.get('content', '').lower()
            for pattern in value_patterns:
                match = re.search(pattern, hist_content)
                if match:
                    return match.group(1).strip()
        
        # Default to boolean true for presence-based preferences
        return True
    
    def _adjust_confidence(
        self,
        base_confidence: float,
        context: Dict[str, Any],
        indicator_type: str
    ) -> float:
        """Adjust confidence based on context factors."""
        confidence = base_confidence
        
        # Adjust based on history consistency
        history = context.get('history', [])
        if history:
            consistency = self._calculate_history_consistency(
                history,
                indicator_type
            )
            confidence *= consistency
        
        # Adjust based on context strength
        context_strength = self._calculate_context_strength(context)
        confidence *= context_strength
        
        return round(min(1.0, max(0.0, confidence)), 2)
    
    def _calculate_history_consistency(
        self,
        history: List[Dict[str, Any]],
        indicator_type: str
    ) -> float:
        """Calculate consistency factor from history."""
        if len(history) < 2:
            return 1.0  # No history to check
            
        # Count consistent indicators
        consistent_count = 0
        total_checked = min(len(history), 5)  # Check last 5 interactions
        
        for i in range(total_checked):
            interaction = history[-(i+1)]  # Start from most recent
            if self._has_consistent_indicator(interaction, indicator_type):
                consistent_count += 1
        
        return 0.8 + (0.2 * consistent_count / total_checked)
    
    def _has_consistent_indicator(
        self,
        interaction: Dict[str, Any],
        indicator_type: str
    ) -> bool:
        """Check if interaction has consistent indicator."""
        content = interaction.get('content', '').lower()
        
        # Check for indicator type keywords
        if indicator_type in self.context_indicators:
            keywords = self.context_indicators[indicator_type]["keywords"]
            return any(kw in content for kw in keywords)
        
        return False
    
    def _calculate_context_strength(
        self,
        context: Dict[str, Any]
    ) -> float:
        """Calculate context strength factor."""
        strength = 1.0
        
        # Reduce strength for older context
        if context.get('age_minutes', 0) > 30:
            strength *= 0.9
        
        # Increase strength for user-confirmed preferences
        if context.get('user_confirmed', False):
            strength *= 1.1
        
        # Adjust for context completeness
        if context.get('incomplete', False):
            strength *= 0.8
        
        return round(min(1.0, max(0.0, strength)), 2)
