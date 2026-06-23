"""Deterministic rule engine for identifying transaction issues."""

from __future__ import annotations

from typing import Any

from src.issue_taxonomy import IssueType


def identify_issue(txn: dict[str, Any]) -> str:
    """Return the first matching issue label for a transaction dictionary."""
    if txn.get("BANK_STATUS") == "SUCCESS" and txn.get("MERCHANT_CREDITED") == "NO":
        return IssueType.AMOUNT_DEBITED_MERCHANT_NOT_CREDITED.value

    if txn.get("REFUND_STATUS") == "INITIATED":
        return IssueType.REFUND_PENDING.value

    if txn.get("REFUND_STATUS") == "COMPLETED":
        return IssueType.REFUND_COMPLETED.value

    if txn.get("SETTLEMENT_STATUS") == "PENDING":
        return IssueType.SETTLEMENT_DELAY.value

    if txn.get("SETTLEMENT_STATUS") == "FAILED":
        return IssueType.SETTLEMENT_FAILURE.value

    if txn.get("TXN_STATUS") == "Pending":
        return IssueType.UPI_PENDING.value

    if txn.get("TXN_STATUS") == "Failed":
        return IssueType.FAILED_PAYMENT.value

    return IssueType.NORMAL_SUCCESS.value
