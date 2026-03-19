#!/usr/bin/env python3
"""
Enhanced Code Arena - A coding assistant with virtualenv integration, testing, and memory.
Uses Ollama with muhammad-albasha/llama3.1-python:latest for code generation and chat.
"""

import os
import sys
import uuid
import json
import time
import glob
import asyncio
import logging
import tempfile
import subprocess
import re
import shlex
import aiohttp
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional, Union, Tuple, AsyncGenerator, Set

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("CodeArena")

# Rich is optional but recommended - try to import it
try:
    from rich.console import Console
    from rich.markdown import Markdown
    from rich.syntax import Syntax
    from rich.panel import Panel
    from rich.table import Table
    from rich.prompt import Confirm
    RICH_AVAILABLE = True
    console = Console()
except ImportError:
    RICH_AVAILABLE = False
    console = None
    print("Rich library not found. Install with: pip install rich")
    print("For better UI experience, rich is recommended")

class OllamaClient:
    """Client for interacting with Ollama API."""
    
    def __init__(
        self, 
        model_name: str = "muhammad-albasha/llama3.1-python:latest",
        api_base: str = "http://localhost:11434",
        timeout: int = 300  # Extended timeout
    ):
        """Initialize Ollama client."""
        self.model_name = model_name
        self.api_base = api_base
        self.timeout = timeout
        self.session = None
    
    async def _ensure_session(self):
        """Ensure aiohttp session exists."""
        if self.session is None:
            self.session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=self.timeout)
            )
    
    async def generate_embedding(self, text: str) -> List[float]:
        """Generate embeddings for text using Ollama API."""
        await self._ensure_session()
        
        # Handle empty text
        if not text or not text.strip():
            # Return a zero vector of standard embedding size
            return [0.0] * 4096
        
        url = f"{self.api_base}/api/embeddings"
        payload = {
            "model": self.model_name,
            "prompt": text
        }
        
        try:
            async with self.session.post(url, json=payload) as response:
                if response.status != 200:
                    error_text = await response.text()
                    logger.error(f"API error: {error_text}")
                    # Return a zero vector on error
                    return [0.0] * 4096
                
                result = await response.json()
                return result.get("embedding", [])
        except Exception as e:
            logger.error(f"Error generating embedding: {str(e)}")
            # Return a zero vector on error
            return [0.0] * 4096
    
    async def chat(
        self,
        messages: List[Dict[str, str]],
        stream: bool = True,
        temperature: float = 0.7,
        max_tokens: int = 2048
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Send a chat request to the Ollama API."""
        await self._ensure_session()
        
        url = f"{self.api_base}/api/chat"
        payload = {
            "model": self.model_name,
            "messages": messages,
            "stream": stream,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens
            }
        }
        
        try:
            async with self.session.post(url, json=payload) as response:
                if response.status != 200:
                    error_text = await response.text()
                    logger.error(f"API error: {error_text}")
                    yield {"content": f"Error: API returned {response.status} - {error_text}", "role": "assistant"}
                    return
                
                if stream:
                    # Handle streaming response
                    full_response = ""
                    async for line in response.content:
                        if line:
                            try:
                                chunk = json.loads(line)
                                if "message" in chunk and "content" in chunk["message"]:
                                    chunk_content = chunk["message"]["content"]
                                    full_response += chunk_content
                                    is_done = chunk.get("done", False)
                                    
                                    yield {
                                        "content": chunk_content,
                                        "role": "assistant",
                                        "done": is_done
                                    }
                                    
                                    # Only exit if we've actually received a done flag
                                    # This prevents premature termination
                                    if is_done:
                                        break
                            except json.JSONDecodeError:
                                continue
                    
                    # If we haven't received a "done" flag but we've reached the end of the stream
                    # Send a final message with the done flag
                    if full_response:
                        yield {
                            "content": "",  # Empty content to signify we're done
                            "role": "assistant",
                            "done": True
                        }
                else:
                    # Handle non-streaming response
                    result = await response.json()
                    if "message" in result and "content" in result["message"]:
                        yield {
                            "content": result["message"]["content"],
                            "role": "assistant",
                            "done": True
                        }
        except asyncio.TimeoutError:
            logger.error("Ollama API request timed out")
            yield {"content": "Error: Request to Ollama API timed out. The model might be too busy or unavailable.", "role": "assistant"}
        except Exception as e:
            logger.error(f"Error in chat: {str(e)}")
            yield {"content": f"Error: {str(e)}", "role": "assistant"}
    
    async def close(self):
        """Close session."""
        if self.session:
            await self.session.close()
            self.session = None

class VirtualenvManager:
    """Manages isolated Python environments using virtualenv for safe code execution."""
    
    def __init__(self, base_dir: Optional[Path] = None):
        """Initialize virtualenv environment manager."""
        self.base_dir = base_dir or Path.home() / ".code_arena" / "virtualenvs"
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.active_envs: Dict[str, Dict[str, Any]] = {}
        
    async def create_environment(
        self, 
        env_id: Optional[str] = None, 
        packages: Optional[List[str]] = None,
        python_version: str = "3"  # Just specify major version, virtualenv will use system Python
    ):
        """Create a new virtualenv environment."""
        env_id = env_id or f"env_{uuid.uuid4().hex[:8]}"
        env_path = self.base_dir / env_id
        
        # Check if environment already exists
        if env_path.exists():
            logger.warning(f"Environment {env_id} already exists, will be reused")
        else:
            logger.info(f"Creating virtualenv environment: {env_id}")
            
            try:
                # Create virtual environment using virtualenv
                cmd = f"virtualenv {env_path} -p python{python_version}"
                
                # Show human-in-the-loop prompt
                if RICH_AVAILABLE:
                    console.print(f"[yellow]About to create virtual environment {env_id} using Python {python_version}. Proceed? (y/n)[/yellow]")
                else:
                    print(f"About to create virtual environment {env_id} using Python {python_version}. Proceed? (y/n)")
                    
                user_input = input().lower()
                if user_input != 'y':
                    raise RuntimeError("User aborted environment creation")
                
                process = await asyncio.create_subprocess_shell(
                    cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                
                stdout, stderr = await process.communicate()
                
                if process.returncode != 0:
                    raise RuntimeError(f"Failed to create virtualenv environment: {stderr.decode()}")
                
                logger.info(f"Created virtualenv environment at {env_path}")
                
                # Install packages if specified
                if packages:
                    await self.install_packages(env_id, packages)
                
            except Exception as e:
                logger.error(f"Failed to create environment {env_id}: {str(e)}")
                raise
        
        # Record active environment
        self.active_envs[env_id] = {
            "path": str(env_path),
            "created_at": datetime.now().isoformat(),
            "packages": packages or [],
            "python_version": python_version
        }
        
        return env_id
    
    async def install_packages(self, env_id: str, packages: List[str]) -> bool:
        """Install packages in the specified environment."""
        if env_id not in self.active_envs:
            logger.error(f"Environment {env_id} not found")
            return False
        
        env_path = Path(self.active_envs[env_id]["path"])
        logger.info(f"Installing packages in {env_id}: {', '.join(packages)}")
        
        # Get pip path for this environment
        pip_path = env_path / "bin" / "pip" if os.name != 'nt' else env_path / "Scripts" / "pip"
        
        try:
            # Show human-in-the-loop prompt for package installation
            if RICH_AVAILABLE:
                console.print(f"[yellow]About to install these packages in {env_id}: {', '.join(packages)}. Proceed? (y/n)[/yellow]")
            else:
                print(f"About to install these packages in {env_id}: {', '.join(packages)}. Proceed? (y/n)")
                
            user_input = input().lower()
            if user_input != 'y':
                return False
            
            # Install packages
            process = await asyncio.create_subprocess_exec(
                str(pip_path), "install", *packages,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode != 0:
                logger.error(f"Failed to install packages: {stderr.decode()}")
                return False
            
            # Update environment record
            self.active_envs[env_id]["packages"].extend(packages)
            return True
            
        except Exception as e:
            logger.error(f"Failed to install packages in {env_id}: {str(e)}")
            return False
    
    async def execute_code(
        self, 
        env_id: str, 
        code: str, 
        timeout: int = 30, 
        max_memory: int = 512,  # MB
        extra_args: Optional[List[str]] = None,
        input_data: Optional[str] = None
    ) -> Dict[str, Any]:
        """Execute code in the specified environment with resource limits."""
        if env_id not in self.active_envs:
            logger.error(f"Environment {env_id} not found")
            return {"success": False, "error": f"Environment {env_id} not found"}
        
        env_path = Path(self.active_envs[env_id]["path"])
        
        # Create a temporary file for the code
        with tempfile.NamedTemporaryFile(suffix='.py', mode='w', delete=False) as temp_file:
            temp_file.write(code)
            temp_file_path = temp_file.name
        
        logger.info(f"Executing code in environment {env_id}")
        
        try:
            # Get python interpreter path for this environment
            python_path = env_path / "bin" / "python" if os.name != 'nt' else env_path / "Scripts" / "python"
            
            # Show human-in-the-loop prompt for code execution
            if RICH_AVAILABLE:
                console.print(f"[yellow]About to execute code in {env_id}. This might execute potentially unsafe code. Proceed? (y/n)[/yellow]")
                console.print(f"[blue]First 100 chars of code: {code[:100]}...[/blue]")
            else:
                print(f"About to execute code in {env_id}. This might execute potentially unsafe code. Proceed? (y/n)")
                print(f"First 100 chars of code: {code[:100]}...")
                
            user_input = input().lower()
            if user_input != 'y':
                return {
                    "success": False,
                    "error": "User aborted code execution",
                    "stdout": "",
                    "stderr": "",
                    "return_code": -1,
                    "execution_time": 0
                }
            
            # Prepare command to execute code with resource limitations
            cmd = [str(python_path), temp_file_path]
            
            # Add extra arguments if provided
            if extra_args:
                cmd.extend(extra_args)
            
            # Execute with timeout
            start_time = datetime.now()
            
            # Create subprocess with or without input data
            if input_data:
                process = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    stdin=asyncio.subprocess.PIPE
                )
                
                try:
                    stdout, stderr = await asyncio.wait_for(
                        process.communicate(input_data.encode()), 
                        timeout=timeout
                    )
                except asyncio.TimeoutError:
                    # Kill the process if it times out
                    try:
                        process.kill()
                    except Exception:
                        pass
                    return {
                        "success": False,
                        "error": f"Execution timed out after {timeout} seconds",
                        "stdout": "",
                        "stderr": "",
                        "return_code": -1,
                        "execution_time": timeout
                    }
            else:
                process = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                
                try:
                    stdout, stderr = await asyncio.wait_for(
                        process.communicate(), 
                        timeout=timeout
                    )
                except asyncio.TimeoutError:
                    # Kill the process if it times out
                    try:
                        process.kill()
                    except Exception:
                        pass
                    return {
                        "success": False,
                        "error": f"Execution timed out after {timeout} seconds",
                        "stdout": "",
                        "stderr": "",
                        "return_code": -1,
                        "execution_time": timeout
                    }
            
            execution_time = (datetime.now() - start_time).total_seconds()
            
            result = {
                "success": process.returncode == 0,
                "stdout": stdout.decode().strip(),
                "stderr": stderr.decode().strip(),
                "return_code": process.returncode,
                "execution_time": execution_time
            }
            
            if process.returncode != 0:
                result["error"] = stderr.decode().strip() or "Unknown error"
            
            return result
                
        except Exception as e:
            logger.error(f"Failed to execute code in {env_id}: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "stdout": "",
                "stderr": "",
                "return_code": -1,
                "execution_time": None
            }
        finally:
            # Clean up the temporary file
            try:
                os.unlink(temp_file_path)
            except Exception:
                pass
    
    async def cleanup_environment(self, env_id: str) -> bool:
        """Clean up a specific environment."""
        if env_id not in self.active_envs:
            logger.warning(f"Environment {env_id} not found for cleanup")
            return False
        
        env_path = Path(self.active_envs[env_id]["path"])
        
        try:
            # Remove the environment directory
            import shutil
            shutil.rmtree(env_path, ignore_errors=True)
            
            # Remove from active environments
            del self.active_envs[env_id]
            logger.info(f"Cleaned up environment {env_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to clean up environment {env_id}: {str(e)}")
            return False
    
    async def cleanup_all(self) -> int:
        """Clean up all environments."""
        count = 0
        env_ids = list(self.active_envs.keys())
        
        for env_id in env_ids:
            if await self.cleanup_environment(env_id):
                count += 1
        
        logger.info(f"Cleaned up {count} environments")
        return count

class MemoryManager:
    """Manages code knowledge and solutions memory for the system."""
    
    def __init__(self, base_dir: Optional[Path] = None):
        """Initialize the memory manager."""
        self.base_dir = base_dir or Path.home() / ".code_arena" / "memory"
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.memory_file = self.base_dir / "knowledge_base.json"
        self.fix_memory: Dict[str, List[Dict[str, Any]]] = self._load_memory()
    
    def _load_memory(self) -> Dict[str, List[Dict[str, Any]]]:
        """Load memory from disk."""
        if not self.memory_file.exists():
            # Initialize with empty memory structure
            return {
                "fixes": [],
                "patterns": [],
                "test_solutions": []
            }
        
        try:
            with open(self.memory_file, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load memory file: {str(e)}")
            return {
                "fixes": [],
                "patterns": [],
                "test_solutions": []
            }
    
    def _save_memory(self) -> bool:
        """Save memory to disk."""
        try:
            with open(self.memory_file, 'w') as f:
                json.dump(self.fix_memory, f, indent=2)
            return True
        except Exception as e:
            logger.error(f"Failed to save memory file: {str(e)}")
            return False
    
    def add_fix(
        self, 
        issue_type: str, 
        original_code: str, 
        fixed_code: str, 
        error_message: str, 
        solution_description: str
    ) -> bool:
        """Add a code fix to memory."""
        fix_entry = {
            "issue_type": issue_type,
            "original_code_snippet": self._extract_relevant_snippet(original_code, error_message),
            "fixed_code_snippet": self._extract_relevant_snippet(fixed_code, error_message),
            "error_message": error_message,
            "solution_description": solution_description,
            "timestamp": datetime.now().isoformat()
        }
        
        # Add to fixes list
        self.fix_memory["fixes"].append(fix_entry)
        
        # Extract and save pattern
        pattern = self._extract_fix_pattern(original_code, fixed_code, error_message)
        if pattern:
            self.fix_memory["patterns"].append(pattern)
        
        return self._save_memory()
    
    def add_test_solution(
        self,
        test_name: str,
        code: str,
        description: str,
        test_code: str = ""
    ) -> bool:
        """Add a successful test solution to memory."""
        solution_entry = {
            "test_name": test_name,
            "code": code,
            "test_code": test_code,
            "description": description,
            "timestamp": datetime.now().isoformat()
        }
        
        self.fix_memory["test_solutions"].append(solution_entry)
        return self._save_memory()
    
    def find_similar_fixes(self, error_message: str, code_snippet: str = "", limit: int = 3) -> List[Dict[str, Any]]:
        """Find similar fixes based on error message and code."""
        # Simple matching based on error message similarity
        # A more sophisticated approach would use embeddings or other similarity metrics
        
        if not error_message:
            return []
        
        # Extract key parts of the error message (usually the error type)
        error_parts = error_message.split(":")
        error_type = error_parts[0] if error_parts else error_message
        
        # Find fixes with similar error messages
        similar_fixes = []
        
        for fix in self.fix_memory["fixes"]:
            fix_error = fix.get("error_message", "")
            
            # Check if error types match
            if error_type.lower() in fix_error.lower():
                similar_fixes.append(fix)
        
        # Sort by relevance (for now just by timestamp, newer first)
        similar_fixes.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
        
        return similar_fixes[:limit]
    
    def find_test_solutions(self, test_name: str = "", description: str = "") -> List[Dict[str, Any]]:
        """Find test solutions based on name or description."""
        if not test_name and not description:
            return self.fix_memory["test_solutions"][-5:]  # Return recent solutions
        
        matching_solutions = []
        
        for solution in self.fix_memory["test_solutions"]:
            solution_test_name = solution.get("test_name", "").lower()
            solution_description = solution.get("description", "").lower()
            
            if (test_name and test_name.lower() in solution_test_name) or \
               (description and description.lower() in solution_description):
                matching_solutions.append(solution)
        
        return matching_solutions
    
    def _extract_relevant_snippet(self, code: str, error_message: str, context_lines: int = 5) -> str:
        """Extract the relevant code snippet based on the error message."""
        if not error_message or not code:
            return code[:500]  # Return first 500 chars if no specific error
        
        # Try to extract line numbers from error messages
        line_match = re.search(r'line (\d+)', error_message)
        if line_match:
            try:
                error_line = int(line_match.group(1))
                code_lines = code.split('\n')
                
                # Calculate the range of lines to include
                start_line = max(0, error_line - context_lines - 1)  # -1 because line numbers start at 1
                end_line = min(len(code_lines), error_line + context_lines)
                
                return '\n'.join(code_lines[start_line:end_line])
            except (ValueError, IndexError):
                pass
        
        # If we can't extract a specific snippet, return a portion of the code
        return code[:500]
    
    def _extract_fix_pattern(self, original_code: str, fixed_code: str, error_message: str) -> Optional[Dict[str, Any]]:
        """Extract a fix pattern for future reference."""
        if not original_code or not fixed_code or original_code == fixed_code:
            return None
        
        # Extract error type from the error message
        error_parts = error_message.split(':')
        error_type = error_parts[0] if error_parts else "Unknown error"
        
        # For simplicity, just store the error type and before/after snippets
        return {
            "error_type": error_type,
            "original_pattern": self._extract_relevant_snippet(original_code, error_message),
            "fixed_pattern": self._extract_relevant_snippet(fixed_code, error_message),
            "description": f"Fix for {error_type} error",
            "timestamp": datetime.now().isoformat()
        }

class TestManager:
    """Manages testing for generated code."""
    
    def __init__(
        self,
        virtualenv_manager: VirtualenvManager,
        memory_manager: MemoryManager,
        ollama_client: OllamaClient
    ):
        """Initialize the test manager."""
        self.virtualenv_manager = virtualenv_manager
        self.memory_manager = memory_manager
        self.ollama_client = ollama_client
        self.current_env_id: Optional[str] = None
    
    async def setup_test_environment(self, packages: Optional[List[str]] = None) -> str:
        """Set up a testing environment."""
        env_id = await self.virtualenv_manager.create_environment(
            env_id=f"test_env_{uuid.uuid4().hex[:8]}",
            packages=packages or ["pytest", "requests", "pyyaml"]
        )
        
        self.current_env_id = env_id
        return env_id
    
    async def generate_tests(
        self,
        code: str,
        requirements: str,
        test_framework: str = "pytest",
        max_tokens: int = 4096
    ) -> Dict[str, Any]:
        """Generate tests for the given code."""
        logger.info(f"Generating {test_framework} tests for code...")
        
        # Build prompt for test generation
        prompt = f"""
You are an expert in software testing. I need you to create thorough tests for the following code.

Code Requirements:
{requirements}

Code to Test:
```python
{code}
```

Create comprehensive tests using {test_framework} that will validate if the code meets its requirements.
Include tests for:
1. Basic functionality
2. Edge cases
3. Error handling
4. Input validation

The tests should be runnable and should thoroughly check if the code works as expected.
"""
        
        # Generate test code using LLM
        test_content = ""
        generation_start = datetime.now()
        
        async for response in self.ollama_client.chat(
            messages=[{"role": "user", "content": prompt}],
            stream=True,
            max_tokens=max_tokens
        ):
            if response and response.get("content"):
                test_content += response["content"]
        
        generation_time = (datetime.now() - generation_start).total_seconds()
        
        # Extract test code block if needed
        final_tests = test_content
        test_blocks = re.findall(r'```(?:python)?\s*([\s\S]*?)\s*```', test_content)
        if test_blocks:
            final_tests = test_blocks[0]
        
        return {
            "test_code": final_tests,
            "test_framework": test_framework,
            "generation_time": generation_time,
            "raw_response": test_content,
            "timestamp": datetime.now().isoformat()
        }
    
    async def run_tests(
        self,
        code: str,
        test_code: str,
        env_id: Optional[str] = None,
        timeout: int = 30
    ) -> Dict[str, Any]:
        """Run tests on the given code."""
        env_id = env_id or self.current_env_id
        if not env_id:
            raise ValueError("No test environment available. Call setup_test_environment first.")
        
        # Create a combined test runner script
        test_runner = f"""
# Save main code to file
with open('code_to_test.py', 'w') as f:
    f.write('''{code}''')

# Save test code to file
with open('test_code.py', 'w') as f:
    f.write('''{test_code}''')

# Run tests
import pytest
import sys

print("Running tests...")
result = pytest.main(['-v', 'test_code.py'])
sys.exit(0 if result == 0 else 1)
"""
        
        # Execute the test runner
        execution_start = datetime.now()
        result = await self.virtualenv_manager.execute_code(
            env_id=env_id,
            code=test_runner,
            timeout=timeout
        )
        execution_time = (datetime.now() - execution_start).total_seconds()
        
        # Update result with timing
        result["execution_time"] = execution_time
        
        # Process test results
        tests_passed = result["success"]
        test_output = result["stdout"]
        
        # Extract test summary if available
        test_summary = "No test summary available"
        if "failed" in test_output.lower() and "passed" in test_output.lower():
            summary_lines = [line for line in test_output.splitlines() if "failed" in line.lower() or "passed" in line.lower()]
            if summary_lines:
                test_summary = summary_lines[-1]
        
        return {
            "success": tests_passed,
            "output": test_output,
            "summary": test_summary,
            "execution_time": execution_time,
            "error": result.get("stderr", "") if not tests_passed else ""
        }
    
    async def fix_code(
        self,
        code: str,
        test_code: str,
        test_result: Dict[str, Any],
        requirements: str,
        max_iterations: int = 5,
        max_tokens: int = 4096
    ) -> Dict[str, Any]:
        """Iteratively fix code that fails tests."""
        original_code = code
        current_code = code
        iterations = 0
        fix_history = []
        
        while not test_result.get("success", False) and iterations < max_iterations:
            iterations += 1
            logger.info(f"Attempting to fix code: iteration {iterations}")
            
            # Check memory for similar fixes
            similar_fixes = self.memory_manager.find_similar_fixes(
                test_result.get("error", ""),
                current_code
            )
            
            fix_examples = ""
            if similar_fixes:
                fix_examples = "Previous similar fixes:\n\n"
                for i, fix in enumerate(similar_fixes, 1):
                    fix_examples += f"Example {i}:\n"
                    fix_examples += f"Error: {fix.get('error_message', 'Unknown error')}\n"
                    fix_examples += f"Solution: {fix.get('solution_description', 'No description')}\n\n"
            
            # Build prompt for code fixing
            prompt = f"""
You are an expert Python developer. You need to fix a code that is failing its tests.

Original Requirements:
{requirements}

Current code:
```python
{current_code}
```

Test code:
```python
{test_code}
```

Test execution results:
```
{test_result.get('output', '')}
```

Error message:
```
{test_result.get('error', '')}
```

{fix_examples}

Please fix the code so that it passes all the tests. Focus on addressing the specific issues in the test failure.
Your response should be ONLY the fixed code. No explanations.
"""
            
            # Generate fixed code using LLM
            fixed_content = ""
            generation_start = datetime.now()
            
            async for response in self.ollama_client.chat(
                messages=[{"role": "user", "content": prompt}],
                stream=True,
                max_tokens=max_tokens
            ):
                if response and response.get("content"):
                    fixed_content += response["content"]
            
            generation_time = (datetime.now() - generation_start).total_seconds()
            
            # Extract fixed code if enclosed in code blocks
            fixed_code = fixed_content
            code_blocks = re.findall(r'```(?:python)?\s*([\s\S]*?)\s*```', fixed_content)
            if code_blocks:
                fixed_code = code_blocks[0]
            
            # Show diff and ask for HITL confirmation
            if RICH_AVAILABLE:
                console.print("\n[cyan]Original Code:[/cyan]")
                console.print(Syntax(current_code, "python"))
                console.print("\n[cyan]Fixed Code:[/cyan]")
                console.print(Syntax(fixed_code, "python"))
                console.print(f"\n[yellow]Apply this fix? (iteration {iterations}/{max_iterations}) (y/n)[/yellow]")
            else:
                print("\nOriginal Code:")
                print(current_code)
                print("\nFixed Code:")
                print(fixed_code)
                print(f"\nApply this fix? (iteration {iterations}/{max_iterations}) (y/n)")
                
            user_input = input().lower()
            if user_input != 'y':
                if RICH_AVAILABLE:
                    console.print("[yellow]Would you like to manually edit the code? (y/n)[/yellow]")
                else:
                    print("Would you like to manually edit the code? (y/n)")
                    
                manual_edit = input().lower()
                if manual_edit == 'y':
                    # Create a temporary file with the current code
                    with tempfile.NamedTemporaryFile(suffix='.py', mode='w', delete=False) as temp_file:
                        temp_file.write(current_code)
                        temp_file_path = temp_file.name
                    
                    if RICH_AVAILABLE:
                        console.print(f"[green]Please edit the file at: {temp_file_path}[/green]")
                        console.print("[green]Press Enter when finished...[/green]")
                    else:
                        print(f"Please edit the file at: {temp_file_path}")
                        print("Press Enter when finished...")
                    
                    input()  # Wait for user to finish editing
                    
                    # Read the edited file
                    with open(temp_file_path, 'r') as f:
                        fixed_code = f.read()
                    
                    # Clean up
                    try:
                        os.unlink(temp_file_path)
                    except Exception:
                        pass
                else:
                    # Skip this iteration if not applying the fix
                    continue
            
            # Record the fix
            fix_record = {
                "iteration": iterations,
                "timestamp": datetime.now().isoformat(),
                "original_code": current_code,
                "fixed_code": fixed_code,
                "test_result": test_result
            }
            fix_history.append(fix_record)
            
            # Update current code with the fixed version
            current_code = fixed_code
            
            # Run tests on the fixed code
            test_result = await self.run_tests(
                code=current_code,
                test_code=test_code,
                env_id=self.current_env_id
            )
            
            # Check if tests now pass
            if test_result.get("success", False):
                if RICH_AVAILABLE:
                    console.print("[green]Tests passed! The code has been fixed successfully.[/green]")
                else:
                    print("Tests passed! The code has been fixed successfully.")
                
                # Store successful fix in memory
                error_message = fix_history[0]["test_result"].get("error", "")
                test_output = fix_history[0]["test_result"].get("output", "")
                
                self.memory_manager.add_fix(
                    issue_type="test_failure",
                    original_code=original_code,
                    fixed_code=current_code,
                    error_message=error_message or test_output,
                    solution_description=f"Fixed code after {iterations} iterations to pass all tests."
                )
                
                break
            else:
                if RICH_AVAILABLE:
                    console.print("[red]Tests still failing. Attempting another fix...[/red]")
                    console.print(f"[red]Error: {test_result.get('error', 'Unknown error')}[/red]")
                else:
                    print("Tests still failing. Attempting another fix...")
                    print(f"Error: {test_result.get('error', 'Unknown error')}")
        
        # Return results of the fixing process
        return {
            "success": test_result.get("success", False),
            "original_code": original_code,
            "final_code": current_code,
            "iterations": iterations,
            "fix_history": fix_history,
            "final_test_result": test_result
        }
    
    async def validate_code_with_requirements(
        self,
        code: str,
        requirements: str,
        max_tokens: int = 4096
    ) -> Dict[str, Any]:
        """Validate if code meets the specified requirements."""
        logger.info("Validating code against requirements...")
        
        # Build prompt for validation
        prompt = f"""
You are an expert code reviewer. Evaluate the following code against the requirements.

Requirements:
{requirements}

Code:
```python
{code}
```

Please provide a detailed review:
1. Does the code meet all the requirements? List any missing or partially implemented requirements.
2. Are there any bugs or potential issues?
3. What improvements could be made?

Rate the code from 1-10 in terms of how well it meets the requirements.
"""
        
        # Generate validation report using LLM
        validation_content = ""
        generation_start = datetime.now()
        
        async for response in self.ollama_client.chat(
            messages=[{"role": "user", "content": prompt}],
            stream=True,
            max_tokens=max_tokens
        ):
            if response and response.get("content"):
                validation_content += response["content"]
        
        generation_time = (datetime.now() - generation_start).total_seconds()
        
        # Extract rating if available
        rating_match = re.search(r'rate\s*(?:the\s*code)?\s*(?:from)?\s*\d+\s*(?:to|-)?\s*10\s*(?:as|:)?\s*(\d+)', 
                                validation_content, re.IGNORECASE)
        rating = int(rating_match.group(1)) if rating_match else None
        
        # Determine if validation passed (rating >= 7)
        validation_passed = rating is not None and rating >= 7
        
        return {
            "validation_passed": validation_passed,
            "rating": rating,
            "report": validation_content,
            "generation_time": generation_time,
            "timestamp": datetime.now().isoformat()
        }

class DocumentProcessor:
    """Processes and embeds documents for code context."""
    
    def __init__(
        self,
        ollama_client: OllamaClient,
        base_dir: Optional[Path] = None
    ):
        """Initialize document processor."""
        self.ollama_client = ollama_client
        self.base_dir = base_dir or Path.home() / ".code_arena" / "documents"
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.document_cache: Dict[str, Dict[str, Any]] = {}
        self._load_document_cache()
    
    async def process_directory(
        self,
        directory_path: Union[str, Path],
        file_extensions: Optional[List[str]] = None,
        recursive: bool = True,
        force_reprocess: bool = False
    ) -> Dict[str, Any]:
        """Process all documents in a directory."""
        directory = Path(directory_path)
        if not directory.is_dir():
            raise ValueError(f"Not a valid directory: {directory}")
        
        # Default file extensions for code files
        if file_extensions is None:
            file_extensions = ['.py', '.js', '.ts', '.java', '.c', '.cpp', '.h', '.hpp', '.md', '.txt']
        
        # Show human-in-the-loop prompt
        if RICH_AVAILABLE:
            console.print(f"[yellow]About to process documents in {directory} with extensions: {', '.join(file_extensions)}. Proceed? (y/n)[/yellow]")
        else:
            print(f"About to process documents in {directory} with extensions: {', '.join(file_extensions)}. Proceed? (y/n)")
            
        user_input = input().lower()
        if user_input != 'y':
            return {
                "processed": 0,
                "errors": 0,
                "status": "aborted",
                "message": "User aborted document processing"
            }
        
        # Gather files
        all_files = []
        if recursive:
            for ext in file_extensions:
                all_files.extend(list(directory.glob(f"**/*{ext}")))
        else:
            for ext in file_extensions:
                all_files.extend(list(directory.glob(f"*{ext}")))
        
        # Process files with progress tracking
        processed = 0
        errors = 0
        
        if RICH_AVAILABLE:
            console.print(f"[cyan]Processing {len(all_files)} files...[/cyan]")
        else:
            print(f"Processing {len(all_files)} files...")
        
        for i, file_path in enumerate(all_files):
            try:
                # Skip if already processed and not forcing reprocess
                relative_path = file_path.relative_to(directory)
                cache_key = str(relative_path)
                
                if cache_key in self.document_cache and not force_reprocess:
                    if RICH_AVAILABLE:
                        console.print(f"[cyan]Skipping already processed file ({i+1}/{len(all_files)}): {relative_path}[/cyan]")
                    else:
                        print(f"Skipping already processed file ({i+1}/{len(all_files)}): {relative_path}")
                    processed += 1
                    continue
                
                if RICH_AVAILABLE:
                    console.print(f"[cyan]Processing file ({i+1}/{len(all_files)}): {relative_path}[/cyan]")
                else:
                    print(f"Processing file ({i+1}/{len(all_files)}): {relative_path}")
                
                # Process the file
                result = await self.process_file(file_path)
                
                if result["success"]:
                    processed += 1
                    # Cache the result
                    self.document_cache[cache_key] = {
                        "path": str(file_path),
                        "relative_path": str(relative_path),
                        "processed_at": datetime.now().isoformat(),
                        "embedding_id": result.get("embedding_id"),
                        "content_type": result.get("content_type")
                    }
                    if RICH_AVAILABLE:
                        console.print(f"[green]Successfully processed {relative_path}[/green]")
                    else:
                        print(f"Successfully processed {relative_path}")
                else:
                    errors += 1
                    if RICH_AVAILABLE:
                        console.print(f"[red]Error processing {relative_path}: {result.get('error', 'Unknown error')}[/red]")
                    else:
                        print(f"Error processing {relative_path}: {result.get('error', 'Unknown error')}")
            
            except Exception as e:
                errors += 1
                logger.error(f"Error processing file {file_path}: {str(e)}")
                if RICH_AVAILABLE:
                    console.print(f"[red]Error processing {file_path}: {str(e)}[/red]")
                else:
                    print(f"Error processing {file_path}: {str(e)}")
        
        # Save document cache
        self._save_document_cache()
        
        return {
            "processed": processed,
            "errors": errors,
            "total": len(all_files),
            "status": "completed",
            "directory": str(directory)
        }
    
    async def process_file(self, file_path: Union[str, Path]) -> Dict[str, Any]:
        """Process a single file and store in memory with embeddings."""
        file_path = Path(file_path)
        if not file_path.is_file():
            return {"success": False, "error": f"Not a valid file: {file_path}"}
        
        try:
            # Read file content
            content = file_path.read_text(errors='replace')
            
            # Determine content type
            extension = file_path.suffix.lower()
            content_type = "code" if extension in ['.py', '.js', '.ts', '.java', '.c', '.cpp', '.h', '.hpp'] else "text"
            
            # Generate embedding
            embedding = await self.ollama_client.generate_embedding(content)
            
            # Generate a unique ID for this document
            embedding_id = f"doc_{uuid.uuid4().hex[:12]}"
            
            # Store document with embedding
            doc_path = self.base_dir / f"{embedding_id}.json"
            with open(doc_path, 'w') as f:
                json.dump({
                    "content": content,
                    "embedding": embedding,
                    "metadata": {
                        "type": "document",
                        "content_type": content_type,
                        "file_path": str(file_path),
                        "file_name": file_path.name,
                        "extension": extension,
                        "timestamp": datetime.now().isoformat(),
                        "language": self._determine_language(extension)
                    },
                    "embedding_id": embedding_id
                }, f, indent=2)
            
            return {
                "success": True,
                "embedding_id": embedding_id,
                "content_type": content_type,
                "file_path": str(file_path),
                "file_name": file_path.name
            }
            
        except Exception as e:
            logger.error(f"Failed to process file {file_path}: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "file_path": str(file_path)
            }
    
    def _determine_language(self, extension: str) -> str:
        """Determine programming language from file extension."""
        extension_map = {
            '.py': 'python',
            '.js': 'javascript',
            '.ts': 'typescript',
            '.java': 'java',
            '.c': 'c',
            '.cpp': 'cpp',
            '.h': 'c',
            '.hpp': 'cpp',
            '.rb': 'ruby',
            '.php': 'php',
            '.go': 'go',
            '.rs': 'rust',
            '.swift': 'swift',
            '.kt': 'kotlin',
            '.md': 'markdown',
            '.txt': 'text'
        }
        return extension_map.get(extension.lower(), 'unknown')
    
    def _save_document_cache(self) -> None:
        """Save document cache to disk."""
        cache_path = self.base_dir / "document_cache.json"
        with open(cache_path, 'w') as f:
            json.dump(self.document_cache, f, indent=2)
    
    def _load_document_cache(self) -> None:
        """Load document cache from disk."""
        cache_path = self.base_dir / "document_cache.json"
        if cache_path.exists():
            try:
                with open(cache_path, 'r') as f:
                    self.document_cache = json.load(f)
            except Exception as e:
                logger.warning(f"Failed to load document cache: {str(e)}")
                self.document_cache = {}
        else:
            self.document_cache = {}
    
    async def find_relevant_documents(
        self,
        query: str,
        limit: int = 5,
        min_similarity: float = 0.3
    ) -> List[Dict[str, Any]]:
        """Find documents relevant to a query."""
        try:
            # Generate embedding for the query
            query_embedding = await self.ollama_client.generate_embedding(query)
            
            # Find all document files
            doc_files = list(self.base_dir.glob("doc_*.json"))
            
            documents = []
            
            # Calculate similarity and sort results
            for doc_file in doc_files:
                try:
                    with open(doc_file, 'r') as f:
                        doc_data = json.load(f)
                    
                    # Calculate cosine similarity if embeddings available
                    similarity = 0.0
                    if "embedding" in doc_data and query_embedding:
                        similarity = self._cosine_similarity(query_embedding, doc_data["embedding"])
                    
                    # Only include documents above similarity threshold
                    if similarity >= min_similarity:
                        documents.append({
                            "content": doc_data.get("content", ""),
                            "similarity": similarity,
                            "file_path": doc_data.get("metadata", {}).get("file_path", "Unknown"),
                            "file_name": doc_data.get("metadata", {}).get("file_name", "Unknown"),
                            "language": doc_data.get("metadata", {}).get("language", "unknown"),
                            "embedding_id": doc_data.get("embedding_id", "")
                        })
                except Exception as e:
                    logger.warning(f"Error processing document {doc_file}: {str(e)}")
            
            # Sort by similarity (highest first) and limit results
            documents.sort(key=lambda x: x["similarity"], reverse=True)
            return documents[:limit]
            
        except Exception as e:
            logger.error(f"Failed to find relevant documents: {str(e)}")
            return []
    
    def _cosine_similarity(self, vec1: List[float], vec2: List[float]) -> float:
        """Calculate cosine similarity between two vectors."""
        if not vec1 or not vec2 or len(vec1) != len(vec2):
            return 0.0
        
        dot_product = sum(a * b for a, b in zip(vec1, vec2))
        magnitude1 = sum(a * a for a in vec1) ** 0.5
        magnitude2 = sum(b * b for b in vec2) ** 0.5
        
        if magnitude1 == 0 or magnitude2 == 0:
            return 0.0
            
        return dot_product / (magnitude1 * magnitude2)

class CodeGenerator:
    """Generates code using LLM with context from documents."""
    
    def __init__(
        self,
        ollama_client: OllamaClient,
        document_processor: DocumentProcessor,
        test_manager: TestManager
    ):
        """Initialize the code generator."""
        self.ollama_client = ollama_client
        self.document_processor = document_processor
        self.test_manager = test_manager
        self.code_cache: Dict[str, Dict[str, Any]] = {}
    
    async def generate_code(
        self,
        requirements: str,
        language: str = "python",
        context: Optional[str] = None,
        max_tokens: int = 4096,
        use_document_context: bool = True,
        run_tests: bool = True
    ) -> Dict[str, Any]:
        """Generate code based on requirements and context, with optional testing."""
        logger.info(f"Generating {language} code for: {requirements[:50]}...")
        
        # Check cache first
        cache_key = f"{language}:{requirements}"
        if cache_key in self.code_cache and not run_tests:
            logger.info("Using cached code generation result")
            return self.code_cache[cache_key]
        
        # Gather document context if available and requested
        document_context = ""
        if self.document_processor and use_document_context:
            try:
                relevant_docs = await self.document_processor.find_relevant_documents(
                    query=requirements,
                    limit=3
                )
                
                if relevant_docs:
                    document_context = "Relevant documents for context:\n\n"
                    for i, doc in enumerate(relevant_docs, 1):
                        # Truncate document content if too long
                        content = doc["content"]
                        if len(content) > 1000:
                            content = content[:1000] + "..."
                        
                        document_context += f"Document {i} ({doc['file_name']}):\n```{doc['language']}\n{content}\n```\n\n"
            except Exception as e:
                logger.warning(f"Failed to gather document context: {str(e)}")
        
        # Build prompt for code generation
        prompt = f"""
You are an expert {language} developer tasked with writing high-quality code.

Requirements:
{requirements}

Your task is to:
1. Write {language} code that fully implements the requirements
2. Include clear comments explaining the code
3. Follow best practices for {language} development
4. Add docstrings and type hints when appropriate
5. Make the code efficient and maintainable
6. Ensure the code is well-tested and handles error cases

{document_context}
{context or ''}

Respond ONLY with the code, no explanations. The code should be directly executable.
"""
        
        # Generate code using LLM
        code_content = ""
        generation_start = datetime.now()
        
        async for response in self.ollama_client.chat(
            messages=[{"role": "user", "content": prompt}],
            stream=True,
            max_tokens=max_tokens
        ):
            if response and response.get("content"):
                code_content += response["content"]
        
        generation_time = (datetime.now() - generation_start).total_seconds()
        
        # Extract code block if needed
        final_code = code_content
        code_blocks = re.findall(r'```(?:' + language + r')?\s*([\s\S]*?)\s*```', code_content)
        if code_blocks:
            final_code = code_blocks[0]
        
        # Show human-in-the-loop verification
        if RICH_AVAILABLE:
            console.print(f"[yellow]Generated {language} code based on requirements. Review the code? (y/n)[/yellow]")
        else:
            print(f"Generated {language} code based on requirements. Review the code? (y/n)")
            
        user_input = input().lower()
        if user_input == 'y':
            if RICH_AVAILABLE:
                console.print(f"[cyan]Generated Code:[/cyan]")
                console.print(Syntax(final_code, language=language))
                console.print("[yellow]Is this code acceptable? (y/n)[/yellow]")
            else:
                print(f"Generated Code:")
                print(f"```{language}")
                print(final_code)
                print("```")
                print("Is this code acceptable? (y/n)")
                
            accept_input = input().lower()
            if accept_input != 'y':
                if RICH_AVAILABLE:
                    console.print("[yellow]Would you like to regenerate the code? (y/n)[/yellow]")
                else:
                    print("Would you like to regenerate the code? (y/n)")
                
                regenerate = input().lower()
                if regenerate == 'y':
                    return await self.generate_code(
                        requirements=requirements + " Please try a different approach.",
                        language=language,
                        context=context,
                        max_tokens=max_tokens,
                        use_document_context=use_document_context,
                        run_tests=run_tests
                    )
        
        result = {
            "code": final_code,
            "language": language,
            "generation_time": generation_time,
            "raw_response": code_content,
            "timestamp": datetime.now().isoformat()
        }
        
        # Run tests if requested
        if run_tests and language.lower() == "python":
            if RICH_AVAILABLE:
                console.print("[cyan]Testing generated code...[/cyan]")
            else:
                print("Testing generated code...")
            
            try:
                # Generate tests
                tests_result = await self.test_manager.generate_tests(
                    code=final_code,
                    requirements=requirements
                )
                
                # Create test environment if needed
                if not self.test_manager.current_env_id:
                    await self.test_manager.setup_test_environment()
                
                # Run tests
                test_result = await self.test_manager.run_tests(
                    code=final_code,
                    test_code=tests_result["test_code"]
                )
                
                # Add test results to the result
                result["tests"] = {
                    "test_code": tests_result["test_code"],
                    "success": test_result["success"],
                    "output": test_result["output"],
                    "summary": test_result["summary"]
                }
                
                # If tests failed, attempt to fix the code
                if not test_result["success"]:
                    if RICH_AVAILABLE:
                        console.print("[red]Tests failed. Attempting to fix the code...[/red]")
                    else:
                        print("Tests failed. Attempting to fix the code...")
                    
                    fix_result = await self.test_manager.fix_code(
                        code=final_code,
                        test_code=tests_result["test_code"],
                        test_result=test_result,
                        requirements=requirements
                    )
                    
                    # If the fix was successful, update the code
                    if fix_result["success"]:
                        result["code"] = fix_result["final_code"]
                        result["fix_history"] = fix_result["fix_history"]
                        result["iterations"] = fix_result["iterations"]
                        result["tests"]["success"] = True
                        result["tests"]["fixed"] = True
                        
                        if RICH_AVAILABLE:
                            console.print("[green]Code successfully fixed and now passes all tests.[/green]")
                        else:
                            print("Code successfully fixed and now passes all tests.")
                    else:
                        result["tests"]["fixed"] = False
                        result["fix_attempts"] = fix_result["iterations"]
                        
                        if RICH_AVAILABLE:
                            console.print("[yellow]Could not automatically fix all issues. Manual review recommended.[/yellow]")
                        else:
                            print("Could not automatically fix all issues. Manual review recommended.")
                else:
                    if RICH_AVAILABLE:
                        console.print("[green]Code passed all tests successfully![/green]")
                    else:
                        print("Code passed all tests successfully!")
            except Exception as e:
                logger.error(f"Error during testing: {str(e)}")
                result["tests"] = {
                    "success": False,
                    "error": str(e)
                }
        
        # Cache the result
        self.code_cache[cache_key] = result
        
        return result
    
    async def generate_tests(
        self,
        code: str,
        requirements: str,
        language: str = "python",
        test_framework: str = "pytest",
        max_tokens: int = 4096
    ) -> Dict[str, Any]:
        """Generate test cases for the specified code."""
        return await self.test_manager.generate_tests(
            code=code,
            requirements=requirements,
            test_framework=test_framework
        )
    
    async def improve_code(
        self,
        code: str,
        execution_result: Dict[str, Any],
        requirements: str,
        language: str = "python",
        max_tokens: int = 4096
    ) -> Dict[str, Any]:
        """Improve code based on execution results and feedback."""
        logger.info("Improving code based on execution results...")
        
        # Format execution results for the prompt
        execution_info = ""
        if execution_result.get("success"):
            execution_info = "The code executed successfully with the following output:\n\n"
            execution_info += execution_result.get("stdout", "No output") + "\n\n"
        else:
            execution_info = "The code execution failed with the following error:\n\n"
            execution_info += execution_result.get("error", "Unknown error") + "\n\n"
            execution_info += "Standard Error Output:\n"
            execution_info += execution_result.get("stderr", "No stderr output") + "\n\n"
        
        # Build prompt for code improvement
        prompt = f"""
You are an expert {language} developer tasked with improving existing code.

Original requirements:
{requirements}

Current code:
```{language}
{code}
```

Execution results:
{execution_info}

Your task is to:
1. Fix any errors or issues in the code
2. Improve the code's efficiency and readability
3. Ensure the code meets the original requirements
4. Add better error handling if needed
5. Keep the code structure similar to the original unless major changes are needed

Respond ONLY with the improved code, no explanations. The code should be directly executable.
"""
        
        # Generate improved code using LLM
        improved_content = ""
        generation_start = datetime.now()
        
        async for response in self.ollama_client.chat(
            messages=[{"role": "user", "content": prompt}],
            stream=True,
            max_tokens=max_tokens
        ):
            if response and response.get("content"):
                improved_content += response["content"]
        
        generation_time = (datetime.now() - generation_start).total_seconds()
        
        # Extract improved code block if needed
        improved_code = improved_content
        code_blocks = re.findall(r'```(?:' + language + r')?\s*([\s\S]*?)\s*```', improved_content)
        if code_blocks:
            improved_code = code_blocks[0]
        
        # Show human-in-the-loop verification
        if RICH_AVAILABLE:
            console.print(f"[yellow]Generated improved {language} code. Review the improvements? (y/n)[/yellow]")
        else:
            print(f"Generated improved {language} code. Review the improvements? (y/n)")
            
        user_input = input().lower()
        if user_input == 'y':
            if RICH_AVAILABLE:
                console.print(f"[cyan]Original Code:[/cyan]")
                console.print(Syntax(code, language=language))
                console.print(f"[cyan]Improved Code:[/cyan]")
                console.print(Syntax(improved_code, language=language))
                console.print("[yellow]Are these improvements acceptable? (y/n)[/yellow]")
            else:
                print(f"Original Code:")
                print(f"```{language}")
                print(code)
                print("```")
                print(f"Improved Code:")
                print(f"```{language}")
                print(improved_code)
                print("```")
                print("Are these improvements acceptable? (y/n)")
                
            accept_input = input().lower()
            if accept_input != 'y':
                if RICH_AVAILABLE:
                    console.print("[yellow]Would you like to regenerate the improvements? (y/n)[/yellow]")
                else:
                    print("Would you like to regenerate the improvements? (y/n)")
                    
                regenerate = input().lower()
                if regenerate == 'y':
                    return await self.improve_code(
                        code=code,
                        execution_result=execution_result,
                        requirements=requirements + " Please try a different approach to fixing this code.",
                        language=language,
                        max_tokens=max_tokens
                    )
        
        # If tests passed, store the improvement in memory
        if not execution_result.get("success", False) and self.test_manager:
            # Test if the improvements fixed the issue
            test_result = await self.test_manager.run_tests(
                code=improved_code,
                test_code="",  # Generate simple test to verify it runs
                env_id=self.test_manager.current_env_id
            )
            
            if test_result.get("success", False):
                # Store the successful fix
                error_message = execution_result.get("error", "") or execution_result.get("stderr", "")
                self.test_manager.memory_manager.add_fix(
                    issue_type="execution_error",
                    original_code=code,
                    fixed_code=improved_code,
                    error_message=error_message,
                    solution_description="Fixed code that failed during execution."
                )
        
        return {
            "improved_code": improved_code,
            "language": language,
            "generation_time": generation_time,
            "raw_response": improved_content,
            "timestamp": datetime.now().isoformat(),
            "fixed_issues": not execution_result.get("success", False)
        }

class CodeArenaChat:
    """Chat interface for the Code Arena, integrating all components."""
    
    def __init__(
        self,
        ollama_client: OllamaClient,
        base_dir: Optional[Path] = None
    ):
        """Initialize the code arena chat."""
        self.ollama_client = ollama_client
        self.base_dir = base_dir or Path.home() / ".code_arena"
        self.base_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize components
        self.memory_manager = MemoryManager(self.base_dir / "memory")
        self.env_manager = VirtualenvManager(self.base_dir / "virtualenvs")
        self.document_processor = DocumentProcessor(
            ollama_client=ollama_client,
            base_dir=self.base_dir / "documents"
        )
        self.test_manager = TestManager(
            virtualenv_manager=self.env_manager,
            memory_manager=self.memory_manager,
            ollama_client=ollama_client
        )
        self.code_generator = CodeGenerator(
            ollama_client=ollama_client,
            document_processor=self.document_processor,
            test_manager=self.test_manager
        )
        
        # Session tracking
        self.active_sessions: Dict[str, Dict[str, Any]] = {}
        self.current_session_id: Optional[str] = None
        self.chat_history: List[Dict[str, Any]] = []
    
    async def initialize(self) -> bool:
        """Initialize the code arena chat."""
        try:
            logger.info("Initializing Code Arena Chat...")
            
            # Create default environment
            default_env_id = await self.env_manager.create_environment(
                env_id="default",
                packages=["pytest", "numpy", "pandas", "requests"]
            )
            
            # Setup test environment
            test_env_id = await self.test_manager.setup_test_environment()
            
            logger.info(f"Created default environment: {default_env_id}")
            logger.info(f"Created test environment: {test_env_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize Code Arena Chat: {str(e)}")
            return False
    
    async def create_session(
        self,
        requirements: str,
        language: str = "python",
        packages: Optional[List[str]] = None,
        context: Optional[str] = None,
        run_tests: bool = True
    ) -> Dict[str, Any]:
        """Create a new code session."""
        session_id = f"session_{uuid.uuid4().hex[:8]}"
        logger.info(f"Creating session {session_id} for {language} project")
        
        try:
            # Create environment for the session
            env_id = await self.env_manager.create_environment(
                env_id=f"env_{session_id}",
                packages=packages
            )
            
            # Generate initial code with optional testing
            code_result = await self.code_generator.generate_code(
                requirements=requirements,
                language=language,
                context=context,
                run_tests=run_tests
            )
            
            # Generate tests if not already done during code generation
            test_result = {}
            if not code_result.get("tests"):
                test_result = await self.code_generator.generate_tests(
                    code=code_result["code"],
                    requirements=requirements,
                    language=language
                )
            else:
                test_result = {
                    "test_code": code_result["tests"]["test_code"]
                }
            
            # Create session record
            session = {
                "session_id": session_id,
                "env_id": env_id,
                "language": language,
                "requirements": requirements,
                "created_at": datetime.now().isoformat(),
                "last_updated": datetime.now().isoformat(),
                "iterations": code_result.get("iterations", 0),
                "status": "created",
                "code": code_result["code"],
                "tests": test_result["test_code"],
                "tests_passed": code_result.get("tests", {}).get("success", False),
                "history": [
                    {
                        "type": "code_generation",
                        "timestamp": code_result["timestamp"],
                        "content": code_result["code"]
                    },
                    {
                        "type": "test_generation",
                        "timestamp": datetime.now().isoformat(),
                        "content": test_result["test_code"]
                    }
                ]
            }
            
            # Add fix history if available
            if "fix_history" in code_result:
                session["fix_history"] = code_result["fix_history"]
            
            # Store session
            self.active_sessions[session_id] = session
            self.current_session_id = session_id
            
            # Save session to disk for persistence
            session_path = self.base_dir / "sessions" / f"{session_id}.json"
            session_path.parent.mkdir(exist_ok=True, parents=True)
            with open(session_path, 'w') as f:
                json.dump(session, f, indent=2)
            
            # Add to chat history
            self.chat_history.append({
                "role": "system",
                "content": f"Created new coding session: {session_id}",
                "timestamp": datetime.now().isoformat()
            })
            
            return {
                "session_id": session_id,
                "code": code_result["code"],
                "tests": test_result["test_code"],
                "status": "created",
                "tests_passed": code_result.get("tests", {}).get("success", False)
            }
            
        except Exception as e:
            logger.error(f"Failed to create session: {str(e)}")
            return {
                "error": str(e),
                "status": "failed"
            }
    
    async def run_code(
        self,
        session_id: Optional[str] = None,
        code: Optional[str] = None,
        timeout: int = 30
    ) -> Dict[str, Any]:
        """Run code in a session environment."""
        session_id = session_id or self.current_session_id
        if not session_id:
            error_msg = "No active session. Please create a session first."
            self.chat_history.append({
                "role": "system",
                "content": error_msg,
                "timestamp": datetime.now().isoformat()
            })
            return {"error": error_msg, "status": "error"}
        
        if session_id not in self.active_sessions:
            error_msg = f"Session {session_id} not found"
            self.chat_history.append({
                "role": "system",
                "content": error_msg,
                "timestamp": datetime.now().isoformat()
            })
            return {"error": error_msg, "status": "error"}
        
        session = self.active_sessions[session_id]
        code_to_run = code or session["code"]
        
        try:
            # Execute the code
            execution_start = datetime.now()
            result = await self.env_manager.execute_code(
                env_id=session["env_id"],
                code=code_to_run,
                timeout=timeout
            )
            execution_time = (datetime.now() - execution_start).total_seconds()
            
            # Update result with timing
            result["execution_time"] = execution_time
            
            # Record execution in session history
            session["history"].append({
                "type": "code_execution",
                "timestamp": datetime.now().isoformat(),
                "success": result["success"],
                "stdout": result["stdout"],
                "stderr": result["stderr"],
                "execution_time": execution_time
            })
            
            # Update session
            session["last_updated"] = datetime.now().isoformat()
            session["last_execution"] = result
            
            # Save session to disk
            session_path = self.base_dir / "sessions" / f"{session_id}.json"
            with open(session_path, 'w') as f:
                json.dump(session, f, indent=2)
            
            # If execution failed, try to find similar fixes in memory
            fix_suggestions = ""
            if not result["success"]:
                error_message = result.get("error", "") or result.get("stderr", "")
                similar_fixes = self.memory_manager.find_similar_fixes(error_message, code_to_run)
                
                if similar_fixes:
                    fix_suggestions = "\n\nPotential fixes from memory:\n"
                    for i, fix in enumerate(similar_fixes, 1):
                        fix_suggestions += f"{i}. {fix.get('solution_description', 'No description')}\n"
            
            # Add to chat history
            status = "succeeded" if result["success"] else "failed"
            self.chat_history.append({
                "role": "system",
                "content": f"Code execution {status} in {execution_time:.2f}s{fix_suggestions}",
                "timestamp": datetime.now().isoformat(),
                "metadata": {
                    "execution_result": result
                }
            })
            
            return {
                "session_id": session_id,
                "success": result["success"],
                "stdout": result["stdout"],
                "stderr": result["stderr"],
                "error": result.get("error"),
                "execution_time": execution_time,
                "fix_suggestions": fix_suggestions if fix_suggestions else None
            }
            
        except Exception as e:
            error_msg = f"Failed to run code in session {session_id}: {str(e)}"
            logger.error(error_msg)
            
            # Add to chat history
            self.chat_history.append({
                "role": "system",
                "content": error_msg,
                "timestamp": datetime.now().isoformat()
            })
            
            return {
                "session_id": session_id,
                "success": False,
                "error": str(e),
                "status": "error"
            }
    
    async def run_tests(
        self,
        session_id: Optional[str] = None,
        timeout: int = 60
    ) -> Dict[str, Any]:
        """Run tests for the code in a session."""
        session_id = session_id or self.current_session_id
        if not session_id:
            error_msg = "No active session. Please create a session first."
            self.chat_history.append({
                "role": "system",
                "content": error_msg,
                "timestamp": datetime.now().isoformat()
            })
            return {"error": error_msg, "status": "error"}
        
        if session_id not in self.active_sessions:
            error_msg = f"Session {session_id} not found"
            self.chat_history.append({
                "role": "system",
                "content": error_msg,
                "timestamp": datetime.now().isoformat()
            })
            return {"error": error_msg, "status": "error"}
        
        session = self.active_sessions[session_id]
        
        try:
            # Run tests using test manager
            test_result = await self.test_manager.run_tests(
                code=session["code"],
                test_code=session["tests"],
                timeout=timeout
            )
            
            # Record test execution in session history
            session["history"].append({
                "type": "test_execution",
                "timestamp": datetime.now().isoformat(),
                "success": test_result["success"],
                "output": test_result["output"],
                "summary": test_result["summary"],
                "execution_time": test_result["execution_time"]
            })
            
            # Update session
            session["last_updated"] = datetime.now().isoformat()
            session["last_test_execution"] = {
                "success": test_result["success"],
                "output": test_result["output"],
                "summary": test_result["summary"]
            }
            session["tests_passed"] = test_result["success"]
            
            # Save session to disk
            session_path = self.base_dir / "sessions" / f"{session_id}.json"
            with open(session_path, 'w') as f:
                json.dump(session, f, indent=2)
            
            # Add to chat history
            status = "passed" if test_result["success"] else "failed"
            self.chat_history.append({
                "role": "system",
                "content": f"Tests {status}: {test_result['summary']}",
                "timestamp": datetime.now().isoformat(),
                "metadata": {
                    "test_result": {
                        "success": test_result["success"],
                        "summary": test_result["summary"]
                    }
                }
            })
            
            return {
                "session_id": session_id,
                "tests_passed": test_result["success"],
                "test_output": test_result["output"],
                "test_summary": test_result["summary"],
                "execution_time": test_result["execution_time"]
            }
            
        except Exception as e:
            error_msg = f"Failed to run tests in session {session_id}: {str(e)}"
            logger.error(error_msg)
            
            # Add to chat history
            self.chat_history.append({
                "role": "system",
                "content": error_msg,
                "timestamp": datetime.now().isoformat()
            })
            
            return {
                "session_id": session_id,
                "success": False,
                "error": str(e),
                "status": "error"
            }
    
    async def fix_code(
        self,
        session_id: Optional[str] = None,
        max_iterations: int = 5
    ) -> Dict[str, Any]:
        """Fix code that fails tests."""
        session_id = session_id or self.current_session_id
        if not session_id:
            error_msg = "No active session. Please create a session first."
            self.chat_history.append({
                "role": "system",
                "content": error_msg,
                "timestamp": datetime.now().isoformat()
            })
            return {"error": error_msg, "status": "error"}
        
        if session_id not in self.active_sessions:
            error_msg = f"Session {session_id} not found"
            self.chat_history.append({
                "role": "system",
                "content": error_msg,
                "timestamp": datetime.now().isoformat()
            })
            return {"error": error_msg, "status": "error"}
        
        session = self.active_sessions[session_id]
        
        # Check if we have test results
        if "last_test_execution" not in session:
            # Run tests first
            test_result = await self.run_tests(session_id=session_id)
            
            # If tests pass, no need to fix
            if test_result.get("tests_passed", False):
                return {
                    "session_id": session_id,
                    "success": True,
                    "message": "Code already passes all tests.",
                    "status": "no_fix_needed"
                }
        else:
            # Use existing test results
            test_result = {
                "success": session["last_test_execution"]["success"],
                "output": session["last_test_execution"]["output"],
                "summary": session["last_test_execution"]["summary"],
                "error": "" # No error message in the existing format
            }
            
            # If tests pass, no need to fix
            if test_result["success"]:
                return {
                    "session_id": session_id,
                    "success": True,
                    "message": "Code already passes all tests.",
                    "status": "no_fix_needed"
                }
        
        try:
            # Fix the code using the test manager
            fix_result = await self.test_manager.fix_code(
                code=session["code"],
                test_code=session["tests"],
                test_result=test_result,
                requirements=session["requirements"],
                max_iterations=max_iterations
            )
            
            if fix_result["success"]:
                # Update session with fixed code
                session["code"] = fix_result["final_code"]
                session["iterations"] += fix_result["iterations"]
                session["last_updated"] = datetime.now().isoformat()
                session["tests_passed"] = True
                
                # Add fix history
                if "fix_history" not in session:
                    session["fix_history"] = []
                session["fix_history"].extend(fix_result["fix_history"])
                
                # Add to session history
                session["history"].append({
                    "type": "code_fix",
                    "timestamp": datetime.now().isoformat(),
                    "iterations": fix_result["iterations"],
                    "success": True
                })
                
                # Save session to disk
                session_path = self.base_dir / "sessions" / f"{session_id}.json"
                with open(session_path, 'w') as f:
                    json.dump(session, f, indent=2)
                
                # Add to chat history
                self.chat_history.append({
                    "role": "system",
                    "content": f"Code fixed successfully after {fix_result['iterations']} iterations. All tests now pass.",
                    "timestamp": datetime.now().isoformat()
                })
                
                return {
                    "session_id": session_id,
                    "success": True,
                    "iterations": fix_result["iterations"],
                    "fixed_code": fix_result["final_code"],
                    "test_result": fix_result["final_test_result"]
                }
            else:
                # Record failed fix attempt
                session["history"].append({
                    "type": "code_fix",
                    "timestamp": datetime.now().isoformat(),
                    "iterations": fix_result["iterations"],
                    "success": False
                })
                
                # Save session to disk
                session_path = self.base_dir / "sessions" / f"{session_id}.json"
                with open(session_path, 'w') as f:
                    json.dump(session, f, indent=2)
                
                # Add to chat history
                self.chat_history.append({
                    "role": "system",
                    "content": f"Failed to fix all issues after {fix_result['iterations']} iterations. Some tests still fail.",
                    "timestamp": datetime.now().isoformat()
                })
                
                return {
                    "session_id": session_id,
                    "success": False,
                    "iterations": fix_result["iterations"],
                    "current_code": fix_result["final_code"],
                    "test_result": fix_result["final_test_result"]
                }
        
        except Exception as e:
            error_msg = f"Failed to fix code in session {session_id}: {str(e)}"
            logger.error(error_msg)
            
            # Add to chat history
            self.chat_history.append({
                "role": "system",
                "content": error_msg,
                "timestamp": datetime.now().isoformat()
            })
            
            return {
                "session_id": session_id,
                "success": False,
                "error": str(e),
                "status": "error"
            }
    
    async def improve_code(
        self,
        session_id: Optional[str] = None,
        max_tokens: int = 4096
    ) -> Dict[str, Any]:
        """Improve code based on execution or test results."""
        session_id = session_id or self.current_session_id
        if not session_id:
            error_msg = "No active session. Please create a session first."
            self.chat_history.append({
                "role": "system",
                "content": error_msg,
                "timestamp": datetime.now().isoformat()
            })
            return {"error": error_msg, "status": "error"}
        
        if session_id not in self.active_sessions:
            error_msg = f"Session {session_id} not found"
            self.chat_history.append({
                "role": "system",
                "content": error_msg,
                "timestamp": datetime.now().isoformat()
            })
            return {"error": error_msg, "status": "error"}
        
        session = self.active_sessions[session_id]
        
        # Check if we have execution results to improve upon
        if "last_execution" not in session and "last_test_execution" not in session:
            error_msg = "No execution or test results available for improvement"
            self.chat_history.append({
                "role": "system",
                "content": error_msg,
                "timestamp": datetime.now().isoformat()
            })
            return {"error": error_msg, "status": "error"}
        
        try:
            # Use execution results if available, otherwise test results
            execution_result = session.get("last_execution", {})
            if not execution_result and "last_test_execution" in session:
                # Format test results as an execution result
                test_result = session["last_test_execution"]
                execution_result = {
                    "success": test_result.get("success", False),
                    "stdout": test_result.get("output", ""),
                    "stderr": "",
                    "error": "" if test_result.get("success", False) else "Tests failed"
                }
            
            # Generate improved code
            improvement_result = await self.code_generator.improve_code(
                code=session["code"],
                execution_result=execution_result,
                requirements=session["requirements"],
                language=session["language"],
                max_tokens=max_tokens
            )
            
            # Update session with improved code
            original_code = session["code"]
            session["code"] = improvement_result["improved_code"]
            session["iterations"] += 1
            session["last_updated"] = datetime.now().isoformat()
            
            # Add to history
            session["history"].append({
                "type": "code_improvement",
                "timestamp": improvement_result["timestamp"],
                "content": improvement_result["improved_code"],
                "original_code": original_code
            })
            
            # Save session to disk
            session_path = self.base_dir / "sessions" / f"{session_id}.json"
            with open(session_path, 'w') as f:
                json.dump(session, f, indent=2)
            
            # Add to chat history
            self.chat_history.append({
                "role": "system",
                "content": f"Code improved (iteration {session['iterations']})",
                "timestamp": datetime.now().isoformat(),
                "metadata": {
                    "improvement": {
                        "fixed_issues": improvement_result["fixed_issues"],
                        "generation_time": improvement_result["generation_time"]
                    }
                }
            })
            
            return {
                "session_id": session_id,
                "improved_code": improvement_result["improved_code"],
                "original_code": original_code,
                "fixed_issues": improvement_result["fixed_issues"],
                "iteration": session["iterations"]
            }
            
        except Exception as e:
            error_msg = f"Failed to improve code in session {session_id}: {str(e)}"
            logger.error(error_msg)
            
            # Add to chat history
            self.chat_history.append({
                "role": "system",
                "content": error_msg,
                "timestamp": datetime.now().isoformat()
            })
            
            return {
                "session_id": session_id,
                "success": False,
                "error": str(e),
                "status": "error"
            }
    
    async def process_chat_message(
        self,
        message: str
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Process a chat message and generate a response."""
        # Add user message to history
        self.chat_history.append({
            "role": "user",
            "content": message,
            "timestamp": datetime.now().isoformat()
        })
        
        # Check for commands
        if message.startswith('/'):
            result = await self._handle_command(message)
            if result:
                yield result
                return
        
        # Try to find relevant documents for context
        document_context = ""
        try:
            relevant_docs = await self.document_processor.find_relevant_documents(
                query=message,
                limit=3
            )
            
            if relevant_docs:
                document_context = "I found these relevant documents that might help:\n\n"
                for i, doc in enumerate(relevant_docs, 1):
                    document_context += f"{i}. {doc['file_name']} - Similarity: {doc['similarity']:.2f}\n"
        except Exception as e:
            logger.warning(f"Failed to find relevant documents: {str(e)}")
        
        # Find relevant fixes from memory
        memory_context = ""
        try:
            similar_fixes = self.memory_manager.find_similar_fixes(message, limit=2)
            if similar_fixes:
                memory_context = "\n\nI found these similar code fixes in memory:\n\n"
                for i, fix in enumerate(similar_fixes, 1):
                    memory_context += f"{i}. Issue: {fix.get('issue_type', 'Unknown issue')}\n"
                    memory_context += f"   Solution: {fix.get('solution_description', 'No description')}\n"
        except Exception as e:
            logger.warning(f"Failed to find memory fixes: {str(e)}")
        
        # Generate response
        try:
            # Build context from the last few messages
            context_messages = []
            for msg in self.chat_history[-10:]:  # Last 10 messages for context
                context_messages.append({
                    "role": msg["role"],
                    "content": msg["content"]
                })
            
            # Add session context if available
            session_context = ""
            if self.current_session_id and self.current_session_id in self.active_sessions:
                session = self.active_sessions[self.current_session_id]
                session_context = f"\nCurrent session: {self.current_session_id}\n"
                session_context += f"Language: {session['language']}\n"
                session_context += f"Iterations: {session['iterations']}\n"
                session_context += f"Tests passing: {'Yes' if session.get('tests_passed', False) else 'No'}\n"
                
                if "last_execution" in session:
                    execution = session["last_execution"]
                    session_context += f"Last execution: {'Success' if execution.get('success') else 'Failed'}\n"
                
                if "last_test_execution" in session:
                    test_exec = session["last_test_execution"]
                    session_context += f"Last test execution: {'Passed' if test_exec.get('success') else 'Failed'}\n"
                
                # Send these as system context
                context_messages.append({
                    "role": "system",
                    "content": f"Current coding session information:\n{session_context}\n{document_context}\n{memory_context}"
                })
            
            # Generate streaming response
            response_content = ""
            async for response in self.ollama_client.chat(
                messages=context_messages,
                stream=True,
                temperature=0.7
            ):
                if response and response.get("content"):
                    response_content += response["content"]
                    yield {
                        "role": "assistant",
                        "content": response["content"],
                        "timestamp": datetime.now().isoformat(),
                        "streaming": True
                    }
            
            # Add complete response to history
            self.chat_history.append({
                "role": "assistant",
                "content": response_content,
                "timestamp": datetime.now().isoformat()
            })
            
        except Exception as e:
            error_msg = f"Error generating response: {str(e)}"
            logger.error(error_msg)
            
            # Add error to history
            self.chat_history.append({
                "role": "system",
                "content": error_msg,
                "timestamp": datetime.now().isoformat()
            })
            
            yield {
                "role": "system",
                "content": error_msg,
                "timestamp": datetime.now().isoformat(),
                "error": True
            }
    
    async def _handle_command(self, command: str) -> Optional[Dict[str, Any]]:
        """Handle chat commands."""
        parts = command.split()
        cmd = parts[0].lower()
        args = parts[1:] if len(parts) > 1 else []
        
        if cmd == '/help':
            return {
                "role": "system",
                "content": """Available commands:
/help - Show this help message
/create <language> <requirements> - Create a new coding session
/run - Run the current code
/test - Run tests for the current code
/fix - Fix code that fails tests
/improve - Improve the current code
/session <session_id> - Switch to or show info about a session
/list - List all available sessions
/code - Show the current code
/memory - Show relevant fixes from memory
/process <directory> - Process a directory for documents
/search <query> - Search documents for information
/install <package1> <package2> ... - Install packages in current session
/exit - Exit the Code Arena
""",
                "timestamp": datetime.now().isoformat()
            }
        
        elif cmd == '/create':
            if len(args) < 2:
                return {
                    "role": "system",
                    "content": "Usage: /create <language> <requirements>",
                    "timestamp": datetime.now().isoformat()
                }
            
            language = args[0]
            requirements = ' '.join(args[1:])
            
            result = await self.create_session(
                requirements=requirements,
                language=language,
                run_tests=True
            )
            
            if "error" in result:
                return {
                    "role": "system",
                    "content": f"Failed to create session: {result['error']}",
                    "timestamp": datetime.now().isoformat()
                }
            
            status_msg = ""
            if result.get("tests_passed", False):
                status_msg = " Code passed all tests."
            else:
                status_msg = " Some tests failed. Use /fix to attempt fixes."
            
            return {
                "role": "system",
                "content": f"Created new session {result['session_id']} for {language}. Generated code and tests.{status_msg}",
                "timestamp": datetime.now().isoformat()
            }
        
        elif cmd == '/run':
            result = await self.run_code()
            
            if "error" in result:
                return {
                    "role": "system",
                    "content": f"Error running code: {result['error']}",
                    "timestamp": datetime.now().isoformat()
                }
            
            # Format the output
            content = "Code execution "
            if result["success"]:
                content += f"succeeded in {result['execution_time']:.2f}s\n\nOutput:\n"
                content += result["stdout"] if result["stdout"] else "(No output)"
            else:
                content += f"failed in {result['execution_time']:.2f}s\n\nError:\n"
                content += result["error"] or result["stderr"] or "(No error details)"
                
                if result.get("fix_suggestions"):
                    content += "\n\n" + result["fix_suggestions"]
            
            return {
                "role": "system",
                "content": content,
                "timestamp": datetime.now().isoformat()
            }
        
        elif cmd == '/test':
            result = await self.run_tests()
            
            if "error" in result:
                return {
                    "role": "system",
                    "content": f"Error running tests: {result['error']}",
                    "timestamp": datetime.now().isoformat()
                }
            
            # Format the output
            content = "Test execution "
            if result["tests_passed"]:
                content += f"passed in {result['execution_time']:.2f}s\n\n"
                content += result["test_summary"] + "\n\n"
                content += "Test Output:\n" + result["test_output"]
            else:
                content += f"failed in {result['execution_time']:.2f}s\n\n"
                content += result["test_summary"] + "\n\n"
                content += "Test Output:\n" + result["test_output"]
                content += "\n\nUse /fix to attempt to fix the issues."
            
            return {
                "role": "system",
                "content": content,
                "timestamp": datetime.now().isoformat()
            }
        
        elif cmd == '/fix':
            result = await self.fix_code()
            
            if "error" in result:
                return {
                    "role": "system",
                    "content": f"Error fixing code: {result['error']}",
                    "timestamp": datetime.now().isoformat()
                }
            
            if result.get("status") == "no_fix_needed":
                return {
                    "role": "system",
                    "content": result["message"],
                    "timestamp": datetime.now().isoformat()
                }
            
            if result["success"]:
                content = f"Code fixed successfully after {result['iterations']} iterations. All tests now pass."
            else:
                content = f"Failed to fix all issues after {result['iterations']} iterations. Some tests still fail."
                content += "\n\nTest output:\n" + result["test_result"]["output"]
            
            return {
                "role": "system",
                "content": content,
                "timestamp": datetime.now().isoformat()
            }
        
        elif cmd == '/improve':
            result = await self.improve_code()
            
            if "error" in result:
                return {
                    "role": "system",
                    "content": f"Error improving code: {result['error']}",
                    "timestamp": datetime.now().isoformat()
                }
            
            content = f"Code improved (iteration {result['iteration']})\n"
            if result["fixed_issues"]:
                content += "Fixed issues detected in previous execution.\n"
            else:
                content += "Optimized and improved the code.\n"
            
            return {
                "role": "system",
                "content": content,
                "timestamp": datetime.now().isoformat()
            }
        
        elif cmd == '/session':
            if len(args) == 0:
                # Show current session info
                if not self.current_session_id:
                    return {
                        "role": "system",
                        "content": "No active session. Create one with /create command.",
                        "timestamp": datetime.now().isoformat()
                    }
                
                session = self.active_sessions[self.current_session_id]
                content = f"Current session: {self.current_session_id}\n"
                content += f"Language: {session['language']}\n"
                content += f"Requirements: {session['requirements']}\n"
                content += f"Created: {session['created_at']}\n"
                content += f"Last updated: {session['last_updated']}\n"
                content += f"Iterations: {session['iterations']}\n"
                content += f"Tests passing: {'Yes' if session.get('tests_passed', False) else 'No'}\n"
                
                return {
                    "role": "system",
                    "content": content,
                    "timestamp": datetime.now().isoformat()
                }
            else:
                # Switch to another session
                session_id = args[0]
                if session_id not in self.active_sessions:
                    return {
                        "role": "system",
                        "content": f"Session {session_id} not found. Use /list to see available sessions.",
                        "timestamp": datetime.now().isoformat()
                    }
                
                self.current_session_id = session_id
                return {
                    "role": "system",
                    "content": f"Switched to session {session_id}",
                    "timestamp": datetime.now().isoformat()
                }
        
        elif cmd == '/list':
            if not self.active_sessions:
                return {
                    "role": "system",
                    "content": "No active sessions. Create one with /create command.",
                    "timestamp": datetime.now().isoformat()
                }
            
            content = "Available sessions:\n\n"
            for session_id, session in self.active_sessions.items():
                content += f"- {session_id} ({session['language']}): {session['requirements'][:50]}...\n"
                content += f"  Created: {session['created_at']}, Iterations: {session['iterations']}\n"
                content += f"  Tests passing: {'Yes' if session.get('tests_passed', False) else 'No'}\n"
            
            return {
                "role": "system",
                "content": content,
                "timestamp": datetime.now().isoformat()
            }
        
        elif cmd == '/code':
            if not self.current_session_id:
                return {
                    "role": "system",
                    "content": "No active session. Create one with /create command.",
                    "timestamp": datetime.now().isoformat()
                }
            
            session = self.active_sessions[self.current_session_id]
            language = session['language']
            code = session['code']
            
            content = f"Current code ({language}):\n\n```{language}\n{code}\n```"
            
            return {
                "role": "system",
                "content": content,
                "timestamp": datetime.now().isoformat()
            }
        
        elif cmd == '/memory':
            # Show memory of fixes
            similar_fixes = self.memory_manager.find_similar_fixes("", limit=5)
            if not similar_fixes:
                return {
                    "role": "system",
                    "content": "No fix patterns found in memory.",
                    "timestamp": datetime.now().isoformat()
                }
            
            content = "Recent fix patterns in memory:\n\n"
            for i, fix in enumerate(similar_fixes, 1):
                content += f"{i}. Issue Type: {fix.get('issue_type', 'Unknown')}\n"
                content += f"   Error: {fix.get('error_message', '')[:100]}...\n"
                content += f"   Solution: {fix.get('solution_description', 'No description')}\n\n"
            
            return {
                "role": "system",
                "content": content,
                "timestamp": datetime.now().isoformat()
            }
        
        elif cmd == '/process':
            if len(args) < 1:
                return {
                    "role": "system",
                    "content": "Usage: /process <directory> [--recursive]",
                    "timestamp": datetime.now().isoformat()
                }
            
            directory = args[0]
            recursive = "--recursive" in args
            
            try:
                result = await self.document_processor.process_directory(
                    directory_path=directory,
                    recursive=recursive
                )
                
                content = f"Processed directory: {directory}\n"
                content += f"Files processed: {result['processed']}/{result['total']}\n"
                content += f"Errors: {result['errors']}\n"
                content += f"Status: {result['status']}"
                
                return {
                    "role": "system",
                    "content": content,
                    "timestamp": datetime.now().isoformat()
                }
            except Exception as e:
                return {
                    "role": "system",
                    "content": f"Error processing directory: {str(e)}",
                    "timestamp": datetime.now().isoformat()
                }
        
        elif cmd == '/search':
            if len(args) < 1:
                return {
                    "role": "system",
                    "content": "Usage: /search <query>",
                    "timestamp": datetime.now().isoformat()
                }
            
            query = ' '.join(args)
            
            try:
                documents = await self.document_processor.find_relevant_documents(
                    query=query,
                    limit=5
                )
                
                if not documents:
                    return {
                        "role": "system",
                        "content": "No relevant documents found.",
                        "timestamp": datetime.now().isoformat()
                    }
                
                content = f"Found {len(documents)} relevant documents for '{query}':\n\n"
                
                for i, doc in enumerate(documents, 1):
                    content += f"{i}. {doc['file_name']} (Similarity: {doc['similarity']:.2f})\n"
                    content += f"   Path: {doc['file_path']}\n"
                    
                    # Add a snippet of content
                    snippet = doc['content']
                    if len(snippet) > 300:
                        snippet = snippet[:300] + "..."
                    content += f"   Snippet: {snippet}\n\n"
                
                return {
                    "role": "system",
                    "content": content,
                    "timestamp": datetime.now().isoformat()
                }
            except Exception as e:
                return {
                    "role": "system",
                    "content": f"Error searching documents: {str(e)}",
                    "timestamp": datetime.now().isoformat()
                }
        
        elif cmd == '/install':
            if len(args) < 1:
                return {
                    "role": "system",
                    "content": "Usage: /install <package1> <package2> ...",
                    "timestamp": datetime.now().isoformat()
                }
            
            if not self.current_session_id:
                return {
                    "role": "system",
                    "content": "No active session. Create one with /create command.",
                    "timestamp": datetime.now().isoformat()
                }
            
            session = self.active_sessions[self.current_session_id]
            packages = args
            
            try:
                success = await self.env_manager.install_packages(
                    env_id=session['env_id'],
                    packages=packages
                )
                
                if success:
                    return {
                        "role": "system",
                        "content": f"Successfully installed packages: {', '.join(packages)}",
                        "timestamp": datetime.now().isoformat()
                    }
                else:
                    return {
                        "role": "system",
                        "content": f"Failed to install packages. Check logs for details.",
                        "timestamp": datetime.now().isoformat()
                    }
            except Exception as e:
                return {
                    "role": "system",
                    "content": f"Error installing packages: {str(e)}",
                    "timestamp": datetime.now().isoformat()
                }
        
        elif cmd == '/exit':
            # Clean up before exit
            await self.cleanup()
            
            return {
                "role": "system",
                "content": "Exiting Code Arena. Cleaned up resources.",
                "timestamp": datetime.now().isoformat()
            }
        
        return None
    
    async def cleanup(self) -> None:
        """Clean up resources."""
        try:
            # Clean up environments
            await self.env_manager.cleanup_all()
            
            # Save chat history
            history_path = self.base_dir / "chat_history.json"
            with open(history_path, 'w') as f:
                json.dump(self.chat_history, f, indent=2)
            
            # Save sessions
            for session_id, session in self.active_sessions.items():
                session_path = self.base_dir / "sessions" / f"{session_id}.json"
                session_path.parent.mkdir(exist_ok=True, parents=True)
                with open(session_path, 'w') as f:
                    json.dump(session, f, indent=2)
            
            logger.info("Code Arena Chat cleaned up successfully")
            
        except Exception as e:
            logger.error(f"Error during cleanup: {str(e)}")

async def run_code_arena_chat(ollama_client: OllamaClient, base_dir: Optional[Path] = None) -> None:
    """Run the Code Arena Chat application."""
    # Initialize the chat
    chat = CodeArenaChat(
        ollama_client=ollama_client,
        base_dir=base_dir
    )
    
    # Initialize the chat
    initialized = await chat.initialize()
    if not initialized:
        if RICH_AVAILABLE:
            console.print("[red]Failed to initialize Code Arena Chat.[/red]")
        else:
            print("Failed to initialize Code Arena Chat.")
        return
    
    if RICH_AVAILABLE:
        console.print("[green]Code Arena Chat initialized. Type /help for available commands.[/green]")
    else:
        print("Code Arena Chat initialized. Type /help for available commands.")
    
    # Main chat loop
    try:
        while True:
            # Display prompt
            if RICH_AVAILABLE:
                console.print("[cyan]You:[/cyan] ", end="")
            else:
                print("You: ", end="")
                
            user_input = input()
            
            if user_input.lower() == '/exit':
                # Handle exit command
                if RICH_AVAILABLE:
                    console.print("[yellow]Exiting Code Arena Chat...[/yellow]")
                else:
                    print("Exiting Code Arena Chat...")
                    
                await chat.cleanup()
                break
            
            # Process message and get response
            async for response in chat.process_chat_message(user_input):
                if response["role"] == "assistant":
                    if "streaming" in response and response["streaming"]:
                        # For streaming responses, print without newline
                        if RICH_AVAILABLE:
                            console.print(response["content"], end="")
                        else:
                            print(response["content"], end="", flush=True)
                    else:
                        # For complete responses
                        if RICH_AVAILABLE:
                            console.print(f"\n[blue]Assistant:[/blue] {response['content']}")
                        else:
                            print(f"\nAssistant: {response['content']}")
                elif response["role"] == "system":
                    # System messages (e.g., command results)
                    if RICH_AVAILABLE:
                        console.print(f"\n[green]System:[/green] {response['content']}")
                    else:
                        print(f"\nSystem: {response['content']}")
            
            # Print a newline after streaming responses
            print()
    
    except KeyboardInterrupt:
        if RICH_AVAILABLE:
            console.print("\n[yellow]Interrupted. Cleaning up resources...[/yellow]")
        else:
            print("\nInterrupted. Cleaning up resources...")
            
        await chat.cleanup()
    except Exception as e:
        if RICH_AVAILABLE:
            console.print(f"\n[red]Error in chat loop: {str(e)}[/red]")
        else:
            print(f"\nError in chat loop: {str(e)}")
            
        await chat.cleanup()
    
    if RICH_AVAILABLE:
        console.print("[green]Code Arena Chat terminated. Thank you for using the application.[/green]")
    else:
        print("Code Arena Chat terminated. Thank you for using the application.")

async def main():
    """Main entry point for standalone script."""
    # Parse command line arguments
    import argparse
    
    parser = argparse.ArgumentParser(description="Code Arena - An enhanced coding assistant with LLM integration, testing, and memory")
    parser.add_argument("--dir", "-d", help="Directory to process for code context")
    parser.add_argument("--model", help="Ollama model to use (default: muhammad-albasha/llama3.1-python:latest)")
    parser.add_argument("--base-url", help="Ollama API base URL (default: http://localhost:11434)")
    parser.add_argument("--data-dir", help="Base directory for Code Arena data")
    parser.add_argument("--no-tests", action="store_true", help="Disable automatic testing of generated code")
    
    args = parser.parse_args()
    
    # Setup base directory
    base_dir = None
    if args.data_dir:
        base_dir = Path(args.data_dir)
    else:
        base_dir = Path.home() / ".code_arena"
    base_dir.mkdir(parents=True, exist_ok=True)
    
    # Display welcome message
    if RICH_AVAILABLE:
        console.print("=" * 60)
        console.print("[bold cyan]ENHANCED CODE ARENA - Coding Assistant with Testing & Memory[/bold cyan]")
        console.print("Powered by Ollama and muhammad-albasha/llama3.1-python")
        console.print("=" * 60)
        console.print()
    else:
        print("=" * 60)
        print("ENHANCED CODE ARENA - Coding Assistant with Testing & Memory")
        print("Powered by Ollama and muhammad-albasha/llama3.1-python")
        print("=" * 60)
        print()
    
    try:
        # Initialize Ollama client
        model = args.model or "muhammad-albasha/llama3.1-python:latest"
        base_url = args.base_url or "http://localhost:11434"
        
        if RICH_AVAILABLE:
            console.print(f"[green]Initializing with model: {model}[/green]")
        else:
            print(f"Initializing with model: {model}")
            
        client = OllamaClient(model_name=model, api_base=base_url)
        
        # Process directory if specified
        if args.dir:
            if RICH_AVAILABLE:
                console.print(f"[cyan]Will process directory: {args.dir}[/cyan]")
            else:
                print(f"Will process directory: {args.dir}")
        
        # Run the chat
        await run_code_arena_chat(client, base_dir)
        
    except Exception as e:
        if RICH_AVAILABLE:
            console.print(f"[red]Error in Code Arena: {str(e)}[/red]")
        else:
            print(f"Error in Code Arena: {str(e)}")
            
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
