"""Tests for Gemini-backed complaint intent extraction."""

from src.core.intent_extractor import _parse_intent_json, _request_intent_raw_output
from src.issue_taxonomy import IssueType


def _run_case(label: str, complaint: str) -> list[dict]:
    """Run extraction for a case and print raw model output plus parsed intents."""
    raw_output = _request_intent_raw_output(complaint)
    intents = _parse_intent_json(raw_output)

    print(f"\n{'='*80}")
    print(label)
    print(f"{'='*80}")
    print("COMPLAINT:")
    print(complaint)
    print("\nRAW MODEL OUTPUT:")
    print(raw_output)
    print("\nPARSED INTENTS:")
    print(intents)
    print(f"{'='*80}\n")

    return intents


def test_extract_intents_single_clear_intent() -> None:
    """Case 1: UPI debit without merchant credit should map to amount-debited intent."""
    complaint = "I paid ₹2,400 via UPI but the money hasn't reached the merchant."
    intents = _run_case("Case 1 — single clear intent", complaint)

    intent_names = {item.get("intent") for item in intents}
    assert IssueType.AMOUNT_DEBITED_MERCHANT_NOT_CREDITED.value in intent_names
    high_confidence = [
        item
        for item in intents
        if item.get("intent") == IssueType.AMOUNT_DEBITED_MERCHANT_NOT_CREDITED.value
        and item.get("confidence") == "high"
    ]
    assert high_confidence, "Expected high-confidence Amount Debited but Merchant Not Credited"


def test_extract_intents_overlapping_intents() -> None:
    """Case 2: refund initiated plus unrecognized transaction implies two intents."""
    complaint = (
        "The merchant says the refund has been initiated, but I also contacted my "
        "bank because I don't recognise this transaction at all."
    )
    intents = _run_case("Case 2 — overlapping intents", complaint)

    intent_names = {item.get("intent") for item in intents}
    assert IssueType.REFUND_PENDING.value in intent_names
    assert IssueType.CHARGEBACK_DISPUTE.value in intent_names
    assert len(intents) >= 2


def test_extract_intents_vague_low_signal_complaint() -> None:
    """Case 3: vague complaint should not produce a high-confidence assertion."""
    complaint = "Something went wrong with my payment."
    intents = _run_case("Case 3 — vague, low-signal complaint", complaint)

    if not intents:
        return

    assert all(item.get("confidence") != "high" for item in intents)


def test_extract_intents_hinglish_complaint() -> None:
    """Case 4: Hinglish complaint — print output only, no specific assertion yet."""
    complaint = "Mere account se paise kat gaye but merchant ko nahi mila, 3 din ho gaye."
    _run_case("Case 4 — Hinglish complaint", complaint)
