"""
json_validator.py — Thin re-export shim for backward compatibility.

This file is now a facade. All implementation lives in modular files:
  - knowledge_unit.py     → _make_unit, KnowledgeUnit integration
  - llm_schemas.py        → JSON schema constants
  - source_classifier.py  → classify_source_quality
  - atom_quality.py       → structural quality heuristics
  - embedding_gates.py    → embedding-based quality/dedup/drift
  - entity_filter.py      → cognitive filter + entity extraction
  - llm_schema_guard.py   → LLM call infrastructure + normalization
  - distillation_pipeline.py → main orchestrator + all passes

All public symbols are re-exported here for backward compatibility.
"""

import logging

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────
# Re-exports (backward compatibility — all consumers import from here)
# ──────────────────────────────────────────────────────────────────────

# Main pipeline entry point
from src.utils.distillation_pipeline import (
    extract_technical_atoms,
    llm_compress_to_claims,
)

# Semantic entity extraction
from src.utils.embedding_gates import (
    _extract_entities_semantic,
)

# Entity filter (string-based, used by pipeline)
from src.utils.entity_filter import (
    _extract_entities_from_atoms,
)

# LLM schemas (for consumers that pass them to Ollama)
from src.utils.llm_schemas import (
    ATOM_EXTRACTION_SCHEMA,
    CRITIQUE_SCHEMA,
    COMPRESSION_SCHEMA,
)

# KnowledgeUnit factory
from src.utils.knowledge_unit import (
    _make_unit,
)

# Normalization functions
from src.utils.llm_schema_guard import (
    _normalize_single_atom,
    _normalize_single_atom_fallback,
)

# ──────────────────────────────────────────────────────────────────────
# JSONValidator class (kept here — imported by frontier.py)
# ──────────────────────────────────────────────────────────────────────

import json
import re
from typing import Dict, Any, Optional


class JSONValidator:
    """Validates and repairs LLM-generated JSON responses using iterative prompting."""

    def __init__(self, max_attempts: int = 3):
        self.max_attempts = max_attempts
        self.logger = logging.getLogger(__name__)

    async def validate_and_fix_json(
        self, llm_client, response_text: str, schema: Dict[str, Any]
    ) -> Dict[str, Any]:
        attempts = 0
        current_json = None

        try:
            json_text = self._extract_json(response_text)
            if json_text:
                current_json = json.loads(json_text)
                if self._validate_schema(current_json, schema):
                    return current_json
        except (json.JSONDecodeError, Exception) as e:
            self.logger.warning(f"Initial validation failed: {e}")

        while attempts < self.max_attempts:
            attempts += 1
            try:
                if current_json is None:
                    prompt = self._create_format_repair_prompt(response_text, schema)
                else:
                    prompt = self._create_correction_prompt(current_json, schema)

                messages = [{"role": "user", "content": prompt}]
                repair_content = ""
                async for response in llm_client.chat(
                    messages=messages, stream=True, temperature=0.2, format='json'
                ):
                    if response and response.content:
                        repair_content += response.content

                json_text = self._extract_json(repair_content)
                if not json_text:
                    if attempts >= self.max_attempts:
                        break
                    continue

                try:
                    current_json = json.loads(json_text)
                    if self._validate_schema(current_json, schema):
                        return current_json
                except Exception:
                    if attempts >= self.max_attempts:
                        break
                    continue
            except Exception as e:
                self.logger.error(f"Repair attempt {attempts} failed: {e}")
                if attempts >= self.max_attempts:
                    break

        self.logger.warning(f"All repair attempts failed, using fallback")
        return self._create_fallback_response(schema)

    def _create_format_repair_prompt(self, invalid_text: str, schema: Dict[str, Any]) -> str:
        schema_str = json.dumps(schema, indent=2)
        return f"Fix this JSON to match:\n```json\n{schema_str}\n```\n\nInvalid input:\n```\n{invalid_text}\n```\n\nReturn ONLY valid JSON."

    def _create_correction_prompt(self, current_json: Dict[str, Any], schema: Dict[str, Any]) -> str:
        current_str = json.dumps(current_json, indent=2)
        schema_str = json.dumps(schema, indent=2)
        return f"Fix this invalid JSON:\n```json\n{current_str}\n```\n\nTo match this schema:\n```json\n{schema_str}\n```\n\nReturn ONLY the fixed JSON."

    def _extract_json(self, text: str) -> Optional[str]:
        code_block_pattern = r'```(?:json)?\s*([\s\S]*?)\s*```'
        for match in re.findall(code_block_pattern, text):
            try:
                json.loads(match.strip())
                return match.strip()
            except json.JSONDecodeError:
                continue

        for match in re.findall(r'(\{[\s\S]*\}|\[[\s\S]*\])', text):
            try:
                json.loads(match.strip())
                return match.strip()
            except json.JSONDecodeError:
                continue

        start_idx = text.find('{')
        if start_idx >= 0:
            open_count = 0
            for i in range(start_idx, len(text)):
                if text[i] == '{':
                    open_count += 1
                elif text[i] == '}':
                    open_count -= 1
                    if open_count == 0:
                        try:
                            json.loads(text[start_idx:i+1])
                            return text[start_idx:i+1]
                        except json.JSONDecodeError:
                            pass
        return None

    def _validate_schema(self, data: Dict[str, Any], schema: Dict[str, Any]) -> bool:
        try:
            for field in schema.get('required', []):
                if field not in data:
                    return False
            for field, field_schema in schema.get('properties', {}).items():
                if field in data:
                    if field_schema.get('type') == 'string' and not isinstance(data[field], str):
                        return False
                    elif field_schema.get('type') == 'array' and not isinstance(data[field], list):
                        return False
            return True
        except Exception:
            return False

    def _create_fallback_response(self, schema: Dict[str, Any], context: Optional[Dict] = None) -> Dict[str, Any]:
        fallback = {}
        for field in schema.get('required', []):
            field_schema = schema.get('properties', {}).get(field, {})
            field_type = field_schema.get('type', 'string')
            if field_type == 'string':
                fallback[field] = context.get('fallback_string', '') if context else ''
            elif field_type in ('array', 'number', 'boolean', 'object'):
                fallback[field] = [] if field_type == 'array' else (0 if field_type == 'number' else (False if field_type == 'boolean' else {}))
            else:
                fallback[field] = None
        return fallback
