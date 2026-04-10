"""
llm_schema_guard.py — LLM call infrastructure, response parsing, and normalization.

Generic LLM communication with schema guard and automatic retry.
All LLM responses are parsed, validated, and normalized to KnowledgeUnit dicts.
"""

import json
import logging
import re
from typing import Any, Dict, List, Optional

from src.utils.text_processing import repair_json
from src.utils.knowledge_unit import _make_unit
from src.utils.llm_schemas import (
    ATOM_EXTRACTION_SCHEMA,
    CRITIQUE_SCHEMA,
)

logger = logging.getLogger(__name__)


class WrongSchemaError(Exception):
    """Raised when LLM returns valid JSON but with the wrong schema key."""
    pass


# ──────────────────────────────────────────────────────────────────────
# Schema-guarded LLM calls
# ──────────────────────────────────────────────────────────────────────

async def _call_llm_with_schema_guard(
    llm_client, prompt: str, expected_schema: str,
    temperature: float, max_tokens: int,
    error_prefix: str,
    retry_temp: float = 0.05,
    format: Optional[Dict[str, Any]] = None
) -> List[Dict[str, Any]]:
    """
    Generic LLM call with schema guard and automatic retry.
    Detects wrong schema (e.g. critique instead of atoms) and retries.

    Args:
        format: Ollama JSON Schema for grammar-constrained decoding.
            When passed, Ollama guarantees structurally valid JSON output.
    """
    messages = [{"role": "user", "content": prompt}]
    response_content = ""

    try:
        async for chunk in llm_client.chat(
            messages=messages, stream=True,
            temperature=temperature, max_tokens=max_tokens,
            format=format
        ):
            if hasattr(chunk, 'content') and chunk.content:
                response_content += chunk.content
            elif isinstance(chunk, dict) and 'content' in chunk:
                response_content += chunk['content']

        if not response_content or len(response_content.strip()) < 10:
            return []

        # Schema guard: detect wrong mode BEFORE attempting parse
        stripped = response_content.strip()
        wrong_schemas = {'atoms': 'critique', 'critique': 'atoms', 'claims': 'critique'}
        wrong_key = wrong_schemas.get(expected_schema)
        if wrong_key and stripped.startswith(f'{{"{wrong_key}"'):
            logger.warning(f"[Distillery] {error_prefix}: Model returned '{wrong_key}' instead of '{expected_schema}' — mode contamination")
            return []

        try:
            atoms = _extract_atoms_from_llm_response(response_content, expected_schema=expected_schema)
        except WrongSchemaError:
            logger.info(f"[Distillery] {error_prefix}: Wrong schema detected — retrying with strict schema guard")
            atoms = []

        # Retry once with stricter settings if zero yield
        if not atoms:
            logger.info(f"[Distillery] {error_prefix}: Zero atoms — retrying with stricter prompt")
            strict_prompt = f"""MODE: {expected_schema.upper()}

Return ONLY a JSON object with the key "{expected_schema}". NOTHING ELSE.

If {expected_schema == 'atoms':
    '{{"atoms": [{{"type": "claim", "content": "A complete factual statement with subject and verb.", "confidence": 0.8}}]}}'
elif expected_schema == 'claims':
    '{{"claims": [{{"content": "A factual claim.", "confidence": 0.7}}]}}'
else:
    '{{"critique": [{{"index": 1, "valid": true}}]}}'}

DOCUMENT (condensed):
{prompt[-2000:] if 'DOCUMENT:' in prompt else prompt[:1500]}
"""
            messages2 = [{"role": "user", "content": strict_prompt}]
            response_content = ""
            async for chunk in llm_client.chat(
                messages=messages2, stream=True,
                temperature=retry_temp, max_tokens=max_tokens,
                format=format
            ):
                if hasattr(chunk, 'content') and chunk.content:
                    response_content += chunk.content
                elif isinstance(chunk, dict) and 'content' in chunk:
                    response_content += chunk['content']

            if response_content and len(response_content.strip()) >= 10:
                return _extract_atoms_from_llm_response(response_content, expected_schema=expected_schema)

        return atoms

    except TypeError as e:
        # "unhashable type: 'dict'" — likely Ollama internal error with schema dict
        logger.warning(f"[Distillery] {error_prefix}: Type error (likely dict hashing in Ollama): {e}")
        return []
    except Exception as e:
        logger.error(f"[Distillery] {error_prefix} LLM call failed: {e}")
        return []


