"""Tests for complaint intent extraction (deterministic, no live Gemini calls)."""

from unittest.mock import patch

from src.core.intent_extractor import _parse_intent_json, extract_intents
from src.issue_taxonomy import IssueType

CASE_1_RAW = """[
  {
    "intent": "Amount Debited but Merchant Not Credited",
    "confidence": "high",
    "evidence": "money hasn't reached the merchant"
  }
]"""

CASE_2_RAW = """[
  {
    "intent": "Refund Pending",
    "confidence": "high",
    "evidence": "refund has been initiated"
  },
  {
    "intent": "Chargeback / Dispute",
    "confidence": "high",
    "evidence": "don't recognise this transaction at all"
  }
]"""

CASE_3_RAW = """[
  {
    "intent": "Failed Payment",
    "confidence": "low",
    "evidence": "Something went wrong with my payment"
  }
]"""

CASE_4_RAW = """[
  {
    "intent": "Amount Debited but Merchant Not Credited",
    "confidence": "high",
    "evidence": "paise kat gaye but merchant ko nahi mila"
  }
]"""


def _run_case(label: str, complaint: str, raw_output: str) -> list[dict]:
    """Run extraction with a mocked Gemini response and print outputs."""
    with patch(
        "src.core.intent_extractor._request_intent_raw_output",
        return_value=raw_output,
    ):
        intents = extract_intents(complaint)

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
    intents = _run_case("Case 1 — single clear intent", complaint, CASE_1_RAW)

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
    intents = _run_case("Case 2 — overlapping intents", complaint, CASE_2_RAW)

    intent_names = {item.get("intent") for item in intents}
    assert IssueType.REFUND_PENDING.value in intent_names
    assert IssueType.CHARGEBACK_DISPUTE.value in intent_names
    assert len(intents) >= 2


def test_extract_intents_vague_low_signal_complaint() -> None:
    """Case 3: vague complaint should not produce a high-confidence assertion."""
    complaint = "Something went wrong with my payment."
    intents = _run_case("Case 3 — vague, low-signal complaint", complaint, CASE_3_RAW)

    if not intents:
        return

    assert all(item.get("confidence") != "high" for item in intents)


def test_extract_intents_hinglish_complaint() -> None:
    """Case 4: Hinglish complaint — print output only, no specific assertion yet."""
    complaint = "Mere account se paise kat gaye but merchant ko nahi mila, 3 din ho gaye."
    intents = _run_case("Case 4 — Hinglish complaint", complaint, CASE_4_RAW)
    assert len(intents) >= 1


def test_parse_intent_json_handles_fenced_output() -> None:
    """Parser should accept markdown-fenced JSON without calling Gemini."""
    fenced = '```json\n[{"intent": "UPI Pending", "confidence": "high", "evidence": "stuck"}]\n```'
    parsed = _parse_intent_json(fenced)
    assert parsed[0]["intent"] == "UPI Pending"
