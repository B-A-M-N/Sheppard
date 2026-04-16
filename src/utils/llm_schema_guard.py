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

import asyncio


async def _call_llm_with_schema_guard(
    llm_client, prompt: str, expected_schema: str,
    temperature: float, max_tokens: int,
    error_prefix: str,
    retry_temp: float = 0.05,
    format: Optional[Dict[str, Any]] = None,
    max_retries: int = 3,
    task_type=None,
) -> Optional[List[Dict[str, Any]]]:
    """
    Generic LLM call with schema guard, Pydantic validation, and retry loop.

    Returns:
        List of validated atoms on success
        None on LLM failure (triggers ExtractionError in caller)
        [] on empty/zero-yield (valid: no atoms found)
    """
    messages = [{"role": "user", "content": prompt}]
    validation_error = None  # Accumulated validation error for retry feedback

    for attempt in range(max_retries):
        response_content = ""

        try:
            stream_fn = (
                llm_client.task_stream(task_type, messages=messages, format=format, temperature=temperature)
                if task_type is not None
                else llm_client.chat(messages=messages, stream=True, temperature=temperature, max_tokens=max_tokens, format=format)
            )
            async for chunk in stream_fn:
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
                if attempt < max_retries - 1:
                    backoff = 2 ** attempt
                    logger.info(f"[Distillery] {error_prefix}: Retrying in {backoff}s (attempt {attempt+1}/{max_retries})")
                    messages.append({"role": "assistant", "content": response_content})
                    messages.append({"role": "user", "content": f"Previous output used wrong schema '{wrong_key}'. Return ONLY JSON with key '{expected_schema}'."})
                    await asyncio.sleep(backoff)
                    continue
                return []

            try:
                atoms = _extract_atoms_from_llm_response(response_content, expected_schema=expected_schema)
            except WrongSchemaError:
                if attempt < max_retries - 1:
                    backoff = 2 ** attempt
                    logger.info(f"[Distillery] {error_prefix}: Wrong schema — retrying (attempt {attempt+1}/{max_retries})")
                    messages.append({"role": "assistant", "content": response_content})
                    messages.append({"role": "user", "content": f"Previous output used wrong schema. Return ONLY JSON with key '{expected_schema}'."})
                    await asyncio.sleep(backoff)
                    continue
                return []

            # Retry once with stricter settings if zero yield (existing behavior)
            if not atoms:
                strict_prompt = f"""MODE: {expected_schema.upper()}

Return ONLY a JSON object with the key "{expected_schema}". NOTHING ELSE.

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
            logger.warning(f"[Distillery] {error_prefix}: Type error (attempt {attempt+1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                await asyncio.sleep(2 ** attempt)
                continue
            return None
        except Exception as e:
            logger.error(f"[Distillery] {error_prefix} LLM call failed (attempt {attempt+1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                await asyncio.sleep(2 ** attempt)
                continue
            return None

    return None  # All retries exhausted


# ──────────────────────────────────────────────────────────────────────
# FIRE-03: Pydantic validation layer
# ──────────────────────────────────────────────────────────────────────

def _validate_extracted_atoms(atoms: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Validate extracted atoms against Pydantic schema.
    Filters out atoms that violate content constraints (too short, too long, wrong type).
    Returns only validated atoms.
    """
    try:
        from src.utils.atom_validator import AtomValidator
    except ImportError:
        return atoms  # Graceful degradation if validator not available

    valid = []
    for atom in atoms:
        content = atom.get('content', atom.get('text', ''))
        atom_type = atom.get('type', 'claim')
        try:
            AtomValidator(type=atom_type, content=content)
            valid.append(atom)
        except Exception:
            logger.debug(f"[Distillery] Atom filtered by Pydantic validation: {content[:50]}...")
    return valid


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
            # FIRE-03: Pydantic validation after parse
            validated = _validate_extracted_atoms(atoms)
            if validated:
                return validated
            # If validation filters all atoms, fall through to repair
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


# Prompt leakage patterns — LLM returning instructions instead of content
_PROMPT_LEAKAGE_PATTERNS = [
    "rephrase as",
    "complete sentence version",
    "or null",
    "output format",
    "respond with only",
    "you must",
    "do not",
    "never produce",
    "schema",
    "knowledge atom contract",
    "extract one finding",
    "granularity rules",
]


def _is_prompt_leakage(content: str) -> bool:
    """Detect if content is prompt instructions leaking into output."""
    content_lower = content.lower()
    return any(pattern in content_lower for pattern in _PROMPT_LEAKAGE_PATTERNS)


from src.utils.normalize_atom_schema import normalize_atom_schema


def _normalize_single_atom(item: Any) -> Optional[Dict[str, Any]]:
    """Convert a single item into a KnowledgeUnit dict. Returns {} if unusable."""
    if isinstance(item, dict):
        item = normalize_atom_schema(item)
        content = item.get('text', '')
        if not content or not isinstance(content, str):
            return None
        content = content.strip()
        if len(content) < 15:
            return None
        if content.startswith('http') and ' ' not in content[:100]:
            return None
        # Reject prompt leakage artifacts
        if _is_prompt_leakage(content):
            logger.debug(f"[schema_guard] Rejecting prompt leakage: {content[:80]!r}")
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
    item = normalize_atom_schema(item)
    content = item.get('text', '')
    if not content or not isinstance(content, str):
        return None
    content = content.strip()
    if len(content) < 20:
        return None
    if content.startswith('http') and ' ' not in content[:100]:
        return None
    # Reject prompt leakage artifacts
    if _is_prompt_leakage(content):
        logger.debug(f"[schema_guard_fallback] Rejecting prompt leakage: {content[:80]!r}")
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
