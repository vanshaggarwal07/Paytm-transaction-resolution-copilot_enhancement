"""Tests for merchant portfolio alerts."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.core.merchant_analytics import get_merchant_alerts

MERCHANTS_PATH = Path("data/merchants.csv")
REQUIRED_ALERT_KEYS = {
    "severity",
    "category",
    "title",
    "message",
    "transaction_count",
    "recommended_action",
}
ALLOWED_SEVERITIES = {"critical", "warning", "info"}


def _first_merchant_mid() -> str:
    """Return the first merchant MID from merchants.csv."""
    merchants = pd.read_csv(MERCHANTS_PATH, keep_default_na=False)
    return str(merchants.iloc[0]["MID"])


def test_get_merchant_alerts_returns_list() -> None:
    """Alerts for a real MID should return a non-empty list."""
    alerts = get_merchant_alerts(_first_merchant_mid())
    assert isinstance(alerts, list)
    assert alerts


def test_alert_dict_shape_and_severity_values() -> None:
    """Every alert should expose required keys and valid severity values."""
    alerts = get_merchant_alerts(_first_merchant_mid())

    for alert in alerts:
        assert set(alert.keys()) == REQUIRED_ALERT_KEYS
        assert alert["severity"] in ALLOWED_SEVERITIES
        assert isinstance(alert["category"], str)
        assert isinstance(alert["title"], str)
        assert isinstance(alert["message"], str)
        assert isinstance(alert["transaction_count"], int)
        assert isinstance(alert["recommended_action"], str)


def test_all_clear_merchant_returns_operational_info_alert() -> None:
    """Merchants without issues should still receive an info all-clear alert."""
    merchants = pd.read_csv(MERCHANTS_PATH, keep_default_na=False)
    from src.core.merchant_analytics import get_merchant_summary

    all_clear_mid = None
    for _, row in merchants.iterrows():
        summary = get_merchant_summary(row["MID"])
        if (
            summary["chargebacks"] == 0
            and summary["settlement_issues"] == 0
            and summary["merchant_not_credited"] == 0
            and summary["failed"] == 0
            and summary["pending"] == 0
        ):
            all_clear_mid = row["MID"]
            break

    assert all_clear_mid is not None, "Expected at least one all-clear merchant"
    alerts = get_merchant_alerts(all_clear_mid)
    assert alerts
    assert any(
        alert["severity"] == "info"
        and alert["title"] == "All Systems Operational"
        for alert in alerts
    )


def test_settlement_delay_merchant_returns_warning_alert() -> None:
    """A merchant with settlement issues should trigger a warning alert."""
    from src.core.merchant_analytics import get_merchant_summary

    merchants = pd.read_csv(MERCHANTS_PATH, keep_default_na=False)
    settlement_mid = None
    for _, row in merchants.iterrows():
        if get_merchant_summary(row["MID"])["settlement_issues"] > 0:
            settlement_mid = row["MID"]
            break

    assert settlement_mid is not None
    alerts = get_merchant_alerts(settlement_mid)
    assert any(
        alert["severity"] == "warning"
        and alert["title"] == "Settlement Delays Detected"
        for alert in alerts
    )
