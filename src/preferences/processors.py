"""
Processors for handling preference analysis and relationships.
File: src/preferences/processors.py
"""

import logging
from typing import Dict, Any, List, Optional, Set, Tuple
from datetime import datetime

from src.preferences.models import (
    Preference,
    PreferenceSet,
    PreferenceCategory,
    PreferenceType,
    PreferenceValue,
    PreferenceMetadata
)
from src.preferences.exceptions import ProcessingError

logger = logging.getLogger(__name__)

class PreferenceContext:
    """Manages context for preference processing."""
    
    def __init__(self, max_history: int = 10):
        """
        Initialize preference context.
        
        Args:
            max_history: Maximum history items to track
        """
        self.history: List[Dict[str, Any]] = []
        self.max_history = max_history
        self.current_context: Dict[str, Any] = {}
    
    def add_to_history(
        self,
        preference: Preference,
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Add preference to history.
        
        Args:
            preference: Preference to add
            metadata: Optional additional metadata
        """
        history_item = {
            "preference": preference.model_dump(),
            "timestamp": datetime.now().isoformat(),
            "metadata": metadata or {}
        }
        
        self.history.append(history_item)
        if len(self.history) > self.max_history:
            self.history.pop(0)  # Remove oldest item
    
    def update_context(self, context_data: Dict[str, Any]) -> None:
        """
        Update current context.
        
        Args:
            context_data: New context data
        """
        self.current_context.update(context_data)
    
    def get_recent_preferences(
        self,
        category: Optional[PreferenceCategory] = None,
        limit: int = 5
    ) -> List[Preference]:
        """
        Get recent preferences.
        
        Args:
            category: Optional category filter
            limit: Maximum number of preferences to return
            
        Returns:
            List[Preference]: Recent preferences
        """
        preferences = []
        for item in reversed(self.history):
            pref_data = item["preference"]
            if category and pref_data["category"] != category:
                continue
            try:
                preferences.append(Preference(**pref_data))
                if len(preferences) >= limit:
                    break
            except Exception as e:
                logger.warning(f"Failed to load preference: {str(e)}")
        return preferences
    
    def clear_history(self) -> None:
        """Clear preference history."""
        self.history.clear()
    
    def clear_context(self) -> None:
        """Clear current context."""
        self.current_context.clear()

class PreferenceRelation:
    """Manages relationships between preferences."""
    
    def __init__(self):
        """Initialize preference relation manager."""
        self.relations: Dict[str, Dict[str, float]] = {}
        self.conflict_threshold = 0.7  # Similarity threshold for conflicts
    
    def add_relation(
        self,
        pref1: Preference,
        pref2: Preference,
        strength: float
    ) -> None:
        """
        Add relationship between preferences.
        
        Args:
            pref1: First preference
            pref2: Second preference
            strength: Relationship strength (0-1)
        """
        if strength < 0 or strength > 1:
            raise ValueError("Strength must be between 0 and 1")
            
        # Create relation entries
        if pref1.id not in self.relations:
            self.relations[pref1.id] = {}
        if pref2.id not in self.relations:
            self.relations[pref2.id] = {}
            
        # Store bidirectional relationship
        self.relations[pref1.id][pref2.id] = strength
        self.relations[pref2.id][pref1.id] = strength
    
    def get_related_preferences(
        self,
        preference: Preference,
        min_strength: float = 0.5
    ) -> List[Tuple[str, float]]:
        """
        Get related preferences.
        
        Args:
            preference: Source preference
            min_strength: Minimum relationship strength
            
        Returns:
            List[Tuple[str, float]]: Related preference IDs and strengths
        """
        if preference.id not in self.relations:
            return []
            
        return [
            (pref_id, strength)
            for pref_id, strength in self.relations[preference.id].items()
            if strength >= min_strength
        ]
    
    def check_conflicts(
        self,
        preference: Preference,
        existing_preferences: List[Preference]
    ) -> List[Tuple[Preference, float]]:
        """
        Check for conflicts with existing preferences.
        
        Args:
            preference: Preference to check
            existing_preferences: Existing preferences to check against
            
        Returns:
            List[Tuple[Preference, float]]: Conflicting preferences and strengths
        """
        conflicts = []
        
        for existing in existing_preferences:
            if self._are_conflicting(preference, existing):
                similarity = self._calculate_similarity(preference, existing)
                if similarity >= self.conflict_threshold:
                    conflicts.append((existing, similarity))
        
        return conflicts
    
    def _are_conflicting(
        self,
        pref1: Preference,
        pref2: Preference
    ) -> bool:
        """Check if preferences conflict."""
        # Same category and key but different values
        if (pref1.category == pref2.category and 
            pref1.key == pref2.key and 
            pref1.value.value != pref2.value.value):
            return True
        
        # Check for semantic conflicts
        if self._have_semantic_conflict(pref1, pref2):
            return True
        
        return False
    
    def _have_semantic_conflict(
        self,
        pref1: Preference,
        pref2: Preference
    ) -> bool:
        """Check for semantic conflicts between preferences."""
        # Example semantic conflicts:
        # - Dark theme vs Light theme
        # - Auto-save enabled vs Manual save only
        # - Notifications enabled vs Do not disturb
        
        semantic_conflicts = {
            ("appearance", "theme"): {
                ("dark", "light"),
                ("light", "system")
            },
            ("behavior", "auto_save"): {
                (True, False)
            },
            ("notifications", "enabled"): {
                (True, False)
            }
        }
        
        conflict_key = (pref1.category.value, pref1.key)
        if conflict_key in semantic_conflicts:
            values = (pref1.value.value, pref2.value.value)
            return values in semantic_conflicts[conflict_key]
        
        return False
    
    def _calculate_similarity(
        self,
        pref1: Preference,
        pref2: Preference
    ) -> float:
        """Calculate similarity between preferences."""
        score = 0.0
        checks = 0
        
        # Check category
        if pref1.category == pref2.category:
            score += 0.3
        checks += 1
        
        # Check key similarity
        key_similarity = self._string_similarity(pref1.key, pref2.key)
        score += 0.3 * key_similarity
        checks += 1
        
        # Check value type
        if pref1.value.type == pref2.value.type:
            score += 0.2
        checks += 1
        
        # Check value similarity
        value_similarity = self._value_similarity(
            pref1.value,
            pref2.value
        )
        score += 0.2 * value_similarity
        checks += 1
        
        return score / checks
    
    def _string_similarity(self, str1: str, str2: str) -> float:
        """Calculate string similarity."""
        # Simple Levenshtein distance based similarity
        if str1 == str2:
            return 1.0
            
        # Convert to sets of characters
        set1 = set(str1)
        set2 = set(str2)
        
        # Calculate Jaccard similarity
        intersection = len(set1.intersection(set2))
        union = len(set1.union(set2))
        
        return intersection / union if union > 0 else 0.0
    
    def _value_similarity(
        self,
        val1: PreferenceValue,
        val2: PreferenceValue
    ) -> float:
        """Calculate similarity between preference values."""
        if val1.type != val2.type:
            return 0.0
            
        if val1.type == PreferenceType.BOOLEAN:
            return 1.0 if val1.value == val2.value else 0.0
            
        elif val1.type in {PreferenceType.INTEGER, PreferenceType.FLOAT}:
            try:
                # Normalize numerical difference
                max_val = max(abs(val1.value), abs(val2.value))
                if max_val == 0:
                    return 1.0
                diff = abs(val1.value - val2.value)
                return max(0.0, 1.0 - (diff / max_val))
            except (TypeError, ValueError):
                return 0.0
                
        elif val1.type == PreferenceType.STRING:
            return self._string_similarity(
                str(val1.value),
                str(val2.value)
            )
            
        elif val1.type == PreferenceType.ENUM:
            if hasattr(val1, 'options') and val1.options == val2.options:
                return 1.0 if val1.value == val2.value else 0.0
            return 0.0
            
        return 0.0

class PreferenceProcessor:
    """Process and analyze preferences."""
    
    def __init__(
        self,
        context: PreferenceContext,
        relations: PreferenceRelation
    ):
        """
        Initialize preference processor.
        
        Args:
            context: Preference context manager
            relations: Preference relation manager
        """
        self.context = context
        self.relations = relations
        self.processors = {
            PreferenceCategory.APPEARANCE: self._process_appearance,
            PreferenceCategory.BEHAVIOR: self._process_behavior,
            PreferenceCategory.PRIVACY: self._process_privacy
        }
    
    async def process_preference(
        self,
        preference: Preference,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Tuple[bool, Optional[str], Optional[Dict[str, Any]]]:
        """
        Process a preference.
        
        Args:
            preference: Preference to process
            metadata: Optional additional metadata
            
        Returns:
            Tuple[bool, Optional[str], Optional[Dict[str, Any]]]: 
                (success, error message, processed data)
        """
        try:
            # Check for conflicts
            conflicts = self.relations.check_conflicts(
                preference,
                self.context.get_recent_preferences(preference.category)
            )
            
            if conflicts:
                return (
                    False,
                    "Conflicts with existing preferences",
                    {"conflicts": conflicts}
                )
            
            # Process by category
            if preference.category in self.processors:
                processor = self.processors[preference.category]
                success, error, data = await processor(preference)
                if not success:
                    return False, error, data
            
            # Update context
            self.context.add_to_history(preference, metadata)
            
            # Add relationships
            self._add_relationships(preference)
            
            return True, None, data
            
        except Exception as e:
            logger.error(f"Preference processing failed: {str(e)}")
            return False, str(e), None
    
    async def process_preference_set(
        self,
        preference_set: PreferenceSet,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Tuple[bool, Optional[str], Dict[str, Any]]:
        """
        Process a set of preferences.
        
        Args:
            preference_set: PreferenceSet to process
            metadata: Optional additional metadata
            
        Returns:
            Tuple[bool, Optional[str], Dict[str, Any]]: 
                (success, error message, results)
        """
        results = {
            "processed": [],
            "failed": [],
            "conflicts": []
        }
        
        try:
            # Process each preference
            for key, preference in preference_set.preferences.items():
                success, error, data = await self.process_preference(
                    preference,
                    {
                        **(metadata or {}),
                        "set_id": preference_set.id,
                        "preference_key": key
                    }
                )
                
                if success:
                    results["processed"].append({
                        "key": key,
                        "data": data
                    })
                else:
                    if data and "conflicts" in data:
                        results["conflicts"].append({
                            "key": key,
                            "conflicts": data["conflicts"]
                        })
                    else:
                        results["failed"].append({
                            "key": key,
                            "error": error
                        })
            
            return (
                len(results["processed"]) > 0,
                None if results["processed"] else "No preferences processed",
                results
            )
            
        except Exception as e:
            logger.error(f"Preference set processing failed: {str(e)}")
            return False, str(e), results
    
    def _add_relationships(self, preference: Preference) -> None:
        """Add relationships for new preference."""
        recent = self.context.get_recent_preferences(
            category=preference.category
        )
        
        for existing in recent:
            similarity = self.relations._calculate_similarity(
                preference,
                existing
            )
            if similarity > 0.3:  # Minimum threshold for relationship
                self.relations.add_relation(
                    preference,
                    existing,
                    similarity
                )
    
    async def _process_appearance(
        self,
        preference: Preference
    ) -> Tuple[bool, Optional[str], Dict[str, Any]]:
        """Process appearance preference."""
        try:
            processed_data = {
                "theme_compatibility": True,
                "applied_changes": []
            }
            
            # Process based on key
            if preference.key == "theme":
                # Validate theme value
                valid_themes = {"light", "dark", "system"}
                if preference.value.value not in valid_themes:
                    return (
                        False,
                        f"Invalid theme value. Must be one of: {valid_themes}",
                        None
                    )
                
                processed_data["applied_changes"].append(
                    f"Applied {preference.value.value} theme"
                )
                
            elif preference.key == "color_scheme":
                # Add color scheme processing
                processed_data["applied_changes"].append(
                    f"Updated color scheme to {preference.value.value}"
                )
            
            return True, None, processed_data
            
        except Exception as e:
            logger.error(f"Appearance processing failed: {str(e)}")
            return False, str(e), {}
    
    async def _process_behavior(
        self,
        preference: Preference
    ) -> Tuple[bool, Optional[str], Dict[str, Any]]:
        """Process behavior preference."""
        try:
            processed_data = {
                "behavior_updates": [],
                "side_effects": []
            }
            
            # Process based on key
            if preference.key == "auto_save":
                if not isinstance(preference.value.value, bool):
                    return (
                        False,
                        "Auto-save value must be boolean",
                        None
                    )
                
                processed_data["behavior_updates"].append(
                    f"Auto-save {'enabled' if preference.value.value else 'disabled'}"
                )
                
                # Check for related settings
                if preference.value.value:
                    processed_data["side_effects"].append(
                        "Enabled periodic backups"
                    )
                
            elif preference.key == "confirm_actions":
                if not isinstance(preference.value.value, bool):
                    return (
                        False,
                        "Confirm actions value must be boolean",
                        None
                    )
                
                processed_data["behavior_updates"].append(
                    f"Action confirmation {'enabled' if preference.value.value else 'disabled'}"
                )
                
            elif preference.key == "default_view":
                valid_views = {"list", "grid", "detail"}
                if preference.value.value not in valid_views:
                    return (
                        False,
                        f"Invalid view value. Must be one of: {valid_views}",
                        None
                    )
                
                processed_data["behavior_updates"].append(
                    f"Default view set to {preference.value.value}"
                )
            
            return True, None, processed_data
            
        except Exception as e:
            logger.error(f"Behavior processing failed: {str(e)}")
            return False, str(e), {}
    
    async def _process_privacy(
        self,
        preference: Preference
    ) -> Tuple[bool, Optional[str], Dict[str, Any]]:
        """Process privacy preference."""
        try:
            processed_data = {
                "privacy_updates": [],
                "warnings": [],
                "required_actions": []
            }
            
            # Process based on key
            if preference.key == "data_retention_days":
                if not isinstance(preference.value.value, int):
                    return (
                        False,
                        "Data retention days must be an integer",
                        None
                    )
                
                if preference.value.value < 1:
                    return (
                        False,
                        "Data retention days must be at least 1",
                        None
                    )
                
                if preference.value.value > 365:
                    processed_data["warnings"].append(
                        "Long retention periods may have privacy implications"
                    )
                
                processed_data["privacy_updates"].append(
                    f"Data retention set to {preference.value.value} days"
                )
                processed_data["required_actions"].append(
                    "Update data cleanup schedule"
                )
                
            elif preference.key == "analytics_enabled":
                if not isinstance(preference.value.value, bool):
                    return (
                        False,
                        "Analytics enabled value must be boolean",
                        None
                    )
                
                processed_data["privacy_updates"].append(
                    f"Analytics {'enabled' if preference.value.value else 'disabled'}"
                )
                
                if preference.value.value:
                    processed_data["warnings"].append(
                        "Enabling analytics will collect usage data"
                    )
                
            elif preference.key == "data_sharing":
                valid_levels = {"none", "minimal", "full"}
                if preference.value.value not in valid_levels:
                    return (
                        False,
                        f"Invalid sharing level. Must be one of: {valid_levels}",
                        None
                    )
                
                processed_data["privacy_updates"].append(
                    f"Data sharing set to {preference.value.value}"
                )
                
                if preference.value.value == "full":
                    processed_data["warnings"].append(
                        "Full data sharing enabled - review privacy policy"
                    )
                    processed_data["required_actions"].append(
                        "Update data sharing permissions"
                    )
            
            return True, None, processed_data
            
        except Exception as e:
            logger.error(f"Privacy processing failed: {str(e)}")
            return False, str(e), {}

    async def get_effective_preferences(
        self,
        category: Optional[PreferenceCategory] = None
    ) -> Dict[str, Any]:
        """
        Get current effective preferences.
        
        Args:
            category: Optional category filter
            
        Returns:
            Dict[str, Any]: Current effective preferences
        """
        effective = {}
        
        # Get recent preferences
        recent = self.context.get_recent_preferences(
            category=category,
            limit=100  # Get enough to cover all preferences
        )
        
        # Group by category and key
        grouped: Dict[str, Dict[str, List[Preference]]] = {}
        for pref in recent:
            cat = pref.category.value
            if cat not in grouped:
                grouped[cat] = {}
            if pref.key not in grouped[cat]:
                grouped[cat][pref.key] = []
            grouped[cat][pref.key].append(pref)
        
        # Get most recent for each category/key
        for cat, keys in grouped.items():
            if category and cat != category.value:
                continue
                
            effective[cat] = {}
            for key, prefs in keys.items():
                # Sort by timestamp (most recent first)
                sorted_prefs = sorted(
                    prefs,
                    key=lambda p: p.metadata.timestamp,
                    reverse=True
                )
                if sorted_prefs:
                    effective[cat][key] = {
                        "value": sorted_prefs[0].value.value,
                        "timestamp": sorted_prefs[0].metadata.timestamp,
                        "confidence": sorted_prefs[0].metadata.confidence
                    }
        
        return effective
    
    async def analyze_preferences(
        self,
        category: Optional[PreferenceCategory] = None
    ) -> Dict[str, Any]:
        """
        Analyze preference patterns.
        
        Args:
            category: Optional category filter
            
        Returns:
            Dict[str, Any]: Preference analysis
        """
        analysis = {
            "patterns": {},
            "conflicts": [],
            "suggestions": [],
            "statistics": {
                "total_preferences": 0,
                "by_category": {},
                "average_confidence": 0.0
            }
        }
        
        # Get preferences to analyze
        preferences = self.context.get_recent_preferences(category)
        if not preferences:
            return analysis
        
        # Calculate statistics
        analysis["statistics"]["total_preferences"] = len(preferences)
        confidence_sum = 0
        
        for pref in preferences:
            # Category stats
            cat = pref.category.value
            if cat not in analysis["statistics"]["by_category"]:
                analysis["statistics"]["by_category"][cat] = 0
            analysis["statistics"]["by_category"][cat] += 1
            
            # Confidence
            confidence_sum += pref.metadata.confidence
            
            # Look for patterns
            self._analyze_patterns(pref, analysis["patterns"])
            
            # Check for conflicts
            conflicts = self.relations.check_conflicts(pref, preferences)
            if conflicts:
                analysis["conflicts"].extend([
                    {
                        "preference": pref.id,
                        "conflicts_with": conflict[0].id,
                        "similarity": conflict[1]
                    }
                    for conflict in conflicts
                ])
        
        # Calculate average confidence
        analysis["statistics"]["average_confidence"] = (
            confidence_sum / len(preferences)
        )
        
        # Generate suggestions
        analysis["suggestions"] = self._generate_suggestions(
            analysis["patterns"],
            analysis["conflicts"]
        )
        
        return analysis
    
    def _analyze_patterns(
        self,
        preference: Preference,
        patterns: Dict[str, Any]
    ) -> None:
        """Analyze patterns in preference usage."""
        category = preference.category.value
        
        if category not in patterns:
            patterns[category] = {
                "common_values": {},
                "change_frequency": {},
                "related_preferences": []
            }
        
        # Track value frequencies
        value_key = f"{preference.key}:{str(preference.value.value)}"
        if value_key not in patterns[category]["common_values"]:
            patterns[category]["common_values"][value_key] = 0
        patterns[category]["common_values"][value_key] += 1
        
        # Track change frequency
        if preference.key not in patterns[category]["change_frequency"]:
            patterns[category]["change_frequency"][preference.key] = 0
        patterns[category]["change_frequency"][preference.key] += 1
        
        # Track related preferences
        related = self.relations.get_related_preferences(
            preference,
            min_strength=0.6
        )
        for rel_id, strength in related:
            patterns[category]["related_preferences"].append({
                "preference_id": rel_id,
                "relationship_strength": strength
            })
    
    def _generate_suggestions(
        self,
        patterns: Dict[str, Any],
        conflicts: List[Dict[str, Any]]
    ) -> List[str]:
        """Generate suggestions based on analysis."""
        suggestions = []
        
        # Suggest based on common values
        for category, data in patterns.items():
            common_values = data["common_values"]
            if common_values:
                most_common = max(
                    common_values.items(),
                    key=lambda x: x[1]
                )
                if most_common[1] >= 3:  # Threshold for suggestion
                    key, value = most_common[0].split(":", 1)
                    suggestions.append(
                        f"Consider making {value} the default for {key} "
                        f"in {category}"
                    )
        
        # Suggest based on conflicts
        if conflicts:
            suggestions.append(
                "Review conflicting preferences to ensure consistency"
            )
        
        # Suggest based on change frequency
        for category, data in patterns.items():
            frequent_changes = {
                k: v for k, v in data["change_frequency"].items()
                if v >= 3  # Threshold for frequent changes
            }
            if frequent_changes:
                for key in frequent_changes:
                    suggestions.append(
                        f"Consider stabilizing {key} preference in {category}"
                    )
        
        return suggestions
