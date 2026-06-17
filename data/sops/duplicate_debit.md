# Duplicate Debit

## Symptoms
- Customer charged twice for the same merchant `ORDER_ID` or same purchase intent.
- Two distinct `TXN_ID`s with Success status, same amount (or same order), close timestamps (often within minutes).
- Customer reports double SMS/debit from bank; merchant may have received one or two credits depending on idempotency handling.
- Often caused by customer retrying during **UPI Pending** or network timeout on first attempt.

## Resolution Steps
1. Identify all `TXN_ID`s linked to the `ORDER_ID` or same customer + merchant + amount within a 30-minute window.
2. Determine merchant credit status for each leg: one Success + one Success is duplicate debit; one Success + one Failed/Pending is not duplicate (educate customer on pending release).
3. Check merchant order fulfilment: if merchant received only one credit, initiate refund on the **extra** Success txn after merchant confirms single order fulfilment.
4. If merchant received **two** credits, coordinate merchant refund of one leg to customer OR initiate Paytm refund on one txn per duplicate-debit policy (merchant liability if double fulfilment occurred).
5. Mark duplicate case in CRM linking primary and secondary `TXN_ID`; set `REFUND_STATUS` = INITIATED on the refund leg only.
6. Advise customer that duplicate refunds follow standard UPI/card timelines (5–7 business days).

## Escalation Rules
- Escalate to **L2 Refunds Ops** when both txns show `MERCHANT_CREDITED` = YES and merchant disputes which leg to reverse.
- Escalate to **Risk/Fraud** if duplicate pattern spans multiple merchants or amounts suggest scripted retry abuse.
- Escalate to **Legal/Chargeback** if customer initiated bank chargeback on one leg while refund is in progress on the other.

## Required Documents
- Both transaction receipts with `TXN_ID`, RRN/UTR, timestamps, and amounts.
- Customer bank statement showing two debits.
- Merchant `ORDER_ID` confirmation (single vs double order/shipment).
- Merchant settlement/credit proof if disputing refund eligibility.

## Expected Resolution Timeline
- **1–2 business days**: Case validation and refund initiation on confirmed duplicate leg.
- **5–7 business days**: Customer credit to source account after refund submission.
- **Up to 10 business days**: If merchant received double credit and merchant-initiated reversal is required first.
