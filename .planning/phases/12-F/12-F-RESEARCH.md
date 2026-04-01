# Phase 12-F: Adversarial Critic Loop - Research

**Researched:** 2026-04-01
**Domain:** Report-level quality assurance and adversarial validation
**Confidence:** HIGH

## Summary

This phase implements the `CriticEngine`, an automated adversarial pass that validates completed Master Briefs before publication. Unlike the existing per-sentence grounding validator, the Critic operates holistically on the full report text and the complete evidence context. It identifies high-level quality issues such as ignored contradictions, near-duplicate content, vague language, and numeric inconsistencies that per-sentence validation misses.

**Primary recommendation:** Use a purely programmatic, deterministic engine for 5 of the 6 checks (Uncited, Derived, Contradictions, Duplication, Numbers) to ensure performance and reliability. Use a regex-based "weasel word" scanner for Vague Language, optionally surfacing issues as advisory warnings rather than blocking errors.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **Critic Architecture:** Input is report text + EvidencePacket; output is CriticReport.
- **Checks:** Uncited Claims, Incorrect Derived Claims, Ignored Contradictions, Duplication, Vague Language, Numeric Accuracy.
- **Integration:** Runs after full report assembly in `synthesis_service.py`.
- **Policy:** The critic is advisory. It logs issues but does not block publishing by default (Option C from context).

### the agent's Discretion
- **Implementation of Checks:** Choice of algorithms (e.g., Jaccard similarity for duplication) and regex patterns for vague language.
- **Severity Mapping:** Defining which issues are "errors" vs "warnings".
- **Refinement Logic:** How to handle transitional phrases and headings in "Uncited Claims" check.

### Deferred Ideas (OUT OF SCOPE)
- **Automatic Retries:** While suggested as an option, the primary scope is detection and logging, not the "Option B" retry loop.
- **LLM-based Criticism:** Using an LLM to "read" the whole report for flow or style is deferred in favor of deterministic checks for speed.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| CRITIC-01 | Uncited Claims detection | Sentence splitting + citation extraction logic. |
| CRITIC-02 | Incorrect Derived Claims | Integration with `DerivationEngine` and ID mapping. |
| CRITIC-03 | Ignored Contradictions | Set intersection of cited atoms vs known conflict pairs. |
| CRITIC-04 | Duplication detection | Pairwise Jaccard similarity on content words. |
| CRITIC-05 | Vague Language detection | "Weasel word" regex patterns for academic writing. |
| CRITIC-06 | Numeric Accuracy | Global number extraction and cross-reference with atoms. |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `re` | Python stdlib | Regex patterns for sentence splitting and vague language | Fast, reliable, no dependencies |
| `math` | Python stdlib | Tolerance-based numeric comparison | Required for floating point safety |
| `difflib` | Python stdlib | Secondary check for text similarity | Built-in, good for sequence matching |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|--------------|
| `DerivationEngine` | Local (12-A) | Computing expected numeric values | Prerequisite for Check 2 |

**Installation:**
No new external packages required. The implementation relies on the Python standard library and existing project modules.

## Architecture Patterns

### Recommended Project Structure
```
src/research/reasoning/
├── critic.py          # NEW: CriticEngine, CriticReport, CriticIssue
├── assembler.py       # (Ref) EvidencePacket structure
└── synthesis_service.py # (Ref) Integration point
```

### Pattern 1: Deterministic Multi-Pass Critic
The `CriticEngine` should execute a series of independent "Checkers" that populate a central `CriticReport`.

```python
class CriticEngine:
    def run(self, report_text: str, packet: EvidencePacket) -> CriticReport:
        report = CriticReport()
        # 1. Holistic Text Analysis (Duplication, Uncited, Vague)
        # 2. Evidence Context Analysis (Contradictions, Derived Claims)
        # 3. Numeric Cross-Verification (Numbers vs Atoms)
        return report
```

### Anti-Patterns to Avoid
- **Blocking on Warnings:** Do not fail the pipeline for `VAGUE_LANGUAGE` or `DUPLICATION` unless extremely high (e.g. >95% overlap). These are often stylistic choices.
- **LLM for Math:** Never use an LLM to verify if `A - B = C`. Use the `DerivationEngine`.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Numeric Comparison | `a == b` | `math.isclose(a, b, rel_tol=1e-9)` | Floating point precision issues |
| Sentence Splitting | `text.split('.')` | `re.split(r'(?<!\w\.\w.)(?<![A-Z][a-z]\.)(?<=\.|\?)\s', text)` | Handles "U.S.A." and "Dr." correctly |
| Weasel Word Lists | Custom guessing | Standard Academic Lists (Quillbot/Proofed) | Based on established linguistic patterns |

