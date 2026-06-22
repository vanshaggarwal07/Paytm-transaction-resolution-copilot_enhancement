"""Generate synthetic resolved case history for historical case retrieval."""

from __future__ import annotations

import logging
import random
import string
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

from src.issue_taxonomy import ISSUE_NAMES, IssueType

logger = logging.getLogger(__name__)

DEFAULT_OUTPUT = Path("data/resolved_cases.csv")
PAYMENT_MODES: tuple[str, ...] = ("UPI", "Card", "Wallet", "NetBanking")

# Exact counts for ~50 rows matching target percentages.
ISSUE_COUNTS: dict[str, int] = {
    IssueType.AMOUNT_DEBITED_MERCHANT_NOT_CREDITED.value: 15,
    IssueType.UPI_PENDING.value: 12,
    IssueType.REFUND_PENDING.value: 10,
    IssueType.FAILED_PAYMENT.value: 2,
    IssueType.REFUND_COMPLETED.value: 2,
    IssueType.SETTLEMENT_DELAY.value: 2,
    IssueType.SETTLEMENT_FAILURE.value: 1,
    IssueType.RECONCILIATION_MISMATCH.value: 1,
    IssueType.DUPLICATE_DEBIT.value: 2,
    IssueType.CHARGEBACK_DISPUTE.value: 2,
    IssueType.NORMAL_SUCCESS.value: 1,
}

COMPLAINT_TEMPLATES: dict[str, tuple[str, ...]] = {
    IssueType.AMOUNT_DEBITED_MERCHANT_NOT_CREDITED.value: (
        "I paid ₹{amount} through {mode} for order {order_ref} but the seller says payment never reached them. My bank already debited it {hours} hours ago!",
        "Money got deducted from my account — ₹{amount} via {mode} — but merchant dashboard still shows unpaid. This is ridiculous, it's been {days} days.",
        "Txn shows success on my side for ₹{amount} ({mode}) yet the shop didn't get the credit. Customer care at the store is asking me to pay again.",
    ),
    IssueType.UPI_PENDING.value: (
        "My {mode} payment of ₹{amount} has been showing 'processing' for {hours} hours now. Should I try again or wait?",
        "UPI txn for ₹{amount} is still pending in my bank app since yesterday. Merchant hasn't confirmed order {order_ref} either.",
        "Why is my ₹{amount} UPI payment still pending after {hours} hours? I'm scared I'll get charged twice if I retry.",
    ),
    IssueType.REFUND_PENDING.value: (
        "You guys initiated a refund for ₹{amount} on {mode} {days} days ago but I still don't see it in my bank account.",
        "Paytm shows refund initiated for ₹{amount} but my passbook has no credit entry after {hours} hours.",
        "Still waiting on ₹{amount} refund from {order_ref}. App says initiated, bank says no incoming credit on {mode}.",
    ),
    IssueType.REFUND_COMPLETED.value: (
        "Your app says refund completed for ₹{amount} on {mode} but my bank statement still doesn't show any credit after {days} days.",
        "Status shows refund completed for ₹{amount} yet my {mode} balance is unchanged. What reference number should I give my bank?",
    ),
    IssueType.FAILED_PAYMENT.value: (
        "Payment failed for ₹{amount} on {mode} but I got a debit SMS anyway for order {order_ref}. Please check.",
        "Failed payment on ₹{amount} ({mode}) for {order_ref} but amount looks blocked in my UPI app. Will it come back?",
    ),
    IssueType.SETTLEMENT_DELAY.value: (
        "I'm a merchant — successful {mode} payments of ₹{amount} from {days} days ago still show settlement pending in my dashboard.",
        "Merchant here: multiple UPI txns totaling around ₹{amount} are credited to customers but settlement to my bank is delayed {days} days.",
    ),
    IssueType.SETTLEMENT_FAILURE.value: (
        "Merchant settlement failed for ₹{amount} — your portal shows FAILED on the batch linked to order {order_ref}.",
        "Settlement status FAILED for yesterday's ₹{amount} payout. IFSC is correct — what reject code did the bank send?",
    ),
    IssueType.RECONCILIATION_MISMATCH.value: (
        "Our daily reconciliation has a ₹{amount} variance on {order_ref} date. Ledger says success but settlement file missing that txn.",
        "Settlement file total is ₹{amount} short vs internal ledger for {mode} batch. Which TXN_IDs are out of sync?",
    ),
    IssueType.DUPLICATE_DEBIT.value: (
        "I was charged twice for the same order {order_ref} — two debits of ₹{amount} on {mode} within {hours} minutes!",
        "Please reverse the extra ₹{amount} charge — I accidentally paid twice when the first {mode} attempt hung for {hours} hours.",
    ),
    IssueType.CHARGEBACK_DISPUTE.value: (
        "My bank raised a dispute on ₹{amount} {mode} charge for order {order_ref} — merchant says they'll fight the chargeback.",
        "Visa chargeback opened on ₹{amount} payment. Merchant account shows reversal debit — what's the dispute case ID?",
    ),
    IssueType.NORMAL_SUCCESS.value: (
        "Everything looks fine: ₹{amount} debited on {mode}, order delivered {days} days ago. Store confirmed payment received. No complaint really.",
        "I panicked earlier but ₹{amount} {mode} payment went through fine for {order_ref} — bank and app both show success now.",
    ),
}

