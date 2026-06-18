"""Tests for deterministic escalation decisions."""

from src.core.escalation_rules import determine_escalation
from src.core.sop_metadata import load_sop_metadata


def test_below_threshold_no_escalation() -> None:
    """Age within threshold does not trigger escalation."""
    metadata = load_sop_metadata("data/sops/refund_pending.md")
    transaction = {"AGE_HOURS": 130}

    result = determine_escalation(transaction, metadata)

    assert result["escalation_required"] is False
    assert result["escalation_team"] is None
    assert result["reason"] == "refund pending 130h, within 168h threshold"


def test_above_threshold_escalates_with_correct_team() -> None:
    """Age beyond threshold escalates to the SOP-defined team."""
    metadata = load_sop_metadata("data/sops/refund_pending.md")
    transaction = {"AGE_HOURS": 170}

    result = determine_escalation(transaction, metadata)

    assert result["escalation_required"] is True
    assert result["escalation_team"] == "L2 Refunds Ops"
    assert result["reason"] == "refund pending 170h, exceeds 168h threshold"


def test_always_escalate_when_threshold_is_null() -> None:
    """SOPs with null threshold escalate immediately regardless of age."""
    metadata = load_sop_metadata("data/sops/chargeback_dispute.md")
    transaction = {"AGE_HOURS": 2}

    result = determine_escalation(transaction, metadata)

    assert result["escalation_required"] is True
    assert result["escalation_team"] == "Chargeback/Disputes team"
    assert result["reason"] == (
        "chargeback / dispute requires immediate escalation (no age threshold)"
    )


def test_never_escalate_when_sop_disallows() -> None:
    """escalation_required=False in metadata blocks escalation for any age."""
    metadata = {
        "issue": "Refund Completed",
        "escalation_required": False,
        "escalation_threshold_hours": 168,
        "escalation_team": "L2 Refunds Ops",
        "expected_resolution_hours": 120,
    }
    transaction = {"AGE_HOURS": 999}

    result = determine_escalation(transaction, metadata)

    assert result["escalation_required"] is False
    assert result["escalation_team"] is None
    assert result["reason"] == "refund completed does not require escalation per SOP policy"
