"""Tests for the deterministic issue identification rules."""

from src.core.issue_rules import identify_issue
from src.core.transaction_lookup import lookup_transaction
from src.issue_taxonomy import IssueType


def test_identify_amount_debited_merchant_not_credited() -> None:
    """Rule 1: SUCCESS bank status with merchant not credited."""
    txn = {
        "BANK_STATUS": "SUCCESS",
        "MERCHANT_CREDITED": "NO",
        "REFUND_STATUS": "NA",
        "SETTLEMENT_STATUS": "NA",
        "TXN_STATUS": "Success",
    }
    assert identify_issue(txn) == IssueType.AMOUNT_DEBITED_MERCHANT_NOT_CREDITED.value


def test_identify_refund_pending() -> None:
    """Rule 2: refund initiated without triggering the debited-not-credited rule."""
    txn = {
        "BANK_STATUS": "SUCCESS",
        "MERCHANT_CREDITED": "YES",
        "REFUND_STATUS": "INITIATED",
        "SETTLEMENT_STATUS": "NA",
        "TXN_STATUS": "Success",
    }
    assert identify_issue(txn) == IssueType.REFUND_PENDING.value


def test_identify_refund_completed() -> None:
    """Rule 3: refund completed without triggering earlier rules."""
    txn = {
        "BANK_STATUS": "SUCCESS",
        "MERCHANT_CREDITED": "YES",
        "REFUND_STATUS": "COMPLETED",
        "SETTLEMENT_STATUS": "NA",
        "TXN_STATUS": "Success",
    }
    assert identify_issue(txn) == IssueType.REFUND_COMPLETED.value


def test_identify_settlement_delay() -> None:
    """Rule 4: settlement still pending."""
    txn = {
        "BANK_STATUS": "SUCCESS",
        "MERCHANT_CREDITED": "YES",
        "REFUND_STATUS": "NA",
        "SETTLEMENT_STATUS": "PENDING",
        "TXN_STATUS": "Success",
    }
    assert identify_issue(txn) == IssueType.SETTLEMENT_DELAY.value


def test_identify_settlement_failure() -> None:
    """Rule 5: settlement failed."""
    txn = {
        "BANK_STATUS": "SUCCESS",
        "MERCHANT_CREDITED": "YES",
        "REFUND_STATUS": "NA",
        "SETTLEMENT_STATUS": "FAILED",
        "TXN_STATUS": "Success",
    }
    assert identify_issue(txn) == IssueType.SETTLEMENT_FAILURE.value


def test_identify_upi_pending() -> None:
    """Rule 6: transaction status pending."""
    txn = {
        "BANK_STATUS": "PENDING",
        "MERCHANT_CREDITED": "NO",
        "REFUND_STATUS": "NA",
        "SETTLEMENT_STATUS": "NA",
        "TXN_STATUS": "Pending",
    }
    assert identify_issue(txn) == IssueType.UPI_PENDING.value


def test_identify_failed_payment() -> None:
    """Rule 7: transaction status failed."""
    txn = {
        "BANK_STATUS": "FAILED",
        "MERCHANT_CREDITED": "NO",
        "REFUND_STATUS": "NA",
        "SETTLEMENT_STATUS": "NA",
        "TXN_STATUS": "Failed",
    }
    assert identify_issue(txn) == IssueType.FAILED_PAYMENT.value


def test_identify_normal_success() -> None:
    """Rule 8: no earlier rule matches."""
    txn = {
        "BANK_STATUS": "SUCCESS",
        "MERCHANT_CREDITED": "YES",
        "REFUND_STATUS": "NA",
        "SETTLEMENT_STATUS": "SETTLED",
        "TXN_STATUS": "Success",
    }
    assert identify_issue(txn) == IssueType.NORMAL_SUCCESS.value


def test_identify_issue_integrates_with_transaction_lookup() -> None:
    """A real CSV row flows from lookup into identify_issue correctly."""
    txn = lookup_transaction("MID000010", "ORD000010", "CUST000010")

    assert txn is not None
    assert identify_issue(txn) == IssueType.AMOUNT_DEBITED_MERCHANT_NOT_CREDITED.value
