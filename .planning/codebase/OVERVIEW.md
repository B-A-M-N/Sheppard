# Sheppard V3 Codebase Mapping - Executive Overview

## 1. Project at a Glance

**Sheppard V3** is a distributed research automation system implementing a "Universal Domain Authority Foundry" paradigm. It combines automated web research, semantic graph reasoning, and LLM-powered synthesis to autonomously investigate complex topics.

**Key Stats**:
- **Language**: Python 3.10+ (async-first), some JavaScript microservices
- **Codebase Size**: ~50k lines across 7 core modules
- **Architecture**: V2/V3 hybrid in migration state
- **Primary Use Case**: Automated multi-source research with knowledge graph construction
- **Deployment**: Docker + docker-compose for local, K8s-ready design

## 2. The Seven Mapping Documents

This directory contains 7 comprehensive analyses of the Sheppard codebase:

### 📚 STACK.md - Technology Stack
- Programming languages and versions
- Core dependencies and their purposes
- Infrastructure requirements (Redis, SQLite, Ollama)
- Build and runtime dependencies tree

**Quick Answer**: "What does this project run on?"

### 🔌 INTEGRATIONS.md - External Services
- Complete inventory of API clients and integrations
- Firecrawl, SearXNG, Playwright, Ollama, OpenRouter
- Configuration and connection details
- Service dependencies and failover strategies

**Quick Answer**: "What external services does this touch?"

### 🏗️ ARCHITECTURE.md - System Design
- High-level architectural vision (V3 Triad Memory Stack)
- Component diagrams and data flow
- Design patterns (pipelines, dependency injection, circuit breaker)
- V2/V3 migration state and challenges

**Quick Answer**: "How is this system put together?"

### 📁 STRUCTURE.md - Module Breakdown
- Detailed walkthrough of each module (`src/llm/`, `src/shepherd/`, etc.)
- Class-level documentation with key methods
- Dependency graph between modules
- Data flow examples (research request, graph query)

**Quick Answer**: "Where does X live in the codebase?"

### 📏 CONVENTIONS.md - Coding Standards
- PEP 8 with project-specific rules
- Naming conventions and formatting (Black, isort)
- Async/await patterns and error handling
- API design, testing standards, CI/CD practices

**Quick Answer**: "How are we supposed to write code here?"

### 🧪 TESTING.md - Quality Practices
- Multi-layered testing strategy (unit → integration → E2E)
- Testing tools (pytest, hypothesis, testcontainers)
- Coverage targets (85%+), quality gates
- Property-based testing, benchmarking, chaos testing

**Quick Answer**: "How do we prove this works?"

### ⚠️ CONCERNS.md - Technical Debt & Risks
- 80+ identified concerns with risk ratings
- Architecture issues (V2/V3 hybrid, memory complexity)
- Code quality (race conditions, error handling)
- Testing gaps, performance bottlenecks, security risks
- Prioritized action items with timelines

**Quick Answer**: "What's broken or risky here?"

## 3. Critical Findings Summary

### 🚨 HIGH PRIORITY CONCERNS

| Category | Issue | Impact | Effort |
|----------|-------|--------|--------|
| Architecture | V2/V3 hybrid state | High complexity, testing burden | 2 weeks |
| Concurrency | Async race conditions in ContextBuffer | Data corruption risk | 1 week |
| Testing | Insufficient integration tests | Unknown pipeline behavior | 1 week |
| Performance | Graph algorithms don't scale | Will fail at 10k+ nodes | 1-2 weeks |
| Testing | LLM mocking inadequate | Slow, flaky tests | 1 week |

### 📊 Codebase Health Metrics

| Metric | Value | Assessment |
|--------|-------|------------|
| Test Coverage | TBD (run pytest --cov) | Target: 85%+ |
| Type Safety | Partial (some mypy gaps) | Target: strict mode |
| Documentation | Excellent (ARCHITECTURE.md) | Maintain this standard |
| Async Quality | Good patterns, some gaps | Need race condition fixes |
| Security | Basic, needs hardening | Input validation audit needed |
| Technical Debt | Medium-High | Estimated 6-8 weeks remediation |

### 🎯 Recommended Immediate Actions (Next 2 Weeks)

