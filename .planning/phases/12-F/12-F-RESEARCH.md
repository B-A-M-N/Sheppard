# Phase 12-F Research: Adversarial Critic Loop

## Research Scope

Add an automated adversarial critic pass that validates completed reports before publishing. The critic catches weak reports that pass per-sentence validation but have holistic quality issues — uncited claims, incorrect derived claims, ignored contradictions, duplication, vague language, and numeric inaccuracies.

---

## Current Validation State

### `_validate_grounding()` in `synthesis_service.py` (lines 236-285)

The validator performs **per-sentence** checks:
1. Every sentence has at least one citation `[A###]`
2. Cited atom exists in the evidence packet
3. At least one cited atom has ≥2 content words in common with the sentence
4. Numbers in sentence appear in cited atoms (with 12-B extension: or are recomputed from multi-atom derivations)

### What Validation Catches

- "The company grew rapidly" → FAIL (no citation)
- "The revenue was $50M [A001]" → PASS IF A001 contains "50" and "revenue"
- "Company A exceeded B by 99% [A001, A002]" → PASS IF recomputed delta matches (with 12-B)

### What Validation Misses

| Issue | Why Validator Misses It |
|-------|------------------------|
| **Near-duplicate sections** | Each sentence passes individually; two nearly identical paragraphs both pass |
| **Ignored contradictions** | Validator checks per-sentence grounding, not whether contradictions in the packet were surfaced |
| **Vague language** | "Many experts suggest" [A001] passes if A001 mentions "experts" |
| **Overall report structure** | Validator doesn't see the full report; only individual sections |
| **Numeric inconsistencies** | Validator checks per-sentence; doesn't cross-reference numbers between sections |
| **Missing derived claims** | If a derived claim exists in EvidencePacket but the LLM didn't mention it, validator doesn't flag this |

---

## The Adversarial Critic Concept

### Validation vs Criticism

| Property | Per-Sentence Validation | Adversarial Critic |
|----------|------------------------|-------------------|
| Scope | Individual sentences | Full report context |
| Approach | Grounding (is this claim supported?) | Quality (is this report well-formed?) |
| Timing | Per section, during writing | After all sections, before publishing |
| Determinism | Pure function (regex + set ops) | May use LLM for some checks |
| Result | pass/fail per section | List of issues + publish recommendation |

### The Critic in the Pipeline

```
generate_master_brief()
  → generate_section_plan()
  → assemble_all_sections()
  → For each section: write → validate (per-sentence)
  → Combine all sections into full_report
  → CRITIC.run(full_report, all_packets)    ← NEW
  → If publishable: store artifact
  → If not: log issues, store anyway (configurable)
```

### Integration Point (`synthesis_service.py`)

After lines 176-214 where `full_report` is built but before lines 216-234 where it's stored:

```python
# After section text assembly complete:
from research.reasoning.critic import CriticEngine
critic = CriticEngine()
critic_report = critic.run(full_report, all_packets)
if not critic.is_publishable(critic_report):
    logger.warning(f"[Critic] Report has {len(critic_report.issues)} issues:")
    for issue in critic_report.issues:
        logger.warning(f"  - {issue}")
    # Option: attach critic_report to artifact metadata for audit trail
```

---

## Critic Check Design: The 6 Checks

### Check 1: Uncited Claims

**Scope:** All declarative sentences in the report.
**Method:** For each sentence without a citation marker, flag as uncited.
**Already checked by validator?** Yes — but validator only checks per-section. This check re-verifies the complete combined report, catching any uncited text that slipped through per-section processing (e.g., in section transitions or introductions).

### Check 2: Incorrect Derived Claims

**Scope:** Sentences expressing derived numeric relationships.
**Method:** For sentences with ≥2 citations and comparative language:
1. Extract the claimed numeric value
2. Look up source atoms
3. Recompute the value using 12-A derivation rules
4. Compare: `abs(claimed - recomputed) <= tolerance`

**This overlaps with validator** but operates on the full report text, not per-section. The critic catches cases where:
- The sentence passed section-level validation (with relaxed matching) but is globally wrong
- Two sections cite the same atoms but make contradictory derived claims

### Check 3: Ignored Contradictions

**Scope:** All sections of the report.
**Method:**
1. Collect all contradictions from EvidencePacket (across all sections)
2. Check if the report mentions either atom from the contradiction pair
3. If both are mentioned but the contradiction is not flagged → issue
**Policy:** Contradictions are NOT automatically errors. A good report should:
- Surface contradictions explicitly ("Sources A and B disagree on X")
- Or use only one side and acknowledge the other
- Never silently present both sides as if they're both true

### Check 4: Duplication

**Scope:** All sentences in the report.
**Method:**
1. Tokenize all sentences into content words (stopword-removed)
2. For each pair of sentences: compute Jaccard similarity on content words
3. Flag pairs with similarity > 0.8 (nearly identical)
4. Also flag sentences within same paragraph that share ≥80% content words

