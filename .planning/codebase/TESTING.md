# Sheppard V3 - Testing & Quality Practices

## 1. Testing Strategy Overview

Sheppard V3 employs a **comprehensive multi-layered testing strategy**:

```
┌─────────────────────────────────────────────┐
│         End-to-End Integration              │  ← Full system validation
├─────────────────────────────────────────────┤
│         Pipeline Integration               │  ← Cross-component flows
├─────────────────────────────────────────────┤
│         Component Integration              │  ← Multi-module interactions
├─────────────────────────────────────────────┤
│         Unit Tests                         │  ← Single function/class
├─────────────────────────────────────────────┤
│         Property Tests                     │  ← Invariant validation
└─────────────────────────────────────────────┘
```

**Coverage Target**: 85%+ overall, 90%+ for critical paths

## 2. Test Framework & Tools

### 2.1 Core Testing Stack
- **pytest**: Test discovery and execution
- **pytest-asyncio**: Async test support
- **pytest-cov**: Coverage reporting
- **pytest-mock**: Mocking utilities
- **pytest-xdist**: Parallel test execution

### 2.2 Specialized Testing Tools
- **hypothesis**: Property-based testing
- **testcontainers**: Database and service integration tests
- **httpx**: Async HTTP mocking for API tests
- **faker**: Test data generation
- **freezegun**: Time control for time-dependent tests
- **pytest-benchmark**: Performance regression testing

### 2.3 Coverage Configuration
```ini
# .coveragerc
[run]
source = src/
omit =
    src/interfaces/web_ui/*
    */tests/*
    */__main__.py

[report]
exclude_lines =
    pragma: no cover
    def __repr__
    raise AssertionError
    raise NotImplementedError
    if __name__ == .__main__.:
    if TYPE_CHECKING:
    @overload
```

## 3. Unit Testing Standards

### 3.1 Test File Structure
```python
# tests/shepherd/test_core.py
import pytest
from shepherd.core import Shepherd
from unittest.mock import AsyncMock, MagicMock

class TestShepherd:
    """Test suite for Shepherd core functionality."""

    @pytest.fixture
    def shepherd(self, mock_llm, mock_memory):
        """Create Shepherd instance with mocked dependencies."""
        return Shepherd(
            llm_client=mock_llm,
            memory=mock_memory
        )

    @pytest.mark.asyncio
    async def test_research_basic(self, shepherd):
        """Test basic research flow."""
        result = await shepherd.research("test topic")
        assert result.success is True
        assert len(result.items) > 0

    @pytest.mark.asyncio
    async def test_research_with_context(self, shepherd):
        """Test research with initial context."""
        context = ContextBuffer()
        result = await shepherd.research("test", context=context)
        assert result.context == context

    @pytest.mark.asyncio
    async def test_research_handles_llm_failure(self, shepherd):
        """Test robust handling of LLM failures."""
        shepherd.llm_client.generate = AsyncMock(side_effect=LLMError)
        result = await shepherd.research("test")
        assert result.success is False
        assert "LLM error" in result.error

@pytest.mark.asyncio
class TestAsyncPipelines:
    """Tests for async pipeline operations."""

    async def test_discovery_pipeline_parallel(self):
        """Verify parallel URL fetching."""
        urls = ["http://a.com", "http://b.com", "http://c.com"]
        results = await fetch_parallel(urls)
        assert len(results) == 3
```

### 3.2 Mocking Guidelines
- **Mock external services only**, not internal logic
- Use `AsyncMock` for async methods
- Mock at the interface boundary, not implementation
- Verify mock calls with `assert_called_once_with()`

```python
# GOOD: Mock at dependency boundary
def test_shepherd_calls_llm(mock_llm):
    shepherd = Shepherd(llm_client=mock_llm)
    shepherd.research("test")
    mock_llm.generate.assert_called_once()

# BAD: Mock internal method
def test_shepherd_bad_mock():
    shepherd = Shepherd()
    shepherd._internal_method = MagicMock()  # Don't mock internals!
```

### 3.3 Fixtures
Centralized in `conftest.py`:
```python
# conftest.py
import pytest
from tests.fixtures import MockLLM, MockMemory

@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()

@pytest.fixture
def mock_llm():
    """Mock LLM client with predictable responses."""
    return MockLLM(responses={
        "default": "Mock response",
        "embedding": [0.1, 0.2, 0.3] * 128
    })

@pytest.fixture
async def redis_client():
    """Test Redis fixture using testcontainers."""
    with redis_container() as container:
        yield await aioredis.from_url(container.url)
```

## 4. Integration Testing

### 4.1 Pipeline Integration Tests
Test complete pipeline flows:

