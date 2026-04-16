"""
normalize_atom_schema.py — Single compatibility layer for atom field names.

Maps LLM/legacy field names to V3 canonical names.
This is the ONLY place that handles field name transitions.
All downstream code must use canonical names only.
"""
import logging

logger = logging.getLogger(__name__)

# Categorical importance/novelty → numeric mapping
_IMPORTANCE_MAP = {"low": 0.2, "medium": 0.5, "high": 0.85}
_NOVELTY_MAP = {"low": 0.2, "medium": 0.5, "high": 0.85}


def normalize_atom_schema(atom: dict) -> dict:
    """
    Map LLM/legacy field names to V3 canonical names.

    Canonical mappings:
      content   -> text  (LLM response -> V3 KnowledgeUnit)
      statement -> text  (legacy synthesis field)
      fact      -> text  (emergency fallback field)

    Also converts categorical importance/novelty to numeric.
    """
    result = dict(atom)  # shallow copy — do not mutate input

    # Map primary legacy keys to canonical 'text'
    if "text" not in result:
        if "content" in result:
            result["text"] = result.pop("content")
        elif "statement" in result:
            result["text"] = result.pop("statement")
        elif "fact" in result:
            result["text"] = result.pop("fact")

    # Remove any remaining legacy keys to prevent dual-key confusion
    for legacy_key in ("content", "statement", "fact"):
        result.pop(legacy_key, None)

    # Convert categorical importance/novelty to numeric
    # NOTE: If LLM doesn't provide these, they remain None — downstream MUST compute them
    imp = result.get("importance")
    if isinstance(imp, str) and imp.lower() in _IMPORTANCE_MAP:
        result["importance"] = _IMPORTANCE_MAP[imp.lower()]
    elif imp is None or not isinstance(imp, (int, float)):
        if imp is not None:
            logger.debug(f"[normalize] Invalid importance value: {imp!r} → None (downstream must compute)")
        result["importance"] = None

    nov = result.get("novelty")
    if isinstance(nov, str) and nov.lower() in _NOVELTY_MAP:
        result["novelty"] = _NOVELTY_MAP[nov.lower()]
    elif nov is None or not isinstance(nov, (int, float)):
        if nov is not None:
            logger.debug(f"[normalize] Invalid novelty value: {nov!r} → None (downstream must compute)")
        result["novelty"] = None

    return result
