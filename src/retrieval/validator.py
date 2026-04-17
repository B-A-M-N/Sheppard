"""
Response grounding validator for Phase 10.

Ensures that every factual claim in a response is supported by the corresponding
retrieved atom via lexical overlap, numeric consistency, and entity consistency.
"""

import re
from typing import List, Dict, Any, Optional, Tuple
from .models import RetrievedItem

# Comparative language patterns for derived claim detection
COMPARATIVE_PATTERNS = [
    r'\bexceeds?\b', r'\bexceeded\b',
    r'\bhigher\s*(than|by)?\b', r'\blower\s*(than|by)?\b',
    r'\bincreased\s*(by)?\b', r'\bdecreased\s*(by)?\b',
    r'\bdifference\s*(of)?\b',
    r'\bmore\s*than\b', r'\bless\s*than\b',
    r'\bfirst\b', r'\bsecond\b', r'\bthird\b',
    r'\branked\b', r'\btop\b', r'\bbottom\b',
    r'\bpercent\b', r'%',
]

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
    Excludes sentence-initial capitalized words (common false positives: "The", "A", etc.).
    """
    # Split into word tokens with position info
    words = re.findall(r'\b\w+\b', text)
    entities = []
    for i, word in enumerate(words):
        if len(word) <= 1:
            continue
        if any(c.isupper() for c in word):
            # Exclude sentence-initial capitalized words (false positives)
            # A word is "sentence-initial" if it's the first word OR preceded by sentence-ending punctuation
            if i == 0:
                continue
            prev_word = words[i - 1] if i > 0 else ''
            if prev_word.endswith('.') or prev_word.endswith('!') or prev_word.endswith('?'):
                continue
            entities.append(word)
    return entities

def _is_comparative_claim(text: str) -> bool:
    """Check if text contains comparative language indicating a derived claim."""
    return any(
        re.search(p, text, re.IGNORECASE) for p in COMPARATIVE_PATTERNS
    )


def _verify_derived_claim(
    text: str,
    claim_nums: List[str],
    citations: List[str],
    item_map: Dict[str, RetrievedItem],
) -> Dict[str, Any]:
    """
    Verify a derived (multi-atom numeric) claim.

    Given text containing a numeric relationship between 2+ cited atoms,
    recompute the expected value from the atom contents and compare to the claimed value.

    Returns:
        {'passed': True} or {'passed': False, 'errors': [...]}
    """
    if len(citations) < 2 or not claim_nums:
        return {'passed': True}

    # Look up cited atoms
    items = [item_map.get(c) for c in citations if c in item_map]
    if len(items) < 2:
        return {'passed': True}  # Can't verify → skip (existing path handles missing citations)

    claimed_value = None
    # The claimed number is typically the LAST numeric in the sentence (the relationship),
    # not the raw values that appear in the atoms. Filter out numbers already in atoms.
    atom_all_nums = set()
    for it in items:
        for n in extract_numbers(it.content):
            atom_all_nums.add(n.replace(',', ''))
    for num in claim_nums:
        norm_num = num.replace(',', '')
        if norm_num not in atom_all_nums:
            claimed_value = float(norm_num)

    if claimed_value is None:
        return {'passed': True}  # No unique number found → can't verify derived claim

    # Recompute from first two cited atoms
    atom_a = items[0]
    atom_b = items[1]

    a_nums = extract_numbers(atom_a.content)
    b_nums = extract_numbers(atom_b.content)

    if not a_nums or not b_nums:
        return {'passed': True}  # No numbers in atoms → skip (can't derive)

    a_val = float(a_nums[0].replace(',', ''))
    b_val = float(b_nums[0].replace(',', ''))

    # Determine expected value based on comparative language
    text_lower = text.lower()

    # Delta: "exceeds by X", "difference of X"
    if _is_delta_pattern(text_lower):
        expected = a_val - b_val
        if abs(claimed_value - expected) > 1e-9:
            return {
                'passed': False,
                'errors': [
                    f"Derived claim mismatch: claimed delta {claimed_value}, "
                    f"computed {a_val} - {b_val} = {expected} from citations {citations[0]}, {citations[1]}."
                ]
            }

    # Percent change: "X% higher/lower", "increased/decreased by X%"
    elif r'\bpercent\b' in text_lower or '%' in text_lower:
        if a_val == 0:
            return {'passed': True}  # Skip division by zero
        expected_pct = ((b_val - a_val) / a_val) * 100.0
        # Handle "higher/lower" language: if text says "X% lower", claimed is negative
        if 'lower' in text_lower or 'decrease' in text_lower or 'dropped' in text_lower:
            # Text expresses decrease as positive number: "25% lower" means -25%
            if claimed_value > 0 and expected_pct < 0:
                claimed_value = -claimed_value
        if abs(claimed_value - expected_pct) > 1e-9:
            return {
                'passed': False,
                'errors': [
                    f"Derived claim mismatch: claimed {claimed_value}%, "
                    f"computed (({b_val} - {a_val}) / {a_val}) * 100 = {expected_pct}% "
                    f"from citations {citations[0]}, {citations[1]}."
                ]
            }

    # Default: no specific rule matched → skip verification
    return {'passed': True}


def _is_delta_pattern(text_lower: str) -> bool:
    """Check if text expresses a delta relationship."""
    delta_patterns = [
        r'\bexceeds?\b', r'\bexceeded\b',
        r'\bdifference\s*(of)?\b',
        r'\bhigher\s*(than|by)?\b', r'\blower\s*(than|by)?\b',
    ]
    return any(re.search(p, text_lower) for p in delta_patterns)


def _normalize_citation_key(citation: str) -> str:
    """Normalize citation markers so `[A1]` and `A1` resolve to the same key."""
    return citation.strip()[1:-1] if citation.strip().startswith('[') and citation.strip().endswith(']') else citation.strip()


def _combined_cited_content(
    citations: List[str],
    item_map: Dict[str, RetrievedItem],
) -> str:
    """Combine all cited atom content into one validation surface."""
    return " ".join(
        item_map[c].content
        for c in citations
        if c in item_map and item_map[c].content
    )


def _validate_multi_citation_block(
    text: str,
    citations: List[str],
    item_map: Dict[str, RetrievedItem],
    claim_nums: List[str],
    has_comparative_language: bool,
) -> Tuple[List[str], List[Dict[str, Any]]]:
    """
    Validate a block grounded by multiple citations against the combined evidence.

    This is more permissive than single-citation validation because a multi-atom
    sentence may intentionally distribute its support across several cited atoms.
    """
    errors: List[str] = []
    details: List[Dict[str, Any]] = []

    missing = [c for c in citations if c not in item_map]
    for cite in missing:
        errors.append(f"Citation [{cite}] referenced but not found in retrieved items.")
        details.append({'claim': text, 'cited': cite, 'error': 'citation_not_found'})

    present = [c for c in citations if c in item_map]
    if not present:
        return errors, details

    combined_content = _combined_cited_content(present, item_map)

    claim_words = set(tokenize(text))
    atom_words = set(tokenize(combined_content))
    content_words = claim_words - STOPWORDS
    overlap = content_words & atom_words
    if len(overlap) < 2:
        errors.append(
            f"Insufficient lexical overlap for citations {', '.join(present)}: "
            f"only {len(overlap)} content words in common."
        )
        details.append({
            'claim': text,
            'cited': present,
            'error': 'lexical_overlap',
            'overlap_count': len(overlap),
        })

    if has_comparative_language and claim_nums:
        derived_validated = _verify_derived_claim(text, claim_nums, present, item_map)
        if not derived_validated['passed']:
            errors.extend(derived_validated['errors'])
            for err in derived_validated['errors']:
                details.append({
                    'claim': text,
                    'cited': present,
                    'error': 'derived_mismatch',
                    'detail': err,
                })
    else:
        combined_nums = {n.replace(',', '') for n in extract_numbers(combined_content)}
        for num in claim_nums:
            norm_num = num.replace(',', '')
            if norm_num not in combined_nums:
                errors.append(
                    f"Number '{num}' in claim not present in combined supporting atoms "
                    f"{', '.join(present)}."
                )
                details.append({
                    'claim': text,
                    'cited': present,
                    'error': 'number_mismatch',
                    'number': num,
                })

    claim_entities = extract_entities(text)
    combined_lower = combined_content.lower()
    for ent in claim_entities:
        if ent.lower() not in combined_lower:
            errors.append(
                f"Entity '{ent}' in claim not present in combined supporting atoms "
                f"{', '.join(present)}."
            )
            details.append({
                'claim': text,
                'cited': present,
                'error': 'entity_missing',
                'entity': ent,
            })

    return errors, details


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
            normalized = _normalize_citation_key(item.citation_key)
            item_map[item.citation_key] = item
            item_map[normalized] = item

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

    # Collect all citations for each text block
    # Merge segments where multiple citations follow the same text
    merged_segments: List[Dict[str, Any]] = []
    for seg in segments:
        text = seg['text'].strip()
        cite = seg['citation']
        if text:
            # Start of a new text block
            merged_segments.append({'text': text, 'citations': [cite] if cite else []})
        elif cite:
            # Citation-only segment — append to previous text block
            if merged_segments:
                merged_segments[-1]['citations'].append(cite)

    # If the response ends with text without a citation, that last segment will have no citation.
    # That's okay if it's just a concluding phrase; but we'll flag it if it contains substantive claims.
    # We will treat uncited text as a claim without citation -> error.

    for seg in merged_segments:
        text = seg['text']
        citations = seg['citations']  # List of all citations for this text block

        if not text or not re.search(r'\w', text):
            continue

        # Filter out None citations
        valid_citations = [_normalize_citation_key(c) for c in citations if c is not None]

        # If segment has no citation, it's uncited
        if not valid_citations:
            errors.append(f"Uncited claim: '{text[:60]}...'")
            details.append({'claim': text, 'cited': False, 'error': 'missing_citation'})
            continue

        # --- Derived claim detection (Phase 12-B) ---
        # If segment cites 2+ atoms AND contains numbers AND comparative language,
        # treat as derived claim → skip single-atom numeric check, verify multi-atom instead.
        claim_nums = extract_numbers(text)
        has_comparative_language = any(
            re.search(p, text, re.IGNORECASE) for p in COMPARATIVE_PATTERNS
        )
        is_multi_citation = len(valid_citations) >= 2

        if is_multi_citation and claim_nums and has_comparative_language:
            # Derived claim detected: verify the numeric relationship against cited atoms
            derived_validated = _verify_derived_claim(text, claim_nums, valid_citations, item_map)
            if not derived_validated['passed']:
                errors.extend(derived_validated['errors'])
                for err in derived_validated['errors']:
                    details.append({'claim': text, 'cited': valid_citations, 'error': 'derived_mismatch', 'detail': err})
            # Continue with lexical/entity checks for derived claims too
        # else: skip derived check (single citation or no comparative language) -> existing path

        if is_multi_citation:
            block_errors, block_details = _validate_multi_citation_block(
                text=text,
                citations=valid_citations,
                item_map=item_map,
                claim_nums=claim_nums,
                has_comparative_language=has_comparative_language,
            )
            errors.extend(block_errors)
            details.extend(block_details)
            details.append({'claim': text, 'cited': valid_citations, 'valid': len(block_errors) == 0})
            continue

        # --- Existing checks for single-citation segments ---
        for cite in valid_citations:
            # Look up the cited item
            if cite not in item_map:
                errors.append(f"Citation [{cite}] referenced but not found in retrieved items.")
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
                errors.append(f"Insufficient lexical overlap for [{cite}]: only {len(overlap)} content words in common.")
                details.append({'claim': text, 'cited': cite, 'error': 'lexical_overlap', 'overlap_count': len(overlap)})

            # --- Numeric Consistency (SKIP for derived claims) ---
            # Derived claims are verified via _verify_derived_claim above.
            # For single-citation claims, existing numeric check still runs.
            if not (is_multi_citation and claim_nums and has_comparative_language):
                atom_nums = extract_numbers(atom_content)
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
                    # Also check if entity appears anywhere in the atom text (case-insensitive)
                    if ent.lower() not in atom_content.lower():
                        errors.append(f"Entity '{ent}' in claim {cite} not present in supporting atom.")
                        details.append({'claim': text, 'cited': cite, 'error': 'entity_missing', 'entity': ent})

        # If all checks passed for this segment, note success
        details.append({'claim': text, 'cited': valid_citations, 'valid': True})

    is_valid = len(errors) == 0
    return {
        'is_valid': is_valid,
        'errors': errors,
        'details': details
    }
