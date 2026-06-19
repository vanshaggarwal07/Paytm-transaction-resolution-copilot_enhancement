"""Tests for the FastAPI resolution endpoints."""

import io
from unittest.mock import patch

from fastapi.testclient import TestClient
from PIL import Image, ImageDraw

from src.core.image_extractor import FIELD_NAMES
from src.core.issue_rules import identify_issue
from src.core.transaction_lookup import lookup_transaction
from src.api.main import app

client = TestClient(app)

CONFLICT_COMPLAINT = (
    "The card issuer raised a chargeback dispute on a previously successful "
    "transaction. The merchant reports a reversal debit from their settlement "
    "account and the customer claims an unauthorised transaction."
)

AGENT_ANSWERS = (
    "The customer confirmed the transaction was authorised — this is a "
    "settlement delay issue, not a dispute."
)


def test_health_returns_200() -> None:
    """GET /health should return 200 with ok status."""
    response = client.get("/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert "llm_configured" in payload
    assert "llm_ready" in payload


def test_resolve_valid_transaction_returns_200_with_keys() -> None:
    """POST /resolve with a known transaction returns issue and response."""
    transaction = lookup_transaction("MID000010", "ORD000010", "CUST000010")
    assert transaction is not None
    expected_issue = identify_issue(transaction)

    response = client.post(
        "/resolve",
        json={
            "mid": "MID000010",
            "order_id": "ORD000010",
            "cust_id": "CUST000010",
            "complaint": "Money deducted but merchant never received payment",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload.get("status") != "clarification_needed"
    assert "issue" in payload
    assert "primary_issue" in payload
    assert "agreement" in payload
    assert "response" in payload
    assert "response_mode" in payload
    assert "case_note" in payload
    assert "groundedness_verified" in payload
    assert "unsupported_claims" in payload
    assert "retrieval_scores" in payload
    retrieval_scores = payload["retrieval_scores"]
    assert set(retrieval_scores.keys()) == {"semantic", "intent", "structural", "final"}
    for key in ("semantic", "intent", "structural", "final"):
        assert isinstance(retrieval_scores[key], (int, float))
    assert payload["issue"] == expected_issue
    assert payload["primary_issue"] == expected_issue
    assert isinstance(payload["response"], str)
    assert isinstance(payload["case_note"], str)
    assert len(payload["case_note"].strip()) > 0
    assert "Explanation:" in payload["response"]


def test_resolve_unknown_transaction_returns_404() -> None:
    """POST /resolve with a made-up key combination returns 404."""
    response = client.post(
        "/resolve",
        json={
            "mid": "MID999999",
            "order_id": "ORD999999",
            "cust_id": "CUST999999",
        },
    )

    assert response.status_code == 404
    assert "No transaction found" in response.json()["detail"]


def test_resolve_clarification_needed_on_conflict() -> None:
    """Conflict complaint returns clarification_needed instead of a full resolution."""
    response = client.post(
        "/resolve",
        json={
            "mid": "MID000002",
            "order_id": "ORD000002",
            "cust_id": "CUST000002",
            "complaint": CONFLICT_COMPLAINT,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "clarification_needed"
    assert isinstance(payload["clarifying_questions"], list)
    assert len(payload["clarifying_questions"]) >= 1
    assert "response" not in payload


def test_resolve_post_clarification_returns_full_resolution() -> None:
    """Agent answers skip clarification and return the full resolution payload."""
    response = client.post(
        "/resolve",
        json={
            "mid": "MID000002",
            "order_id": "ORD000002",
            "cust_id": "CUST000002",
            "complaint": CONFLICT_COMPLAINT,
            "agent_answers": AGENT_ANSWERS,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload.get("status") != "clarification_needed"
    assert payload["primary_issue"] == "Settlement Delay"
    assert isinstance(payload["response"], str)
    assert len(payload["response"].strip()) > 0
    assert "case_note" in payload
    assert "retrieval_scores" in payload


def test_resolve_conflict_case_returns_reconciliation_fields() -> None:
    """Chargeback complaint against Settlement Delay transaction surfaces conflict fields."""
    transaction = lookup_transaction("MID000002", "ORD000002", "CUST000002")
    assert transaction is not None
    assert identify_issue(transaction) == "Settlement Delay"

    response = client.post(
        "/resolve",
        json={
            "mid": "MID000002",
            "order_id": "ORD000002",
            "cust_id": "CUST000002",
            "complaint": CONFLICT_COMPLAINT,
            "agent_answers": AGENT_ANSWERS,
        },
    )

    assert response.status_code == 200
    payload = response.json()

    print("\n--- conflict /resolve response ---")
    print(f"primary_issue: {payload['primary_issue']}")
    print(f"conflict: {payload['conflict']}")
    print(f"agreement: {payload['agreement']}")
    print(f"unresolved_intents: {payload['unresolved_intents']}")
    print(f"extracted_intents: {payload['extracted_intents']}")
    print(f"reconciliation_note: {payload['reconciliation_note']}")
    print("--- end ---\n")

    assert payload.get("status") != "clarification_needed"
    assert payload["primary_issue"] == "Settlement Delay"
    assert isinstance(payload["extracted_intents"], list)
    assert len(payload["extracted_intents"]) >= 1
    assert "retrieval_scores" in payload
    retrieval_scores = payload["retrieval_scores"]
    assert set(retrieval_scores.keys()) == {"semantic", "intent", "structural", "final"}


SETTLEMENT_MULTI_INTENT = [
    {
        "intent": "Settlement Delay",
        "confidence": "high",
        "evidence": "settlement still pending on my dashboard",
    },
    {
        "intent": "Chargeback / Dispute",
        "confidence": "high",
        "evidence": "don't recognise this transaction at all",
    },
]

STUB_SETTLEMENT_RESOLVE_RESPONSE = (
    "Explanation:\n"
    "Settlement for this Wallet payment is still pending on the merchant dashboard.\n\n"
    "Next Action:\n"
    "Verify settlement batch inclusion and merchant bank configuration.\n\n"
    "Escalation:\n"
    "Yes — L2 Settlement Ops.\n\n"
    "Source:\n"
    "settlement_delay.md\n",
    "gemini",
)

STUB_SETTLEMENT_CASE_NOTE = (
    "MID000002 / ORD000002: Settlement Delay — funds not yet reached bank; "
    "secondary Chargeback / Dispute signal flagged for review."
)

STUB_GROUNDEDNESS_OK = {
    "verified": True,
    "unsupported_claims": [],
    "raw_verifier_output": "",
}


def test_resolve_multi_intent_case_returns_secondary_signals() -> None:
    """Settlement Delay transaction with chargeback language surfaces unresolved secondary intents."""
    transaction = lookup_transaction("MID000002", "ORD000002", "CUST000002")
    assert transaction is not None
    assert identify_issue(transaction) == "Settlement Delay"

    complaint = (
        "Settlement for this successful Wallet payment is still pending on my dashboard, "
        "but I also contacted my bank because I don't recognise this transaction at all."
    )

    with patch(
        "src.core.signal_reconciliation.extract_intents",
        return_value=SETTLEMENT_MULTI_INTENT,
    ), patch(
        "src.core.graph_nodes.generate_response",
        return_value=STUB_SETTLEMENT_RESOLVE_RESPONSE,
    ), patch(
        "src.core.graph_nodes.generate_case_note",
        return_value=STUB_SETTLEMENT_CASE_NOTE,
    ), patch(
        "src.core.graph_nodes.verify_groundedness",
        return_value=STUB_GROUNDEDNESS_OK,
    ):
        response = client.post(
            "/resolve",
            json={
                "mid": "MID000002",
                "order_id": "ORD000002",
                "cust_id": "CUST000002",
                "complaint": complaint,
            },
        )

    assert response.status_code == 200
    payload = response.json()

    print("\n--- multi-intent /resolve response ---")
    print(f"primary_issue: {payload['primary_issue']}")
    print(f"conflict: {payload['conflict']}")
    print(f"agreement: {payload['agreement']}")
    print(f"unresolved_intents: {payload['unresolved_intents']}")
    print(f"extracted_intents: {payload['extracted_intents']}")
    print(f"reconciliation_note: {payload['reconciliation_note']}")
    print("--- end ---\n")

    assert payload.get("status") != "clarification_needed"
    assert payload["primary_issue"] == "Settlement Delay"
    assert payload["agreement"] is True
    assert payload["conflict"] is False
    assert "Chargeback / Dispute" in payload["unresolved_intents"]
    assert len(payload["extracted_intents"]) >= 2
    assert "secondary" in payload["reconciliation_note"].lower()
    assert payload["secondary_issue"] == "Chargeback / Dispute"


AMOUNT_DEBITED_INTENTS = [
    {
        "intent": "Amount Debited but Merchant Not Credited",
        "confidence": "high",
        "evidence": "merchant never received payment",
    }
]

STUB_RESOLVE_RESPONSE = (
    "Explanation:\n"
    "Amount was debited from the customer but the merchant was not credited.\n\n"
    "Next Action:\n"
    "Verify bank transfer status and merchant settlement configuration.\n\n"
    "Escalation:\n"
    "No escalation required.\n\n"
    "Source:\n"
    "amount_debited_merchant_not_credited.md\n",
    "gemini",
)

STUB_CASE_NOTE = (
    "MID000010 / ORD000010: Amount Debited but Merchant Not Credited — "
    "customer reports merchant never received payment."
)


def test_resolve_includes_flagged_groundedness_when_verifier_fails() -> None:
    """Flagged groundedness is attached without blocking the resolution response."""
    stubbed_result = {
        "verified": False,
        "unsupported_claims": ["Invented refund amount ₹99999.99"],
        "raw_verifier_output": "- Invented refund amount ₹99999.99",
    }

    with patch(
        "src.core.signal_reconciliation.extract_intents",
        return_value=AMOUNT_DEBITED_INTENTS,
    ), patch(
        "src.core.graph_nodes.generate_response",
        return_value=STUB_RESOLVE_RESPONSE,
    ), patch(
        "src.core.graph_nodes.generate_case_note",
        return_value=STUB_CASE_NOTE,
    ), patch(
        "src.core.graph_nodes.verify_groundedness",
        return_value=stubbed_result,
    ):
        response = client.post(
            "/resolve",
            json={
                "mid": "MID000010",
                "order_id": "ORD000010",
                "cust_id": "CUST000010",
                "complaint": "Money deducted but merchant never received payment",
            },
        )

    assert response.status_code == 200
    payload = response.json()

    assert payload.get("status") != "clarification_needed"
    assert payload["groundedness_verified"] is False
    assert payload["unsupported_claims"] == ["Invented refund amount ₹99999.99"]
    assert isinstance(payload["response"], str)
    assert "Explanation:" in payload["response"]


def _build_test_dashboard_image() -> bytes:
    """Create a PNG screenshot-like image with fake transaction details."""
    image = Image.new("RGB", (800, 400), color="white")
    draw = ImageDraw.Draw(image)
    text = (
        "MID: MID000042  ORDER_ID: ORD000042  CUST_ID: CUST000042\n"
        "Amount: ₹1,499  Mode: UPI  Status: Success"
    )
    draw.text((20, 180), text, fill="black")

    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def test_extract_image_rejects_non_image_content_type() -> None:
    """POST /extract-image with a non-image upload returns 400."""
    response = client.post(
        "/extract-image",
        files={"file": ("document.pdf", b"%PDF-1.4", "application/pdf")},
    )

    assert response.status_code == 400
    assert "Unsupported file type" in response.json()["detail"]


def test_extract_image_with_programmatic_png_returns_extraction() -> None:
    """POST /extract-image with a generated PNG returns all fields and pre_populated."""
    image_bytes = _build_test_dashboard_image()
    response = client.post(
        "/extract-image",
        files={"file": ("dashboard.png", image_bytes, "image/png")},
    )

    assert response.status_code == 200
    payload = response.json()

    print("\n--- /extract-image response ---")
    for field in FIELD_NAMES:
        entry = payload[field]
        print(f"{field}: value={entry['value']!r} confidence={entry['confidence']!r}")
    print(f"pre_populated: {payload['pre_populated']}")
    print(f"extraction_warning: {payload['extraction_warning']!r}")
    print("--- end ---\n")

    for field in FIELD_NAMES:
        assert field in payload
        assert "value" in payload[field]
        assert "confidence" in payload[field]
    assert isinstance(payload["pre_populated"], dict)


def test_extract_image_sets_warning_when_key_identifier_absent() -> None:
    """extraction_warning is set when a key identifier is absent or low-confidence."""
    stubbed_extraction = {
        "MID": {"value": None, "confidence": "absent"},
        "ORDER_ID": {"value": "ORD000042", "confidence": "high"},
        "CUST_ID": {"value": "CUST000042", "confidence": "high"},
        "TXN_AMOUNT": {"value": "1499", "confidence": "high"},
        "PAYMENT_MODE": {"value": "UPI", "confidence": "high"},
        "TXN_STATUS": {"value": "Success", "confidence": "high"},
    }

    with patch("src.api.main.extract_fields_from_image", return_value=stubbed_extraction):
        response = client.post(
            "/extract-image",
            files={"file": ("dashboard.png", b"fake-png-bytes", "image/png")},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["extraction_warning"] is not None
    assert "verify before submitting" in payload["extraction_warning"]
    assert "MID" not in payload["pre_populated"]
