# Phase 12-F: Adversarial Critic Loop - Research

**Researched:** 2026-04-01 (Simulated)
**Domain:** Verification, Quality Gates, Adversarial LLM Assessment
**Confidence:** HIGH

## Summary

The Phase 12-F `CriticEngine` shifts the Sheppard synthesis pipeline from probabilistic generation to verified, deterministic rendering. Rather than relying on the generative LLM to "get it right," we implement a rigorous "Gatekeeper-Critic" architecture. 

The implementation splits validation into two lanes: **Deterministic Gates** for hard constraints (lexical overlap, math verification, citation presence) and an **Adversarial Critic** (LLM-as-a-judge) for semantic constraints (contradiction resolution, scope creep).

**Primary recommendation:** Build a dual-layer `LongformVerifier` that runs fast deterministic checks first (using the existing `DerivationEngine` and `validator.py`), followed by a strict, JSON-enforced `CriticEngine` LLM pass. Cap retry loops at 2 iterations to prevent self-correction oscillation.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **Master Invariant:** The writer never invents intelligence; it renders intelligence already mechanically assembled upstream.
- **Longform Verification Gates:** Must strictly enforce Sentence Grounding, Derived Recomputation, Contradiction Obligation, Section Evidence Thresholds, No Uncited Abstraction, No Expansion Beyond Budget, and Deterministic Regeneration.
- **Failure Actions:** Must reject sentences, reject sections, or trim scope based on the specific gate failure.
- **Test Harness:** Must include a Failure Class Test Harness that injects specific failure modes (eloquence without grounding) and verifies the gates catch them.

### The Agent's Discretion
- Implementation details of the `CriticEngine` prompts.
- Strategy for extracting derived claims from prose for verification.

### Deferred Ideas (OUT OF SCOPE)
- No alternative synthesis models (Must stick to `TaskType.SYNTHESIS`).
- Do not modify existing retrieval mechanisms; only validate the output.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| REQ-12F-01 | Sentence Grounding | Use `src.retrieval.validator` lexical overlap and entity extraction |
| REQ-12F-02 | Derived Recomputation | Reuse `src.research.derivation.engine.verify_derived_claim` |
| REQ-12F-03 | Contradiction Obligation | Use LLM Critic to check if prose addresses `EvidencePacket.contradictions` |
| REQ-12F-04 | Section Evidence Threshold | Simple count `len(packet.atoms) >= MIN_EVIDENCE` |
| REQ-12F-05 | No Uncited Abstraction | Regex check for sentences lacking `[A###]` citations |
| REQ-12F-06 | No Expansion Beyond Budget | LLM Critic checks if prose contains facts not in `packet.atom_ids_used` |
| REQ-12F-07 | Deterministic Regeneration | Assert `ModelRouter().get(TaskType.SYNTHESIS)` has `temperature=0.0` and fixed seed |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `pydantic` | `>=2.5.2` | Structured Critic Output | Ensures the LLM Critic returns reliable, typed JSON for validation |
| `asyncio` | Built-in | Concurrent Section Validation | Allows running the LLM Critic and deterministic gates on multiple sections in parallel |
| `re` / `math` | Built-in | Deterministic Parsing | Fast citation extraction (`\[[A-Z]?\d+\]`) and `math.isclose()` for floats |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `src.research.derivation.engine` | Internal | Numeric Validation | Recomputing "percent change", "delta", and "rank" claims without LLMs |
| `src.retrieval.validator` | Internal | Lexical Checking | Reusing `STOPWORDS` and `extract_entities` for baseline grounding |

## Architecture Patterns

### The Gatekeeper-Critic Split
Separate fast, cheap deterministic checks from slower, semantic LLM checks.

```python
class LongformVerifier:
    async def verify_section(self, prose: str, packet: EvidencePacket) -> VerificationResult:
        # Lane 1: Deterministic Gates (Fast Fail)
        if len(packet.atoms) < MIN_EVIDENCE_FOR_SECTION:
            return VerificationResult(passed=False, reason="evidence_threshold")
        
        grounding_errors = self._check_sentence_grounding(prose, packet)
        if grounding_errors:
            return VerificationResult(passed=False, errors=grounding_errors)
            
        # Lane 2: Adversarial Critic (Semantic Fail)
        critic_result = await self.critic_engine.critique(prose, packet)
        if critic_result.needs_repair:
            return VerificationResult(passed=False, errors=critic_result.failures)
            
        return VerificationResult(passed=True)
```

