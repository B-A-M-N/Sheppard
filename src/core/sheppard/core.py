import logging
from datetime import datetime
from typing import Dict, Any, Optional, List, Union
import asyncio
import json
import os
from ollama import AsyncClient
from ..trustcall import call
from .memory_ops import MemoryOperations
from .interaction import InteractionHandler
from .response import ResponseGenerator
from .tools import ToolManager
from src.config.config import DatabaseConfig, ModelConfig, MemoryConfig, console

logger = logging.getLogger(__name__)

class Sheppard:
    """Main Sheppard AI Assistant class"""
    
    def __init__(self):
        """Initialize Sheppard components"""
        self.logger = logging.getLogger(__name__)
        self._init_clients()
        self._init_components()
        self.conversation_history = []
        self.max_history = 10
        self._shutdown_event = asyncio.Event()
        self._initialization_lock = asyncio.Lock()
        self._processing_lock = asyncio.Lock()
        self._initialized = False
        self._last_error_time = None
        self._error_count = 0
        self._max_errors = 3
        self._error_window = 300  # 5 minutes
        self._health_check_interval = 60  # 1 minute

    def _init_clients(self):
        """Initialize Ollama clients with model specifications"""
        try:
            self.main_chat_client = AsyncClient(host=ModelConfig.OLLAMA_HOST)
            self.short_context_client = AsyncClient(host=ModelConfig.OLLAMA_HOST)
            self.long_context_client = AsyncClient(host=ModelConfig.OLLAMA_HOST)
            self.embedding_client = AsyncClient(host=ModelConfig.OLLAMA_HOST)
            
            model_config = ModelConfig.MODEL_CONFIG
            self.main_chat_model = f"{model_config['main_chat']['name']}:{model_config['main_chat']['tag']}"
            self.short_context_model = f"{model_config['short_context']['name']}:{model_config['short_context']['tag']}"
            self.long_context_model = f"{model_config['long_context']['name']}:{model_config['long_context']['tag']}"
            self.embedding_model = f"{model_config['embedding']['name']}:{model_config['embedding']['tag']}"
            
        except Exception as e:
            self.logger.error(f"Error initializing clients: {str(e)}")
            raise

    def _init_components(self):
        """Initialize system components"""
        try:
            self.memory_ops = MemoryOperations(
                self.embedding_client,
                self.embedding_model,
                MemoryConfig.MEMORY_CONFIG  # Changed from DatabaseConfig to MemoryConfig
            )

            # Try to initialize CMK runtime (optional — falls back gracefully)
            self.cmk_runtime = None
            try:
                from src.core.memory.cmk.runtime import CMKRuntime
                from src.core.memory.cmk.config import CMKConfig

                cmk_config = CMKConfig.from_env()
                cmk_config.embedding.host = ModelConfig.OLLAMA_HOST
                cmk_config.embedding.model = "nomic-embed-text"

                self.cmk_runtime = CMKRuntime(config=cmk_config)
                self.logger.info("CMK Runtime initialized (optional)")
            except Exception as cmk_err:
                self.logger.debug(f"CMK Runtime not available: {cmk_err}")
                self.cmk_runtime = None

            self.response_gen = ResponseGenerator(
                self.main_chat_client,
                self.short_context_client,
                self.long_context_client,
                self.main_chat_model,
                self.short_context_model,
                self.long_context_model,
                cmk_runtime=self.cmk_runtime,  # Inject CMK for evidence-tier responses
            )

            self.tool_manager = ToolManager(self.main_chat_client)

            self.interaction = InteractionHandler(
                self.memory_ops,
                self.response_gen,
                self.tool_manager
            )
            
        except Exception as e:
            self.logger.error(f"Error initializing components: {str(e)}")
            raise

    async def initialize(self) -> bool:
        """Initialize all system components"""
        if self._initialized:
            return True

        async with self._initialization_lock:
            try:
                self.logger.info("Initializing Sheppard core components...")

                if not await self._verify_models():
                    self.logger.error("Required models not available")
                    return False

                if not await self.memory_ops.initialize():
                    self.logger.error("Failed to initialize memory operations")
                    return False

                if not await self.tool_manager.initialize():
                    self.logger.error("Failed to initialize tool manager")
                    return False

                asyncio.create_task(self._periodic_health_check())
                self._initialized = True
                self.logger.info("✓ Sheppard initialized successfully")
                return True
                
            except Exception as e:
                self.logger.error(f"Error during initialization: {str(e)}")
                return False

    async def _verify_models(self) -> bool:
        """Verify that required models are available"""
        try:
            required_models = [
                self.main_chat_model,
                self.short_context_model,
                self.long_context_model,
                self.embedding_model
            ]
            
            for model in required_models:
                try:
                    response = await self.main_chat_client.list()
                    models = [m['name'].lower() for m in response['models']]
                    base_model = model.split(':')[0].lower()
                    
                    if not any(base_model in m for m in models):
                        self.logger.error(f"Required model {model} not found")
                        return False
                except Exception as e:
                    self.logger.error(f"Error checking model {model}: {str(e)}")
                    return False
            
            return True
            
        except Exception as e:
            self.logger.error(f"Error verifying models: {str(e)}")
            return False

    async def check_health(self) -> Dict[str, Any]:
        """Check the health status of all components"""
        try:
            health_status = {
                "healthy": True,
                "components": {
                    "memory": await self.memory_ops.validate_connection(),
                    "tools": await self.tool_manager.validate_health(),
                    "interaction": await self.interaction.validate_health()
                },
                "error_rate": self._error_count / max(1, self.max_history),
                "timestamp": datetime.now().isoformat()
            }
            
            # Update overall health status
            health_status["healthy"] = all(health_status["components"].values()) and health_status["error_rate"] < 0.5
            
            return health_status
            
        except Exception as e:
            self.logger.error(f"Error checking health: {str(e)}")
            return {"healthy": False, "error": str(e)}

    async def process_input(self, user_input: str) -> str:
        """Process user input and generate response"""
        if self._shutdown_event.is_set():
            return "System is shutting down. Please wait."
            
        if not self._initialized:
            return "System is not initialized. Please wait for initialization to complete."

        if await self._check_error_threshold():
            return "System is experiencing issues. Please try again later."

        async with self._processing_lock:
            start_time = datetime.now()
            
            try:
                if not await self._validate_input(user_input):
                    return "Please provide a valid input."

                if not await self._check_system_health():
                    return "System is performing maintenance. Please try again shortly."

                response = await self.interaction.process_interaction(user_input, self.conversation_history)
                await self._update_conversation_history(user_input, response)
                await self._record_successful_processing(start_time)
                return response
                
            except Exception as e:
                await self._handle_processing_error(e, start_time)
                return "I encountered an unexpected issue. Please try again."

    async def _validate_input(self, user_input: str) -> bool:
        """Validate user input"""
        try:
            if not user_input or not isinstance(user_input, str):
                return False
                
            cleaned_input = user_input.strip()
            if not cleaned_input:
                return False
                
            if len(cleaned_input) > 2000:
                return False
                
            if not all(char.isprintable() for char in cleaned_input):
                return False
                
            return True
            
        except Exception as e:
            self.logger.error(f"Error validating input: {str(e)}")
            return False

    async def _check_system_health(self) -> bool:
        """Check health of all system components"""
        try:
            health_status = await self.check_health()
            return health_status["healthy"]
            
        except Exception as e:
            self.logger.error(f"Error checking system health: {str(e)}")
            return False

    async def _check_error_threshold(self) -> bool:
        """Check if error threshold has been exceeded"""
        try:
            current_time = datetime.now()
            
            if self._last_error_time and \
               (current_time - self._last_error_time).total_seconds() > self._error_window:
                self._error_count = 0
                self._last_error_time = None
                
            return self._error_count >= self._max_errors
            
        except Exception as e:
            self.logger.error(f"Error checking error threshold: {str(e)}")
            return True

    async def _periodic_health_check(self) -> None:
        """Perform periodic health checks"""
        while not self._shutdown_event.is_set():
            try:
                await asyncio.sleep(self._health_check_interval)
                if not await self._check_system_health():
                    self.logger.warning("System health check failed")
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Error in health check: {str(e)}")

    async def _update_conversation_history(self, user_input: str, response: str) -> None:
        """Update conversation history with bounds checking"""
        try:
            current_time = datetime.now().isoformat()
            
            self.conversation_history.append({
                "role": "user",
                "content": user_input,
                "timestamp": current_time
            })
            
            self.conversation_history.append({
                "role": "assistant",
                "content": response,
                "timestamp": current_time
            })
            
            if len(self.conversation_history) > self.max_history * 2:
                self.conversation_history = self.conversation_history[-self.max_history*2:]
            
            await self._save_conversation_history()
                
        except Exception as e:
            self.logger.error(f"Error updating conversation history: {str(e)}")

    async def _record_successful_processing(self, start_time: datetime) -> None:
        """Record successful processing metrics"""
        try:
            processing_time = (datetime.now() - start_time).total_seconds()
            self.logger.info(f"Processing completed in {processing_time:.2f} seconds")
            
            if self._error_count > 0:
                self._error_count = 0
                self._last_error_time = None
                
        except Exception as e:
            self.logger.error(f"Error recording processing success: {str(e)}")

    async def _handle_processing_error(self, error: Exception, start_time: datetime) -> None:
        """Handle processing error and update metrics"""
        try:
            self._error_count += 1
            self._last_error_time = datetime.now()
            processing_time = (datetime.now() - start_time).total_seconds()
            
            self.logger.error(
                f"Processing error after {processing_time:.2f} seconds: {str(error)}",
                exc_info=True
            )
            await self._save_error_context(error, processing_time)
            
        except Exception as e:
            self.logger.error(f"Error handling processing error: {str(e)}")

    async def _save_conversation_history(self) -> None:
        """Save conversation history to file"""
        try:
            history_file = os.path.join(
                DatabaseConfig.CONVERSATIONS_DIR,
                f"conversation_{datetime.now().strftime('%Y%m%d')}.json"
            )
            
            with open(history_file, 'w', encoding='utf-8') as f:
                json.dump({
                    "timestamp": datetime.now().isoformat(),
                    "history": self.conversation_history
                }, f, indent=2, ensure_ascii=False)
                
        except Exception as e:
            self.logger.error(f"Error saving conversation history: {str(e)}")

    async def _save_error_context(self, error: Exception, processing_time: float) -> None:
        """Save error context for debugging"""
        try:
            error_file = os.path.join(
                DatabaseConfig.DATA_DIR,
                'logs',
                f"error_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            )
            
            error_context = {
                "timestamp": datetime.now().isoformat(),
                "error_type": type(error).__name__,
                "error_message": str(error),
                "processing_time": processing_time,
                "conversation_state": {
                    "history_length": len(self.conversation_history),
                    "last_interaction": self.conversation_history[-2:] if self.conversation_history else None
                },
                "system_state": {
                    "initialized": self._initialized,
                    "error_count": self._error_count,
                    "processing_lock": self._processing_lock.locked()
                }
            }
            
            with open(error_file, 'w') as f:
                json.dump(error_context, f, indent=2)
                
        except Exception as e:
            self.logger.error(f"Error saving error context: {str(e)}")

    async def _save_final_state(self) -> None:
        """Save final state during shutdown"""
        try:
            final_state = {
                "timestamp": datetime.now().isoformat(),
                "conversation_history": self.conversation_history,
                "error_count": self._error_count,
                "last_error": str(self._last_error_time) if self._last_error_time else None
            }
            
            state_file = os.path.join(
                DatabaseConfig.DATA_DIR,
                f"final_state_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            )
            
            with open(state_file, 'w') as f:
                json.dump(final_state, f, indent=2)
                
        except Exception as e:
            self.logger.error(f"Error saving final state: {str(e)}")

    async def shutdown(self) -> None:
        """Perform clean shutdown of all components"""
        try:
            self._shutdown_event.set()
            
            if not self._initialized:
                return

            if self.conversation_history:
                await self._save_conversation_history()

            await self._save_final_state()

            shutdown_tasks = []
            
            if self.memory_ops:
                shutdown_tasks.append(self.memory_ops.cleanup())
            if self.tool_manager:
                shutdown_tasks.append(self.tool_manager.shutdown())
            if self.interaction:
                shutdown_tasks.append(self.interaction.cleanup())
            
            try:
                await asyncio.wait_for(
                    asyncio.gather(*shutdown_tasks, return_exceptions=True),
                    timeout=10.0
                )
            except asyncio.TimeoutError:
                self.logger.warning("Shutdown timed out, some cleanup tasks may not have completed")
            
            self._initialized = False
            self.logger.info("✓ Sheppard shutdown completed successfully")
            
        except Exception as e:
            self.logger.error(f"Error during shutdown: {str(e)}")
            raise
        finally:
            self.memory_ops = None
            self.tool_manager = None
            self.interaction = None
            self.conversation_history = []

    def __str__(self) -> str:
        """String representation"""
        status = "🟢" if self._initialized and not self._shutdown_event.is_set() else "🔴"
        return (
            f"Sheppard(status={status}, "
            f"initialized={self._initialized}, "
            f"history_size={len(self.conversation_history)}, "
            f"error_count={self._error_count})"
        )

    def __repr__(self) -> str:
        """Detailed string representation"""
        return json.dumps({
            "status": {
                "initialized": self._initialized,
                "shutdown_event": self._shutdown_event.is_set(),
                "error_count": self._error_count,
                "last_error": str(self._last_error_time) if self._last_error_time else None
            },
            "configuration": {
                "max_history": self.max_history,
                "error_window": self._error_window,
                "max_errors": self._max_errors,
                "health_check_interval": self._health_check_interval
            },
            "state": {
                "conversation_history_length": len(self.conversation_history),
                "processing_lock": self._processing_lock.locked(),
                "initialization_lock": self._initialization_lock.locked()
            },
            "models": {
                "main": self.main_chat_model,
                "short_context": self.short_context_model,
                "long_context": self.long_context_model,
                "embedding": self.embedding_model
            }
        }, indent=2)
        
