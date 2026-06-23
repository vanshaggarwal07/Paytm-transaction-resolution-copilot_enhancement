"""Tests for issue taxonomy helpers."""

import pytest

from src.issue_taxonomy import IssueType, slugify_issue


@pytest.mark.parametrize(
    ("issue_name", "expected_slug"),
    [
        (
            IssueType.AMOUNT_DEBITED_MERCHANT_NOT_CREDITED.value,
            "amount_debited_but_merchant_not_credited",
        ),
        (IssueType.UPI_PENDING.value, "upi_pending"),
        (IssueType.CHARGEBACK_DISPUTE.value, "chargeback_dispute"),
    ],
)
def test_slugify_issue(issue_name: str, expected_slug: str) -> None:
    """slugify_issue produces lowercase underscore slugs from display names."""
    assert slugify_issue(issue_name) == expected_slug
