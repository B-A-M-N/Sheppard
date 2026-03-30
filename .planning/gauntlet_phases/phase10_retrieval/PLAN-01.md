# Phase 10 Plan 01: V3Retriever and Grounding Validator Implementation

## Mission

Implement the core retrieval grounding and validation components required by the Phase 10 truth contract. This establishes the foundation for truth-bound interactive answering.

## Context

- **Contract:** PHASE-10-CONTEXT.md defines strict rules: sequential citations, no hard filtering, fallback on emptiness, contradiction preservation.
- **Scope:** Implement V3Retriever and validate_response_grounding; unit tests required.

## Tasks

<task type="auto">
  <name>Task 1: Implement V3Retriever with sequential IDs and build_context_block</name>
  <files>
    - src/retrieval/models.py
    - src/retrieval/retriever.py
  </files>
  <read_first>
    - PHASE-10-CONTEXT.md (sections 0, 3, 6, 7)
    - src/research/reasoning/retriever.py (for data structures)
    - src/research/reasoning/v3_retriever.py (reference behavior)
  </read_first>
  <behavior>
    - Create retrieval module under src/retrieval/
    - Define RetrievedItem dataclass with fields: content, source, strategy, knowledge_level, item_type, relevance_score, trust_score, recency_days, tech_density, citation_key, metadata
    - Define RoleBasedContext with lists: definitions, evidence, contradictions, project_artifacts, unresolved, and all_items property
    - Implement V3Retriever class:
      * __init__(self, adapter): store adapter with chroma.query method
      * retrieve(self, query_text, topic_filter=None, max_results=12) -> RoleBasedContext
        - Build where clause for topic_filter if provided
        - Call adapter.chroma.query(collection="knowledge_atoms", query_text=query_text, where=..., limit=max_results)
        - Convert results to RetrievedItem objects, compute relevance = 1 - distance
        - Populate ctx.evidence; leave other roles empty for now
        - Do NOT apply any confidence threshold filter; include all returned results
      * build_context_block(self, ctx, project_name=None, show_sources=True) -> str
        - Assign sequential citation keys [A001], [A002], ... to every item in ctx.all_items (deterministic order: definitions, evidence, contradictions, project_artifacts, unresolved)
        - Format sections: ### Definitions & Key Concepts, ### Supporting Evidence, ### Conflicting Evidence, ### Project-Specific Context, ### Unresolved Questions
        - Each bullet includes content and citation if show_sources
    - Ensure the implementation is fully type-annotated and async-compatible (retrieve should be async if chroma.query is async)
  </behavior>
  <action>
    Create src/retrieval/models.py with dataclasses. Create src/retrieval/retriever.py with V3Retriever implementation. Include __init__.py to make package.
  </action>
  <verify>
    <automated>
      test -f src/retrieval/retriever.py &&
      grep -q "class V3Retriever" src/retrieval/retriever.py &&
      grep -q "build_context_block" src/retrieval/retriever.py &&
      grep -q "\[A001\]" src/retrieval/retriever.py
    </automated>
  </verify>
  <acceptance_criteria>
    - V3Retriever class is importable
    - retrieve() method executes without errors (when given a mock adapter)
    - build_context_block() produces a string with [A001] citations
  </acceptance_criteria>
  <done>V3Retriever implementation complete and verified.</done>
</task>