RESOLUTION_TEMPLATES: dict[str, tuple[str, ...]] = {
    IssueType.AMOUNT_DEBITED_MERCHANT_NOT_CREDITED.value: (
        "Agent verified NPCI switch logs showed SUCCESS while merchant PG settlement was still pending. "
        "Raised manual credit to acquirer for ₹{amount} {mode} txn; merchant nodal account was credited after T+1 bank reconciliation. "
        "Customer confirmed the shop received payment on follow-up call.",
        "Support traced the debit to a late merchant settlement posting. "
        "Issued a manual credit instruction to the payment aggregator and reconciled the ₹{amount} {mode} entry within the 24-hour NPCI dispute window. "
        "Merchant dashboard updated to paid and the ticket was closed.",
    ),
    IssueType.UPI_PENDING.value: (
        "Agent checked UPI switch status and found the txn stuck in PENDING beyond the 48-hour threshold. "
        "Initiated NPCI auto-reversal; ₹{amount} was returned to the customer's {mode} account within one business day of reversal confirmation.",
        "Support escalated to switch ops after {hours} hours in pending state. "
        "NPCI reversal was triggered and the customer's {mode} passbook showed the ₹{amount} credit within the standard T+1 reversal timeline.",
    ),
    IssueType.REFUND_PENDING.value: (
        "Refund ARN had not propagated to the issuer for {days} days. "
        "L1 re-triggered the refund API with the correct beneficiary VPA; the bank posted ₹{amount} on the T+3 NPCI credit window.",
        "Agent confirmed refund was stuck at INITIATED with no bank posting. "
        "Reprocessed the ₹{amount} {mode} refund with updated RRN; customer passbook reflected the credit after issuer reconciliation.",
    ),
    IssueType.REFUND_COMPLETED.value: (
        "Customer could not locate the refund in passbook despite COMPLETED status. "
        "Agent shared NPCI RRN and bank confirmed delayed posting; ₹{amount} {mode} credit appeared after the next reconciliation cycle.",
        "Support verified refund completion in core ledger and provided ARN to the customer's bank. "
        "Issuer matched the ₹{amount} entry on T+2 and the case was closed after passbook confirmation.",
    ),
    IssueType.FAILED_PAYMENT.value: (
        "Txn failed at switch but a transient debit hold appeared on the customer's {mode} account. "
        "Agent confirmed no merchant credit and the ₹{amount} hold auto-released within the bank's 24-hour reconciliation window.",
        "Support validated FAILED status in NPCI logs with no settlement leg. "
        "Customer was advised the ₹{amount} {mode} block would reverse automatically; funds were visible again within one business day.",
    ),
    IssueType.SETTLEMENT_DELAY.value: (
        "Merchant settlement batch for ₹{amount} {mode} sales was pending beyond T+1 due to a bank holiday. "
        "Settlement ops released the batch manually and the nodal transfer completed on the next working day.",
        "Agent confirmed MERCHANT_CREDITED=YES with SETTLEMENT_STATUS=PENDING for {days} days. "
        "L2 Settlement Ops fast-tracked the ₹{amount} payout after validating acquirer file inclusion.",
    ),
    IssueType.SETTLEMENT_FAILURE.value: (
        "Settlement FAILED due to an invalid beneficiary IFSC on the merchant profile. "
        "Merchant updated bank details and settlement ops reprocessed the ₹{amount} {mode} batch successfully on retry.",
    ),
    IssueType.RECONCILIATION_MISMATCH.value: (
        "Finance flagged a ₹{amount} variance between CRM ledger and acquirer settlement extract. "
        "Recon team identified a missing NPCI line item and backfilled the txn into the nightly {mode} file.",
    ),
    IssueType.DUPLICATE_DEBIT.value: (
        "Two SUCCESS debits were posted for order {order_ref} within {hours} minutes on {mode}. "
        "Agent initiated auto-reversal on the duplicate leg and ₹{amount} was credited back within NPCI T+1 timeline.",
    ),
    IssueType.CHARGEBACK_DISPUTE.value: (
        "Issuer chargeback was received on the ₹{amount} {mode} txn. "
        "Case was routed to the Chargeback Team with delivery proof; representment was filed before the 7-day SLA.",
    ),
    IssueType.NORMAL_SUCCESS.value: (
        "Agent verified SUCCESS status, merchant credit, and settled settlement for the ₹{amount} {mode} payment. "
        "No corrective action was required; customer was advised the transaction had already completed normally.",
    ),
}

