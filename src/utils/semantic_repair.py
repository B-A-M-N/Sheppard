"""
semantic_repair.py — Semantic Recovery Layer for Atom Extraction

Repairs broken atom extractions BEFORE discarding them.
Replaces the old: extract → reject → lose pipeline
With: extract → diagnose → repair → re-evaluate

Repair strategies:
  1. Fragment repair: incomplete sentences → complete factual statements
  2. Overlong split: multi-claim blobs → individual atoms
  3. Low-quality rewrite: vague/ambiguous → precise, self-contained
  4. Meta-statement conversion: "This paper shows..." → direct factual claim

All repairs are attempted locally first (cheap), then LLM-assisted if needed.
"""

import re
import logging
from typing import List, Dict, Any, Optional, Tuple

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# DIAGNOSIS
# ─────────────────────────────────────────────


def diagnose_atom(content: str) -> List[str]:
    """
    Classify what's wrong with an atom. Multiple diagnoses possible.

    Returns list of diagnosis tags:
      - 'fragment': no verb, incomplete thought
      - 'overlong': >200 chars, likely multiple claims
      - 'vague': ambiguous pronouns, no concrete subject
      - 'meta': refers to document structure ("this paper", "we show")
      - 'url_heavy': too many URLs, not factual
      - 'list_item': bullet fragment without context
    """
    diagnoses = []
    if not content or len(content) < 10:
        return ['fragment']

    # Fragment: no verb detected
    if not _has_verb(content):
        diagnoses.append('fragment')

    # Overlong: likely contains multiple claims
    if len(content) > 200:
        diagnoses.append('overlong')

    # Vague: starts with pronoun or demonstrative without clear referent
    vague_starts = ['it ', 'they ', 'this ', 'that ', 'these ', 'those ', 'its ']
    if any(content.lower().startswith(v) for v in vague_starts):
        diagnoses.append('vague')

    # Meta-statement: references document/paper/author rather than facts
    meta_patterns = [
        r'\b(this paper|this article|this document|this study|this blog)\b',
        r'\b(we show|we propose|we found|we introduce|we present)\b',
        r'\b(the authors show|the paper discusses|the article explains)\b',
        r'\b(according to the (document|paper|article|blog))\b',
    ]
    if any(re.search(p, content, re.IGNORECASE) for p in meta_patterns):
        diagnoses.append('meta')

    # URL-heavy: more URLs than words
    url_count = len(re.findall(r'https?://', content))
    word_count = len(content.split())
    if url_count > 0 and url_count * 3 > word_count:
        diagnoses.append('url_heavy')

    # List fragment: starts with bullet/number marker mid-thought
    if re.match(r'^[\-\*\•]\s+', content) or re.match(r'^[a-z]\)\s+', content):
        diagnoses.append('list_item')

    return diagnoses


# ─────────────────────────────────────────────
# CHEAP LOCAL REPAIRS (no LLM)
# ─────────────────────────────────────────────


def repair_fragment_local(content: str, topic: str = '') -> Optional[str]:
    """
    Attempt to repair a fragment without LLM.
    Works for: noun phrases, prepositional fragments, list items.
    """
    content = content.strip()
    if not content:
        return None

    # Strip bullet/number prefixes
    content = re.sub(r'^[\-\*\•]\s+', '', content)
    content = re.sub(r'^\d+[\.\)]\s+', '', content)

    # If it's just a noun phrase, convert to "X is [topic-related]" statement
    if not _has_verb(content) and len(content.split()) <= 8:
        # Capitalize and add period — minimal repair
        content = content[0].upper() + content[1:] if len(content) > 1 else content
        if not content.endswith(('.', '!', '?')):
            content = content + '.'
        # Only return if it's at least minimally informative
        if len(content.split()) >= 3:
            return content
        return None

    # Strip trailing prepositional phrases that make it fragmentary
    # e.g., "Using CRNNs with convolutional layers for" → keep what we have
    trailing_prep = re.search(r'\b(for|with|by|in|on|at|to|from)\s*$', content, re.IGNORECASE)
    if trailing_prep:
        # Remove the trailing preposition
        content = re.sub(r'\s+\b(for|with|by|in|on|at|to|from)\s*$', '.', content, flags=re.IGNORECASE)
        return content if len(content) >= 15 else None

    return None


