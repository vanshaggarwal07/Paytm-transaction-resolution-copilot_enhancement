"""Tests for rule-engine vs complaint signal reconciliation."""

from src.core.signal_reconciliation import reconcile_signals


def test_reconcile_signals_matching_complaint() -> None:
    """Complaint text that retrieves the same SOP yields agreement=True."""
    result = reconcile_signals(
        rule_based_issue="Settlement Delay",
        complaint_text=(
            "Settlement is still pending and the merchant has not received funds yet "
            "on their dashboard."
        ),
    )

    print("\n--- matching reconciliation ---")
    print(result)
    print("--- end ---\n")

    assert result["agreement"] is True
    assert result["primary_issue"] == "Settlement Delay"
    assert result["secondary_issue"] is None


def test_reconcile_signals_conflicting_complaint() -> None:
    """Refund Pending rules vs chargeback complaint surfaces disagreement."""
    result = reconcile_signals(
        rule_based_issue="Refund Pending",
        complaint_text=(
            "The card issuer raised a chargeback dispute on a previously successful "
            "transaction. The merchant reports a reversal debit from their settlement "
            "account and the customer claims an unauthorised transaction despite "
            "earlier success status."
        ),
    )

    print("\n--- conflicting reconciliation ---")
    print(result)
    print("--- end ---\n")

    assert result["agreement"] is False
    assert result["primary_issue"] == "Refund Pending"
    assert result["secondary_issue"] == "Chargeback / Dispute"