# ──────────────────────────────────────────────────────────────────────
# Response parsing
# ──────────────────────────────────────────────────────────────────────

def _extract_atoms_from_llm_response(raw_text: str, expected_schema: str = 'atoms') -> List[Dict[str, Any]]:
    """
    Parse LLM response into structured atoms.
    Strategy 1: Direct json.loads (happy path)
    Strategy 2: repair_json via json_repair library (broken/truncated/conversational JSON)
    NO FALLBACK TO LINE PARSING — fail fast instead of corrupting the pipeline.
    """
    valid_types = {"claim", "evidence", "event", "procedure", "contradiction"}
    schema_keys = {
        'atoms': ['atoms', 'facts', 'items', 'results', 'data'],
        'claims': ['claims', 'atoms', 'facts', 'items'],  # compression output
        'critique': ['critique', 'reviews', 'evaluations', 'analysis']
    }
    required_keys = schema_keys.get(expected_schema, ['atoms'])

    def _has_expected_key(parsed: dict) -> bool:
        return any(key in parsed for key in required_keys)

    # Strategy 1: Direct JSON parse
    try:
        parsed = json.loads(raw_text)
        if isinstance(parsed, dict) and not _has_expected_key(parsed):
            actual_keys = list(parsed.keys())
            logger.warning(f"[Distillery] Schema mismatch: expected one of {required_keys}, got {actual_keys}")
            raise WrongSchemaError(f"Wrong schema: expected {required_keys}, got {actual_keys}")
        atoms = _normalize_atom_list(parsed, expected_schema=expected_schema)
        if atoms:
            return atoms
    except WrongSchemaError:
        raise
    except json.JSONDecodeError:
        pass

    # Strategy 2: repair_json
    try:
        parsed = repair_json(raw_text)
        if parsed:
            if isinstance(parsed, dict) and not _has_expected_key(parsed):
                actual_keys = list(parsed.keys())
                logger.warning(f"[Distillery] Schema mismatch after repair: expected {required_keys}, got {actual_keys}")
                raise WrongSchemaError(f"Wrong schema after repair: expected {required_keys}, got {actual_keys}")
            atoms = _normalize_atom_list(parsed, expected_schema=expected_schema)
            if atoms:
                return atoms
    except WrongSchemaError:
        raise
    except Exception as e:
        logger.warning(f"[Distillery] repair_json failed: {e}")

    logger.warning(f"[Distillery] ALL JSON extraction failed for {len(raw_text)}-char response")
    return []


# ──────────────────────────────────────────────────────────────────────
# Normalization
# ──────────────────────────────────────────────────────────────────────

def _normalize_atom_list(parsed: Any, expected_schema: str = 'atoms') -> List[Dict[str, Any]]:
    """Normalize various JSON structures into a list of atom dicts."""
    if not isinstance(parsed, dict) and not isinstance(parsed, list):
        return []

    if isinstance(parsed, dict):
        schema_keys_map = {
            'atoms': ['atoms', 'facts', 'items', 'results', 'data'],
            'claims': ['claims', 'atoms', 'facts', 'items'],  # compression output
            'critique': ['critique', 'reviews', 'evaluations', 'analysis']
        }
        key_candidates = schema_keys_map.get(expected_schema, ['atoms', 'facts', 'items'])

        raw_items = None
        for key in key_candidates:
            if key in parsed and isinstance(parsed[key], list):
                raw_items = parsed[key]
                break

        if raw_items is None:
            for v in parsed.values():
                if isinstance(v, list):
                    raw_items = v
                    break
            else:
                return []
    else:
        raw_items = parsed

    atoms = []
    for item in raw_items:
        try:
            if expected_schema == 'critique':
                atom = _normalize_critique_item(item)
            else:
                atom = _normalize_single_atom(item)
            if atom:
                atoms.append(atom)
        except (KeyError, TypeError, ValueError) as e:
            logger.debug(f"[Distillery] Skipping malformed atom: {e}")
            continue

    return atoms


