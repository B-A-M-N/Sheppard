"""
Response grounding validator for Phase 10.

Ensures that every factual claim in a response is supported by the corresponding
retrieved atom via lexical overlap, numeric consistency, and entity consistency.
"""

import re
from typing import List, Dict, Any, Tuple, Optional
from .models import RetrievedItem

# Common English stopwords to ignore during lexical overlap comparison
STOPWORDS = {
    # Articles, conjunctions, prepositions, pronouns, auxiliaries
    "a", "an", "the", "and", "or", "but", "if", "because", "as", "until", "while", "of", "at", "by", "for", "with", "about", "against", "between", "into", "through", "during", "before", "after", "above", "below", "to", "from", "up", "down", "in", "out", "on", "off", "over", "under", "again", "further", "then", "once", "here", "there", "when", "where", "why", "how",
    "all", "any", "both", "each", "few", "more", "most", "other", "some", "such", "no", "nor", "not", "only", "own", "same", "so", "than", "too", "very",
    # Personal pronouns
    "i", "you", "he", "she", "it", "we", "they", "me", "him", "her", "us", "them", "my", "your", "his", "its", "our", "their", "mine", "yours", "hers", "ours", "theirs",
    # Possessive determiners
    "its", "our", "their",
    # Auxiliary verbs
    "is", "am", "are", "was", "were", "be", "been", "being", "have", "has", "had", "do", "does", "did", "will", "would", "shall", "should", "can", "could", "may", "might", "must", "ought", "i'm", "you're", "he's", "she's", "it's", "we're", "they're", "i've", "you've", "we've", "they've", "i'd", "you'd", "he'd", "she'd", "we'd", "they'd", "i'll", "you'll", "he'll", "she'll", "we'll", "they'll",
    # Contractions
    "aren", "couldn", "didn", "doesn", "hadn", "hasn", "haven", "isn", "ma", "mightn", "mustn", "needn", "shan", "shouldn", "wasn", "weren", "won", "wouldn", "don", "doesn", "didn", "haven", "hasn", "hadn", "wasn", "weren", "wouldn", "shouldn", "couldn", "mightn", "mustn", "needn", "shan", "aren", "isn", "wasn", "weren", "don", "didn", "won", "can", "will", "just", "now", "d", "ll", "m", "o", "re", "ve", "y", "ain",
    # Common adverbs and interjections that are not content
    "well", "oh", "ah", "uh", "um", "eh", "like", "so", "just", "now", "then", "here", "there",
}

def tokenize(text: str) -> List[str]:
    """
    Split text into lowercase alphanumeric tokens.
    Removes punctuation and splits on non-word characters.
    """
    return [token for token in re.split(r'\W+', text.lower()) if token]

def extract_numbers(text: str) -> List[str]:
    """
    Extract numeric strings from text. Matches integers, decimals with optional commas.
    Examples: "100", "1,000", "3.14".
    """
    # Pattern: digit optionally followed by groups of comma+digits, optional decimal part
    pattern = r'\d[\d,]*\.?\d*'
    matches = re.findall(pattern, text)
    # Strip any trailing period (e.g., from "1,000,000.") that may have been captured
    cleaned = [m.rstrip('.') for m in matches]
    return cleaned

def extract_entities(text: str) -> List[str]:
    """
    Extract candidate named entities using a simple heuristic:
    Any word (length > 1) containing at least one uppercase letter, excluding words that are all lowercase.
    This captures proper nouns, acronyms, and mixed-case words like "SpaceX".
    """
    # Split into word tokens
    words = re.findall(r'\b\w+\b', text)
    entities = [word for word in words if any(c.isupper() for c in word) and len(word) > 1]
    return entities

