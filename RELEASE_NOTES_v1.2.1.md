# Sheppard v1.2.1

Post-release stabilization for the live V3 authority, application, and retrieval path.

## Included

- Local PostgreSQL auto-start on application launch when the configured V3 DSN targets localhost and the service is down.
- Live `application.application_evidence` contract restored:
  `authority_record_id`, `atom_id`, and `bundle_id` are nullable individually, with a non-empty binding constraint.
- DB-backed end-to-end tests for:
  condensation storage,
  synthesis authority binding,
  analysis application persistence,
  retrieval of authority plus contradictions,
  authority maturation,
  analysis feedback loop.
- Authority/advisory persistence coverage expanded:
  contradiction binding,
  related authority records,
  coverage-gap advisories,
  richer status JSON assertions.
- Application feedback loop hardened:
  authority feedback updates preserve required identity fields,
  open questions are persisted as an output type,
  successful application runs increment authority score and success counters.
- Retrieval role-depth improvements:
  project artifact slot,
  unresolved slot,
  exact-match lexical bias,
  authority-aware rerank boosts for core and authority-linked atoms.

## Verification

- `pytest -q tests/core/test_system_postgres_startup.py tests/core/test_system_query_filters.py tests/research/reasoning/test_synthesis_service_authority.py tests/research/reasoning/test_analysis_service_persistence.py tests/research/reasoning/test_v3_retriever_authority.py`
- `pytest -q tests/research/reasoning/test_v3_retriever_batch.py tests/research/reasoning/test_v3_retriever_roles.py tests/research/reasoning/test_authority_advisories.py`
- `pytest -q tests/integration/test_knowledge_pipeline.py tests/integration/test_authority_pipeline_e2e.py tests/integration/test_analysis_application_e2e.py tests/integration/test_retrieval_authority_contradiction_e2e.py tests/integration/test_authority_maturity_flow_e2e.py tests/integration/test_analysis_feedback_loop_e2e.py`
