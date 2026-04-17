"""Helpers for deriving and exposing authority trust state."""

from __future__ import annotations

from typing import Any


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def derive_trust_state(
    status: Any = None,
    advisory: Any = None,
    reuse: Any = None,
) -> str:
    """
    Collapse authority maturity/freshness/reuse signals into a product-facing state.

    States:
      - forming
      - synthesized
      - contested
      - stale
      - reusable
    """
    status_dict = _as_dict(status)
    advisory_dict = _as_dict(advisory)
    reuse_dict = _as_dict(reuse)

    explicit = status_dict.get("trust_state")
    if explicit in {"forming", "synthesized", "contested", "stale", "reusable"}:
        return explicit

    freshness = str(status_dict.get("freshness") or "").lower()
    maturity = str(status_dict.get("maturity") or "").lower()
    contradiction_count = int(status_dict.get("contradiction_count", 0) or 0)
    successful_applications = int(status_dict.get("successful_application_count", 0) or 0)
    reusable = bool(
        reuse_dict.get("ready_for_application")
        or reuse_dict.get("application_history")
        or successful_applications > 0
    )
    contested = bool(
        maturity == "contested"
        or contradiction_count > 0
        or advisory_dict.get("major_contradictions")
        or advisory_dict.get("critic_objections")
    )

    if freshness == "stale":
        return "stale"
    if contested:
        return "contested"
    if reusable:
        return "reusable"
    if maturity in {"synthesized", "matured"}:
        return "synthesized"
    return "forming"
