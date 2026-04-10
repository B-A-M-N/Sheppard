"""
normalize_atom_schema.py — Single compatibility layer for atom field names.

Maps LLM/legacy field names to V3 canonical names.
This is the ONLY place that handles field name transitions.
All downstream code must use canonical names only.
"""


def normalize_atom_schema(atom: dict) -> dict:
    """
    Map LLM/legacy field names to V3 canonical names.

    Canonical mappings:
      content   -> text  (LLM response -> V3 KnowledgeUnit)
      statement -> text  (legacy synthesis field)
      fact      -> text  (emergency fallback field)
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

    return result
