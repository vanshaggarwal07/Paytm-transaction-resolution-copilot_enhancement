"""Generate synthetic customer records aligned with existing transaction CUST_IDs."""

from __future__ import annotations

import logging
import random
import re
import string
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
from faker import Faker

logger = logging.getLogger(__name__)

DEFAULT_TRANSACTIONS_PATH = Path("data/transactions.csv")
DEFAULT_OUTPUT = Path("data/customers.csv")

# PROTOTYPE ONLY: passwords are stored in plain text for local demo auth.
# Never use this pattern in production — hash credentials and use a secrets manager.
fake = Faker("en_IN")


def _load_transaction_cust_ids(transactions_path: Path = DEFAULT_TRANSACTIONS_PATH) -> list[str]:
    """Return sorted unique CUST_ID values from the transactions CSV."""
    if not transactions_path.is_file():
        raise FileNotFoundError(f"Transactions file not found: {transactions_path}")

    transactions = pd.read_csv(transactions_path, keep_default_na=False)
    if "CUST_ID" not in transactions.columns:
        raise ValueError("Transactions CSV is missing the CUST_ID column")

    cust_ids = sorted(transactions["CUST_ID"].astype(str).unique().tolist())
    if not cust_ids:
        raise ValueError("No CUST_ID values found in transactions CSV")

    return cust_ids


def _email_local_part(name: str) -> str:
    """Build a lowercase email local-part from a full name."""
    normalized = re.sub(r"[^a-zA-Z\s]", "", name).strip().lower()
    parts = [part for part in normalized.split() if part]
    if not parts:
        return "customer"
    if len(parts) == 1:
        return parts[0]
    return f"{parts[0]}.{parts[-1]}"


def _build_email(name: str) -> str:
    """Return a gmail.com or yahoo.in address derived from the customer name."""
    domain = random.choice(["gmail.com", "yahoo.in"])
    return f"{_email_local_part(name)}@{domain}"


def _build_username(name: str, cust_id: str) -> str:
    """Return first-name lowercase plus the last three digits of CUST_ID."""
    first_name = name.split()[0].lower()
    cust_suffix = re.sub(r"\D", "", cust_id)[-3:]
    return f"{first_name}{cust_suffix}"


def _build_password() -> str:
    """Return a prototype-only plain-text password in Pay@#### format."""
    return f"Pay@{random.randint(1000, 9999)}"


def _random_registered_since() -> str:
    """Return a random registration timestamp within the last two years."""
    now = datetime.now()
    earliest = now - timedelta(days=730)
    offset_seconds = random.randint(0, int((now - earliest).total_seconds()))
    registered_at = earliest + timedelta(seconds=offset_seconds)
    return registered_at.isoformat(timespec="seconds")


def generate_customers(
    transactions_path: Path = DEFAULT_TRANSACTIONS_PATH,
) -> pd.DataFrame:
    """Build one customer row per unique CUST_ID present in transactions."""
    cust_ids = _load_transaction_cust_ids(transactions_path)
    records: list[dict[str, str]] = []

    for cust_id in cust_ids:
        name = fake.name()
        records.append(
            {
                "CUST_ID": cust_id,
                "NAME": name,
                "EMAIL": _build_email(name),
                "USERNAME": _build_username(name, cust_id),
                "PASSWORD": _build_password(),
                "REGISTERED_SINCE": _random_registered_since(),
            }
        )

    return pd.DataFrame(
        records,
        columns=[
            "CUST_ID",
            "NAME",
            "EMAIL",
            "USERNAME",
            "PASSWORD",
            "REGISTERED_SINCE",
        ],
    )


def validate_customers_against_transactions(
    customers: pd.DataFrame,
    transactions_path: Path = DEFAULT_TRANSACTIONS_PATH,
) -> None:
    """Ensure every generated CUST_ID exists in the transactions CSV."""
    transaction_cust_ids = set(_load_transaction_cust_ids(transactions_path))
    customer_cust_ids = set(customers["CUST_ID"].astype(str).tolist())
    missing = customer_cust_ids - transaction_cust_ids
    if missing:
        raise ValueError(
            f"customers.csv contains CUST_ID values not in transactions.csv: {sorted(missing)}"
        )


def write_customers_csv(
    output_path: Path = DEFAULT_OUTPUT,
    transactions_path: Path = DEFAULT_TRANSACTIONS_PATH,
) -> Path:
    """Generate customers and persist them to a CSV file."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    customers = generate_customers(transactions_path=transactions_path)
    validate_customers_against_transactions(customers, transactions_path=transactions_path)
    customers.to_csv(output_path, index=False)
    logger.info("Wrote %s customer records to %s", len(customers), output_path)
    return output_path


def main() -> None:
    """CLI entry point for generating the customers CSV."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    write_customers_csv()


if __name__ == "__main__":
    main()