OUTCOME_BY_ISSUE: dict[str, tuple[str, ...]] = {
    IssueType.AMOUNT_DEBITED_MERCHANT_NOT_CREDITED.value: (
        "Resolved - Manual Credit",
        "Resolved - Auto Reversal",
    ),
    IssueType.UPI_PENDING.value: (
        "Resolved - Auto Reversal",
    ),
    IssueType.REFUND_PENDING.value: (
        "Resolved - Refund Processed",
        "Escalated - L2 Refund Team",
    ),
    IssueType.REFUND_COMPLETED.value: (
        "Resolved - Refund Processed",
    ),
    IssueType.FAILED_PAYMENT.value: (
        "Resolved - Auto Reversal",
    ),
    IssueType.SETTLEMENT_DELAY.value: (
        "Resolved - Awaited Settlement",
        "Escalated - L2 Refund Team",
    ),
    IssueType.SETTLEMENT_FAILURE.value: (
        "Resolved - Manual Credit",
    ),
    IssueType.RECONCILIATION_MISMATCH.value: (
        "Resolved - Manual Credit",
    ),
    IssueType.DUPLICATE_DEBIT.value: (
        "Resolved - Auto Reversal",
        "Resolved - Refund Processed",
    ),
    IssueType.CHARGEBACK_DISPUTE.value: (
        "Escalated - Chargeback Team",
    ),
    IssueType.NORMAL_SUCCESS.value: (
        "Resolved - Awaited Settlement",
    ),
}


def _random_amount() -> str:
    """Format a random amount string for complaint/resolution text."""
    value = round(random.uniform(99, 24999), 0)
    return f"{int(value):,}"


def _random_txn_amount() -> float:
    """Sample a transaction amount consistent with transactions.csv."""
    return round(random.uniform(50, 25000), 2)


