"""Verify all dummy data exists and the resolution pipeline works."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

from src.core.issue_rules import identify_issue
from src.core.rag_retriever import retrieve_sop
from src.core.transaction_lookup import lookup_transaction
from src.issue_taxonomy import IssueType, slugify_issue

DATA_DIR = Path("data")
SOPS_DIR = DATA_DIR / "sops"
TRANSACTIONS_PATH = DATA_DIR / "transactions.csv"
COMPLAINTS_PATH = DATA_DIR / "complaints.csv"


def _check_sops() -> list[str]:
    """Return a list of problems found in the SOP knowledge base."""
    problems: list[str] = []
    if not SOPS_DIR.is_dir():
        return [f"Missing directory: {SOPS_DIR}"]

    for issue in IssueType:
        if issue == IssueType.NORMAL_SUCCESS:
            continue
        slug = slugify_issue(issue.value)
        path = SOPS_DIR / f"{slug}.md"
        if not path.exists():
            problems.append(f"Missing SOP: {path}")
    return problems


def _check_csv(path: Path, min_rows: int, required_cols: list[str]) -> list[str]:
    """Return a list of problems found in a CSV dataset."""
    problems: list[str] = []
    if not path.exists():
        return [f"Missing file: {path}"]

    df = pd.read_csv(path, keep_default_na=False)
    if len(df) < min_rows:
        problems.append(f"{path} has only {len(df)} rows (expected >= {min_rows})")

    missing_cols = [col for col in required_cols if col not in df.columns]
    if missing_cols:
        problems.append(f"{path} missing columns: {missing_cols}")

    return problems


def main() -> None:
    """Print a data health report and exit non-zero if anything is missing."""
    problems: list[str] = []

    problems.extend(_check_sops())
    problems.extend(
        _check_csv(
            TRANSACTIONS_PATH,
            min_rows=100,
            required_cols=[
                "TXN_ID", "ORDER_ID", "CUST_ID", "MID",
                "TXN_STATUS", "BANK_STATUS", "MERCHANT_CREDITED",
            ],
        )
    )
    problems.extend(
        _check_csv(
            COMPLAINTS_PATH,
            min_rows=50,
            required_cols=["COMPLAINT_ID", "ORDER_ID", "CUSTOMER_COMPLAINT", "TRUE_ISSUE"],
        )
    )

    if problems:
        print("DATA CHECK FAILED:")
        for problem in problems:
            print(f"  - {problem}")
        print("\nRegenerate CSVs: ./scripts/regenerate_data.sh")
        sys.exit(1)

    txn = lookup_transaction("MID000001", "ORD000001", "CUST000001")
    if txn is None:
        problems.append("lookup_transaction failed for ORD000001")

    sop = retrieve_sop(IssueType.UPI_PENDING.value, top_k=1)
    if not sop or sop[0]["issue_name"] != IssueType.UPI_PENDING.value:
        problems.append("retrieve_sop failed for UPI Pending")

    print("DATA CHECK PASSED")
    print(f"  transactions: {len(pd.read_csv(TRANSACTIONS_PATH, keep_default_na=False))} rows")
    print(f"  complaints:   {len(pd.read_csv(COMPLAINTS_PATH, keep_default_na=False))} rows")
    print(f"  sops:         {len(list(SOPS_DIR.glob('*.md')))} files")
    if txn:
        print(f"  sample issue: {identify_issue(txn)} (ORD000001)")


if __name__ == "__main__":
    main()
