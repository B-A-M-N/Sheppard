# Sheppard V3 - Coding Standards & Conventions

## 1. Language & Style Guides

### 1.1 Python
- **Version**: Python 3.10+
- **Style**: PEP 8 with 100 character line length
- **Docstrings**: Google style
- **Type hints**: Required for all function signatures and class methods
- **Formatting**: Black auto-formatter with `.black` configuration
- **Import sorting**: `isort` with profile=black

### 1.2 JavaScript/TypeScript (if applicable)
- For microservices (Firecrawl wrapper, Playwright scripts)
- Use ES2020+ features
- Prefer TypeScript for new code
- ESLint with standard config

## 2. Naming Conventions

| Element | Convention | Example |
|---------|------------|---------|
| Packages/Modules | `lower_snake_case` | `llm_client`, `memory_store` |
| Classes | `PascalCase` | `Shepherd`, `DiscoveryPipeline` |
| Functions/Methods | `snake_case` | `run_discovery()`, `query_graph()` |
| Variables | `snake_case` | `context_buffer`, `item_count` |
| Constants | `UPPER_SNAKE_CASE` | `MAX_TOKENS`, `REDIS_TIMEOUT` |
| Files | `snake_case.py` | `embedding_matcher.py`, `context_buffer.py` |
| Private members | `_prefix` | `_cache`, `_internal_state` |

## 3. Code Organization Principles

### 3.1 File Structure
- Max 500 lines per file
- Single responsibility per module
- Related functionality grouped in subpackages
- `__init__.py` minimal, explicit exports only

### 3.2 Class Design
- Prefer composition over inheritance
- Dependency injection for testability
- Keep methods under 50 lines
- Extract helper functions for complex logic

### 3.3 Function Design
- Functions should do one thing well
- Max 3 parameters (use **kwargs for extensibility)
- Return values should be typed and documented
- Side effects clearly documented

## 4. Async/Await Patterns

Sheppard makes extensive use of async for I/O-bound operations.

### 4.1 Rules
- All I/O operations must be async (database, HTTP, file)
- Use `asyncio.gather()` for parallel operations
- Avoid `async def` for CPU-bound functions
- Never mix blocking calls in async code

### 4.2 Examples
```python
# GOOD
async def fetch_content(urls: List[str]) -> List[str]:
    tasks = [self.scraper.fetch(url) for url in urls]
    return await asyncio.gather(*tasks)

# BAD
def fetch_content_sync(urls):  # Blocks event loop!
    time.sleep(1)
    return results
```

### 4.3 Context Managers
Use async context managers for resource cleanup:
```python
async with self.http_session.post(url, data) as resp:
    return await resp.json()
```

## 5. Error Handling & Resilience

### 5.1Exception Handling
- Catch specific exceptions, not bare `except:`
- Use custom exception types for domain errors
- Always log exceptions with context
- Re-raise or return sentinel values consistently

### 5.2 Retry Pattern
```python
@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=4, max=10),
    retry=retry_if_exception_type(ConnectionError)
)
async def fetch_with_retry(url):
    return await self.client.get(url)
```

### 5.3 Circuit Breaker
- External service calls wrapped in circuit breaker
- Failure threshold: 5 consecutive failures
- Recovery timeout: 60 seconds
- Use `pybreaker` library

## 6. Logging Standards

### 6.1 Structured Logging
```python
import structlog

logger = structlog.get_logger()
logger.info("pipeline_started", pipeline="discovery", topic=topic)
logger.error("scrape_failed", url=url, error=str(e))
```

### 6.2 Log Levels
- `DEBUG`: Detailed debugging information
- `INFO`: Normal operation milestones
- `WARNING`: Recoverable issues, degraded operation
- `ERROR`: Failures that don't crash the system
- `CRITICAL`: System-breaking failures

### 6.3 Correlation IDs
- Generate `request_id` at API entry point
- Pass through all async calls
- Include in all log entries and metrics

