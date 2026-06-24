"""Tests for prototype customer authentication and transaction lookup."""

from pathlib import Path

import pandas as pd

from src.core.customer_auth import authenticate_customer, get_customer_transactions

CUSTOMERS_PATH = Path("data/customers.csv")
TRANSACTIONS_PATH = Path("data/transactions.csv")


def _first_customer_row() -> dict:
    """Return the first row from the generated customers CSV."""
    customers = pd.read_csv(CUSTOMERS_PATH, keep_default_na=False)
    assert not customers.empty, "data/customers.csv must exist — run generate_customers.py first"
    return customers.iloc[0].to_dict()


def test_authenticate_customer_with_valid_credentials() -> None:
    """Valid username/password returns the matching customer dict."""
    customer = _first_customer_row()
    result = authenticate_customer(customer["USERNAME"], customer["PASSWORD"])

    assert result is not None
    assert isinstance(result, dict)
    assert result["CUST_ID"] == customer["CUST_ID"]
    assert result["USERNAME"] == customer["USERNAME"]


def test_authenticate_customer_with_wrong_password() -> None:
    """Wrong password returns None."""
    customer = _first_customer_row()
    result = authenticate_customer(customer["USERNAME"], "Pay@0000")

    assert result is None


def test_get_customer_transactions_returns_sorted_rows() -> None:
    """Known CUST_ID returns non-empty transaction history with expected keys."""
    customer = _first_customer_row()
    transactions = get_customer_transactions(customer["CUST_ID"])

    assert isinstance(transactions, list)
    assert len(transactions) > 0

    first = transactions[0]
    for key in (
        "TXN_ID",
        "ORDER_ID",
        "CUST_ID",
        "MID",
        "PAYMENT_MODE",
        "TXN_AMOUNT",
        "TXN_STATUS",
        "TXN_TIMESTAMP",
    ):
        assert key in first

    assert first["CUST_ID"] == customer["CUST_ID"]

    if len(transactions) > 1:
        assert transactions[0]["TXN_TIMESTAMP"] >= transactions[1]["TXN_TIMESTAMP"]
