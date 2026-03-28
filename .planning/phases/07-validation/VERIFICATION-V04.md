# VERIFICATION-V04: Cross-component consistency

**Test executed**: `pytest tests/validation/v04_consistency.py -q`

**Test method**:
- Created a mission, source, chunk, and atom in PostgreSQL via the storage adapter.
- Stored the atom with evidence using `store_atom_with_evidence`, which indexes the atom into Chroma and caches in Redis.
- After a 0.5s stabilization period, fetched the atom from the DB and from the Chroma knowledge_atoms collection.
- Compared the atom's document content (built via `SemanticProjectionBuilder`) and metadata between DB and index.

**Sample size**: 1 atom, 1 source, 1 chunk (small scale)

**Results**:
- Document content matched exactly between DB and Chroma.
- All metadata fields (atom_id, topic_id, domain_profile_id, atom_type, confidence, importance, stability, core_atom_flag, contradiction_flag) matched.
- Zero mismatches found.

**Verdict**: PASS

**Notes**: The test verifies that the atom indexing pipeline (`store_atom_with_evidence`) produces a consistent view across PostgreSQL (source of truth) and the Chroma retrieval index. The stabilization period allows asynchronous indexing to complete.