## 7. Configuration Management

### 7.1 Environment Variables
- All configuration via environment variables
- Use Pydantic `BaseSettings` for typed config
- Example in `src/utils/config.py`:
```python
class Settings(BaseSettings):
    OLLAMA_HOST: str = "http://localhost:11434"
    REDIS_URL: str = "redis://localhost:6379"
    DATABASE_PATH: Path = Path("data/memory.db")

    class Config:
        env_file = ".env"
```

### 7.2 Secrets
- Never hardcode secrets
- Use `.env` for local development (gitignored)
- Use secret management in production (Vault, AWS Secrets)
- Rotate API keys regularly

## 8. Database Conventions

### 8.1 Schema Changes
- Use Alembic for migrations
- Migration files named: `YYYYMMDD_HHMMSS_description.py`
- Always include `upgrade()` and `downgrade()`
- Test migrations on backup before production

### 8.2 Queries
- Use async database drivers (`aiosqlite`, `asyncpg`)
- Parameterized queries only (no string formatting)
- Connection pooling configured in settings
- Timeout on all queries (5 seconds)

### 8.3 Transactions
- Use explicit transaction boundaries
- Atomic operations for critical writes
- Rollback on errors
```python
async with db.transaction():
    await db.execute(...)
    await db.execute(...)
```

## 9. API Design

### 9.1 REST Principles
- Use nouns for resources, verbs for actions
- Plural resource names: `/shepherd/research`, not `/shepherd/research`
- Version in URL: `/api/v1/`
- JSON for all request/response bodies
- Proper HTTP status codes

### 9.2 Response Format
```json
{
  "success": true,
  "data": { ... },
  "error": null,
  "request_id": "abc123"
}
```

### 9.3 Pagination
- Limit/offset for simple queries
- Cursor-based for large datasets
- Include pagination metadata:
```json
{
  "items": [...],
  "next_cursor": "xyz789",
  "has_more": true
}
```

## 10. Testing Conventions

### 10.1 Test Structure
Mirror source tree:
```
tests/
├── llm/
│   ├── test_client.py
│   └── test_embedding.py
├── shepherd/
│   ├── test_core.py
│   └── pipelines/
│       ├── test_discovery.py
│       └── test_validation.py
```

### 10.2 Naming
- Test files: `test_*.py`
- Test functions: `test_<behavior_under_test>()`
- Fixtures: `@pytest.fixture` with descriptive names
- Test classes: `Test<ClassUnderTest>`

### 10.3 Mocking Strategy
- Mock external APIs (LLM providers, scrapers)
- Use `pytest-asyncio` for async tests
- Integration tests with testcontainers
- Unit tests: isolate to single component

### 10.4 Assertions
```python
# GOOD
assert result.success is True
assert len(result.items) > 0
assert "error" not in response

# BAD
assert result  # Too vague
```

## 11. Commit Messages

Follow conventional commits:
```
<type>(<scope>): <subject>

<body>

<footer>
```

Types: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`

Example:
```
feat(pipelines): add multi-source validation

- Implement cross-validation against 3 independent sources
- Add credibility scoring based on domain reputation
- Store validation results in metadata

