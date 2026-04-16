"""
Phase 12-B validator tests for derived multi-citation claims.
"""

import os
import sys

# Ensure src/ is on sys.path for bare imports.
_project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
_src = os.path.join(_project_root, "src")
for _p in (_src, _project_root):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from src.retrieval.models import RetrievedItem
from src.retrieval.validator import validate_response_grounding


def make_item(citation_key: str, text: str) -> RetrievedItem:
    return RetrievedItem(
        content=text,
        source="test",
        strategy="test",
        citation_key=citation_key,
        knowledge_level="B",
        item_type="claim",
    )


def test_validator_correct_derived_delta():
    response = "Metric units exceed the comparison units by 25 units [A] [B]."
    items = [
        make_item("A", "Metric units total 100 units."),
        make_item("B", "Comparison units total 75 units."),
    ]

    result = validate_response_grounding(response, items)

    assert result["is_valid"], result["errors"]


def test_validator_correct_derived_percent():
    response = "Metric units increased by 50% [A] [B]."
    items = [
        make_item("A", "Metric units were 80 units before the change."),
        make_item("B", "Metric units are now 120 units after the change."),
    ]

    result = validate_response_grounding(response, items)

    assert result["is_valid"], result["errors"]


def test_validator_incorrect_derived_delta():
    response = "Metric units exceed the comparison units by 30 units [A] [B]."
    items = [
        make_item("A", "Metric units total 100 units."),
        make_item("B", "Comparison units total 75 units."),
    ]

    result = validate_response_grounding(response, items)

    assert not result["is_valid"]
    assert any("Derived claim mismatch" in err for err in result["errors"])


def test_validator_incorrect_derived_percent():
    response = "Metric units increased by 40% [A] [B]."
    items = [
        make_item("A", "Metric units were 80 units before the change."),
        make_item("B", "Metric units are now 120 units after the change."),
    ]

    result = validate_response_grounding(response, items)

    assert not result["is_valid"]
    assert any("Derived claim mismatch" in err for err in result["errors"])


def test_validator_single_citation_still_passes():
    response = "Company revenue was 10 million dollars [A]."
    items = [
        make_item("A", "Company revenue was 10 million dollars in the quarter."),
    ]

    result = validate_response_grounding(response, items)

    assert result["is_valid"], result["errors"]


def test_validator_non_comparative_multi_citation():
    response = "Metric units were 100 units and comparison units were 75 units [A] [B]."
    items = [
        make_item("A", "Metric units total 100 units."),
        make_item("B", "Comparison units total 75 units."),
    ]

    result = validate_response_grounding(response, items)

    assert result["is_valid"], result["errors"]
    assert not any(d.get("error") == "derived_mismatch" for d in result["details"])


def test_validator_kill_test_incorrect_percentage():
    response = "Metric units increased by 25% [A] [B]."
    items = [
        make_item("A", "Metric units were 80 units before the change."),
        make_item("B", "Metric units are now 120 units after the change."),
    ]

    result = validate_response_grounding(response, items)

    assert not result["is_valid"]
    assert any("computed" in err and "%" in err for err in result["errors"])