1. **Fix race conditions**: Add asyncio.Lock to ContextBuffer
2. **Enable API docs**: Verify `/docs` endpoint, add examples
3. **Add integration tests**: 2-3 full pipeline tests
4. **Build MockLLM**: Centralized mocking for LLM-dependent code
5. **Create migration plan**: V2→V3 timeline with decision points

## 4. Quick Reference: Common Questions

### "How does a research request flow through the system?"
→ See ARCHITECTURE.md §6.1
```
User → Shepherd.research() → Discovery → Validation → Consolidation → Report
```

### "Where is LLM routing configured?"
→ STACK.md §4.1 and src/llm/client.py (split-host routing by task type)

### "What's the deal with V2 and V3?"
→ ARCHITECTURE.md §2.2 and CONCERNS.md §2.1 (hybrid state, migration needed)

### "How do I add a new pipeline stage?"
→ STRUCTURE.md §2.2 (pipeline architecture) and CONCERNS.md §19 (testing patterns)

### "What's missing from the tests?"
→ TESTING.md §4.1 (integration gaps) and §4.2 (LLM mocking)

### "How do I deploy this to production?"
⚠️ **No deployment guide exists** - this is a critical gap. See CONCERNS.md §9.2

### "What's the biggest performance bottleneck?"
→ CONCERNS.md §5.1 (graph scaling) and §5.2 (LLM latency)

### "How do I debug V2/V3 interactions?"
→ CONCERNS.md §10.2 (debugging friction) - currently poorly documented

## 5. Architecture Highlights

### 5.1 Triad Memory Stack (V3 Vision)
```
┌─────────────────────────────────────────────┐
│         Elastic Context Buffer (ECB)       │  ← Working memory (in-memory)
├─────────────────────────────────────────────┤
│         Long-term Memory (LTM)             │  ← Persistent (SQLite/Postgres)
├─────────────────────────────────────────────┤
│     Remote Provenance Store (RPS)         │  ← External evidence (RPS)
└─────────────────────────────────────────────┘
```
**Current State**: Implemented but complex, see CONCERNS.md §2.2 for simplification recommendations.

### 5.2 Pipeline Architecture
Three independent pipelines that can be chained:
1. **Discovery**: Multi-strategy search (Firecrawl, APIs, Playwright)
2. **Validation**: Cross-source verification, credibility scoring
3. **Consolidation**: Synthesis, contradiction resolution, report generation

Each pipeline is async, streaming, and pluggable.

### 5.3 SWOC Graph Engine
Semantic Web of Concepts - graph-based reasoning:
- Concepts (nodes) with semantic tags
- Edges with weights
- Algorithms: PageRank, Dijkstra, cycle detection
- LLM-assisted extraction and validation

**Risk**: Naive implementations won't scale beyond ~1k nodes. See CONCERNS.md §5.1.

## 6. Getting Started as a Developer

### 6.1 One-Command Setup (Best Effort)
```bash
# Clone and setup
git clone <repo>
cd Sheppard
make setup  # TODO: Create this Makefile

# Start all services
make dev  # TODO: Create this (runs docker-compose + app)

# Run tests
pytest tests/

# Run with coverage
pytest --cov=src --cov-report=html
open htmlcov/index.html
```

### 6.2 Current Manual Setup (Works Today)
```bash
# 1. Create virtualenv
python -m venv venv
source venv/bin/activate

# 2. Install dependencies
pip install -e .[dev]

# 3. Start infrastructure
docker-compose up -d redis postgres

# 4. Configure
cp .env.example .env
# Edit .env with your API keys

# 5. Run
python -m interfaces.api  # API server
# or
python -m interfaces.cli research "your topic"  # CLI
```

### 6.3 Development Workflow
1. Create feature branch from `main`
2. Make changes with tests
3. Run quality gates: `black --check`, `mypy src/`, `pytest`
4. Open PR with description
5. Address review comments
6. Squash merge on approval

See CONVENTIONS.md §16 for Git workflow details.

## 7. Where to Start Reading Code

### If you want to understand...

