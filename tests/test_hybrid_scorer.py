"""Tests for hybrid SOP scoring."""

from src.core.hybrid_scorer import compute_hybrid_scores


def _print_scored(label: str, scored: list[dict]) -> None:
    """Print full scored candidate list for manual review."""
    print(f"\n{'=' * 80}")
    print(label)
    print(f"{'=' * 80}")
    for index, candidate in enumerate(scored, start=1):
        print(f"\n[{index}] {candidate['issue_name']}")
        print(f"    semantic_score:   {candidate['semantic_score']}")
        print(f"    intent_score:     {candidate['intent_score']}")
        print(f"    structural_score: {candidate['structural_score']}")
        print(f"    final_score:      {candidate['final_score']}")
    print(f"{'=' * 80}\n")


def test_hybrid_scorer_intent_and_structural_boost_upi_pending() -> None:
    """UPI intent + UPI structural rules should rank UPI Pending first."""
    transaction = {
        "PAYMENT_MODE": "UPI",
        "AGE_HOURS": 12,
    }
    extracted_intents = [
        {
            "intent": "UPI Pending",
            "confidence": "high",
            "evidence": "UPI payment still showing pending in my bank app",
        }
    ]

    candidates = [
        {
            "issue_name": "UPI Pending",
            "file_path": "data/sops/upi_pending.md",
            "content": "UPI pending body",
            "sop_metadata": {"expected_resolution_hours": 48},
        },
        {
            "issue_name": "Refund Pending",
            "file_path": "data/sops/refund_pending.md",
            "content": "Refund pending body",
            "sop_metadata": {"expected_resolution_hours": 120},
        },
        {
            "issue_name": "Settlement Delay",
            "file_path": "data/sops/settlement_delay.md",
            "content": "Settlement delay body",
            "sop_metadata": {"expected_resolution_hours": 24},
        },
    ]
    semantic_scores = [0.55, 0.55, 0.55]

    scored = compute_hybrid_scores(
        candidates=candidates,
        semantic_scores=semantic_scores,
        extracted_intents=extracted_intents,
        transaction=transaction,
    )
    _print_scored(
        "Scenario 1 — intent + structural boost (UPI Pending should rank first)",
        scored,
    )

    assert scored[0]["issue_name"] == "UPI Pending"
    assert scored[0]["intent_score"] == 1.0
    assert scored[0]["structural_score"] == 1.0
    assert scored[0]["final_score"] > scored[1]["final_score"]
    assert scored[0]["final_score"] > scored[2]["final_score"]


def test_hybrid_scorer_structural_overrides_weaker_semantic() -> None:
    """Card structural alignment should lift Failed Payment above Refund Pending."""
    transaction = {
        "PAYMENT_MODE": "Card",
        "AGE_HOURS": 6,
    }
    extracted_intents: list[dict] = []

    candidates = [
        {
            "issue_name": "Failed Payment",
            "file_path": "data/sops/failed_payment.md",
            "content": "Failed payment body",
            "sop_metadata": {"expected_resolution_hours": 48},
        },
        {
            "issue_name": "Refund Pending",
            "file_path": "data/sops/refund_pending.md",
            "content": "Refund pending body",
            "sop_metadata": {"expected_resolution_hours": 120},
        },
    ]
    semantic_scores = [0.42, 0.48]

    scored = compute_hybrid_scores(
        candidates=candidates,
        semantic_scores=semantic_scores,
        extracted_intents=extracted_intents,
        transaction=transaction,
    )
    _print_scored(
        "Scenario 2 — structural overrides weaker semantic (Failed Payment should win)",
        scored,
    )

    assert scored[0]["issue_name"] == "Failed Payment"
    assert scored[0]["semantic_score"] < scored[1]["semantic_score"]
    assert scored[0]["structural_score"] == 1.0
    assert scored[1]["structural_score"] == 0.0
    assert scored[0]["final_score"] > scored[1]["final_score"]


def test_hybrid_scorer_chargeback_boost_on_wallet_when_intent_high() -> None:
    """High-confidence chargeback intent should boost chargeback SOP even on Wallet txns."""
    transaction = {
        "PAYMENT_MODE": "Wallet",
        "AGE_HOURS": 146,
    }
    extracted_intents = [
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

    candidates = [
        {
            "issue_name": "Chargeback / Dispute",
            "file_path": "data/sops/chargeback_dispute.md",
            "content": "Chargeback body",
            "sop_metadata": {"expected_resolution_hours": 168},
        },
        {
            "issue_name": "Settlement Failure",
            "file_path": "data/sops/settlement_failure.md",
            "content": "Settlement failure body",
            "sop_metadata": {"expected_resolution_hours": 24},
        },
    ]
    semantic_scores = [0.70, 0.41]

    scored = compute_hybrid_scores(
        candidates=candidates,
        semantic_scores=semantic_scores,
        extracted_intents=extracted_intents,
        transaction=transaction,
    )

    assert scored[0]["issue_name"] == "Chargeback / Dispute"
    assert scored[0]["structural_score"] == 1.0
    assert scored[0]["final_score"] > scored[1]["final_score"]
