"""Prototype customer authentication and transaction history lookup."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)

DEFAULT_CUSTOMERS_PATH = Path("data/customers.csv")
DEFAULT_TRANSACTIONS_PATH = Path("data/transactions.csv")

_CUSTOMERS_DF: pd.DataFrame | None = None
_TRANSACTIONS_DF: pd.DataFrame | None = None


def _load_customers(path: Path = DEFAULT_CUSTOMERS_PATH) -> pd.DataFrame:
    """Load customers CSV, using the module-level cache after the first read."""
    global _CUSTOMERS_DF

    if _CUSTOMERS_DF is None:
        try:
            _CUSTOMERS_DF = pd.read_csv(path, keep_default_na=False)
            logger.info("Loaded %s customer records from %s", len(_CUSTOMERS_DF), path)
        except FileNotFoundError:
            logger.warning("Customers file not found: %s", path)
            _CUSTOMERS_DF = pd.DataFrame()
        except Exception as exc:
            logger.warning("Failed to load customers from %s: %s", path, exc)
            _CUSTOMERS_DF = pd.DataFrame()

    return _CUSTOMERS_DF


def _load_transactions(path: Path = DEFAULT_TRANSACTIONS_PATH) -> pd.DataFrame:
    """Load transactions CSV, using the module-level cache after the first read."""
    global _TRANSACTIONS_DF

    if _TRANSACTIONS_DF is None:
        try:
            _TRANSACTIONS_DF = pd.read_csv(path, keep_default_na=False)
            logger.info("Loaded %s transaction records from %s", len(_TRANSACTIONS_DF), path)
        except FileNotFoundError:
            logger.warning("Transactions file not found: %s", path)
            _TRANSACTIONS_DF = pd.DataFrame()
        except Exception as exc:
            logger.warning("Failed to load transactions from %s: %s", path, exc)
            _TRANSACTIONS_DF = pd.DataFrame()

    return _TRANSACTIONS_DF


def authenticate_customer(username: str, password: str) -> dict[str, Any] | None:
    """Return the matching customer row when credentials match, else None."""
    try:
        customers = _load_customers()
        if customers.empty:
            return None

        matches = customers[
            (customers["USERNAME"] == username) & (customers["PASSWORD"] == password)
        ]
        if matches.empty:
            return None

        return matches.iloc[0].to_dict()
    except Exception as exc:
        logger.warning("Customer authentication failed for username %r: %s", username, exc)
        return None


def get_customer_transactions(cust_id: str) -> list[dict[str, Any]]:
    """Return all transactions for a customer, newest first."""
    try:
        transactions = _load_transactions()
        if transactions.empty:
            return []

        matches = transactions[transactions["CUST_ID"] == cust_id].copy()
        if matches.empty:
            return []

        matches = matches.sort_values("TXN_TIMESTAMP", ascending=False)
        return matches.to_dict(orient="records")
    except Exception as exc:
        logger.warning("Failed to load transactions for customer %r: %s", cust_id, exc)
        return []