| Goal | Start Here | Then |
|------|------------|------|
| How research works end-to-end | `src/shepherd/core.py:Shepherd.research()` | Follow to pipelines |
| How LLM routing works | `src/llm/client.py:LLMClient` | See routing rules |
| How memory works | `src/memory/context_buffer.py:ContextBuffer` | Then `sqlite.py` |
| How graphs are built | `src/swoc/core.py:SWOC` and `Graph` | See `graph_viz.py` |
| How V2/V3 interact | `src/metasystem/core.py:Metasystem` | Bridge methods |
| How to add API endpoint | `src/interfaces/api.py` | FastAPI patterns |
| Testing patterns | `tests/conftest.py` | Then module-specific tests |

## 8. Frequently Modified Areas

Based on git history and architecture, these areas see frequent changes:

1. **`src/shepherd/pipelines/`** - Pipeline logic evolves
2. **`src/llm/client.py`** - LLM provider integration changes
3. **`src/memory/`** - Storage backends are active
4. **`tests/fixtures/`** - Test data needs updates
5. **`.env.example`** - Configuration changes

Areas that are **stable** (change rarely):
- `src/swoc/core.py` (graph engine)
- `src/utils/config.py` (config patterns)
- `docs/` (if documentation existed)

## 9. Known Pain Points

### 9.1 For New Developers
- ❌ No setup script - manual steps required
- ❌ No architecture decision records (ADRs) explaining why
- ❌ V2/V3 confusion - unclear which to use
- ❌ Debugging async race conditions is hard
- ❌ LLM mocking requires understanding of fixtures

### 9.2 For Operators
- ❌ No deployment guide
- ❌ No monitoring setup documented
- ❌ No backup/restore procedures
- ❌ No scaling guidelines
- ❌ Single-instance only currently

### 9.3 For Users
- ❌ API docs missing (Swagger UI not enabled?)
- ❌ No usage examples beyond CLI
- ❌ Error messages can be cryptic
- ❌ No troubleshooting guide

## 10. Comparison to Industry Standards

| Aspect | Sheppard V3 | Industry Best Practice | Gap |
|--------|-------------|----------------------|-----|
| Testing | 80%+ unit, minimal integration | Pyramid: 70% unit, 20% integration, 10% E2E | Integration coverage |
| Observability | Prometheus lib present, no endpoint | Metrics, logs, traces (OpenTelemetry) | Implementation |
| Deployment | docker-compose only | K8s + Helm + Operators | Production readiness |
| Documentation | Excellent architecture doc | ADRs, API docs, deployment, troubleshooting | Multiple gaps |
| Security | Basic | OWASP Top 10 fully addressed | Audit needed |
| Typing | Partial | 100% + mypy strict | Coverage |
| CI/CD | Unknown (no .github/workflows) | Fully automated | Missing entirely |

## 11. Resources & Further Reading

### Within This Codebase
- `ARCHITECTURE.md` - Deep dive into system design
- `CONCERNS.md` - All known issues and recommendations
- `CONVENTIONS.md` - How to write code here
- `TESTING.md` - Testing strategy and patterns

### External References
- [GSD Workflow](https://github.com/anthropics/claude-code/wiki/GSD) - Planning methodology used
- [PEP 8](https://pep8.org/) - Python style guide
- [FastAPI docs](https://fastapi.tiangolo.com/) - API framework
- [pytest-asyncio](https://pytest-asyncio.readthedocs.io/) - Async testing
- [testcontainers-python](https://bitmaths.com/testcontainers/) - Integration testing

## 12. Document Maintenance

These mapping documents should be:

- **Updated**: Quarterly or after major architectural changes
- **Owned by**: Architecture review board
- **Review triggers**:
  - New module added
  - Major dependency version change
  - Migration (V2→V3) completion
  - Deployment target change

**Update process**:
1. Make changes to relevant document(s)
2. Create PR with "docs: update codebase mapping" in title
3. Address review comments
4. Merge and notify team

---

**Quick Access Links**:

- [Stack & Dependencies](STACK.md)
- [External Integrations](INTEGRATIONS.md)
- [System Architecture](ARCHITECTURE.md)
- [Module Structure](STRUCTURE.md)
- [Coding Standards](CONVENTIONS.md)
- [Testing Strategy](TESTING.md)
- [Technical Debt & Risks](CONCERNS.md)

**Questions?** See the individual documents for detailed information.
