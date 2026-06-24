"""Tests for merchant analytics and authentication."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.core.merchant_analytics import (
    authenticate_merchant,
    get_flagged_transactions,
    get_issue_breakdown,
    get_merchant_summary,
)
from src.issue_taxonomy import ISSUE_NAMES, IssueType

MERCHANTS_PATH = Path("data/merchants.csv")
TRANSACTIONS_PATH = Path("data/transactions.csv")


def _first_merchant() -> dict[str, str]:
    """Load the first merchant row for credential-based tests."""
    merchants = pd.read_csv(MERCHANTS_PATH, keep_default_na=False)
    return merchants.iloc[0].to_dict()


def _merchant_with_flagged_transactions() -> str:
    """Return a MID that has at least one non-normal-success transaction."""
    transactions = pd.read_csv(TRANSACTIONS_PATH, keep_default_na=False)
    for mid in transactions["MID"].drop_duplicates():
        if get_merchant_summary(mid)["flagged"] > 0:
            return mid
    raise AssertionError("Expected at least one merchant with flagged transactions")


def test_authenticate_merchant_valid_credentials() -> None:
    """Valid username/password should return a merchant dict with MID."""
    merchant = _first_merchant()
    result = authenticate_merchant(merchant["USERNAME"], merchant["PASSWORD"])
    assert result is not None
    assert result["MID"] == merchant["MID"]


def test_authenticate_merchant_invalid_credentials() -> None:
    """Invalid credentials should return None."""
    merchant = _first_merchant()
    assert authenticate_merchant(merchant["USERNAME"], "wrong-password") is None
    assert authenticate_merchant("invalid-user", merchant["PASSWORD"]) is None


def test_get_merchant_summary_shape_and_totals() -> None:
    """Summary should expose all metrics with consistent totals."""
    merchant = _first_merchant()
    summary = get_merchant_summary(merchant["MID"])

    expected_keys = {
        "total",
        "successful",
        "failed",
        "pending",
        "settlement_issues",
        "chargebacks",
        "merchant_not_credited",
        "flagged",
    }
    assert set(summary.keys()) == expected_keys
    assert all(isinstance(value, int) for value in summary.values())
    assert summary["total"] == summary["successful"] + summary["failed"] + summary["pending"]


def test_get_issue_breakdown_uses_taxonomy() -> None:
    """Breakdown should include every taxonomy issue with integer counts."""
    merchant = _first_merchant()
    breakdown = get_issue_breakdown(merchant["MID"])

    assert set(breakdown.keys()) == set(ISSUE_NAMES)
    assert all(isinstance(value, int) for value in breakdown.values())


def test_get_flagged_transactions_exclude_normal_success() -> None:
    """Flagged transactions should always carry a non-normal issue label."""
    mid = _merchant_with_flagged_transactions()
    flagged = get_flagged_transactions(mid)

    assert flagged
    for txn in flagged:
        assert "issue" in txn
        assert txn["issue"] != IssueType.NORMAL_SUCCESS.value
