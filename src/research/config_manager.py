"""
Configuration management for research system.
"""

import logging
from typing import Dict, Any, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)

class ConfigurationManager:
    """Manages research system configuration."""
    
    def __init__(self):
        """Initialize configuration manager."""
        self.category_settings = {
            'travel': {
                'min_reliability': 0.6,
                'max_pages': 8,
                'required_terms': ['destination', 'trip', 'visit', 'vacation', 'tour', 'travel'],
                'exclude_terms': ['ticket', 'booking', 'cheap', 'deal']
            },
            'general': {
                'min_reliability': 0.7,
                'max_pages': 5,
                'required_terms': [],
                'exclude_terms': ['ad', 'sponsored', 'promotion']
            }
        }
        
        self.trusted_domains = {
            'wikipedia.org': 0.9,
            'britannica.com': 0.95,
            'nationalgeographic.com': 0.95,
            '.gov': 0.95,
            '.edu': 0.9
        }
        
        self.fallback_sources = {
            'travel': [
                'https://www.lonelyplanet.com/articles',
                'https://www.nationalgeographic.com/travel'
            ],
            'general': [
                'https://www.wikipedia.org',
                'https://www.britannica.com'
            ]
        }
    
    def get_category_settings(self, category: str) -> Dict[str, Any]:
        """Get settings for a specific category."""
        return self.category_settings.get(category, self.category_settings['general'])
    
    def get_trusted_domains(self) -> Dict[str, float]:
        """Get trusted domain configurations."""
        return self.trusted_domains.copy()
    
    def get_fallback_sources(self, category: str) -> list:
        """Get fallback sources for a category."""
        return self.fallback_sources.get(category, self.fallback_sources['general']).copy()
    
    def update_category_settings(self, category: str, settings: Dict[str, Any]) -> None:
        """Update settings for a category."""
        if category in self.category_settings:
            self.category_settings[category].update(settings)
        else:
            self.category_settings[category] = settings
    
    def add_trusted_domain(self, domain: str, reliability: float) -> None:
        """Add a new trusted domain."""
        self.trusted_domains[domain] = min(1.0, max(0.0, reliability))
    
    def add_fallback_source(self, category: str, source: str) -> None:
        """Add a new fallback source for a category."""
        if category not in self.fallback_sources:
            self.fallback_sources[category] = []
        if source not in self.fallback_sources[category]:
            self.fallback_sources[category].append(source)
            
    def get_config_status(self) -> Dict[str, Any]:
        """Get configuration status information."""
        return {
            'categories': list(self.category_settings.keys()),
            'trusted_domains': len(self.trusted_domains),
            'fallback_sources': {
                category: len(sources) 
                for category, sources in self.fallback_sources.items()
            }
        }
