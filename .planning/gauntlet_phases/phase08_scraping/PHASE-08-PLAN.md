# PHASE 08 — SCRAPING / CONTENT NORMALIZATION AUDIT

## Mission

Audit the content acquisition and normalization path to verify that fetched content is usable for downstream distillation.

## GSD Workflow

- Discuss: What formats are supported?
- Plan: Trace content from fetch to chunk
- Execute: Inspect normalizers, test edge cases
- Verify: Produce NORMALIZATION_SPEC_AS_IMPLEMENTED.md

## Prompt for Agent

```
You are executing Phase 08 for Sheppard V3: Scraping / Content Normalization Audit.

Mission:
Audit the content acquisition and normalization path to verify that fetched content is usable for downstream distillation.

Objectives:
1. Verify fetch path(s) and source adapters
2. Verify PDF/static/web handling
3. Verify normalization format
4. Verify metadata capture
5. Verify source attribution preservation
6. Verify fallback/error handling for malformed content

Required method:
- Inspect scraper/fetcher code
- Inspect normalization/transformation code
- Inspect metadata extraction
- Inspect how failures and low-quality fetches are handled

Deliverables (write to .planning/gauntlet_phases/phase08_scraping/):
- CONTENT_INGEST_AUDIT.md
- NORMALIZATION_SPEC_AS_IMPLEMENTED.md
- SOURCE_METADATA_AUDIT.md
- FETCH_FAILURE_REPORT.md
- PHASE-08-VERIFICATION.md

Mandatory checks:
- Is content chunked before or after normalization?
- Is raw source preserved?
- Are citations/URLs retained?
- How are PDFs treated?
- How are empty or low-signal pages rejected?

Hard fail conditions:
- Content is scraped but not normalized consistently
- Source metadata is lost
- Distillation inputs are malformed or underspecified
- The system cannot distinguish empty vs. useful content

Completion bar:
PASS only if the refinery input contract is explicit and stable.
```

## Deliverables

- **CONTENT_INGEST_AUDIT.md**
- **NORMALIZATION_SPEC_AS_IMPLEMENTED.md**
- **SOURCE_METADATA_AUDIT.md**
- **FETCH_FAILURE_REPORT.md**
- **PHASE-08-VERIFICATION.md**

## Verification Template

```markdown
# Phase 08 Verification

## Normalization

- [ ] Format coverage documented (HTML, PDF, etc.)
- [ ] Chunking strategy defined
- [ ] Metadata preservation verified
- [ ] Empty/garbage detection exists
- [ ] Failure fallbacks implemented

## Evidence

- (normalizer code, chunking logic)

## Verdict

**Status:** PASS / PARTIAL / FAIL

## Gaps

- (unsupported formats, missing metadata)
```

## Completion Criteria

PASS when all supported input formats produce consistent, chunkable, attributed content.
