# src/core/sheppard/response.py
import logging
from typing import Dict, Any, List, Optional
import json
from datetime import datetime
import asyncio
import os
from ..trustcall import call

logger = logging.getLogger(__name__)

class ResponseGenerator:
    """Handles response generation and processing"""

    def __init__(
        self,
        main_client,
        short_context_client,
        long_context_client,
        main_model,
        short_model,
        long_model,
        cmk_runtime=None,  # Optional: inject CMKRuntime for evidence-tier responses
    ):
        self.main_client = main_client
        self.short_context_client = short_context_client
        self.long_context_client = long_context_client
        self.main_model = main_model
        self.short_model = short_model
        self.long_model = long_model
        self.max_context_length = 4000
        self.response_cache = {}
        self.cache_ttl = 3600  # 1 hour

        # CMK integration (optional)
        self.cmk_runtime = cmk_runtime
        self.cmk_enabled = cmk_runtime is not None

        self.system_prompt = (
            "You are Sheppard, an AI assistant powered by Ollama models, specializing in "
            "general problem-solving. Your responses should be informative, helpful, and context-aware. "
            "Use the available tools when necessary to assist the user effectively. "
            "Always think step by step and explain your reasoning when appropriate."
        )
        
        self.response_stats = {
            "total_responses": 0,
            "cached_responses": 0,
            "average_length": 0,
            "model_usage": {
                "main": 0,
                "short": 0,
                "long": 0
            }
        }

    async def generate_response(
        self,
        user_input: str,
        memories: Dict[str, Any],
        conversation_history: List[Dict[str, str]],
        tool_analysis: Dict[str, Any]
    ) -> str:
        """Generate response based on input and context"""
        try:
            # Check cache first
            cache_key = self._generate_cache_key(user_input, memories)
            cached_response = self._get_cached_response(cache_key)
            if cached_response:
                self.response_stats["cached_responses"] += 1
                return cached_response

            # Try CMK path if enabled and available
            if self.cmk_enabled:
                try:
                    cmk_response = await self._generate_with_cmk(
                        user_input, conversation_history
                    )
                    if cmk_response:
                        self._update_response_stats(cmk_response)
                        self._cache_response(cache_key, cmk_response)
                        return cmk_response
                except Exception as e:
                    logger.warning(f"[ResponseGen] CMK path failed: {e}, falling back to standard")

            # Standard fallback
            context_summary = await self._summarize_context(memories)

            # Build messages
            messages = self._build_messages(
                user_input,
                context_summary,
                conversation_history,
                tool_analysis
            )

            # Get response from appropriate model
            response = await self._get_model_response(messages)
            
            if isinstance(response, dict) and 'message' in response:
                generated_response = response['message']['content']
                
                # Update statistics safely
                self.response_stats["total_responses"] += 1
                
                # Calculate new average length safely
                if self.response_stats["total_responses"] > 0:
                    current_total = self.response_stats["average_length"] * (self.response_stats["total_responses"] - 1)
                    new_total = current_total + len(generated_response)
                    self.response_stats["average_length"] = new_total / self.response_stats["total_responses"]
                else:
                    self.response_stats["average_length"] = len(generated_response)
                
                # Cache response
                self._cache_response(cache_key, generated_response)
                
                return generated_response
            
            raise ValueError("Unexpected response format")
            
        except Exception as e:
            logger.error(f"Error generating response: {str(e)}")
            return "I encountered an error while processing your request. Please try again."

    async def _generate_with_cmk(
        self,
        user_input: str,
        conversation_history: List[Dict[str, str]],
    ) -> Optional[str]:
        """
        Generate response using CMK evidence pipeline.

        Returns None if CMK is unavailable or has no relevant knowledge,
        triggering fallback to standard generation.
        """
        if not self.cmk_runtime:
            return None

        # CMK query: intent → plan → retrieval → evidence pack
        intent = self.cmk_runtime.intent_profiler.profile(user_input)
        plan = self.cmk_runtime.evidence_planner.plan(intent)

        # Retrieve with CMK
        if self.cmk_runtime.concept_retriever:
            pack = await self.cmk_runtime.query_with_concepts(user_input)
        else:
            pack = await self.cmk_runtime.query(user_input)

        # If no evidence found, let standard path handle it
        if pack.is_empty:
            return None

        # Build CMK-constrained messages with evidence tiers
        from src.core.memory.cmk.prompt_contract import build_cmk_prompt
        messages = build_cmk_prompt(
            evidence_pack=pack,
            user_query=user_input,
            intent=intent,
            conversation_history=conversation_history[-5:] if conversation_history else None,
            abstraction_gate=pack.abstraction_gate,
            definition_supported=pack.definition_supported,
        )

        response = await self._get_model_response(messages)
        return response

    def _update_response_stats(self, response: str):
        """Update response statistics."""
        self.response_stats["total_responses"] += 1
        if self.response_stats["total_responses"] > 0:
            current_total = self.response_stats["average_length"] * (self.response_stats["total_responses"] - 1)
            new_total = current_total + len(response)
            self.response_stats["average_length"] = new_total / self.response_stats["total_responses"]
        else:
            self.response_stats["average_length"] = len(response)

    async def _summarize_context(self, memories: Dict[str, Any]) -> str:
        """Summarize memory context"""
        try:
            memory_texts = []
            for layer, layer_memories in memories.items():
                if isinstance(layer_memories, list):
                    for memory in layer_memories:
                        if isinstance(memory, dict):
                            input_text = memory.get('input', '')
                            response_text = memory.get('response', '')
                            importance = memory.get('importance_score', 0.0)
                            
                            if input_text or response_text:
                                memory_texts.append(
                                    f"{layer.upper()} [importance: {importance:.2f}]:\n"
                                    f"Input: {input_text}\n"
                                    f"Response: {response_text}"
                                )

            if not memory_texts:
                return ""

            response = await self.short_context_client.chat(
                model=self.short_model,
                messages=[
                    {
                        "role": "system",
                        "content": "Summarize the following context concisely:"
                    },
                    {
                        "role": "user",
                        "content": "\n\n".join(memory_texts)
                    }
                ]
            )
            
            self.response_stats["model_usage"]["short"] += 1
            
            if isinstance(response, dict) and 'message' in response:
                return response['message']['content']
            return ""
            
        except Exception as e:
            logger.error(f"Error summarizing context: {str(e)}")
            return ""

    def _build_messages(
        self,
        user_input: str,
        context_summary: str,
        conversation_history: List[Dict[str, str]],
        tool_analysis: Dict[str, Any]
    ) -> List[Dict[str, str]]:
        """Build messages for model interaction"""
        messages = [
            {"role": "system", "content": self.system_prompt}
        ]
        
        # Add context if available
        if context_summary:
            messages.append({
                "role": "system", 
                "content": f"Relevant Context:\n{context_summary}"
            })
        
        # Add tool analysis if available
        if tool_analysis:
            messages.append({
                "role": "system",
                "content": f"Tool Analysis: {json.dumps(tool_analysis)}"
            })
        
        # Add recent conversation history
        messages.extend(conversation_history[-5:])  # Last 5 exchanges
        
        # Add current input
        messages.append({"role": "user", "content": user_input})
        
        return messages

    async def _get_model_response(
        self,
        messages: List[Dict[str, str]]
    ) -> Dict[str, Any]:
        """Get response from appropriate model based on context length"""
        try:
            total_length = sum(len(m['content']) for m in messages)
            
            if total_length > self.max_context_length:
                self.response_stats["model_usage"]["long"] += 1
                return await self.long_context_client.chat(
                    model=self.long_model,
                    messages=messages
                )
            
            self.response_stats["model_usage"]["main"] += 1
            return await self.main_client.chat(
                model=self.main_model,
                messages=messages
            )
            
        except Exception as e:
            logger.error(f"Error getting model response: {str(e)}")
            raise

    def _generate_cache_key(self, user_input: str, memories: Dict[str, Any]) -> str:
        """Generate cache key for response"""
        try:
            memory_hashes = []
            for layer_memories in memories.values():
                if isinstance(layer_memories, list):
                    for memory in layer_memories:
                        if isinstance(memory, dict):
                            memory_hashes.append(memory.get('memory_hash', ''))
            
            key_components = [user_input] + sorted(memory_hashes)
            return hash(''.join(key_components)).__str__()
            
        except Exception as e:
            logger.error(f"Error generating cache key: {str(e)}")
            return hash(user_input).__str__()

    def _get_cached_response(self, cache_key: str) -> Optional[str]:
        """Get cached response if available and not expired"""
        try:
            if cache_key in self.response_cache:
                cached_item = self.response_cache[cache_key]
                if (datetime.now() - cached_item['timestamp']).total_seconds() < self.cache_ttl:
                    return cached_item['response']
                else:
                    del self.response_cache[cache_key]
            return None
            
        except Exception as e:
            logger.error(f"Error retrieving cached response: {str(e)}")
            return None

    def _cache_response(self, cache_key: str, response: str) -> None:
        """Cache a response"""
        try:
            self.response_cache[cache_key] = {
                'response': response,
                'timestamp': datetime.now()
            }
            
            # Clean old cache entries
            current_time = datetime.now()
            expired_keys = [
                k for k, v in self.response_cache.items()
                if (current_time - v['timestamp']).total_seconds() > self.cache_ttl
            ]
            
            for k in expired_keys:
                del self.response_cache[k]
                
        except Exception as e:
            logger.error(f"Error caching response: {str(e)}")

    def get_response_stats(self) -> Dict[str, Any]:
        """Get response generation statistics"""
        try:
            cache_hit_rate = 0
            if self.response_stats["total_responses"] > 0:
                cache_hit_rate = (
                    self.response_stats["cached_responses"] / 
                    self.response_stats["total_responses"] * 100
                )

            return {
                "total_responses": self.response_stats["total_responses"],
                "cached_responses": self.response_stats["cached_responses"],
                "cache_hit_rate": f"{cache_hit_rate:.2f}%",
                "average_length": int(self.response_stats["average_length"]),
                "model_usage": self.response_stats["model_usage"],
                "cache_size": len(self.response_cache),
                "cache_ttl": self.cache_ttl
            }
        except Exception as e:
            logger.error(f"Error generating response stats: {str(e)}")
            return {}

    async def cleanup(self) -> None:
        """Cleanup response generator resources"""
        try:
            # Clear cache
            self.response_cache.clear()
            
            # Reset statistics
            self.response_stats = {
                "total_responses": 0,
                "cached_responses": 0,
                "average_length": 0,
                "model_usage": {
                    "main": 0,
                    "short": 0,
                    "long": 0
                }
            }
            
            logger.info("Response generator cleanup completed")
            
        except Exception as e:
            logger.error(f"Error during response generator cleanup: {str(e)}")

    def __str__(self) -> str:
        """String representation"""
        stats = self.get_response_stats()
        return (
            f"ResponseGenerator("
            f"total_responses={stats['total_responses']}, "
            f"cache_hit_rate={stats['cache_hit_rate']}, "
            f"models=[{self.main_model}, {self.short_model}, {self.long_model}])"
        )
