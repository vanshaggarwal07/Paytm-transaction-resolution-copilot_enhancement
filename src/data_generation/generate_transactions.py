"""Generate synthetic transaction records with causally consistent fields."""

from __future__ import annotations

import logging
import random
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)

PAYMENT_MODES: tuple[str, ...] = ("UPI", "Card", "Wallet", "NetBanking")
DEFAULT_OUTPUT = Path("data/transactions.csv")


def _pick_txn_status() -> str:
    """Sample a transaction status using the target Success/Failed/Pending mix."""
    return random.choices(
        ["Success", "Failed", "Pending"],
        weights=[70, 15, 15],
        k=1,
    )[0]


def _derive_bank_and_merchant(txn_status: str) -> tuple[str, str]:
    """Derive bank and merchant credit fields from transaction status."""
    if txn_status == "Success":
        merchant_credited = random.choices(["YES", "NO"], weights=[85, 15], k=1)[0]
        return "SUCCESS", merchant_credited
    if txn_status == "Failed":
        return "FAILED", "NO"
    return "PENDING", "NO"


def _derive_refund_status(txn_status: str, merchant_credited: str) -> str:
    """Set refund status only for successful debits that were not merchant-credited."""
    if txn_status == "Success" and merchant_credited == "NO":
        return random.choices(
            ["INITIATED", "COMPLETED", "NA"],
            weights=[1, 1, 1],
            k=1,
        )[0]
    return "NA"


def _derive_settlement_status(merchant_credited: str) -> str:
    """Set settlement status only when the merchant was credited."""
    if merchant_credited == "YES":
        return random.choices(
            ["SETTLED", "PENDING", "FAILED"],
            weights=[80, 15, 5],
            k=1,
        )[0]
    return "NA"


def _random_amount() -> float:
    """Sample a transaction amount between 50 and 25000 with two decimals."""
    return round(random.uniform(50, 25000), 2)


def generate_transactions(count: int = 150) -> pd.DataFrame:
    """Build a dataframe of synthetic transactions with consistent field logic."""
    now = datetime.now()
    records: list[dict[str, object]] = []

    for index in range(1, count + 1):
        txn_status = _pick_txn_status()
        bank_status, merchant_credited = _derive_bank_and_merchant(txn_status)
        age_hours = random.randint(1, 240)
        txn_timestamp = (now - timedelta(hours=age_hours)).isoformat(timespec="seconds")

        records.append(
            {
                "TXN_ID": f"TXN{index:06d}",
                "ORDER_ID": f"ORD{index:06d}",
                "CUST_ID": f"CUST{index:06d}",
                "MID": f"MID{index:06d}",
                "PAYMENT_MODE": random.choice(PAYMENT_MODES),
                "TXN_AMOUNT": _random_amount(),
                "TXN_STATUS": txn_status,
                "BANK_STATUS": bank_status,
                "MERCHANT_CREDITED": merchant_credited,
                "REFUND_STATUS": _derive_refund_status(txn_status, merchant_credited),
                "SETTLEMENT_STATUS": _derive_settlement_status(merchant_credited),
                "AGE_HOURS": age_hours,
                "TXN_TIMESTAMP": txn_timestamp,
            }
        )

    return pd.DataFrame(records)


def write_transactions_csv(
    output_path: Path = DEFAULT_OUTPUT,
    count: int = 150,
) -> Path:
    """Generate transactions and persist them to a CSV file."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    dataframe = generate_transactions(count=count)
    dataframe.to_csv(output_path, index=False)
    logger.info("Wrote %s transaction records to %s", len(dataframe), output_path)
    return output_path


def main() -> None:
    """CLI entry point for generating the transactions CSV."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    write_transactions_csv()


if __name__ == "__main__":
    main()
