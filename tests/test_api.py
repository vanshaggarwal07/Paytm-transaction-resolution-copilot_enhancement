"""Tests for the FastAPI resolution endpoints."""

from fastapi.testclient import TestClient

from src.core.issue_rules import identify_issue
from src.core.transaction_lookup import lookup_transaction
from src.api.main import app

client = TestClient(app)


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
    assert "issue" in payload
    assert "primary_issue" in payload
    assert "agreement" in payload
    assert "response" in payload
    assert "response_mode" in payload
    assert payload["issue"] == expected_issue
    assert payload["primary_issue"] == expected_issue
    assert isinstance(payload["response"], str)
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


def test_resolve_divergent_complaint_returns_signal_disagreement() -> None:
    """Rule-engine issue stays primary when complaint retrieval disagrees."""
    transaction = lookup_transaction("MID000002", "ORD000002", "CUST000002")
    assert transaction is not None
    expected_issue = identify_issue(transaction)
    assert expected_issue == "Settlement Delay"

    chargeback_complaint = (
        "The card issuer raised a chargeback dispute on a previously successful "
        "transaction. The merchant reports a reversal debit from their settlement "
        "account and the customer claims an unauthorised transaction."
    )

    response = client.post(
        "/resolve",
        json={
            "mid": "MID000002",
            "order_id": "ORD000002",
            "cust_id": "CUST000002",
            "complaint": chargeback_complaint,
        },
    )

    assert response.status_code == 200
    payload = response.json()

    print("\n--- divergent /resolve response ---")
    print(f"primary_issue: {payload['primary_issue']}")
    print(f"secondary_issue: {payload['secondary_issue']}")
    print(f"agreement: {payload['agreement']}")
    print(f"issue (legacy): {payload['issue']}")
    print(f"sop_source: {payload['sop_source']}")
    print("--- end ---\n")

    assert payload["agreement"] is False
    assert payload["primary_issue"] == "Settlement Delay"
    assert payload["issue"] == "Settlement Delay"
    assert payload["secondary_issue"] == "Chargeback / Dispute"
    assert payload["sop_source"] == "settlement_delay.md"