```python
# tests/integration/test_pipelines.py
import pytest
from shepherd.pipelines import DiscoveryPipeline, ValidationPipeline

@pytest.mark.integration
@pytest.mark.asyncio
async def test_full_pipeline_integration():
    """Test discovery → validation → consolidation flow."""
    context = ContextBuffer()

    # Discovery
    discovery = DiscoveryPipeline()
    context = await discovery.run("quantum computing", context)
    assert len(context.items) >= 10

    # Validation
    validation = ValidationPipeline()
    context = await validation.run(context)
    for item in context.items:
        assert item.metadata.get('score', 0) > 50

    # Consolidation
    consolidation = ConsolidationPipeline()
    report = await consolidation.run(context)
    assert report.summary is not None
    assert len(report.uncertainties) > 0
```

### 4.2 External Service Tests
Use `testcontainers` for realistic integration:

```python
# tests/integration/test_redis.py
import pytest
from testcontainers.redis import RedisContainer

@pytest.fixture(scope="session")
def redis_container():
    with RedisContainer("redis:7-alpine") as container:
        container.start()
        yield container
        container.stop()

@pytest.mark.asyncio
async def test_redis_cache_integration(redis_container):
    cache = RedisCache(redis_container.get_connection_url())
    await cache.set("key", "value")
    result = await cache.get("key")
    assert result == "value"
```

### 4.3 API Integration Tests
```python
# tests/integration/test_api.py
import pytest
from httpx import AsyncClient
from interfaces.api import app

@pytest.mark.asyncio
async def test_research_endpoint():
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/shepherd/research",
            json={"topic": "artificial intelligence"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "items" in data["data"]
```

## 5. Property-Based Testing

Use `hypothesis` to generate edge cases:

```python
# tests/property/test_context_buffer.py
from hypothesis import given, strategies as st

class TestContextBufferProperties:
    """Property-based tests for context buffer invariants."""

    @given(st.lists(st.text(), min_size=1, max_size=100))
    async def test_add_items_preserves_token_count(self, items):
        """Adding items should maintain correct token count."""
        buffer = ContextBuffer(max_tokens=4000)
        for item in items[:50]:
            buffer.add(item)
        assert buffer.token_count <= 4000

    @given(st.integers(min_value=1, max_value=100))
    def test_token_limit_enforced(self, limit):
        """Context buffer never exceeds token limit."""
        buffer = ContextBuffer(max_tokens=limit)
        large_text = "x " * 10000  # 10k tokens
        buffer.add(large_text)
        assert buffer.token_count <= limit
```

## 6. Performance & Load Testing

### 6.1 Benchmark Tests
```python
# tests/benchmark/test_pipeline_performance.py
import pytest

@pytest.mark.benchmark(group="discovery")
async def test_discovery_pipeline_performance(benchmark):
    """Benchmark discovery pipeline latency."""
    pipeline = DiscoveryPipeline()

    async def run_pipeline():
        return await pipeline.run("benchmark topic")

    result = await benchmark(run_pipeline)
    assert result is not None

# Run: pytest tests/benchmark/ --benchmark-only
```

### 6.2 Load Testing
Separate load testing suite using `locust`:
```python
# load_tests/locustfile.py
from locust import HttpUser, task

class ShepherdUser(HttpUser):
    @task
    def research_endpoint(self):
        self.client.post("/api/v1/shepherd/research", json={
            "topic": "test"
        })
```

Run: `locust -f load_tests/locustfile.py`

## 7. Test Data Management

### 7.1 Fixtures Directory
```
tests/fixtures/
├── llm_responses/         # Canned LLM responses (JSON)
├── sample_pages/          # HTML pages for scraping tests
├── documents/             # PDFs, articles for parsing tests
├── databases/             # SQLite test databases
└── graphs/                # Sample graph data
```

### 7.2 Factory Pattern
```python
# tests/factories.py
class ItemFactory:
    @staticmethod
    def create(content="test", metadata=None, **kwargs):
        return MemoryItem(
            content=content,
            metadata=metadata or {},
            created_at=datetime.utcnow(),
            **kwargs
        )

# Usage
def test_something():
    item = ItemFactory.create(tags=["test"], score=95)
```

## 8. Continuous Integration

### 8.1 CI Pipeline (GitHub Actions)
```yaml
# .github/workflows/ci.yml
name: CI

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    services:
      redis:
        image: redis:7-alpine
      postgres:
        image: postgres:15
    steps:
      - uses: actions/checkout@v3
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.10'
      - name: Install dependencies
        run: pip install -e .[dev]
      - name: Run linting
        run: black --check src/ tests/
      - name: Run type checking
        run: mypy src/
      - name: Run tests
        run: pytest --cov=src --cov-report=xml
      - name: Upload coverage
        uses: codecov/codecov-action@v3
```