def repair_meta_local(content: str) -> Optional[str]:
    """
    Convert meta-statements to direct claims.
    "This paper shows that X is Y" → "X is Y"
    "We propose a novel approach for X" → "A novel approach for X is proposed"
    """
    # "This paper/article/document shows/demonstrates/proves that ..."
    that_match = re.search(
        r'(?:this paper|this article|this document|this study|this blog|we show|we found|we propose)\s+(?:that\s+)?(.+?)(?:\.|$)',
        content, re.IGNORECASE
    )
    if that_match:
        claim = that_match.group(1).strip()
        if len(claim) >= 15 and _has_verb(claim):
            claim = claim[0].upper() + claim[1:] if len(claim) > 1 else claim
            if not claim.endswith(('.', '!', '?')):
                claim += '.'
            return claim

    # "The authors show/demonstrate that ..."
    author_match = re.search(
        r'(?:the authors|the researchers|the team)\s+(?:show|demonstrate|found|propose)\s+(?:that\s+)?(.+?)(?:\.|$)',
        content, re.IGNORECASE
    )
    if author_match:
        claim = author_match.group(1).strip()
        if len(claim) >= 15 and _has_verb(claim):
            return claim

    # "According to X, ..." → keep the claim part
    according_match = re.search(
        r'according to [^,]+,\s*(.+?)(?:\.|$)',
        content, re.IGNORECASE
    )
    if according_match:
        claim = according_match.group(1).strip()
        if len(claim) >= 15 and _has_verb(claim):
            claim = claim[0].upper() + claim[1:] if len(claim) > 1 else claim
            if not claim.endswith(('.', '!', '?')):
                claim += '.'
            return claim

    return None


def split_overlong(content: str) -> List[str]:
    """
    Split an overlong atom into individual claims by sentence boundary.
    Each resulting sentence becomes a candidate atom.
    """
    if len(content) <= 200:
        return [content]

    # Split on sentence boundaries
    sentences = re.split(r'(?<=[.!?])\s+', content)
    sentences = [s.strip() for s in sentences if s.strip() and len(s) >= 15]

    if not sentences:
        return [content[:200]]  # Last resort

    # Validate each sentence has a verb
    valid = []
    for s in sentences:
        if _has_verb(s) and len(s.split()) >= 5:
            if not s.endswith(('.', '!', '?')):
                s += '.'
            valid.append(s)

    return valid if valid else [content[:200]]


def repair_vague_local(content: str) -> Optional[str]:
    """
    Repair vague pronouns by making the subject explicit where possible.
    "It achieves 95% accuracy" → "The method achieves 95% accuracy"
    """
    replacements = {
        'it achieves': 'The method achieves',
        'it uses': 'The approach uses',
        'it provides': 'The system provides',
        'it consists': 'The architecture consists',
        'it is': 'This approach is',
        'they achieve': 'The authors achieve',
        'they found': 'The researchers found',
        'they propose': 'The authors propose',
        'they use': 'The researchers use',
        'this approach': 'The proposed approach',
        'this method': 'The proposed method',
        'this model': 'The proposed model',
        'these results': 'The experimental results',
    }

    lower = content.lower()
    for pattern, replacement in replacements.items():
        if lower.startswith(pattern):
            repaired = replacement + content[len(pattern):]
            return repaired

    return None


# ─────────────────────────────────────────────
# LLM-ASSISTED REPAIR
# ─────────────────────────────────────────────

_REPAIR_PROMPT = """Convert the following text into a single factual, self-contained statement.

Rules:
- Preserve the original meaning exactly — do NOT add new facts
- You must preserve all qualifiers, caveats, version bounds, environment-specific conditions,
  negative conditions, and comparative wording.
- Do not generalize a bounded claim into a universal one.
- If the original is awkward but semantically precise, preserve precision over readability.
- Remove fragments and incomplete thoughts
- Remove meta-references ("this paper", "we show", "according to")
- Make it standalone: understandable without any external context
- Output exactly 1 sentence ending with a period
- Use third person ("the model", "the method", not "our" or "we")

TEXT TO REPAIR:
{text}

OUTPUT ONLY the repaired sentence, nothing else."""


async def repair_with_llm(content: str, topic: str, llm_client) -> Optional[str]:
    """
    Use LLM to repair an atom that local repairs couldn't fix.
    Temperature=0 for deterministic repair.
    """
    prompt = _REPAIR_PROMPT.format(text=content[:300])

    try:
        messages = [{"role": "user", "content": prompt}]
        response = ""
        async for chunk in llm_client.chat(messages=messages, stream=True, temperature=0.0, max_tokens=256):
            if hasattr(chunk, 'content') and chunk.content:
                response += chunk.content

        response = response.strip()
        # Clean up: extract first sentence if LLM added commentary
        first_sentence = re.split(r'(?<=[.!?])\s+', response)[0]
        if len(first_sentence) >= 15 and _has_verb(first_sentence):
            if not first_sentence.endswith(('.', '!', '?')):
                first_sentence += '.'
            return first_sentence
        return None

    except Exception as e:
        logger.debug(f"[SemanticRepair] LLM repair failed: {e}")
        return None


