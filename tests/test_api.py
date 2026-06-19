"""Tests for the FastAPI resolution endpoints."""

from unittest.mock import patch

from fastapi.testclient import TestClient

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


def test_resolve_multi_intent_case_returns_secondary_signals() -> None:
    """Settlement Delay transaction with chargeback language surfaces unresolved secondary intents."""
    transaction = lookup_transaction("MID000002", "ORD000002", "CUST000002")
    assert transaction is not None
    assert identify_issue(transaction) == "Settlement Delay"

    complaint = (
        "Settlement for this successful Wallet payment is still pending on my dashboard, "
        "but I also contacted my bank because I don't recognise this transaction at all."
    )

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


def test_resolve_includes_flagged_groundedness_when_verifier_fails() -> None:
    """Flagged groundedness is attached without blocking the resolution response."""
    stubbed_result = {
        "verified": False,
        "unsupported_claims": ["Invented refund amount ₹99999.99"],
        "raw_verifier_output": "- Invented refund amount ₹99999.99",
    }

    with patch("src.core.graph_nodes.verify_groundedness", return_value=stubbed_result):
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

    assert payload["groundedness_verified"] is False
    assert payload["unsupported_claims"] == ["Invented refund amount ₹99999.99"]
    assert isinstance(payload["response"], str)
    assert "Explanation:" in payload["response"]