### 8.2 Pre-commit Hooks
```yaml
# .pre-commit-config.yaml
repos:
  - repo: https://github.com/psf/black
    rev: 23.9.1
    hooks:
      - id: black
  - repo: https://github.com/pycqa/isort
    rev: 5.12.0
    hooks:
      - id: isort
  - repo: https://github.com/pycqa/mypy
    rev: v1.5.1
    hooks:
      - id: mypy
  - repo: https://github.com/pre-commit/mirrors-prettier
    rev: v3.0.3
    hooks:
      - id: prettier
        types: [markdown, yaml, json]
```

## 9. Quality Gates

### 9.1 Minimum Thresholds
- **Coverage**: 85% overall, 90% critical paths
- **Type checking**: 0 errors with mypy
- **Linting**: Black/isort passes
- **Benchmarks**: No regression >5% in latency

### 9.2 Quality Checks Automated
```bash
# Quality gate script
black --check src/ tests/ || exit 1
isort --check-only src/ tests/ || exit 1
mypy src/ || exit 1
pytest --cov=src --cov-fail-under=85 || exit 1
pytest tests/benchmark/ --benchmark-compare || exit 1
```

## 10. Debugging Tests

### 10.1 Verbose Output
```bash
# Single test with verbose output
pytest tests/shepherd/test_core.py::TestShepherd::test_research_basic -vv

# Drop to debugger on failure
pytest --pdb

# Show print statements
pytest -s

# Show local variables in traceback
pytest --tb=long
```

### 10.2 Test Markers
```python
# Slow tests
@pytest.mark.slow
async def test_large_dataset_processing():
    pass

# Requires external service
@pytest.mark.integration
async def test_with_real_redis():
    pass

# Flaky tests (skip by default)
@pytest.mark.flaky
async def test_eventually_consistent():
    pass
```

Run selectively:
```bash
pytest -m "not slow and not integration"  # Fast unit tests only
pytest -m "integration"  # Only integration tests
```

### 10.3 Debug Logging
```python
# conftest.py
import logging
logging.basicConfig(level=logging.DEBUG)

# Or use pytest.ini
[pytest]
log_cli = true
log_cli_level = DEBUG
log_cli_format = %(asctime)s [%(levelname)8s] %(name)s: %(message)s
```

## 11. Special Testing Patterns

### 11.1 Testing Async Generators
```python
@pytest.mark.asyncio
async def test_pipeline_streaming():
    pipeline = DiscoveryPipeline()
    results = []
    async for item in pipeline.stream("topic"):
        results.append(item)
        if len(results) >= 10:
            break
    assert len(results) == 10
```

### 11.2 Testing Time-Dependent Code
```python
from freezegun import freeze_time

@freeze_time("2024-01-15 12:00:00")
async def test_expiration_logic():
    item = MemoryItem(created_at=datetime.utcnow(), ttl_hours=24)
    assert item.is_expired() is False

    with freeze_time("2024-01-16 12:01:00"):
        assert item.is_expired() is True
```

### 11.3 Testing LLM Interactions
```python
# tests/mock_llm_responses.py
MOCK_RESPONSES = {
    "summarize": {
        "choices": [{
            "message": {
                "content": '{"summary": "Test summary", "confidence": 0.95}'
            }
        }]
    }
}

class MockLLM:
    def __init__(self, responses=None):
        self.responses = responses or MOCK_RESPONSES

    async def generate(self, prompt, **kwargs):
        task_type = self._detect_task(prompt)
        return self.responses.get(task_type, self.responses["default"])
```

## 12. Memory & Database Testing

### 12.1 In-Memory Database
```python
@pytest.fixture
async def test_db():
    """Create temporary SQLite database."""
    db = SQLiteMemory(":memory:")
    await db.initialize()
    yield db
    await db.close()

async def test_memory_store_retrieve(test_db):
    item = MemoryItem(content="test", metadata={"key": "value"})
    await test_db.store(item)
    results = await test_db.query({"metadata.key": "value"})
    assert len(results) == 1
    assert results[0].content == "test"
```

### 12.2 Database Migration Tests
```python
async def test_migration_upgrade():
    """Test database schema migration."""
    # Start with old schema
    old_db = SQLiteMemory(":memory:", schema_version=1)
    await old_db.initialize()

    # Run migration
    await migrate_database(old_db, target_version=2)

    # Verify new schema
    columns = await old_db.get_columns("items")
    assert "new_column" in columns
```

## 13. Graph Testing

### 13.1 SWOC Graph Tests
```python
# tests/swoc/test_graph.py
def test_graph_cycle_detection():
    graph = Graph()
    graph.add_edge("A", "B", weight=1)
    graph.add_edge("B", "C", weight=1)
    graph.add_edge("C", "A", weight=1)  # Creates cycle

    cycles = graph.find_cycles()
    assert len(cycles) > 0

def test_pagerank_convergence():
    graph = generate_test_graph(nodes=100, edges=500)
    ranks = graph.pagerank(iterations=100)
    assert all(0 <= r <= 1 for r in ranks.values())
    assert abs(sum(ranks.values()) - 1.0) < 0.01
```