## Common Pitfalls

### Pitfall 1: False Positives in Uncited Claims
**What goes wrong:** Section headers (`## Analysis`) and bullet point prefixes are flagged as uncited claims.
**How to avoid:** Filter out sentences that lack verbs, start with markdown header symbols, or are shorter than 5 words.

### Pitfall 2: Citation ID Mapping
**What goes wrong:** The report uses `[A001]` but the packet uses `atom_id` UUIDs.
**How to avoid:** `EvidencePacket` must provide a `id_map` that links `global_id` (the citation string) to the actual `atom_id`.

### Pitfall 3: Jaccard Performance
**What goes wrong:** $O(n^2)$ comparison on a massive report takes seconds.
**How to avoid:** Only compare sentences within a 3-paragraph window or only compare sentences between different sections.

## Code Examples

### Vague Language Patterns (Source: Academic Writing Standards)
```python
WEASEL_WORDS_REGEX = re.compile(
    r'\b(it is (said|thought|believed|claimed)|research shows|experts agree|'
    r'studies (suggest|show)|critics claim|many|some|numerous|a (few|fraction|lot)|'
    r'most|various|several|arguably|apparently|supposedly|seemingly|possibly|'
    r'probably|relatively|fairly|quite|somewhat|rather|mostly|largely|'
    r'virtually|potentially|reportedly|allegedly|may|might|could|'
    r'appears to|tends to|seems to|clearly|obviously|extremely|very|'
    r'really|significantly|substantially)\b', 
    re.IGNORECASE
)
```

### Jaccard Similarity for Duplication
```python
def get_jaccard_sim(str1: str, str2: str) -> float:
    a = set(re.findall(r'\w+', str1.lower()))
    b = set(re.findall(r'\w+', str2.lower()))
    # Remove citations from comparison
    a = {t for t in a if not re.match(r'a\d+', t)}
    b = {t for t in b if not re.match(r'a\d+', b)}
    if not a or not b: return 0.0
    return len(a & b) / len(a | b)
```

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 7.4.3 |
| Config file | pytest.ini |
| Quick run command | `pytest tests/research/reasoning/test_critic.py` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| CRITIC-01 | Flags sentences without `[A###]` | Unit | `pytest tests/research/reasoning/test_critic.py -k uncited` | ❌ Wave 0 |
| CRITIC-02 | Verifies arithmetic of derived claims | Unit | `pytest tests/research/reasoning/test_critic.py -k derived` | ❌ Wave 0 |
| CRITIC-03 | Flags ignored contradictions | Unit | `pytest tests/research/reasoning/test_critic.py -k contradictions` | ❌ Wave 0 |
| CRITIC-04 | Detects >80% lexical overlap | Unit | `pytest tests/research/reasoning/test_critic.py -k duplicate` | ❌ Wave 0 |
| CRITIC-05 | Identifies weasel words | Unit | `pytest tests/research/reasoning/test_critic.py -k vague` | ❌ Wave 0 |
| CRITIC-06 | Cross-checks numbers with source atoms | Unit | `pytest tests/research/reasoning/test_critic.py -k numeric` | ❌ Wave 0 |

### Wave 0 Gaps
- [ ] `tests/research/reasoning/test_critic.py` — Mocked EvidencePackets with known errors.
- [ ] `src/research/reasoning/critic.py` — Engine skeleton.

## Sources

### Primary (HIGH confidence)
- `12-F-CONTEXT.md` - Defined the 6 specific checks and integration point.
- `src/research/derivation/engine.py` - Source of truth for derived claim arithmetic.
- `src/retrieval/validator.py` - Existing per-sentence validation logic patterns.

### Secondary (MEDIUM confidence)
- [Quillbot: Weasel Words in Academic Writing](https://quillbot.com/blog/weasel-words/) - Regex patterns for vague language.
- [Proofed: Avoiding Vague Language](https://proofed.com/writing-tips/how-to-avoid-vague-language-in-academic-writing/) - Additional weasel word lists.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - Pure Python stdlib.
- Architecture: HIGH - Deterministic engine matches project pattern.
- Pitfalls: HIGH - Common issues in NLP/RAG systems.

**Research date:** 2026-04-01
**Valid until:** 2026-05-01