**Edge case mitigation:** Two sections may legitimately reference the same facts (e.g., summary and detail). To avoid false positives:
- Only flag near-duplicate sentences in DIFFERENT sections (same-section duplication is the writer's choice)
- Summary sentences that paraphrase earlier detailed sentences are acceptable if they add new context

### Check 5: Vague Language

**Scope:** All sentences in the report.
**Method:** Regex-based detection of vague patterns:
- Undefined group references: "some say", "many believe", "experts claim", "research suggests"
- Unquantified adjectives: "highly rated", "very popular", "extremely dangerous", "moderate increase"
- Time references without dates: "recently", "in the past few years", "soon"

**Tolerance level:** Vague claims from the CRITIC are WARNINGS, not errors. The validator would have checked that they're cited. The critic flags them for human review.

### Check 6: Numeric Accuracy

**Scope:** All numbers in the report.
**Method:**
1. Extract all numbers from report text
2. For each number, find the cited atom(s) in that sentence
3. Check the number appears in at least one cited atom (or is a derived value from 12-A rules)
4. Flag numbers that don't appear in any cited atom AND don't match any derived claim

**Difference from Check 2:** Check 6 is broader — it catches ALL numeric inconsistencies, not just derived claims. Check 2 is specifically for computed relationships (delta, percent). Check 6 catches typos, mis-copied numbers, and fabricated statistics.

---

## LLM vs Programmatic Checks

| Check | Method | Why |
|-------|--------|-----|
| UNCITED_CLAIMS | Programmatic (regex sentence split + citation extraction) | Precise, deterministic, fast |
| INCORRECT_DERIVED | Programmatic (recompute from atoms) | Arithmetic is exact |
| IGNORED_CONTRADICTIONS | Programmatic (set intersection: report mentions vs contradiction atoms) | Contradictions are structured data |
| DUPLICATION | Programmatic (Jaccard similarity on token sets) | Text similarity is computational |
| VAGUE_LANGUAGE | Hybrid (programmatic regex + optional LLM for context) | Regex catches patterns; LLM judges if vague language is justified |
| NUMERIC_ACCURACY | Programmatic (number extraction + atom matching) | Numbers are exact |

Only `VAGUE_LANGUAGE` has a potential LLM component (for context understanding). The other 5 are purely computational and deterministic.

---

## CriticReport Dataclass

```python
@dataclass
class CriticIssue:
    check: str                   # Which check failed
    severity: str                # "error" | "warning"
    location: str                # Section name or sentence index
    detail: str                  # Human-readable description
    sentence: str                # The offending sentence (if applicable)

@dataclass
class CriticReport:
    issues: List[CriticIssue] = field(default_factory=list)
    uncited_claims: List[str] = field(default_factory=list)
    derived_errors: List[str] = field(default_factory=list)
    ignored_contradictions: List[str] = field(default_factory=list)
    duplicates: List[str] = field(default_factory=list)
    vague_claims: List[str] = field(default_factory=list)
    numeric_errors: List[str] = field(default_factory=list)
```

---

## Publishability Decision

```python
def is_publishable(self, report: CriticReport) -> bool:
    """Publishable = no errors (warnings are acceptable)."""
    return not any(issue.severity == "error" for issue in report.issues)
```

| Condition | Action |
|-----------|--------|
| No issues | Publish normally |
| Warnings only | Publish with warnings logged |
| Errors present | Log issues, publish with warning |

**Note:** The critic should NOT block publishing (per context: "Option C: log issues and publish anyway"). The critic is advisory, not a gate. Future phases can make it blocking for specific issue types.

---

## False Positive Mitigation

### Uncited Claims
- False positive: headings, section titles, transitional phrases
- Mitigation: Only check sentences with >5 content words and declarative structure

### Ignored Contradictions
- False positive: Both sides mentioned but report correctly handles them (e.g., "A says X, but B says Y, and the evidence supports B")
- Mitigation: Check if the report contains language indicating contradiction resolution ("however", "but", "disagrees", "conflicts")

### Vague Language
- False positive: legitimate contextual phrases that happen to contain vague words
- Mitigation: Only flag if the vague phrase is NOT followed by a concrete fact in the same sentence

### Duplication
- False positive: legitimate repetition for emphasis across distant sections
- Mitigation: Only flag if the same content appears >2 times AND the sections are adjacent

---

## Performance Impact

| Check | Cost | Reason |
|-------|------|--------|
| Uncited claims | O(n sentences) — regex | Negligible |
| Derived errors | O(n sentences) — set lookup + arithmetic | Negligible (~0.1ms per sentence) |
| Contradictions | O(n sentences × m contradictions) — small sets | Negligible |
| Duplication | O(n² sentences) — pairwise comparison | For 80 sentences, ~3200 comparisons — ~5ms |
| Vague language | O(n sentences) — regex | Negligible |
| Numeric accuracy | O(n sentences) — set lookup | Negligible |

Total: ~10ms for a full 8-section report. The LLM-based vagueness check (if used) would add ~1 LLM call for the full report, ~2-5 seconds.

---

## Dependencies on Upstream Phases

| Phase | What It Provides | Used By |
|-------|-----------------|---------|
| 12-A | DerivedClaim objects on EvidencePacket | Check 2 (derived errors) |
| 12-B | Extended validator knowledge | The critic uses the same derived claim rules as the dual validator |
| 12-C | Claim graph with structured contradictions | Check 3 (ignored contradictions) |
| 12-D | Section plans with claim groups | The critic reports issue locations as section names |
| 12-E | Claim graph on EvidencePacket | Check 3 (contradictions) — graph is the canonical source |
| Synthesis | Full report text (all sections combined) | All checks operate on final report text |
