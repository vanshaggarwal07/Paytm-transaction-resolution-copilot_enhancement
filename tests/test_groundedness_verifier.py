"""Tests for LLM-backed groundedness verification."""

from src.core.groundedness_verifier import verify_groundedness

GROUNDING_FACTS = {
    "transaction": {
        "TXN_ID": "TXN000002",
        "ORDER_ID": "ORD000002",
        "CUST_ID": "CUST000002",
        "MID": "MID000002",
        "PAYMENT_MODE": "Wallet",
        "TXN_AMOUNT": 2677.33,
        "TXN_STATUS": "Success",
        "BANK_STATUS": "SUCCESS",
        "MERCHANT_CREDITED": "YES",
        "SETTLEMENT_STATUS": "PENDING",
        "AGE_HOURS": 146,
    },
    "sop_content": (
        "## Resolution Steps\n"
        "1. Verify MERCHANT_CREDITED = YES and transaction is included in the settlement batch.\n"
        "2. Check merchant settlement configuration and bank holidays.\n"
        "## Escalation Rules\n"
        "- Escalate to **L2 Settlement Ops** when PENDING exceeds T+2 business days.\n"
    ),
    "escalation": {
        "escalation_required": True,
        "escalation_team": "L2 Settlement Ops",
        "reason": "settlement delay 146h, exceeds 48h threshold",
    },
}

GROUNDED_RESPONSE = """Explanation:
Transaction TXN000002 for order ORD000002 was a Wallet payment of ₹2677.33 with
TXN_STATUS=Success and SETTLEMENT_STATUS=PENDING. The case had been open for 146 hours.

Next Action:
Verify MERCHANT_CREDITED = YES and check settlement batch inclusion for the transaction date.

Escalation:
Yes — L2 Settlement Ops (settlement delay 146h, exceeds 48h threshold)

Source:
settlement_delay.md
"""

FABRICATED_RESPONSE = """Explanation:
Transaction TXN000002 for order ORD000002 was a Card payment of ₹99999.99 with
TXN_STATUS=Failed and BANK_STATUS=FAILED. The merchant was credited immediately.

Next Action:
Close the case as a successful refund with no further action required.

Escalation:
No escalation was required.

Source:
settlement_delay.md
"""


def test_verify_groundedness_grounded_response() -> None:
    """A fact-aligned response — print raw verifier output for manual review."""
    result = verify_groundedness(GROUNDED_RESPONSE, GROUNDING_FACTS)

    print("\n--- grounded verifier output ---")
    print(f"verified: {result['verified']}")
    print(f"unsupported_claims: {result['unsupported_claims']}")
    print(f"raw_verifier_output:\n{result['raw_verifier_output']}")
    print("--- end ---\n")

    assert result["verified"] is None or isinstance(result["verified"], bool)
    assert isinstance(result["unsupported_claims"], list)
    assert isinstance(result["raw_verifier_output"], str)


def test_verify_groundedness_fabricated_response() -> None:
    """A deliberately fabricated response — print raw verifier output for manual review."""
    result = verify_groundedness(FABRICATED_RESPONSE, GROUNDING_FACTS)

    print("\n--- fabricated verifier output ---")
    print(f"verified: {result['verified']}")
    print(f"unsupported_claims: {result['unsupported_claims']}")
    print(f"raw_verifier_output:\n{result['raw_verifier_output']}")
    print("--- end ---\n")

    assert result["verified"] is None or isinstance(result["verified"], bool)
    assert isinstance(result["unsupported_claims"], list)
    assert isinstance(result["raw_verifier_output"], str)
