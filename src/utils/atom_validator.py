"""
Post-generation Pydantic validation for atom extraction output.
Strips markdown fences, parses JSON, validates schema, rejects unknown fields.
"""
import json
import re
from typing import List, Literal
from pydantic import BaseModel, Field


class AtomValidator(BaseModel):
    """Validates a single extracted atom."""
    type: Literal["claim", "evidence", "event", "procedure", "contradiction"] = "claim"
    content: str = Field(min_length=20, max_length=300)

    class Config:
        extra = "forbid"


class AtomBatchValidator(BaseModel):
    """Validates the full extraction response."""
    atoms: List[AtomValidator]

    class Config:
        extra = "forbid"


def validate_atom_response(raw_output: str) -> List[dict]:
    """
    Strip markdown, parse JSON, validate against Pydantic schema.

    Raises ValueError or pydantic.ValidationError on failure.
    Returns list of validated atom dicts.
    """
    # 1. Strip markdown fences
    cleaned = re.sub(r'^```(?:json)?\s*|\s*```$', '', raw_output.strip(), flags=re.DOTALL)

    # 2. Parse JSON
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as e:
        raise ValueError(f"JSON parse failed: {e}") from e

    # 3. Validate against Pydantic schema
    batch = AtomBatchValidator.model_validate(data)

    # 4. Return validated atoms as dicts
    return [a.model_dump() for a in batch.atoms]
