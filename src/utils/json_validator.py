"""
Fix for JSONValidator to correctly use OllamaClient.chat method.
File: src/utils/json_validator.py
"""

import json
import logging
import re
from typing import Dict, Any, List, Optional, Union, Callable
import asyncio

logger = logging.getLogger(__name__)

class JSONValidator:
    """Validates and repairs LLM-generated JSON responses using iterative prompting."""
    
    def __init__(self, max_attempts: int = 3):
        """Initialize validator with retry settings."""
        self.max_attempts = max_attempts
        self.logger = logging.getLogger(__name__)
    
    async def validate_and_fix_json(
        self, 
        llm_client, 
        response_text: str, 
        schema: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Validate and fix JSON from LLM response using iterative prompting.
        
        Args:
            llm_client: Ollama client instance
            response_text: Text response from LLM to parse as JSON
            schema: Expected structure of the JSON
            
        Returns:
            Dict[str, Any]: Valid JSON object
        """
        attempts = 0
        current_json = None
        
        # First try to parse the JSON directly
        try:
            # Extract JSON if surrounded by other text
            json_text = self._extract_json(response_text)
            if json_text:
                current_json = json.loads(json_text)
                # Validate against schema
                if self._validate_schema(current_json, schema):
                    return current_json  # Already valid
        except json.JSONDecodeError as e:
            self.logger.warning(f"Initial JSON parse failed: {str(e)}")
            # Continue to repair flow
        except Exception as e:
            self.logger.warning(f"Initial validation failed: {str(e)}")
            # Continue to repair flow if we have partial JSON
        
        # Iterative repair flow
        while attempts < self.max_attempts:
            attempts += 1
            self.logger.info(f"JSON repair attempt {attempts}/{self.max_attempts}")
            
            try:
                # If we couldn't parse it at all, ask for complete reformat
                if current_json is None:
                    prompt = self._create_format_repair_prompt(response_text, schema)
                else:
                    # If we have JSON but invalid, ask for corrections
                    prompt = self._create_correction_prompt(current_json, schema)
                
                # Get the repair from LLM - using correct parameters for your OllamaClient
                messages = [{"role": "user", "content": prompt}]
                
                # Use the client.chat method with the correct parameters
                repair_content = ""
                async for response in llm_client.chat(
                    messages=messages,
                    stream=True,
                    temperature=0.2  # Low temperature for precision
                ):
                    if response and response.content:
                        repair_content += response.content
                
                # Try to extract and parse JSON from response
                json_text = self._extract_json(repair_content)
                if not json_text:
                    self.logger.warning(f"No JSON found in repair response")
                    if attempts >= self.max_attempts:
                        break
                    continue
                
                try:
                    current_json = json.loads(json_text)
                    
                    # Validate against schema
                    if self._validate_schema(current_json, schema):
                        self.logger.info(f"JSON successfully repaired after {attempts} attempts")
                        return current_json  # Success!
                except Exception as e:
                    self.logger.warning(f"Repair parsing failed: {str(e)}")
                    if attempts >= self.max_attempts:
                        break
                    continue
            
            except Exception as e:
                self.logger.error(f"Repair attempt {attempts} failed: {str(e)}")
                if attempts >= self.max_attempts:
                    break
        
        # If we get here, all attempts failed - return fallback
        self.logger.warning(f"All repair attempts failed, using fallback")
        return self._create_fallback_response(schema)
    
    def _create_format_repair_prompt(self, invalid_text: str, schema: Dict[str, Any]) -> str:
        """Create prompt to format completely invalid JSON."""
        schema_str = json.dumps(schema, indent=2)
        return f"""
        The following text was supposed to be valid JSON but has formatting issues:
        
        ```
        {invalid_text}
        ```
        
        I need you to fix this and provide properly formatted JSON that matches this structure:
        
        ```json
        {schema_str}
        ```
        
        Return ONLY the fixed JSON with no explanation or other text. Make sure all required fields are present.
        The output should be valid JSON that can be parsed by json.loads().
        """
    
    def _create_correction_prompt(self, current_json: Dict[str, Any], schema: Dict[str, Any]) -> str:
        """Create prompt to correct an invalid JSON object."""
        current_str = json.dumps(current_json, indent=2)
        schema_str = json.dumps(schema, indent=2)
        return f"""
        The following JSON does not properly conform to the required structure:
        
        ```json
        {current_str}
        ```
        
        I need you to fix this JSON to match this structure:
        
        ```json
        {schema_str}
        ```
        
        Return the complete fixed JSON object with all required fields.
        Respond ONLY with the fixed JSON and no additional text.
        """
    
    def _extract_json(self, text: str) -> Optional[str]:
        """Extract JSON from text that might contain other content."""
        # Try to find JSON in code blocks first
        code_block_pattern = r'```(?:json)?\s*([\s\S]*?)\s*```'
        code_matches = re.findall(code_block_pattern, text)
        
        for match in code_matches:
            try:
                # Validate it's parseable
                json.loads(match.strip())
                return match.strip()
            except json.JSONDecodeError:
                continue
        
        # Try to find JSON with brackets
        bracket_pattern = r'(\{[\s\S]*\}|\[[\s\S]*\])'
        bracket_matches = re.findall(bracket_pattern, text)
        
        for match in bracket_matches:
            try:
                json.loads(match.strip())
                return match.strip()
            except json.JSONDecodeError:
                continue
                
        # Try finding the first { and matching closing }
        start_idx = text.find('{')
        if start_idx >= 0:
            # Simple bracket counting - not perfect but often works
            open_count = 0
            for i in range(start_idx, len(text)):
                if text[i] == '{':
                    open_count += 1
                elif text[i] == '}':
                    open_count -= 1
                    if open_count == 0:
                        # Found potential JSON
                        json_text = text[start_idx:i+1]
                        try:
                            json.loads(json_text)
                            return json_text
                        except json.JSONDecodeError:
                            pass
        
        return None
    
    def _validate_schema(self, data: Dict[str, Any], schema: Dict[str, Any]) -> bool:
        """Simple schema validation - checks required fields and basic types."""
        try:
            # Check required fields
            for field in schema.get('required', []):
                if field not in data:
                    self.logger.warning(f"Required field missing: {field}")
                    return False
            
            # Check property types
            for field, field_schema in schema.get('properties', {}).items():
                if field in data:
                    # Check type
                    if field_schema.get('type') == 'string' and not isinstance(data[field], str):
                        self.logger.warning(f"Field {field} should be string, got {type(data[field])}")
                        return False
                    elif field_schema.get('type') == 'array' and not isinstance(data[field], list):
                        self.logger.warning(f"Field {field} should be array, got {type(data[field])}")
                        return False
                    
                    # Check string constraints
                    if field_schema.get('type') == 'string' and field_schema.get('minLength'):
                        min_length = field_schema.get('minLength')
                        if len(data[field]) < min_length:
                            self.logger.warning(f"Field {field} too short: {len(data[field])} < {min_length}")
                            return False
                    
                    # Check array constraints
                    if field_schema.get('type') == 'array' and field_schema.get('minItems'):
                        min_items = field_schema.get('minItems')
                        if len(data[field]) < min_items:
                            self.logger.warning(f"Array {field} too short: {len(data[field])} < {min_items}")
                            return False
            
            return True
            
        except Exception as e:
            self.logger.error(f"Schema validation error: {str(e)}")
            return False
    
    def _create_fallback_response(self, schema: Dict[str, Any]) -> Dict[str, Any]:
        """Create a minimal valid response that matches the schema."""
        fallback = {}
        
        # Fill in required fields with minimal valid values
        for field in schema.get('required', []):
            field_schema = schema.get('properties', {}).get(field, {})
            field_type = field_schema.get('type', 'string')
            
            if field_type == 'string':
                fallback[field] = f"Fallback {field}"
            elif field_type == 'array':
                fallback[field] = ["Fallback item"]
            elif field_type == 'number':
                fallback[field] = 0
            elif field_type == 'boolean':
                fallback[field] = False
            elif field_type == 'object':
                fallback[field] = {}
            else:
                fallback[field] = None
        
        return fallback

# Update extract_key_information function to use the correct OllamaClient.chat method
async def extract_key_information(
    llm_client,
    text: str,
    topic: str,
    schema: Dict[str, Any] = None
) -> Dict[str, Any]:
    """
    Extract and validate key information from content.
    
    Args:
        llm_client: Ollama client instance
        text: Content to analyze
        topic: Topic of research
        schema: Expected structure (default: key findings schema)
        
    Returns:
        Dict[str, Any]: Validated key information
    """
    try:
        # Use default schema if none provided
        if schema is None:
            schema = {
                "type": "object",
                "required": ["summary", "key_takeaways"],
                "properties": {
                    "summary": {
                        "type": "string",
                        "minLength": 10
                    },
                    "key_takeaways": {
                        "type": "array",
                        "items": {
                            "type": "string"
                        },
                        "minItems": 1
                    },
                    "detailed_analysis": {
                        "type": "string"
                    },
                    "limitations": {
                        "type": "string"
                    },
                    "actionable_insights": {
                        "type": "string"
                    }
                }
            }
        
        # Build extraction prompt
        prompt = f"""
Analyze this content about "{topic}" and extract the most important information.
Output a valid JSON object with these exact keys:
- "summary": A brief summary of the content
- "key_takeaways": An array of key points (1-5 items)
- "detailed_analysis": A more thorough analysis
- "limitations": Any limitations or cautions
- "actionable_insights": Practical advice based on the content
The response MUST be valid JSON that can be parsed with json.loads().
Format the response as:
{{
  "summary": "...",
  "key_takeaways": ["point 1", "point 2"],
  "detailed_analysis": "...",
  "limitations": "...",
  "actionable_insights": "..."
}}
Content to analyze:
{text[:3000]}
"""
        
        # Use the client's API properly - handle the async generator
        messages = [{"role": "user", "content": prompt}]
        response_content = ""
        
        # Process the async generator correctly using the correct parameters
        async for chunk in llm_client.chat(
            messages=messages,
            stream=True,
            temperature=0.3
        ):
            if hasattr(chunk, 'content') and chunk.content:
                response_content += chunk.content
            elif isinstance(chunk, dict) and 'content' in chunk:
                response_content += chunk['content']
        
        # Validate and fix if needed
        validator = JSONValidator()
        return await validator.validate_and_fix_json(
            llm_client,
            response_content,
            schema
        )
    except Exception as e:
        logger.error(f"Key information extraction failed: {str(e)}")
        # Return a minimal valid fallback
        return {
            "summary": f"Information about {topic}",
            "key_takeaways": [f"Content related to {topic}"],
            "detailed_analysis": "",
            "limitations": "",
            "actionable_insights": ""
        }
