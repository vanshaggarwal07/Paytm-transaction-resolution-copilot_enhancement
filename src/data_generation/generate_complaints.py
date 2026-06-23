"""Generate synthetic customer complaints for evaluation with labeled TRUE_ISSUE."""

from __future__ import annotations

import logging
import random
import string
from pathlib import Path

import pandas as pd

from src.issue_taxonomy import IssueType

logger = logging.getLogger(__name__)

DEFAULT_OUTPUT = Path("data/complaints.csv")
PAYMENT_MODES: tuple[str, ...] = ("UPI", "Card", "Wallet", "NetBanking")

# Weighted toward the most common real-world payment complaints.
ISSUE_WEIGHTS: dict[str, int] = {
    IssueType.AMOUNT_DEBITED_MERCHANT_NOT_CREDITED.value: 22,
    IssueType.UPI_PENDING.value: 16,
    IssueType.REFUND_PENDING.value: 14,
    IssueType.FAILED_PAYMENT.value: 9,
    IssueType.DUPLICATE_DEBIT.value: 8,
    IssueType.REFUND_COMPLETED.value: 8,
    IssueType.CHARGEBACK_DISPUTE.value: 7,
    IssueType.SETTLEMENT_DELAY.value: 6,
    IssueType.SETTLEMENT_FAILURE.value: 4,
    IssueType.RECONCILIATION_MISMATCH.value: 3,
    IssueType.NORMAL_SUCCESS.value: 3,
}

COMPLAINT_TEMPLATES: dict[str, tuple[str, ...]] = {
    IssueType.AMOUNT_DEBITED_MERCHANT_NOT_CREDITED.value: (
        "I paid ₹{amount} through {mode} for order {order_ref} but the seller says payment never reached them. My bank already debited it {hours} hours ago!",
        "Money got deducted from my account — ₹{amount} via {mode} — but merchant dashboard still shows unpaid. This is ridiculous, it's been {days} days.",
        "Txn shows success on my side for ₹{amount} ({mode}) yet the shop didn't get the credit. Customer care at the store is asking me to pay again.",
        "Please help! ₹{amount} left my {mode} account for {order_ref} and the merchant insists they haven't received anything since {hours} hours.",
        "I have the debit SMS for ₹{amount} on {mode} but order {order_ref} is stuck because seller says amount not credited to them.",
    ),
    IssueType.UPI_PENDING.value: (
        "My {mode} payment of ₹{amount} has been showing 'processing' for {hours} hours now. Should I try again or wait?",
        "UPI txn for ₹{amount} is still pending in my bank app since yesterday. Merchant hasn't confirmed order {order_ref} either.",
        "Paid ₹{amount} via UPI and it's been pending for almost {days} days — no debit, no success, nothing final!",
        "Stuck on pending for ₹{amount} ({mode}). I didn't get failure message but merchant says they can't see the payment yet.",
        "Why is my ₹{amount} UPI payment still pending after {hours} hours? I'm scared I'll get charged twice if I retry.",
    ),
    IssueType.REFUND_PENDING.value: (
        "You guys initiated a refund for ₹{amount} on {mode} {days} days ago but I still don't see it in my bank account.",
        "Refund status says initiated for order {order_ref} (₹{amount}) but nothing has come back to my {mode} yet. Getting impatient.",
        "I was told refund of ₹{amount} is on the way via {mode} — it's been {days} days. Where is my money?",
        "Paytm shows refund initiated for ₹{amount} but my passbook has no credit entry after {hours} hours.",
        "Still waiting on ₹{amount} refund from {order_ref}. App says initiated, bank says no incoming credit on {mode}.",
    ),
    IssueType.REFUND_COMPLETED.value: (
        "Your app says refund completed for ₹{amount} on {mode} but my bank statement still doesn't show any credit after {days} days.",
        "Refund marked completed for order {order_ref} (₹{amount}) — I need the RRN because my bank can't find it.",
        "You claim ₹{amount} refund is done via {mode} but I swear nothing hit my account in {days} days. Prove it landed.",
        "Status shows refund completed for ₹{amount} yet my {mode} balance is unchanged. What reference number should I give my bank?",
        "Completed refund for ₹{amount} on paper but customer care at my bank says no matching credit in last {days} days.",
    ),
    IssueType.FAILED_PAYMENT.value: (
        "Payment failed for ₹{amount} on {mode} but I got a debit SMS anyway for order {order_ref}. Please check.",
        "App says transaction failed for ₹{amount} via {mode} — merchant didn't get paid but my bank shows a hold from {hours} hours ago.",
        "Tried paying ₹{amount} with {mode}, it failed twice, and now I'm worried money was taken without order confirmation.",
        "Failed payment on ₹{amount} ({mode}) for {order_ref} but amount looks blocked in my UPI app. Will it come back?",
        "Order unpaid because txn failed, yet I see ₹{amount} deducted on {mode}. Fix this — I didn't get the product.",
    ),
    IssueType.SETTLEMENT_DELAY.value: (
        "I'm a merchant — successful {mode} payments of ₹{amount} from {days} days ago still show settlement pending in my dashboard.",
        "My shop MID isn't getting T+1 settlement. ₹{amount} batch from {order_ref} era is still pending after {days} business days.",
        "Merchant here: multiple UPI txns totaling around ₹{amount} are credited to customers but settlement to my bank is delayed {days} days.",
        "Settlement for last week's {mode} sales (about ₹{amount}) hasn't hit my nodal account. Dashboard says pending since {hours} hours.",
        "Why is settlement still pending for ₹{amount}? Customers paid via {mode} {days} days back and I'm waiting for the transfer.",
    ),
    IssueType.SETTLEMENT_FAILURE.value: (
        "Merchant settlement failed for ₹{amount} — your portal shows FAILED on the batch linked to order {order_ref}.",
        "My settlement of ₹{amount} via {mode} route failed with a bank reject. Customers were charged but I got nothing.",
        "Settlement status FAILED for yesterday's ₹{amount} payout. IFSC is correct — what reject code did the bank send?",
        "I'm a seller: ₹{amount} settlement failed and support asked for cancelled cheque. This is urgent, sales from {days} days ago.",
        "Failed settlement entry for ₹{amount} on my merchant account — customers paid on {mode} but transfer to my bank bounced.",
    ),
    IssueType.RECONCILIATION_MISMATCH.value: (
        "Merchant recon report shows ₹{amount} mismatch for {days}-day file — your txn count doesn't match NPCI settlement for {mode}.",
        "Our daily reconciliation has a ₹{amount} variance on {order_ref} date. Ledger says success but settlement file missing that txn.",
        "Finance team flagged mismatch: ₹{amount} delta between Paytm dashboard and acquirer file for last {days} days of {mode} payments.",
        "Recon ticket needed — one ₹{amount} txn shows credited in CRM but absent from yesterday's bank reconciliation extract.",
        "Settlement file total is ₹{amount} short vs internal ledger for {mode} batch. Which TXN_IDs are out of sync?",
    ),
    IssueType.DUPLICATE_DEBIT.value: (
        "I was charged twice for the same order {order_ref} — two debits of ₹{amount} on {mode} within {hours} minutes!",
        "Duplicate payment! Same ₹{amount} taken two times via {mode} for one purchase. I only ordered once.",
        "Got double debit SMS for ₹{amount} each on {mode}. Merchant maybe received one payment but I lost ₹{amount} twice.",
        "Please reverse the extra ₹{amount} charge — I accidentally paid twice when the first {mode} attempt hung for {hours} hours.",
        "Two successful txns of ₹{amount} on {mode} for order {order_ref}. I need one refunded immediately.",
    ),
    IssueType.CHARGEBACK_DISPUTE.value: (
        "My bank raised a dispute on ₹{amount} {mode} charge for order {order_ref} — merchant says they'll fight the chargeback.",
        "I filed a chargeback with my card issuer for ₹{amount} because goods never arrived. Paytm merchant is contesting it.",
        "Received chargeback notice on ₹{amount} txn from {days} days ago ({mode}). Need to submit representment docs ASAP.",
        "Customer disputed ₹{amount} via bank — reason merchandise not received. I have delivery proof for {order_ref} though.",
        "Visa chargeback opened on ₹{amount} payment. Merchant account shows reversal debit — what's the dispute case ID?",
    ),
    IssueType.NORMAL_SUCCESS.value: (
        "Payment of ₹{amount} via {mode} for {order_ref} shows success, merchant shipped, and I got delivery — just confirming no issue?",
        "Everything looks fine: ₹{amount} debited on {mode}, order delivered {days} days ago. Store confirmed payment received. No complaint really.",
        "Txn successful for ₹{amount}, merchant credited, settlement settled on their end. Customer just checking status is normal.",
        "I panicked earlier but ₹{amount} {mode} payment went through fine for {order_ref} — bank and app both show success now.",
        "All good on ₹{amount} payment via {mode} — success status, merchant has the money. Wanted to close the ticket myself.",
    ),
}