def _random_age_hours() -> int:
    """Sample case age in hours consistent with transactions.csv."""
    return random.randint(1, 240)


def _random_hours() -> int:
    """Sample a plausible hours value for template substitution."""
    return random.randint(2, 72)


def _random_days() -> int:
    """Sample a plausible days value for template substitution."""
    return random.randint(1, 14)


def _random_order_ref() -> str:
    """Generate a casual order reference fragment."""
    suffix = "".join(random.choices(string.digits, k=4))
    return f"ORD{suffix}"


def _fill_template(template: str, *, mode: str, amount: str) -> str:
    """Substitute randomized details into a text template."""
    return template.format(
        amount=amount,
        mode=mode,
        hours=_random_hours(),
        days=_random_days(),
        order_ref=_random_order_ref(),
    )


def _build_issue_schedule() -> list[str]:
    """Return a shuffled list of issue labels matching ISSUE_COUNTS."""
    schedule: list[str] = []
    for issue, count in ISSUE_COUNTS.items():
        schedule.extend([issue] * count)
    random.shuffle(schedule)
    return schedule


def generate_case_history(count: int | None = None) -> pd.DataFrame:
    """Build synthetic resolved case records."""
    schedule = _build_issue_schedule()
    if count is not None:
        schedule = schedule[:count]

    now = datetime.now()
    records: list[dict[str, object]] = []

    for index, issue in enumerate(schedule, start=1):
        mode = random.choice(PAYMENT_MODES)
        amount_text = _random_amount()
        complaint = _fill_template(
            random.choice(COMPLAINT_TEMPLATES[issue]),
            mode=mode,
            amount=amount_text,
        )
        resolution = _fill_template(
            random.choice(RESOLUTION_TEMPLATES[issue]),
            mode=mode,
            amount=amount_text,
        )
        age_hours = _random_age_hours()
        resolution_timestamp = (
            now - timedelta(hours=max(1, age_hours - random.randint(1, 12)))
        ).isoformat(timespec="seconds")

        records.append(
            {
                "CASE_ID": f"CASE{index:06d}",
                "ISSUE": issue,
                "COMPLAINT": complaint,
                "RESOLUTION_SUMMARY": resolution,
                "OUTCOME": random.choice(OUTCOME_BY_ISSUE[issue]),
                "AGE_HOURS": age_hours,
                "PAYMENT_MODE": mode,
                "TXN_AMOUNT": _random_txn_amount(),
                "RESOLUTION_TIMESTAMP": resolution_timestamp,
                "RATING": random.choices(
                    ["helpful", "not_helpful"],
                    weights=[80, 20],
                    k=1,
                )[0],
            }
        )

    return pd.DataFrame(records)


def validate_issue_names(dataframe: pd.DataFrame) -> None:
    """Raise if any generated issue is outside the canonical taxonomy."""
    invalid = sorted(set(dataframe["ISSUE"]) - set(ISSUE_NAMES))
    if invalid:
        raise ValueError(f"Generated issues not in taxonomy: {invalid}")


def write_case_history_csv(
    output_path: Path = DEFAULT_OUTPUT,
    count: int | None = None,
    seed: int = 42,
) -> Path:
    """Generate resolved cases and persist them to CSV."""
    random.seed(seed)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    dataframe = generate_case_history(count=count)
    validate_issue_names(dataframe)
    dataframe.to_csv(output_path, index=False)
    logger.info("Wrote %s resolved case records to %s", len(dataframe), output_path)
    return output_path


def main() -> None:
    """CLI entry point for generating resolved case history."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    dataframe = generate_case_history()
    validate_issue_names(dataframe)
    write_case_history_csv()
    print("\n--- ISSUE value_counts ---")
    print(dataframe["ISSUE"].value_counts().to_string())
    print("\n--- 10 random rows ---")
    print(dataframe.sample(n=min(10, len(dataframe)), random_state=42).to_string(index=False))


if __name__ == "__main__":
    main()
