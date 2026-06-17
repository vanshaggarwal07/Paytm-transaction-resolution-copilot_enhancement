# UPI Pending

## Symptoms
- Transaction shows `TXN_STATUS` = Pending and `BANK_STATUS` = PENDING at the time of complaint.
- Customer sees "payment processing" or a pending UPI mandate/collect request in their banking app.
- `MERCHANT_CREDITED` is NO; no settlement or refund has been triggered.
- Amount may appear as blocked or on hold in some bank UPI apps, but final debit is not confirmed.

## Resolution Steps
1. Identify the UPI flow type: P2M pay, collect request, or intent/QR — pending behaviour differs by flow.
2. Check NPCI UPI timeout rules: collect requests typically expire in 30 minutes; pay transactions may remain pending up to 24–48 hours depending on issuer bank processing.
3. Advise the customer **not** to retry payment for the same `ORDER_ID` until the pending state resolves, to avoid duplicate debits.
4. Poll transaction status every 4–6 hours via internal switch query; do not manually mark Success or Failed.
5. If status remains Pending beyond **48 hours**, initiate a status enquiry with the remitter bank using RRN/UTR.
6. If the bank confirms no debit occurred, close as Failed with no refund needed. If debit occurred but switch still Pending, follow the **Amount Debited but Merchant Not Credited** SOP.

## Escalation Rules
- Escalate to **L2 UPI Ops** when pending exceeds 48 hours with a valid RRN issued.
- Escalate to **Remitter bank** when issuer confirms debit but NPCI switch shows indeterminate state.
- Escalate to **Risk** if customer reports multiple pending transactions on the same order within 1 hour (possible duplicate attempt pattern).

## Required Documents
- UPI transaction reference (RRN/UTR) from customer's banking app.
- Screenshot of pending status in payer bank UPI history with timestamp.
- Merchant `ORDER_ID` and order amount for cross-verification.

## Expected Resolution Timeline
- **Within 30 minutes**: Most collect-request pendings expire or complete automatically.
- **24–48 hours**: Standard NPCI/issuer resolution window for pay transactions stuck in pending.
- **3–5 business days**: Bank status enquiry and manual switch update if still unresolved after 48 hours.