def _normalize_critique_item(item: Any) -> Optional[Dict[str, Any]]:
    """Normalize a critique item into a valid dict with index, valid, reason, fix."""
    if not isinstance(item, dict):
        return None
    index = item.get('index', 0)
    valid = item.get('valid', False)
    if not isinstance(index, int) or index < 1:
        return None
    if not isinstance(valid, bool):
        return None
    result = {'index': index, 'valid': valid}
    reason = item.get('reason', '')
    if reason and isinstance(reason, str):
        result['reason'] = reason
    fix = item.get('fix')
    if fix and isinstance(fix, str):
        result['fix'] = fix
    return result


def _normalize_single_atom(item: Any) -> Optional[Dict[str, Any]]:
    """Convert a single item into a KnowledgeUnit dict. Returns {} if unusable."""
    if isinstance(item, dict):
        content = item.get('content', item.get('fact', item.get('text', item.get('statement', ''))))
        if not content or not isinstance(content, str):
            return None
        content = content.strip()
        if len(content) < 15:
            return None
        if content.startswith('http') and ' ' not in content[:100]:
            return None

        atom_type = str(item.get('type', 'claim')).lower().strip()
        valid_types = {"claim", "evidence", "event", "procedure", "contradiction"}
        if atom_type not in valid_types:
            atom_type = "claim"

        confidence = item.get('confidence', 0.6)
        try:
            confidence = float(confidence)
        except (ValueError, TypeError):
            confidence = 0.5

        tags = []
        if item.get('compressed'):
            tags.append('compressed')

        return _make_unit(text=content, confidence=confidence, atom_type=atom_type, tags=tags)

    elif isinstance(item, str) and len(item.strip()) >= 10:
        return _make_unit(text=item.strip(), confidence=0.5, atom_type='claim')

    return None


def _normalize_single_atom_fallback(item: Any) -> Optional[Dict[str, Any]]:
    """Relaxed normalization for fallback mode — shorter sentences allowed."""
    if not isinstance(item, dict):
        return None
    content = item.get('content', item.get('fact', item.get('text', item.get('statement', ''))))
    if not content or not isinstance(content, str):
        return None
    content = content.strip()
    if len(content) < 20:
        return None
    if content.startswith('http') and ' ' not in content[:100]:
        return None

    atom_type = str(item.get('type', 'claim')).lower().strip()
    valid_types = {"claim", "evidence", "event", "procedure", "contradiction"}
    if atom_type not in valid_types:
        atom_type = "claim"

    confidence = item.get('confidence', 0.5)
    try:
        confidence = float(confidence)
    except (ValueError, TypeError):
        confidence = 0.5

    tags = ['fallback']
    if item.get('compressed'):
        tags.append('compressed')

    return _make_unit(text=content, confidence=confidence, atom_type=atom_type, tags=tags)


def _parse_lines_fallback(text: str, valid_types: set) -> List[Dict[str, Any]]:
    """Last-resort line parser. Only reached when ALL JSON strategies fail."""
    atoms = []
    typed_pattern = re.compile(r'^[\s\-\*•]+\[(\w+)\]\s+(.+)$', re.MULTILINE)
    for match in typed_pattern.finditer(text):
        atom_type = match.group(1).strip().lower()
        content = match.group(2).strip()
        if atom_type not in valid_types:
            atom_type = "claim"
        if len(content) >= 10:
            atoms.append({"type": atom_type, "content": content, "confidence": 0.6})
    if atoms:
        return atoms

    bullet_pattern = re.compile(r'^[\s\-\*•]+\s+(.+)$', re.MULTILINE)
    for match in bullet_pattern.finditer(text):
        content = match.group(1).strip()
        if len(content) >= 10 and not content.startswith('#'):
            atoms.append({"type": "claim", "content": content, "confidence": 0.4})
    return atoms
