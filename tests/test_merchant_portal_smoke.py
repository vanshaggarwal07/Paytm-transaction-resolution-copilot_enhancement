"""Smoke tests for merchant portal data integrity and analytics contracts."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.core.merchant_analytics import (
    authenticate_merchant,
    get_issue_breakdown,
    get_merchant_alerts,
    get_merchant_summary,
)
from src.issue_taxonomy import ISSUE_NAMES

MERCHANTS_PATH = Path("data/merchants.csv")
TRANSACTIONS_PATH = Path("data/transactions.csv")


def test_merchants_csv_exists_with_minimum_rows() -> None:
    """Merchants master data should exist with at least five records."""
    assert MERCHANTS_PATH.exists()
    merchants = pd.read_csv(MERCHANTS_PATH, keep_default_na=False)
    assert len(merchants) >= 5


def test_every_merchant_mid_exists_in_transactions() -> None:
    """Every merchant MID must have at least one transaction."""
    merchants = pd.read_csv(MERCHANTS_PATH, keep_default_na=False)
    transactions = pd.read_csv(TRANSACTIONS_PATH, keep_default_na=False)
    merchant_mids = set(merchants["MID"])
    transaction_mids = set(transactions["MID"])
    assert merchant_mids.issubset(transaction_mids)


def test_authenticate_merchant_rejects_bad_credentials() -> None:
    """Invalid credentials should not authenticate."""
    merchants = pd.read_csv(MERCHANTS_PATH, keep_default_na=False)
    merchant = merchants.iloc[0]
    assert authenticate_merchant(merchant["USERNAME"], "wrong-password") is None


def test_get_merchant_summary_totals_for_all_merchants() -> None:
    """Summary totals should reconcile for every merchant MID."""
    merchants = pd.read_csv(MERCHANTS_PATH, keep_default_na=False)

    for _, row in merchants.iterrows():
        summary = get_merchant_summary(row["MID"])
        assert summary["total"] == summary["successful"] + summary["failed"] + summary["pending"]


def test_get_merchant_alerts_never_empty() -> None:
    """Every merchant should receive at least the operational info alert."""
    merchants = pd.read_csv(MERCHANTS_PATH, keep_default_na=False)

    for _, row in merchants.iterrows():
        alerts = get_merchant_alerts(row["MID"])
        assert alerts
        assert any(alert["severity"] in {"critical", "warning", "info"} for alert in alerts)


def test_get_issue_breakdown_includes_all_taxonomy_keys() -> None:
    """Issue breakdown should zero-fill every taxonomy issue name."""
    merchants = pd.read_csv(MERCHANTS_PATH, keep_default_na=False)
    mid = str(merchants.iloc[0]["MID"])
    breakdown = get_issue_breakdown(mid)
    assert set(breakdown.keys()) == set(ISSUE_NAMES)
    assert all(isinstance(value, int) for value in breakdown.values())
