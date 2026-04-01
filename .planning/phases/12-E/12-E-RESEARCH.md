# Phase 12-E Research: Evidence-Aware Composition & Frontier Scope Fix

## Research Scope

Phase 12-E has two independent deliverables:
1. **Evidence-aware synthesis** — Upgrade synthesis to two-stage: skeleton claims first, then prose generation
2. **Frontier scope overhaul** — Replace hardcoded `max_pages=100` with saturation-driven corpus budget

---

## Part 1: Evidence-Aware Composition

### Current Synthesis State

**`synthesis_service.py` (286 lines) — single-pass flow:**

```python
# For each section (lines 109-149):
prose = await self.archivist.write_section(packet, "")  # LLM writes from raw packet
valid = self._validate_grounding(prose, packet)
```

**`ArchivistSynthAdapter.write_section()`** — The LLM receives:
- `EvidencePacket.section_title`
- `EvidencePacket.section_objective`
- `EvidencePacket.atoms` (flat list of dicts)
- No structural guidance

### The Problem: LLM Organization Challenge

The writer LLM receives a flat list of atoms and must:
1. Understand all atom content
2. Organize it into a coherent section
3. Generate accurate citations
4. Ensure every claim is supported

This is the hardest synthesis task — full organization + full writing + full citation. LLMs struggle when overloaded with unstructured evidence. They tend to:
- Cite atoms that don't support the claim
- Miss important atoms
- Produce disorganized sections
- Fabricate relationships between atoms

### Two-Stage Solution

**Stage 1: Skeleton Building** — Extract structured claims from evidence
```python
skeleton = _build_skeleton_from_claims(packet.derived_claims, packet.atoms)
# Produces:
# - Claim: "Company A revenue = $13M [A001]"
# - Derived Claim: "A exceeds B by 30% [A001, A002]"
# - Claim: "Company B revenue = $10M [A002]"
```

**Stage 2: Prose Generation** — LLM converts skeleton to natural language
```python
prose = await self.archivist.write_section_from_skeleton(packet, skeleton)
# LLM writes: "Company A's revenue reached $13 million [A001], exceeding..."
# The skeleton provides structure; LLM only converts to prose
```

### Why This Works Better

| Metric | Single-Pass | Two-Stage |
|--------|-------------|-----------|
| LLM task | Organize + Write + Cite | Write prose (organization and citation provided) |
| Hallucination risk | High (must invent structure) | Low (structure is evidence-derived) |
| Citation accuracy | LLM-generated | Skeleton provides exact mapping |
| Determinism | Variable | Skeleton is deterministic; prose follows skeleton |

### _build_skeleton_from_claims

```python
def _build_skeleton_from_claims(
    derived_claims: List[DerivedClaim],
    atoms: List[Dict]
) -> List[SkeletonClaim]:
    """Extract structured claim skeleton from evidence packet.

    Each SkeletonClaim contains:
    - claim_text: Natural language summary of the fact
    - citation_keys: List of atom IDs supporting this claim
    - claim_type: "direct" or "derived"
    - severity: how important this claim is (major/minor/context)

    Returns: Sorted list [major claims first, then minor, then context]
    """
```

