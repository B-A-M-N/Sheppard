from src.utils.distillation_pipeline import semantic_preservation_check


def test_semantic_preservation_check_rejects_scope_and_negation_drift():
    original = {"text": "Postgres does not enable parallel hash joins on Windows in version 15 by default."}
    repaired = {"text": original["text"], "normalized_text": "Postgres enables parallel hash joins by default."}
    check = semantic_preservation_check(original, repaired)
    assert check["core_claim_preserved"] is False or check["scope_preserved"] is False
    assert check["negation_preserved"] is False


def test_semantic_preservation_check_accepts_qualifier_preserving_overlay():
    original = {"text": "CUDA graphs can reduce launch overhead when kernels are small."}
    repaired = {"text": original["text"], "normalized_text": "CUDA graphs can reduce launch overhead when kernels are small."}
    check = semantic_preservation_check(original, repaired)
    assert check["core_claim_preserved"] is True
    assert check["qualifiers_preserved"] is True
    assert check["drift_score"] <= 0.15
