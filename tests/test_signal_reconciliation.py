"""Tests for rule-engine vs complaint signal reconciliation."""

from unittest.mock import patch

from src.core.signal_reconciliation import reconcile_signals
from src.core.transaction_lookup import lookup_transaction

SETTLEMENT_DELAY_INTENTS = [
    {
        "intent": "Settlement Delay",
        "confidence": "high",
        "evidence": (
            "settlement for this successful Wallet payment is still pending on my "
            "dashboard — the funds have not reached my bank account yet"
        ),
    }
]

REFUND_AND_CHARGEBACK_INTENTS = [
    {
        "intent": "Refund Pending",
        "confidence": "high",
        "evidence": "refund has been initiated",
    },
    {
        "intent": "Chargeback / Dispute",
        "confidence": "high",
        "evidence": "don't recognise this transaction at all",
    },
]

CHARGEBACK_CONFLICT_INTENTS = [
    {
        "intent": "Chargeback / Dispute",
        "confidence": "high",
        "evidence": "card issuer raised a chargeback dispute",
    },
    {
        "intent": "Settlement Failure",
        "confidence": "high",
        "evidence": "reversal debit from their settlement account",
    },
]


def _print_reconciliation(label: str, result: dict) -> None:
    """Print full reconciliation output for manual review."""
    print(f"\n{'='*80}")
    print(label)
    print(f"{'='*80}")
    for key, value in result.items():
        print(f"{key}: {value}")
    print(f"{'='*80}\n")


def test_reconcile_signals_full_agreement_no_extras() -> None:
    """Settlement Delay complaint aligns with rule engine with no secondary intents."""
    transaction = lookup_transaction("MID000002", "ORD000002", "CUST000002")
    assert transaction is not None

    complaint = (
        "I'm a merchant and settlement for this successful Wallet payment is still "
        "pending on my dashboard — the funds have not reached my bank account yet."
    )

    with patch(
        "src.core.signal_reconciliation.extract_intents",
        return_value=SETTLEMENT_DELAY_INTENTS,
    ):
        result = reconcile_signals(
            rule_based_issue="Settlement Delay",
            complaint_text=complaint,
            transaction=transaction,
        )
    _print_reconciliation("Full agreement — no secondary intents", result)

    assert result["primary_issue"] == "Settlement Delay"
    assert result["agreement"] is True
    assert result["conflict"] is False
    assert result["unresolved_intents"] == []
    assert "Settlement Delay" in result["reconciliation_note"]
    assert "conflict" not in result["reconciliation_note"].lower()
    assert "secondary" not in result["reconciliation_note"].lower()


def test_reconcile_signals_agreement_with_secondary_intents() -> None:
    """Refund Pending rules plus chargeback language surfaces a secondary intent."""
    transaction = lookup_transaction("MID000069", "ORD000069", "CUST000069")
    assert transaction is not None

    complaint = (
        "The merchant says the refund has been initiated, but I also contacted my "
        "bank because I don't recognise this transaction at all."
    )

    with patch(
        "src.core.signal_reconciliation.extract_intents",
        return_value=REFUND_AND_CHARGEBACK_INTENTS,
    ):
        result = reconcile_signals(
            rule_based_issue="Refund Pending",
            complaint_text=complaint,
            transaction=transaction,
        )
    _print_reconciliation("Agreement with unresolved secondary intents", result)

    assert result["primary_issue"] == "Refund Pending"
    assert result["agreement"] is True
    assert result["conflict"] is False
    assert "Refund Pending" in {_intent.get("intent") for _intent in result["extracted_intents"]}
    assert "Chargeback / Dispute" in result["unresolved_intents"]
    assert len(result["unresolved_intents"]) >= 1
    assert "Refund Pending" in result["reconciliation_note"]
    assert "Chargeback / Dispute" in result["reconciliation_note"]
    assert "secondary" in result["reconciliation_note"].lower()


def test_reconcile_signals_full_conflict() -> None:
    """Settlement Delay rules vs chargeback complaint surfaces explicit conflict."""
    transaction = lookup_transaction("MID000002", "ORD000002", "CUST000002")
    assert transaction is not None

    complaint = (
        "The card issuer raised a chargeback dispute on a previously successful "
        "transaction. The merchant reports a reversal debit from their settlement "
        "account and the customer claims an unauthorised transaction despite "
        "earlier success status."
    )

    with patch(
        "src.core.signal_reconciliation.extract_intents",
        return_value=CHARGEBACK_CONFLICT_INTENTS,
    ):
        result = reconcile_signals(
            rule_based_issue="Settlement Delay",
            complaint_text=complaint,
            transaction=transaction,
        )
    _print_reconciliation("Full conflict — rule engine vs complaint intents", result)

    assert result["primary_issue"] == "Settlement Delay"
    assert result["agreement"] is False
    assert result["conflict"] is True
    assert "Settlement Delay" not in result["unresolved_intents"]
    assert "Chargeback / Dispute" in result["unresolved_intents"]
    assert "Settlement Delay" in result["reconciliation_note"]
    assert "Chargeback / Dispute" in result["reconciliation_note"]
    assert "conflict" in result["reconciliation_note"].lower()
