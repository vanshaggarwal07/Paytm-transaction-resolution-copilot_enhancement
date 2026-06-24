"""Generate synthetic merchant records aligned with transaction MIDs."""

from __future__ import annotations

import logging
import random
import re
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
from faker import Faker

logger = logging.getLogger(__name__)

DEFAULT_TRANSACTIONS_PATH = Path("data/transactions.csv")
DEFAULT_OUTPUT = Path("data/merchants.csv")

CITIES: tuple[str, ...] = (
    "Mumbai",
    "Delhi",
    "Bengaluru",
    "Hyderabad",
    "Chennai",
    "Pune",
    "Kolkata",
    "Ahmedabad",
)

EMAIL_DOMAINS: tuple[str, ...] = (
    "gmail.in",
    "paytm.in",
    "business.in",
    "merchant.in",
    "shop.in",
)

BUSINESS_TYPES: tuple[str, ...] = (
    "Electronics",
    "Grocery",
    "Fashion",
    "Food & Beverage",
    "Travel",
    "Healthcare",
    "Education",
)

# Weighted toward Electronics, Grocery, and Fashion.
BUSINESS_TYPE_WEIGHTS: tuple[int, ...] = (30, 28, 22, 8, 6, 4, 2)

BUSINESS_SUFFIXES: dict[str, tuple[str, ...]] = {
    "Electronics": ("Electronics", "Mobile Store", "TechZone India", "Appliances"),
    "Grocery": ("Grocery Store", "Kirana Store", "Supermart", "Provision Store"),
    "Fashion": ("Fashion Hub", "Garments", "Boutique", "Textiles"),
    "Food & Beverage": ("Restaurant", "Cafe", "Sweets", "Food Court"),
    "Travel": ("Travels", "Tours", "Holidays", "Car Rentals"),
    "Healthcare": ("Pharmacy", "Clinic", "Medical Store", "Diagnostics"),
    "Education": ("Academy", "Coaching", "Books", "Learning Centre"),
}


def _load_unique_mids(transactions_path: Path = DEFAULT_TRANSACTIONS_PATH) -> list[str]:
    """Collect unique MID values from the transactions CSV."""
    transactions = pd.read_csv(transactions_path, usecols=["MID"])
    return sorted(transactions["MID"].drop_duplicates().tolist())


def _build_merchant_name(fake: Faker, business_type: str) -> str:
    """Build a realistic Indian merchant name from surname templates."""
    surname = fake.last_name()
    suffix = random.choice(BUSINESS_SUFFIXES[business_type])
    template = random.choice(
        (
            "{surname} {suffix}",
            "{surname} & Sons {suffix}",
            "{surname} Family {suffix}",
        )
    )
    return template.format(surname=surname, suffix=suffix)


def _clean_for_email(merchant_name: str) -> str:
    """Convert merchant name to an email-safe local part."""
    local_part = merchant_name.lower()
    local_part = re.sub(r"[^a-z0-9]+", "", local_part)
    return local_part or "merchant"


def _build_username(merchant_name: str, mid: str) -> str:
    """Username = first word lowercase + last 3 digits of MID."""
    first_word = merchant_name.split()[0].lower()
    mid_digits = re.sub(r"\D", "", mid)[-3:]
    return f"{first_word}{mid_digits}"


def _build_password() -> str:
    """Prototype-only plain-text password — never use in production."""
    return f"Merch@{random.randint(1000, 9999)}"


def _random_onboarded_since() -> str:
    """Random onboarding date within the last 3 years."""
    days_ago = random.randint(0, 3 * 365)
    onboarded = datetime.now() - timedelta(days=days_ago)
    return onboarded.date().isoformat()


def generate_merchants(
    transactions_path: Path = DEFAULT_TRANSACTIONS_PATH,
) -> pd.DataFrame:
    """Build one merchant row per unique MID found in transactions.csv."""
    fake = Faker("en_IN")
    mids = _load_unique_mids(transactions_path)
    records: list[dict[str, str]] = []

    for mid in mids:
        business_type = random.choices(BUSINESS_TYPES, weights=BUSINESS_TYPE_WEIGHTS, k=1)[0]
        merchant_name = _build_merchant_name(fake, business_type)
        email = f"{_clean_for_email(merchant_name)}@{random.choice(EMAIL_DOMAINS)}"

        records.append(
            {
                "MID": mid,
                "MERCHANT_NAME": merchant_name,
                "BUSINESS_TYPE": business_type,
                "EMAIL": email,
                "USERNAME": _build_username(merchant_name, mid),
                # Prototype-only plain-text password — never use in production.
                "PASSWORD": _build_password(),
                "CITY": random.choice(CITIES),
                "ONBOARDED_SINCE": _random_onboarded_since(),
            }
        )

    return pd.DataFrame(records)


def write_merchants_csv(
    output_path: Path = DEFAULT_OUTPUT,
    transactions_path: Path = DEFAULT_TRANSACTIONS_PATH,
) -> Path:
    """Generate merchants and persist them to a CSV file."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    dataframe = generate_merchants(transactions_path=transactions_path)
    dataframe.to_csv(output_path, index=False)
    logger.info("Wrote %s merchant records to %s", len(dataframe), output_path)
    return output_path


def main() -> None:
    """CLI entry point for generating the merchants CSV."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    write_merchants_csv()


if __name__ == "__main__":
    main()
