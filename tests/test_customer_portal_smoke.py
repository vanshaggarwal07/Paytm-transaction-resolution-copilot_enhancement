"""Smoke tests for customer portal data and auth dependencies."""

from pathlib import Path

import pandas as pd

from src.core.customer_auth import authenticate_customer, get_customer_transactions

CUSTOMERS_PATH = Path("data/customers.csv")
TRANSACTIONS_PATH = Path("data/transactions.csv")

REQUIRED_TRANSACTION_KEYS = (
    "ORDER_ID",
    "TXN_STATUS",
    "TXN_AMOUNT",
    "MID",
    "CUST_ID",
)


def test_customers_csv_exists_with_minimum_rows() -> None:
    """customers.csv must exist and contain at least 10 customer records."""
    assert CUSTOMERS_PATH.is_file(), f"Missing {CUSTOMERS_PATH}"

    customers = pd.read_csv(CUSTOMERS_PATH, keep_default_na=False)
    assert len(customers) >= 10


def test_every_customer_cust_id_exists_in_transactions() -> None:
    """Every CUST_ID in customers.csv must appear in transactions.csv."""
    customers = pd.read_csv(CUSTOMERS_PATH, keep_default_na=False)
    transactions = pd.read_csv(TRANSACTIONS_PATH, keep_default_na=False)

    customer_ids = set(customers["CUST_ID"].astype(str))
    transaction_ids = set(transactions["CUST_ID"].astype(str))
    missing = customer_ids - transaction_ids

    assert not missing, f"CUST_ID values missing from transactions.csv: {sorted(missing)}"


def test_authenticate_customer_rejects_invalid_credentials() -> None:
    """Invalid credentials must return None."""
    result = authenticate_customer("bad_user", "bad_pass")
    assert result is None


def test_get_customer_transactions_returns_expected_shape() -> None:
    """Real CUST_ID values return transaction dicts with required keys."""
    customers = pd.read_csv(CUSTOMERS_PATH, keep_default_na=False)
    sample_cust_id = str(customers.iloc[0]["CUST_ID"])

    transactions = get_customer_transactions(sample_cust_id)

    assert isinstance(transactions, list)
    assert len(transactions) > 0
    for txn in transactions:
        for key in REQUIRED_TRANSACTION_KEYS:
            assert key in txn