<task type="auto">
  <name>Task 2: Implement validate_response_grounding</name>
  <files>
    - src/retrieval/validator.py
  </files>
  <read_first>
    - PHASE-10-CONTEXT.md section 1 (Grounded answers only)
    - src/llm/validators.py for patterns
  </read_first>
  <behavior>
    - Implement function validate_response_grounding(response_text: str, retrieved_items: List[RetrievedItem]) -> dict with keys: is_valid (bool), errors (list of str), details (dict)
    - Requirements:
      * Lexical overlap: For each claim (sentence or clause), the content words (non-stopwords) must have at least 2 words that appear in the cited atom's content. Stopwords list: common English stopwords.
      * Numeric consistency: If the claim contains numbers, every number must appear in the cited atom (exact match, allowing formatting differences like commas).
      * Entity consistency: Significant named entities (proper nouns, technical terms) in the claim must appear in the cited atom. Use simple heuristic: words starting with capital letters (except sentence starters) or all-caps acronyms; optionally use regex for capitalized multi-word entities.
      * Multi-clause handling: If a claim includes multiple citations (e.g., "X [A001] and Y [A002]"), split the claim by citations and validate each segment against its corresponding retrieved item.
    - Algorithm:
      1. Split response into sentences (or by punctuation).
      2. For each sentence, detect cited atom key(s): extract [A###] patterns.
      3. For each citation, get the corresponding RetrievedItem.content.
      4. Compare claim text (without the citation marker) to the atom content:
         - Tokenize to words, lowercased, remove stopwords.
         - Count overlapping words; require >= 2.
         - Extract numbers from claim and atom; ensure claim numbers ⊆ atom numbers.
         - Extract entities (capitalized words not at start of sentence) and verify they appear in atom (case-insensitive match).
      5. Accumulate failures.
    - Return validation result: is_valid = len(errors)==0.
  </behavior>
  <action>
    Create src/retrieval/validator.py with the function and helper utilities (stopword list, tokenization, number extraction, entity extraction). Write clear docstrings. Ensure deterministic behavior.
  </action>
  <verify>
    <automated>
      test -f src/retrieval/validator.py &&
      grep -q "def validate_response_grounding" src/retrieval/validator.py
    </automated>
  </verify>
  <acceptance_criteria>
    - Function exists and is importable
    - Basic validation passes for a sample with good grounding
    - Rejects unsupported additions
  </acceptance_criteria>
  <done>validate_response_grounding implementation complete.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 3 (TDD): Write unit tests for V3Retriever</name>
  <files>
    - tests/retrieval/test_retriever.py
  </files>
  <read_first>
    - src/retrieval/retriever.py
  </read_first>
  <behavior>
    - Use pytest and pytest-asyncio.
    - Create mock adapter with chroma.query method returning sample data.
    - Test cases:
      * retrieve returns RoleBasedContext with evidence items
      * Items have correct metadata and relevance scores
      * No filtering beyond limit
      * build_context_block assigns sequential keys [A001], [A002]...
      * build_context_block includes sections in correct order
      * Empty context returns empty string
    - Aim for >90% coverage of retriever.py
  </behavior>
  <action>
    Write tests using RED-GREEN-REFACTOR:
    - RED: Write failing tests first, run pytest, confirm failures.
    - GREEN: Implement minimal code to pass.
    - REFACTOR: Clean up if needed, keep tests passing.
  </action>
  <verify>
    <automated>pytest tests/retrieval/test_retriever.py -v --tb=short</automated>
  </verify>
  <acceptance_criteria>
    - All tests pass (12+ tests)
    - Coverage >= 90%
  </acceptance_criteria>
  <done>Retriever tests complete.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 4 (TDD): Write unit tests for validate_response_grounding</name>
  <files>
    - tests/retrieval/test_validator.py
  </files>
  <read_first>
    - src/retrieval/validator.py
  </read_first>
  <behavior>
    - Test lexical overlap: happy path (≥2 overlap), failure (<2 overlap), stopword handling.
    - Test numeric consistency: numbers present in atom match claim; extra numbers in claim fail.
    - Test entity consistency: entities from claim appear in atom; missing entities fail.
    - Test multi-clause: different citations for different clauses, each validated separately.
    - Test edge cases: empty response, missing citations, non-ASCII characters.
    - Target: 41 tests covering all branches.
  </behavior>
  <action>
    Write tests using TDD cycle. Use parametrize for many cases.
    Ensure tests fail before implementation, then implement to pass.
  </action>
  <verify>
    <automated>pytest tests/retrieval/test_validator.py -v --tb=short</automated>
  </verify>
  <acceptance_criteria>
    - All tests pass (41+ tests)
    - Coverage >= 95%
  </acceptance_criteria>
  <done>Validator tests complete.</done>
</task>

<task type="auto">
  <name>Task 5: Run full test suite and generate coverage report</name>
  <files>
    - tests/retrieval/
  </files>
  <behavior>
    - Run pytest for all retrieval tests.
    - Generate coverage report using pytest-cov: coverage run -m pytest; coverage html; coverage report.
    - Verify total tests >= 50, all pass.
  </behavior>
  <action>
    Execute tests and produce coverage data. Ensure no failures.
    If any test fails, debug and fix immediately; stop and report if unfixable within 3 attempts (Rule 5).
  </action>
  <verify>
    <automated>
      pytest tests/retrieval/ -q &&
      coverage report -m | grep -E "TOTAL|src/retrieval"
    </automated>
  </verify>
  <acceptance_criteria>
    - Total tests >= 50, all pass
    - Coverage for src/retrieval and src/.../validator.py >= 95%
  </acceptance_criteria>
  <done>All tests passing, coverage meets targets.</done>
</task>

<verification>
- All tests in tests/retrieval/ pass without failures.
- Coverage report indicates >=95% for new modules.
- Code inspection confirms adherence to PHASE-10-CONTEXT.md (sequential IDs, no confidence filtering, build_context_block present, validation strict).
</verification>

<success_criteria>
- V3Retriever fully implemented and tested
- validate_response_grounding fully implemented and tested
- Test suite passes (>=50 tests, high coverage)
- Commit: "Phase 10: PLAN-01 — V3Retriever and validator implementation"
- Results documented in .planning/gauntlet_phases/phase10_retrieval/01-RESULTS.md
</success_criteria>

<output>
Deliverables:
- Source files: src/retrieval/models.py, src/retrieval/retriever.py, src/retrieval/validator.py, src/retrieval/__init__.py
- Tests: tests/retrieval/test_retriever.py, tests/retrieval/test_validator.py
- Results: .planning/gauntlet_phases/phase10_retrieval/01-RESULTS.md
</output>
