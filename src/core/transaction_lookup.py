"""Look up synthetic transactions by merchant, order, and customer identifiers."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)

DEFAULT_TRANSACTIONS_PATH = Path("data/transactions.csv")

# Cached transactions dataframe — loaded once on first lookup.
_TRANSACTIONS_CACHE: pd.DataFrame | None = None


def _load_transactions(path: Path = DEFAULT_TRANSACTIONS_PATH) -> pd.DataFrame:
    """Load transactions CSV, using the module-level cache after the first read."""
    global _TRANSACTIONS_CACHE

    if _TRANSACTIONS_CACHE is None:
        try:
            _TRANSACTIONS_CACHE = pd.read_csv(path, keep_default_na=False)
            logger.info("Loaded %s transaction records from %s", len(_TRANSACTIONS_CACHE), path)
        except FileNotFoundError as exc:
            logger.error("Transactions file not found: %s", path)
            raise FileNotFoundError(f"Transactions file not found: {path}") from exc
        except pd.errors.EmptyDataError as exc:
            logger.error("Transactions file is empty: %s", path)
            raise ValueError(f"Transactions file is empty: {path}") from exc

    return _TRANSACTIONS_CACHE


def lookup_transaction(mid: str, order_id: str, cust_id: str) -> dict[str, Any] | None:
    """Return the transaction row matching all three keys, or None if not found."""
    try:
        transactions = _load_transactions()
    except (FileNotFoundError, ValueError):
        raise

    matches = transactions[
        (transactions["MID"] == mid)
        & (transactions["ORDER_ID"] == order_id)
        & (transactions["CUST_ID"] == cust_id)
    ]

    if matches.empty:
        return None

    return matches.iloc[0].to_dict()
