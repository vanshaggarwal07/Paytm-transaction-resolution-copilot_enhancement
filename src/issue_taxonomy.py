"""Single source of truth for Paytm transaction issue names."""

from enum import Enum
import re


class IssueType(str, Enum):
    """Canonical issue names used across rules, SOPs, and labels."""

    AMOUNT_DEBITED_MERCHANT_NOT_CREDITED = "Amount Debited but Merchant Not Credited"
    UPI_PENDING = "UPI Pending"
    REFUND_PENDING = "Refund Pending"
    REFUND_COMPLETED = "Refund Completed"
    FAILED_PAYMENT = "Failed Payment"
    SETTLEMENT_DELAY = "Settlement Delay"
    SETTLEMENT_FAILURE = "Settlement Failure"
    RECONCILIATION_MISMATCH = "Reconciliation Mismatch"
    DUPLICATE_DEBIT = "Duplicate Debit"
    CHARGEBACK_DISPUTE = "Chargeback / Dispute"
    NORMAL_SUCCESS = "Normal Success"


ISSUE_NAMES: tuple[str, ...] = tuple(issue.value for issue in IssueType)


def slugify_issue(issue_name: str) -> str:
    """Convert a display issue name to a lowercase underscore slug."""
    slug = issue_name.lower()
    slug = re.sub(r"[^a-z0-9]+", "_", slug)
    return slug.strip("_")
