"""Tests for transaction lookup."""

from src.core.transaction_lookup import lookup_transaction


def test_lookup_transaction_returns_matching_row() -> None:
    """A real MID/ORDER_ID/CUST_ID combination returns the expected transaction."""
    result = lookup_transaction("MID000001", "ORD000001", "CUST000001")

    assert result is not None
    assert result["ORDER_ID"] == "ORD000001"
    assert result["MID"] == "MID000001"
    assert result["CUST_ID"] == "CUST000001"


def test_lookup_transaction_returns_none_for_unknown_combination() -> None:
    """A made-up key combination returns None."""
    result = lookup_transaction("MID999999", "ORD999999", "CUST999999")

    assert result is None