### The Strict Bounded Correction Loop
Never allow the LLM to self-correct indefinitely. Introduce a hard retry limit.
```python
MAX_RETRIES = 2
for attempt in range(MAX_RETRIES):
    prose = await archivist.write_section(packet, feedback_context)
    result = await verifier.verify_section(prose, packet)
    if result.passed:
        return prose
    feedback_context = f"CRITIC REJECTION: {result.errors}. REVISE AND CITE STRICTLY."

return "[SECTION REJECTED: VERIFICATION FAILED AFTER RETRIES]"
```

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Recomputing Deltas/Percentages | Custom arithmetic parsers | `DerivationEngine` | The derivation engine in `src/research/derivation/engine.py` is already deterministic and handles the specific logic for `delta` and `percent_change`. |
| Finding Missing Citations | Custom String slicing | `src.retrieval.validator` regex | The codebase already has hardened regex for `\[[A-Z0-9]+\]` and `extract_numbers`. |
| LLM JSON Structuring | Custom JSON stripping | `pydantic.BaseModel` + `extract_json` | LLMs frequently wrap JSON in markdown blocks (` ```json `); use existing utilities to reliably parse it. |

## Common Pitfalls

### Pitfall 1: The "Oscillating Hallucination" Loop
**What goes wrong:** The LLM hallucinates a claim. The Critic flags it. The LLM removes it but hallucinates a *new* citation to fill the gap.
**How to avoid:** Cap retries at 2. If it fails twice, the section is flagged as `[INSUFFICIENT EVIDENCE]` rather than looping forever.

### Pitfall 2: Lexical Overlap False Negatives
**What goes wrong:** A sentence perfectly summarizes an atom using synonyms, but fails the `validator.py` lexical overlap check (requires >= 2 content words).
**How to avoid:** Use the deterministic check as a *first pass*. If lexical overlap fails, escalate that specific sentence to the LLM Critic to ask: "Is this claim semantically supported by the atom despite using different words?"

### Pitfall 3: Floating Point Validation Mismatches
**What goes wrong:** `25.0` (from prose) != `24.9999999` (from derived calculation).
**How to avoid:** Never use `==` for extracted numbers. Use `math.isclose(a, b, rel_tol=1e-9)`.

## Code Examples

### The Adversarial Critic Prompt Pattern
Ensure the LLM adopts a hostile, highly structured persona.
```python
class CriticOutput(BaseModel):
    passed: bool
    unsupported_claims: list[str]
    ignored_contradictions: list[str]
    scope_expansions: list[str]

CRITIC_PROMPT = """
You are a Hostile Auditor. Your job is to DESTROY this text by finding claims that are NOT supported by the provided Evidence Atoms.
1. Check Contradictions: If the section requires addressing a contradiction, and it doesn't, FAIL IT.
2. Check Scope: If the text includes facts, dates, or entities NOT in the atoms, FAIL IT (Expansion Beyond Budget).
Return strictly the JSON schema requested.
"""
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Unverified LLM outputs | Verification loops | Mid-2023 | Eliminated undetected hallucinations in enterprise deployments. |
| Regex-only checking | Gatekeeper + LLM Critic | Late 2023 | Catches semantic drift that string-matching misses. |

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | `pytest` |
| Config file | `pytest.ini` |
| Quick run command | `pytest tests/research/reasoning/test_longform_verification.py -v` |
| Full suite command | `pytest tests/ -v` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| REQ-12F-01 | Rejects sentences missing lexical/semantic support | unit | `pytest tests/research/reasoning/test_longform_verification.py::test_sentence_grounding` | ❌ Wave 0 |
| REQ-12F-02 | Fails section if derived math doesn't match | unit | `pytest tests/research/reasoning/test_longform_verification.py::test_derived_recomputation` | ❌ Wave 0 |
| REQ-12F-03 | Flags section if required contradictions are ignored | unit | `pytest tests/research/reasoning/test_longform_verification.py::test_contradiction_obligation` | ❌ Wave 0 |
| REQ-12F-06 | Trims or fails text that expands beyond atom facts | unit | `pytest tests/research/reasoning/test_longform_verification.py::test_expansion_budget` | ❌ Wave 0 |
| REQ-12F-08 | Failure Class test suite correctly flags injected flaws | integration | `pytest tests/research/reasoning/test_failure_injection.py` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `pytest tests/research/reasoning/test_longform_verification.py`
- **Per wave merge:** `pytest tests/`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/research/reasoning/test_longform_verification.py` — unit tests for the deterministic and LLM gates.
- [ ] `tests/research/reasoning/test_failure_injection.py` — specific harness to inject "eloquence without grounding" and verify it gets caught.
- [ ] `src/research/reasoning/longform_verifier.py` — core implementation file missing.

## Sources

### Primary (HIGH confidence)
- `.planning/phases/12-F/12-F-CONTEXT.md` - Core definitions for gates and failure actions.
- `src/research/derivation/engine.py` - Source of truth for deterministic numeric checks.
- `src/retrieval/validator.py` - Source of truth for existing lexical overlap rules.

### Secondary (MEDIUM confidence)
- Industry patterns on Generator-Critic LLM workflows and Bounded Retries.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - Directly aligned with existing Sheppard infrastructure (`OllamaClient`, `asyncio`, `pydantic`).
- Architecture: HIGH - Gatekeeper-Critic pattern perfectly fits the "mechanically assembled" mandate.
- Pitfalls: HIGH - Addresses known hallucination recovery oscillation directly.
