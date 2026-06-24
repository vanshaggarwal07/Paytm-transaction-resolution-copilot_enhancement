"""Merchant dashboard analytics over transactions and merchant master data."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import pandas as pd

from src.core.issue_rules import identify_issue
from src.issue_taxonomy import ISSUE_NAMES, IssueType

logger = logging.getLogger(__name__)

DEFAULT_TRANSACTIONS_PATH = Path("data/transactions.csv")
DEFAULT_MERCHANTS_PATH = Path("data/merchants.csv")

_TXN_DF: pd.DataFrame = pd.read_csv(DEFAULT_TRANSACTIONS_PATH, keep_default_na=False)
_MERCHANT_DF: pd.DataFrame = pd.read_csv(DEFAULT_MERCHANTS_PATH, keep_default_na=False)
_ENRICHED_CACHE: dict[str, pd.DataFrame] = {}

logger.info("Loaded %s transactions and %s merchants", len(_TXN_DF), len(_MERCHANT_DF))


def _row_to_dict(row: pd.Series) -> dict[str, Any]:
    """Convert a dataframe row to a plain dictionary."""
    return row.to_dict()


def _get_enriched_for_mid(mid: str) -> pd.DataFrame:
    """Return issue-enriched transactions for a merchant, using module cache."""
    if mid in _ENRICHED_CACHE:
        return _ENRICHED_CACHE[mid]

    merchant_txns = _TXN_DF[_TXN_DF["MID"] == mid].copy()
    merchant_txns["issue"] = merchant_txns.apply(
        lambda row: identify_issue(row.to_dict()),
        axis=1,
    )
    _ENRICHED_CACHE[mid] = merchant_txns
    return merchant_txns


def authenticate_merchant(username: str, password: str) -> dict[str, Any] | None:
    """Return the merchant row when credentials match, otherwise None."""
    matches = _MERCHANT_DF[
        (_MERCHANT_DF["USERNAME"] == username) & (_MERCHANT_DF["PASSWORD"] == password)
    ]
    if matches.empty:
        return None
    return _row_to_dict(matches.iloc[0])


def get_merchant_summary(mid: str) -> dict[str, int]:
    """Return aggregate transaction metrics for a merchant."""
    merchant_txns = _get_enriched_for_mid(mid)

    successful = int((merchant_txns["TXN_STATUS"] == "Success").sum())
    failed = int((merchant_txns["TXN_STATUS"] == "Failed").sum())
    pending = int((merchant_txns["TXN_STATUS"] == "Pending").sum())
    total = len(merchant_txns)

    settlement_issues = int(
        merchant_txns["SETTLEMENT_STATUS"].isin(["PENDING", "FAILED"]).sum()
    )
    chargebacks = int(
        (merchant_txns["issue"] == IssueType.CHARGEBACK_DISPUTE.value).sum()
    )
    merchant_not_credited = int(
        (
            merchant_txns["issue"]
            == IssueType.AMOUNT_DEBITED_MERCHANT_NOT_CREDITED.value
        ).sum()
    )
    flagged = int(
        (merchant_txns["issue"] != IssueType.NORMAL_SUCCESS.value).sum()
    )

    return {
        "total": total,
        "successful": successful,
        "failed": failed,
        "pending": pending,
        "settlement_issues": settlement_issues,
        "chargebacks": chargebacks,
        "merchant_not_credited": merchant_not_credited,
        "flagged": flagged,
    }


def get_merchant_transactions(
    mid: str,
    status_filter: str | None = None,
    issue_filter: str | None = None,
    flagged_only: bool = False,
) -> list[dict[str, Any]]:
    """Return filtered merchant transactions sorted by TXN_TIMESTAMP descending."""
    merchant_txns = _get_enriched_for_mid(mid)

    if status_filter is not None:
        merchant_txns = merchant_txns[merchant_txns["TXN_STATUS"] == status_filter]

    if issue_filter is not None:
        merchant_txns = merchant_txns[merchant_txns["issue"] == issue_filter]

    if flagged_only:
        merchant_txns = merchant_txns[
            merchant_txns["issue"] != IssueType.NORMAL_SUCCESS.value
        ]

    sorted_txns = merchant_txns.sort_values("TXN_TIMESTAMP", ascending=False)
    return [_row_to_dict(row) for _, row in sorted_txns.iterrows()]


def get_issue_breakdown(mid: str) -> dict[str, int]:
    """Return per-issue transaction counts with zero-filled taxonomy keys."""
    merchant_txns = _get_enriched_for_mid(mid)
    counts = merchant_txns["issue"].value_counts().to_dict()
    return {issue_name: int(counts.get(issue_name, 0)) for issue_name in ISSUE_NAMES}


def get_flagged_transactions(mid: str) -> list[dict[str, Any]]:
    """Return non-success issue transactions sorted by TXN_TIMESTAMP descending."""
    return get_merchant_transactions(mid=mid, flagged_only=True)


_ALERT_SEVERITY_ORDER: dict[str, int] = {
    "critical": 0,
    "warning": 1,
    "info": 2,
}


def get_merchant_alerts(mid: str) -> list[dict[str, Any]]:
    """Return portfolio alerts for a merchant, sorted by severity."""
    summary = get_merchant_summary(mid)
    merchant_txns = _get_enriched_for_mid(mid)

    total = summary["total"]
    failed = summary["failed"]
    chargebacks = summary["chargebacks"]
    merchant_not_credited = summary["merchant_not_credited"]
    settlement_issues = summary["settlement_issues"]

    aged_pending_count = int(
        (
            (merchant_txns["TXN_STATUS"] == "Pending")
            & (merchant_txns["AGE_HOURS"].astype(float) > 48)
        ).sum()
    )

    alerts: list[dict[str, Any]] = []

    if chargebacks > 3:
        alerts.append(
            {
                "severity": "critical",
                "category": "chargebacks",
                "title": "Chargeback Alert",
                "message": f"{chargebacks} chargebacks detected on your account.",
                "transaction_count": chargebacks,
                "recommended_action": (
                    "Review disputed transactions immediately and prepare "
                    "evidence packages."
                ),
            }
        )

    if total > 5 and (failed / total) > 0.20:
        alerts.append(
            {
                "severity": "critical",
                "category": "payment_failures",
                "title": "High Payment Failure Rate",
                "message": f"{failed / total:.0%} of your transactions are failing.",
                "transaction_count": failed,
                "recommended_action": (
                    "Contact your payment gateway or bank for technical review."
                ),
            }
        )

    if merchant_not_credited > 5:
        alerts.append(
            {
                "severity": "critical",
                "category": "settlement_credits",
                "title": "Settlement Credits Pending",
                "message": (
                    f"{merchant_not_credited} payments received by customer "
                    "not yet credited to your account."
                ),
                "transaction_count": merchant_not_credited,
                "recommended_action": (
                    "Escalate to settlements team with transaction list."
                ),
            }
        )

    if settlement_issues > 0:
        alerts.append(
            {
                "severity": "warning",
                "category": "settlement_delays",
                "title": "Settlement Delays Detected",
                "message": (
                    f"{settlement_issues} settlements are pending or failed."
                ),
                "transaction_count": settlement_issues,
                "recommended_action": (
                    "Monitor settlement dashboard. Escalate if unresolved > 48h."
                ),
            }
        )

    if aged_pending_count > 0:
        alerts.append(
            {
                "severity": "warning",
                "category": "stale_pending",
                "title": "Stale Pending Transactions",
                "message": (
                    f"{aged_pending_count} transactions have been pending "
                    "for over 48 hours."
                ),
                "transaction_count": aged_pending_count,
                "recommended_action": (
                    "These may require manual intervention or will auto-reverse."
                ),
            }
        )

    has_critical_or_warning = any(
        alert["severity"] in {"critical", "warning"} for alert in alerts
    )
    if not has_critical_or_warning:
        alerts.append(
            {
                "severity": "info",
                "category": "operational",
                "title": "All Systems Operational",
                "message": "No payment issues detected on your account.",
                "transaction_count": 0,
                "recommended_action": "",
            }
        )

    alerts.sort(key=lambda alert: _ALERT_SEVERITY_ORDER[alert["severity"]])
    return alerts