Closes #123
```

## 12. Documentation Requirements

### 12.1 Code Documentation
- All public classes/methods need docstrings
- Include examples for complex functions
- Document assumptions and edge cases
- Keep README.md updated with setup instructions

### 12.2 API Documentation
- FastAPI auto-generates OpenAPI schema
- Add descriptions to all endpoint parameters
- Include response examples
- Document error responses

### 12.3 Architecture Decisions
- Record major decisions in ADR directories
- Include: context, decision, consequences, alternatives
- Mark as `PROPOSED`, `ACCEPTED`, or `SUPERSEDED`

## 13. Performance Guidelines

### 13.1 Memory Management
- Stream large datasets, don't load entirely in memory
- Use generators for processing pipelines
- Implement `__slots__` for high-volume classes
- Monitor memory usage with `tracemalloc`

### 13.2 Concurrency
- Use `asyncio.Semaphore` to limit concurrent operations
- Batch database writes (100 items per batch)
- Rate limit external API calls
- Tune worker counts based on system resources

### 13.3 Caching
- Cache expensive operations (embedding generation, LLM calls)
- Use Redis with appropriate TTLs
- Cache invalidation on data updates
- Monitor cache hit rates

## 14. Security Practices

### 14.1 Input Validation
- Validate all user inputs with Pydantic
- Sanitize content before processing
- Limit file sizes and content types
- Escape output to prevent injection

### 14.2 API Keys
- Never log API keys or tokens
- Mask sensitive data in error messages
- Rotate keys regularly
- Use least-privilege API keys

### 14.3 Network Security
- Use HTTPS for all external calls
- Verify SSL certificates
- Implement request timeouts (5-30s)
- Rate limiting on API endpoints

## 15. Observability

### 15.1 Metrics
```python
from prometheus_client import Counter, Histogram

latency_histogram = Histogram('shepherd_pipeline_latency', 'Pipeline latency', ['stage'])
request_counter = Counter('shepherd_requests_total', 'Total requests', ['endpoint', 'method'])
```

### 15.2 Tracing
- Use OpenTelemetry for distributed tracing
- Trace IDs propagate across service boundaries
- Sample 10% of requests in production

### 15.3 Health Checks
- `/health` endpoint for liveness
- `/ready` endpoint for readiness (DB, Redis connectivity)
- `/metrics` endpoint for Prometheus scraping

## 16. Version Control

### 16.1 Git Workflow
- `main` branch always deployable
- Feature branches: `feat/<description>`
- Fix branches: `fix/<description>`
- Pull requests required for all changes
- Squash merge for clean history

### 16.2 `.gitignore`
- `venv/`, `.venv/`
- `__pycache__/`, `*.pyc`
- `.env`
- `data/` (except schema fixtures)
- `logs/`
- `.pytest_cache/`
- `*.db` (except empty template)

## 17. Code Review Checklist

- [ ] Type hints present and correct
- [ ] Async/await used appropriately
- [ ] Error handling covers failure modes
- [ ] Logging includes context (request_id, etc.)
- [ ] Tests added/updated
- [ ] No secrets in code
- [ ] Performance impact considered
- [ ] Documentation updated
- [ ] Follows PEP 8 / Black formatting
- [ ] No breaking changes without migration

## 18. Anti-Patterns & Code Smells

**AVOID**:
```python
# God objects with too many responsibilities
class Shepherd:
    def research(self): ...
    def scrape(self): ...
    def validate(self): ...  # Too many methods!

# Deep inheritance hierarchies
class BaseClass: ...
class ExtendedClass(BaseClass): ...
class FurtherExtended(ExtendedClass): ...  # Don't!

# Mutable default arguments
def process(items=[]):  # BAD - shared mutable default
    pass

# Global state
GLOBAL_CACHE = {}  # Use dependency injection instead

# Synchronous I/O in async code
def fetch_data():
    requests.get(url)  # BLOCKING!

# String concatenation for SQL
query = f"SELECT * FROM items WHERE id = {item_id}"  # SQL injection risk!
```

## 19. Refactoring Guidelines

When refactoring:
1. Ensure tests cover existing behavior
2. Make small, incremental changes
3. Run tests after each change
4. Keep code working throughout
5. Document rationale for significant changes
6. Update ADRs if architectural impact

## 20. Performance Profiling

Tools and approaches:
- `cProfile` for CPU profiling
- `memory_profiler` for memory usage
- `asyncio` debug mode for event loop issues
- Database query analysis with `EXPLAIN`
- Prometheus metrics for production monitoring

Profiling command:
```bash
python -m cProfile -o profile.out main.py
snakeviz profile.out
```
