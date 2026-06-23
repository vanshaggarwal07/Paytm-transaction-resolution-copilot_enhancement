"""Tests for SOP YAML frontmatter parsing."""

from pathlib import Path

from src.core.sop_metadata import load_sop_metadata

SOPS_DIR = Path("data/sops")


def test_load_sop_metadata_settlement_delay() -> None:
    """Settlement Delay frontmatter matches escalation and timeline prose."""
    metadata = load_sop_metadata(str(SOPS_DIR / "settlement_delay.md"))

    assert metadata["issue"] == "Settlement Delay"
    assert metadata["escalation_required"] is True
    assert metadata["escalation_threshold_hours"] == 48
    assert metadata["escalation_team"] == "L2 Settlement Ops"
    assert metadata["expected_resolution_hours"] == 24


def test_load_sop_metadata_refund_pending() -> None:
    """Refund Pending frontmatter reflects the >7 business day escalation rule."""
    metadata = load_sop_metadata(str(SOPS_DIR / "refund_pending.md"))

    assert metadata["issue"] == "Refund Pending"
    assert metadata["escalation_required"] is True
    assert metadata["escalation_threshold_hours"] == 168
    assert metadata["escalation_team"] == "L2 Refunds Ops"
    assert metadata["expected_resolution_hours"] == 120


def test_load_sop_metadata_chargeback_dispute() -> None:
    """Chargeback frontmatter captures immediate escalation with no hour threshold."""
    metadata = load_sop_metadata(str(SOPS_DIR / "chargeback_dispute.md"))

    assert metadata["issue"] == "Chargeback / Dispute"
    assert metadata["escalation_required"] is True
    assert metadata["escalation_threshold_hours"] is None
    assert metadata["escalation_team"] == "Chargeback/Disputes team"
    assert metadata["expected_resolution_hours"] == 168