def validate_response_grounding(
    response_text: str,
    retrieved_items: List[RetrievedItem]
) -> Dict[str, Any]:
    """
    Validate that each claim in the response is grounded in its cited atom.

    The response must contain citations [A###] linking to items in retrieved_items.
    The validation checks lexical overlap (>=2 content words), numeric consistency,
    and entity consistency for each claim-citation pair.

    Args:
        response_text: The full response string from the LLM.
        retrieved_items: List of RetrievedItem objects, each with a citation_key set.

    Returns:
        A dictionary with keys:
          - is_valid (bool): True if all checks pass.
          - errors (list of str): Human-readable error messages.
          - details (list of dict): Per-segment validation details.
    """
    errors: List[str] = []
    details: List[Dict[str, Any]] = []

    # Build a mapping from citation_key to RetrievedItem
    item_map: Dict[str, RetrievedItem] = {}
    for item in retrieved_items:
        if item.citation_key:
            item_map[item.citation_key] = item

    # Split the response into text segments and citation markers
    # Pattern matches [A001] etc.
    citation_pattern = r'(\[[A-Za-z0-9]+\])'
    parts = re.split(citation_pattern, response_text)

    # Reconstruct alternating segments: text, citation, text, citation, ...
    segments: List[Dict[str, Optional[str]]] = []
    for i, part in enumerate(parts):
        if i % 2 == 0:
            # text segment
            segments.append({'text': part, 'citation': None})
        else:
            # citation marker
            if segments:
                segments[-1]['citation'] = part
            else:
                # Citation at start? That's odd but treat as separate segment
                segments.append({'text': '', 'citation': part})

    # If the response ends with text without a citation, that last segment will have no citation.
    # That's okay if it's just a concluding phrase; but we'll flag it if it contains substantive claims.
    # We will treat uncited text as a claim without citation -> error.

    for seg in segments:
        text = seg['text'].strip()
        cite = seg['citation']

        if not text:
            continue

        # If segment has no citation, it's uncited
        if not cite:
            errors.append(f"Uncited claim: '{text[:60]}...'")
            details.append({'claim': text, 'cited': False, 'error': 'missing_citation'})
            continue

        # Look up the cited item
        if cite not in item_map:
            errors.append(f"Citation {cite} referenced but not found in retrieved items.")
            details.append({'claim': text, 'cited': cite, 'error': 'citation_not_found'})
            continue

        atom = item_map[cite]
        atom_content = atom.content

        # --- Lexical Overlap ---
        claim_words = set(tokenize(text))
        atom_words = set(tokenize(atom_content))
        content_words = claim_words - STOPWORDS
        overlap = content_words & atom_words
        if len(overlap) < 2:
            errors.append(f"Insufficient lexical overlap for {cite}: only {len(overlap)} content words in common.")
            details.append({'claim': text, 'cited': cite, 'error': 'lexical_overlap', 'overlap_count': len(overlap)})

        # --- Numeric Consistency ---
        claim_nums = extract_numbers(text)
        atom_nums = extract_numbers(atom_content)
        # Normalize numbers by removing commas for comparison
        norm_atom_nums = [n.replace(',', '') for n in atom_nums]
        for num in claim_nums:
            norm_num = num.replace(',', '')
            if norm_num not in norm_atom_nums:
                errors.append(f"Number '{num}' in claim {cite} not present in supporting atom.")
                details.append({'claim': text, 'cited': cite, 'error': 'number_mismatch', 'number': num})

        # --- Entity Consistency ---
        claim_entities = extract_entities(text)
        atom_entities = [e.lower() for e in extract_entities(atom_content)]
        for ent in claim_entities:
            if ent.lower() not in atom_entities:
                errors.append(f"Entity '{ent}' in claim {cite} not present in supporting atom.")
                details.append({'claim': text, 'cited': cite, 'error': 'entity_missing', 'entity': ent})

        # If all checks passed for this segment, note success
        details.append({'claim': text, 'cited': cite, 'valid': True})

    is_valid = len(errors) == 0
    return {
        'is_valid': is_valid,
        'errors': errors,
        'details': details
    }
