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
    assert "response" in payload
    assert "response_mode" in payload
    assert payload["issue"] == expected_issue
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
