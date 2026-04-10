"""
source_classifier.py — Fast source quality gating (string-based).

Classifies sources before extraction to skip dictionaries, nav pages, etc.
"""

from src.utils.llm_schemas import _LOW_VALUE_SOURCE_PATTERNS

# Additional hard-skip domains that were slipping through
_HARD_SKIP_DOMAINS = [
    "oed.com", "merriam-webster.com", "cambridge.org/dictionary",
    "dictionary.com", "lexico.com", "collinsdictionary.com",
    "thefreedictionary.com", "wordreference.com", "urbanup.com",
    "definitions.net", "encyclopedia.com", "britannica.com/dictionary",
]


def classify_source_quality(url: str, content: str) -> str:
    """Classify source before extraction. Returns 'skip', 'standard', 'academic'."""
    url_lower = url.lower() if url else ''

    # Hard skip: dictionary/reference domains (explicit list)
    for domain in _HARD_SKIP_DOMAINS:
        if domain in url_lower:
            return 'skip'

    # Hard skip: lexical entries, definitions-only pages
    for pattern in _LOW_VALUE_SOURCE_PATTERNS:
        if pattern in url_lower:
            return 'skip'

    # Also check content for dictionary-like patterns (URL might be masked/redirected)
    if url_lower and not any(x in url_lower for x in ['arxiv.org', 'ieee.org', 'acm.org', 'springer.com', 'nature.com', '.edu/', 'doi.org']):
        content_lower = content[:500].lower() if content else ''
        dict_indicators = [
            'see the full definition', 'meaning of', 'pronunciation of',
            'first known use', 'noun (as defined in', 'verb (as defined in',
            'kids definition', 'medical definition', 'legal definition',
            'subscribe to access', 'start your free trial',
        ]
        matches = sum(1 for ind in dict_indicators if ind in content_lower)
        if matches >= 2:
            return 'skip'

    if any(x in url_lower for x in ['arxiv.org', 'ieee.org', 'acm.org', 'springer.com', 'nature.com', '.edu/', 'doi.org']):
        return 'academic'

    return 'standard'