# ─────────────────────────────────────────────
# MAIN REPAIR ENTRY POINT
# ─────────────────────────────────────────────


async def repair_atom(
    atom: Dict[str, Any],
    topic: str,
    llm_client=None,
    use_llm: bool = True
) -> Optional[Dict[str, Any]]:
    """
    Attempt to repair a single atom through escalating strategies.

    Strategy order (cheap → expensive):
    1. Local repairs (fragment, meta, vague, overlong split)
    2. LLM-assisted repair (if local fails and use_llm=True)
    3. Return None if unrepairable

    Returns repaired atom dict or None.
    """
    content = atom.get('text', atom.get('content', ''))
    if not content:
        return None

    diagnoses = diagnose_atom(content)
    if not diagnoses:
        return atom  # No issues, return as-is

    repaired_content = None

    # Try local repairs based on diagnosis
    for diagnosis in diagnoses:
        if diagnosis == 'fragment':
            repaired_content = repair_fragment_local(content, topic)
        elif diagnosis == 'meta':
            repaired_content = repair_meta_local(content)
        elif diagnosis == 'vague':
            repaired_content = repair_vague_local(content)
        elif diagnosis == 'overlong':
            # For overlong, split and return first valid sentence
            splits = split_overlong(content)
            if len(splits) > 1:
                # Return the best (longest) split as the repaired atom
                repaired_content = max(splits, key=len)
            else:
                repaired_content = splits[0] if splits else None
        elif diagnosis == 'url_heavy':
            # Strip URLs and try again
            stripped = re.sub(r'https?://\S+', '', content).strip()
            stripped = re.sub(r'\s+', ' ', stripped)
            if len(stripped) >= 15 and _has_verb(stripped):
                if not stripped.endswith(('.', '!', '?')):
                    stripped += '.'
                repaired_content = stripped
        elif diagnosis == 'list_item':
            repaired_content = repair_fragment_local(content, topic)

        if repaired_content:
            break

    # If local repairs failed, try LLM
    if not repaired_content and use_llm and llm_client:
        repaired_content = await repair_with_llm(content, topic, llm_client)

    if not repaired_content:
        return None  # Unrepairable

    # Validate the repair
    if len(repaired_content) < 15 or not _has_verb(repaired_content):
        return None  # Repair didn't produce a valid atom

    # Return repaired atom, preserving original metadata but marking it
    return {
        "type": atom.get("type", "claim"),
        "content": content,
        "text": content,
        "normalized_text": repaired_content,
        "confidence": atom.get("confidence", 0.5) * 0.85,  # Penalty for repaired atoms
        "repaired": True,
        "original": content,
        "repair_notes_json": {
            "mode": "overlay",
            "reason": ",".join(diagnoses),
            "original_text": content,
            "normalized_text": repaired_content,
        },
    }


async def repair_atom_batch(
    atoms: List[Dict[str, Any]],
    topic: str,
    llm_client=None,
    use_llm: bool = True,
    max_llm_repairs: int = 10
) -> List[Dict[str, Any]]:
    """
    Repair a batch of atoms. Returns list of valid (original + repaired) atoms.
    Limits LLM calls to prevent runaway costs.
    """
    result = []
    llm_calls = 0

    for atom in atoms:
        content = atom.get('text', atom.get('content', ''))
        diagnoses = diagnose_atom(content)

        if not diagnoses:
            result.append(atom)  # Already valid
            continue

        # Attempt repair
        repaired = await repair_atom(atom, topic, llm_client, use_llm=use_llm and llm_calls < max_llm_repairs)
        if repaired:
            result.append(repaired)
            if repaired.get('repaired'):
                llm_calls += 1
            logger.debug(
                f"[SemanticRepair] Repaired atom: {content[:60]}... → {repaired['content'][:60]}..."
            )
        else:
            logger.debug(f"[SemanticRepair] Unrepairable atom: {content[:80]}...")

    return result


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

def _has_verb(text: str) -> bool:
    """Cheap heuristic: does this sentence have a verb-like word?"""
    verb_patterns = [
        ' is ', ' are ', ' was ', ' were ', ' has ', ' have ', ' had ',
        ' can ', ' could ', ' will ', ' would ', ' should ', ' may ',
        ' uses ', ' used ', ' using ', ' provides ', ' achieves ',
        ' reduces ', ' increases ', ' improves ', ' shows ',
        ' demonstrates ', ' implements ', ' requires ', ' supports ',
        ' enables ', ' allows ', ' prevents ', ' detects ', ' generates ',
        ' trains ', ' trained ', ' predicts ', ' evaluates ', ' compares ',
        ' consists ', ' contains ', ' produces ', ' creates ',
    ]
    text_lower = text.lower()
    return any(v in text_lower for v in verb_patterns)
