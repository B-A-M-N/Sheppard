"""
knowledge_unit.py — Canonical KnowledgeUnit factory.

Single point where all pipeline stages converge.
Every distillery pass, fallback, and compression call routes through here.
"""

import hashlib
import logging
from typing import Any, Dict, List, Optional

from src.research.domain_schema import KnowledgeUnit

logger = logging.getLogger(__name__)


def _make_unit(
    text: str,
    confidence: float = 0.5,
    source: str = "",
    atom_type: str = "claim",
    tags: Optional[List[str]] = None,
    **extra: Any,
) -> Dict[str, Any]:
    """
    Create a KnowledgeUnit and return it as a dict for pipeline compatibility.

    This is THE single point where all pipeline stages converge.
    Every distillery pass, fallback, and compression call routes through here.
    """
    text = (text or "").strip()
    if not text:
        return {}

    # Auto-repair missing sentence termination
    _endings = {'.', '!', '?'}
    _closers = {')', ']', '"', '>', '°', '%'}
    if not any(text.endswith(e) for e in _endings | _closers):
        text = text + '.'

    # Clamp confidence
    confidence = max(0.0, min(1.0, float(confidence)))

    # Build tags
    tag_list = list(tags or [])
    if atom_type not in tag_list:
        tag_list.insert(0, atom_type)

    unit_id = "ku_" + hashlib.sha256(text.encode()).hexdigest()[:12]

    unit = KnowledgeUnit(
        id=unit_id,
        text=text,
        confidence=confidence,
        source=source or "",
        tags=tag_list,
        atom_type=atom_type,
        **{k: v for k, v in extra.items() if k in KnowledgeUnit.model_fields},
    )
    return unit.to_dict()