## 14. Chaos & Resilience Testing

### 14.1 Fault Injection
```python
@pytest.mark.asyncio
async def test_llm_retry_on_timeout():
    """Verify system retries on LLM timeout."""
    llm = MockLLM()
    llm.generate = AsyncMock(side_effect=[
        asyncio.TimeoutError,
        asyncio.TimeoutError,
        "Success"
    ])

    shepherd = Shepherd(llm_client=llm)
    result = await shepherd.research("test")

    assert llm.generate.call_count == 3
    assert result.success is True
```

### 14.2 Resource Exhaustion
```python
async def test_memory_limit_enforcement():
    """Test context buffer respects memory limits."""
    buffer = ContextBuffer(max_tokens=100)
    large_text = "x " * 10000

    with pytest.raises(MemoryLimitExceeded):
        buffer.add(large_text, strict=True)
```

## 15. Test Maintenance

### 15.1 Flaky Test Policy
- Flaky tests must be marked with `@pytest.mark.flaky`
- Create issue to track investigation
- Run flaky tests separately in CI
- Investigate and fix within 24 hours

### 15.2 Test Cleanup
- Delete temporary files in teardown
- Use `tmp_path` fixture for temp directories
- Ensure test isolation (no shared state)
- Clean up testcontainers properly

### 15.3 Test Documentation
```python
def test_edge_case_handling():
    """
    Test system behavior when input contains malformed data.

    Edge cases:
    1. Empty string content
    2. HTML tags in plain text
    3. Non-UTF8 characters
    4. Extremely long single words

    Expected: Graceful degradation, no crashes.
    """
```

## 16. Running Tests

### 16.1 Development Workflow
```bash
# Run all tests
pytest tests/

# Run with coverage
pytest --cov=src --cov-report=html

# Run specific test file
pytest tests/shepherd/test_core.py

# Run with marker
pytest -m "not slow"

# Run failed tests only
pytest --last-failed

# Parallel execution
pytest -n auto
```

### 16.2 Watch Mode
```bash
# Auto-run on file changes
ptw  # (pytest-watch)

# With specific patterns
ptw --runner "pytest -k test_discovery"
```

### 16.3 CI-Like Local Checks
```bash
# Full CI suite locally
black --check src/ tests/
isort --check-only src/ tests/
mypy src/
pytest --cov=src --cov-report=xml --benchmark-compare
```

## 17. Monitoring Test Health

### 17.1 Coverage Tracking
```bash
# Generate HTML report
pytest --cov=src --cov-report=html
open htmlcov/index.html

# Check missing lines
pytest --cov=src --cov-report=term-missing
```

### 17.2 Benchmark Regression
```bash
# Save baseline
pytest tests/benchmark/ --benchmark-save=baseline

# Compare against baseline
pytest tests/benchmark/ --benchmark-compare=baseline

# Show detailed comparison
pytest tests/benchmark/ --benchmark-compare=baseline --benchmark-verbose
```

### 17.3 Flaky Test Detection
```bash
# Run tests 5 times to detect flakiness
pytest --repeat=5 --flaky-report=flaky_report.txt
```

## 18. Test Coverage by Module

| Module | Target | Current | Notes |
|--------|--------|---------|-------|
| `llm/client.py` | 90% | TBD | Mock external API calls |
| `shepherd/core.py` | 90% | TBD | Integration tests critical |
| `shepherd/pipelines/` | 85% | TBD | Each pipeline separately |
| `swoc/core.py` | 85% | TBD | Graph algorithm edge cases |
| `metasystem/` | 80% | TBD | V2 bridge compatibility |
| `interfaces/api.py` | 85% | TBD | Endpoint coverage |
| `utils/` | 80% | TBD | Exception paths |

## 19. Known Testing Challenges

### 19.1 LLM Non-Determinism
- Solution: Mock LLM responses in unit tests
- Use property-based testing for prompt variations
- Regression test against golden response sets

### 19.2 External API Rate Limits
- Solution: Mock all third-party APIs
- Use `pytest-httpx` for HTTP interception
- Respect rate limits in integration tests

### 19.3 Time-Dependent Tests
- Solution: `freezegun` for time control
- Test with explicit timestamps
- Use relative time assertions

### 19.4 Async Complexity
- Solution: `pytest-asyncio` fixture
- Test async generators with `async for`
- Ensure proper event loop cleanup

## 20. Future Testing Improvements

Planned enhancements:
- Contract testing for API boundaries
- Mutation testing to check test quality
- Automated flaky test detection in CI
- Performance regression alerts
- Canary testing with production-like data
- Chaos engineering tests for resilience