def _random_amount() -> str:
    """Format a random complaint amount between 99 and 24999 rupees."""
    value = round(random.uniform(99, 24999), 0)
    return f"{int(value):,}"


def _random_hours() -> int:
    """Sample a plausible complaint age in hours."""
    return random.randint(2, 72)


def _random_days() -> int:
    """Sample a plausible complaint age in days."""
    return random.randint(1, 14)


def _random_order_ref() -> str:
    """Generate a casual order reference fragment for complaint text."""
    suffix = "".join(random.choices(string.digits, k=4))
    return f"ORD{suffix}"


def _fill_template(template: str) -> str:
    """Substitute randomized details into a complaint template."""
    return template.format(
        amount=_random_amount(),
        mode=random.choice(PAYMENT_MODES),
        hours=_random_hours(),
        days=_random_days(),
        order_ref=_random_order_ref(),
    )


def _pick_weighted_issue() -> str:
    """Sample a TRUE_ISSUE label using real-world complaint frequency weights."""
    issues = list(ISSUE_WEIGHTS.keys())
    weights = [ISSUE_WEIGHTS[issue] for issue in issues]
    return random.choices(issues, weights=weights, k=1)[0]


def generate_complaints(count: int = 100) -> pd.DataFrame:
    """Build labeled synthetic complaints for evaluation."""
    records: list[dict[str, str]] = []

    for index in range(1, count + 1):
        true_issue = _pick_weighted_issue()
        template = random.choice(COMPLAINT_TEMPLATES[true_issue])
        complaint_text = _fill_template(template)

        records.append(
            {
                "COMPLAINT_ID": f"CMP{index:06d}",
                "ORDER_ID": f"ORD{index:06d}",
                "CUSTOMER_COMPLAINT": complaint_text,
                "TRUE_ISSUE": true_issue,
            }
        )

    return pd.DataFrame(records)


def write_complaints_csv(
    output_path: Path = DEFAULT_OUTPUT,
    count: int = 100,
) -> Path:
    """Generate complaints and persist them to a CSV file."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    dataframe = generate_complaints(count=count)
    dataframe.to_csv(output_path, index=False)
    logger.info("Wrote %s complaint records to %s", len(dataframe), output_path)
    return output_path


def main() -> None:
    """CLI entry point for generating the complaints CSV."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    write_complaints_csv()


if __name__ == "__main__":
    main()
