"""
normalize_atom_schema.py — Single compatibility layer for atom field names.

Maps LLM/legacy field names to V3 canonical names.
This is the ONLY place that handles field name transitions.
All downstream code must use canonical names only.
"""

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
    imp = result.get("importance")
    if isinstance(imp, str) and imp.lower() in _IMPORTANCE_MAP:
        result["importance"] = _IMPORTANCE_MAP[imp.lower()]
    elif imp is None or not isinstance(imp, (int, float)):
        result["importance"] = 0.5  # default

    nov = result.get("novelty")
    if isinstance(nov, str) and nov.lower() in _NOVELTY_MAP:
        result["novelty"] = _NOVELTY_MAP[nov.lower()]
    elif nov is None or not isinstance(nov, (int, float)):
        result["novelty"] = 0.5  # default

    return result