The skeleton is built programmatically (no LLM):
1. For each atom, extract key claims (numbers, entities) → direct claims
2. For each derived claim, format the computation → derived claims
3. Sort by importance (derived claims first — they're the insights)

### ArchivistSynthAdapter Extension

New method `write_section_from_skeleton()`:

```python
async def write_section_from_skeleton(
    self, packet: EvidencePacket, skeleton: List[SkeletonClaim]
) -> str:
    """Generate prose from structured skeleton.

    The skeleton provides the organization; LLM fills in natural language.
    """
    skeleton_text = "\n".join(f"- {c.claim_text} [{', '.join(c.citation_keys)}]" for c in skeleton)
    prompt = f"""
Write a clear, professional section titled: {packet.section_title}
Objectives: {packet.section_objective}

Required claims (in order):
{skeleton_text}

For each claim, write natural prose that accurately reflects the evidence.
Every fact must have a citation [AXXX] matching the required claims above.
"""
    return await self.client.complete(...)
```

### Files Changed

| File | Change |
|------|--------|
| `src/research/reasoning/synthesis_service.py` | Add two-stage composition logic |
| `src/research/archivist/synth_adapter.py` | Add `write_section_from_skeleton` method |
| `tests/research/reasoning/test_synthesis_v2.py` | NEW — two-stage tests |

---

## Part 2: Frontier Scope Overhaul

### Current Frontier Limits

**`src/research/acquisition/frontier.py`** — `AdaptiveFrontier` class:

```python
class AdaptiveFrontier:
    MAX_RESPAWN_CYCLES = 3          # Maximum times to regenerate frontier
    MAX_CONSECUTIVE_ZERO_YIELD = 5  # Maximum consecutive zero-discovery nodes
```

**`src/research/firecrawl_config.py`**:
```python
@dataclass
class FirecrawlConfig:
    max_pages: int = 100  # Hard page limit across ALL crawls
```

**`src/research/models.py`** — `CrawlerConfig`:
```python
max_pages: int = 100  # Fixed limit
```

**`src/research/config.py`** — `BrowserConfig`:
```python
max_pages: int = 100  # Fixed limit
```

### The Problem: 100 Pages Is Arbitrary

The `max_pages=100` limit was set as a reasonable default. But:

1. For narrow topics, 10 pages might exhaust all relevant evidence
2. For broad topics (like "Python programming"), 100 pages is too few
3. The original design intended budget-driven stopping (5GB corpus), not page count
4. The frontier already has epistemic exhaustion detection (`MAX_CONSECUTIVE_ZERO_YIELD`, `MAX_RESPAWN_CYCLES`), but page limit stops crawler first

### Required Changes

Replace `max_pages=100` with:

1. **`max_corpus_bytes` budget** — Default ~5GB (configurable)
   - Crawler tracks total bytes ingested across all pages
   - Stops when budget is reached OR saturation is detected

2. **Saturation detection** — The frontier already tracks:
   - `exhausted_modes` per node (GROUNDING, EXPANSION, DIALECTIC, VERIFICATION all tried)
   - `consecutive_zero_yield` counter
   - `total_ingested` count

3. **`max_pages` becomes emergency safety stop** — e.g., 10,000 pages
   - Prevents runaway infinite loops
   - Default should be much higher since budget/saturation should stop first

### Implementation Locations

| File | Current | Change |
|------|---------|--------|
| `src/research/firecrawl_config.py:18` | `max_pages: int = 100` | Add `max_corpus_bytes: int = 5_000_000_000`, keep `max_pages` as safety (10,000) |
| `src/research/models.py:895` | `max_pages: int = 100` | Add `max_corpus_bytes` field |
| `src/research/config.py:232` | `max_pages: int = 100` | Add `max_corpus_bytes` field |
| `src/research/acquisition/frontier.py` | Uses only `MAX_CONSECUTIVE_ZERO_YIELD` and `MAX_RESPAWN_CYCLES` | Add `bytes_ingested` budget check in the main loop (line 98 area) |

### Budget Check in Frontier Loop

```python
# In AdaptiveFrontier.run() while loop:
while True:
    # 1. Budget check
    if self.total_bytes_ingested >= self.policy.max_corpus_bytes:
        await self._complete_mission("BUDGET_EXHAUSTED")
        break

    # 2. Existing budget check
    status = self.sm.budget.get_status(self.mission_id)
    ...

    # 3. Rest of the loop continues...
```

### Saturation Detection

Current saturation is checked by `_is_saturated()` (line 420-421):
```python
def _is_saturated(self) -> bool:
    return all(n.status == "saturated" for n in self.nodes.values())
```

This is already correct — when all nodes are saturated, the frontier attempts respawn. After `MAX_RESPAWN_CYCLES` failed respawns, it fails with `NO_DISCOVERY`. This is epistemic exhaustion: all exploration modes exhausted + no new discoveries.

The key change is that page limit no longer stops exploration before exhaustion reaches its natural conclusion.

---

## Integration Points

### Part 1 (Composition)

- `SynthesisService.generate_master_brief()` — orchestrates two-stage composition
- `ArchivistSynthAdapter.write_section_from_skeleton()` — new constrained writer
- Dual validator (12-B) validates output — unchanged

### Part 2 (Frontier)

- `FireCrawlClient._get_page_content()` — checks cumulative bytes vs budget
- `AdaptiveFrontier.run()` — checks budget in the main loop
- `CrawlerConfig` — `max_corpus_bytes` field drives budget
- Existing frontier checks (saturation, zero-yield) drive early stopping

---

## Risk Analysis

### Two-Stage Synthesis

| Risk | Impact | Mitigation |
|------|--------|------------|
| Skeleton misses important atoms | Prose won't cover them | Skeleton building iterates over ALL atoms (not just highest-scored) |
| Skeleton too verbose | LLM prompt gets very long | Skeleton uses compressed summaries — one sentence per claim |
| Prose deviates from skeleton | LLM adds unverified claims | Validator (12-B) catches un-grounded sentences |

### Frontier Scope

| Risk | Impact | Mitigation |
|------|--------|------------|
| 5GB budget too large | Excessive cost | Budget is configurable; default can be tuned |
| Early termination by saturation | Not enough evidence | Respawn cycles (3×) ensure thorough exploration |
| Page count 10,000 too high | Never triggers as safety | Budget/saturation should always stop first; 10,000 is just a failsafe |

## Dependencies

| Part | Depends On |
|------|------------|
| Part 1 (Composition) | 12-C claim graph (for structured skeleton building), 12-B dual validator (output validation) |
| Part 2 (Frontier) | Existing frontier infrastructure (already has exhaustion detection) |
