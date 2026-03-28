# PHASE 06 — DISCOVERY ENGINE VERIFICATION

## Mission

Audit the discovery layer to verify that topic expansion, search, and URL harvesting behave as claimed.

## GSD Workflow

- Discuss: What discovery claims exist?
- Plan: Verify decomposition and search implementations
- Execute: Inspect code, run examples if possible
- Verify: Produce DISCOVERY_AUDIT.md

## Prompt for Agent

```
You are executing Phase 06 for Sheppard V3: Discovery Engine Verification.

Mission:
Audit the discovery layer to verify that topic expansion, search, and URL harvesting behave as claimed.

Objectives:
1. Verify taxonomic decomposition exists
2. Verify epistemic mode selection exists
3. Verify multi-page search/deep mine behavior exists
4. Verify discovery dedupe and prioritization
5. Verify that discovered URLs are relevant and non-trivial

Required method:
- Inspect decomposition code and prompts
- Inspect search integrations
- Inspect discovery scheduling and fanout
- Inspect relevance filtering and dedupe logic
- Run or inspect example outputs where possible

Deliverables (write to .planning/gauntlet_phases/phase06_discovery/):
- DISCOVERY_AUDIT.md
- TAXONOMY_GENERATION_AUDIT.md
- SEARCH_BEHAVIOR_REPORT.md
- URL_SELECTION_HEURISTICS.md
- PHASE-06-VERIFICATION.md

Mandatory ambiguity extraction:
Explicitly surface:
- decomposition depth defaults
- search page depth defaults
- result scoring rules
- rejection criteria
- obscure-source discovery proof vs. aspiration

Hard fail conditions:
- Discovery is just thin search wrapping with inflated claims
- Taxonomy generation is claimed but not enforced
- Search depth is claimed but not implemented
- URL quality controls are absent

Completion bar:
PASS only if discovery behavior is concretely evidenced and operationally meaningful.
```

## Deliverables

- **DISCOVERY_AUDIT.md**
- **TAXONOMY_GENERATION_AUDIT.md**
- **SEARCH_BEHAVIOR_REPORT.md**
- **URL_SELECTION_HEURISTICS.md**
- **PHASE-06-VERIFICATION.md**

## Verification Template

```markdown
# Phase 06 Verification

## Discovery Claims

- [ ] Taxonomic decomposition implemented
- [ ] Epistemic modes defined and used
- [ ] Multi-page search verified
- [ ] Deduplication logic present
- [ ] URL quality filtering exists

## Evidence

- (prompts, code, examples)

## Verdict

**Status:** PASS / PARTIAL / FAIL

## Missing/Inflated Claims

- (list where claims exceed implementation)
```

## Completion Criteria

PASS only if discovery is more than thin search wrapping; must produce structured, bounded topic expansion.
