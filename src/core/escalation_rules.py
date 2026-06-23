"""Deterministic escalation decisions from transaction facts and SOP metadata."""

from __future__ import annotations

from typing import Any


def _issue_phrase(sop_metadata: dict[str, Any]) -> str:
    """Return a lowercase issue label for human-readable escalation reasons."""
    issue = sop_metadata.get("issue", "case")
    return str(issue).lower()


def determine_escalation(transaction: dict[str, Any], sop_metadata: dict[str, Any]) -> dict[str, Any]:
    """Return escalation_required, escalation_team, and a fact-based reason string."""
    issue_label = _issue_phrase(sop_metadata)
    age_hours = int(transaction.get("AGE_HOURS", 0))
    team = sop_metadata.get("escalation_team")

    if not sop_metadata.get("escalation_required"):
        return {
            "escalation_required": False,
            "escalation_team": None,
            "reason": f"{issue_label} does not require escalation per SOP policy",
        }

    threshold = sop_metadata.get("escalation_threshold_hours")
    if threshold is None:
        return {
            "escalation_required": True,
            "escalation_team": team,
            "reason": f"{issue_label} requires immediate escalation (no age threshold)",
        }

    threshold_hours = int(threshold)
    if age_hours > threshold_hours:
        return {
            "escalation_required": True,
            "escalation_team": team,
            "reason": (
                f"{issue_label} {age_hours}h, exceeds {threshold_hours}h threshold"
            ),
        }

    return {
        "escalation_required": False,
        "escalation_team": None,
        "reason": f"{issue_label} {age_hours}h, within {threshold_hours}h threshold",
    }
