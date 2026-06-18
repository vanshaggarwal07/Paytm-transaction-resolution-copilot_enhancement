---
issue: "Amount Debited but Merchant Not Credited"
escalation_required: true
escalation_threshold_hours: 24
escalation_team: "L2 Acquiring Ops"
expected_resolution_hours: 24
---
# Amount Debited but Merchant Not Credited

## Symptoms
- Customer's bank account or Paytm wallet shows a successful debit for the transaction amount.
- Merchant dashboard shows no corresponding credit or order confirmation for the same `ORDER_ID` / `TXN_ID`.
- `TXN_STATUS` is Success at the payer side, but `MERCHANT_CREDITED` is NO and settlement has not posted.
- Customer reports payment deducted but order/service not received; merchant insists payment not received.

## Resolution Steps
1. Pull the transaction by `TXN_ID` and verify payer debit timestamp, `BANK_STATUS`, and UPI reference number (RRN/UTR).
2. Check NPCI UPI switch status: confirm whether the collect/pay request reached `SUCCESS` at the acquirer leg while the merchant settlement leg is still `PENDING` or unmatched.
3. Query the merchant settlement batch for the transaction date. T+1 settlement means credits initiated on business day D typically reflect in the merchant's nodal account by end of day D+1 (excluding bank holidays).
4. If the debit is confirmed at the bank but no merchant credit after T+1, raise an internal reconciliation ticket against the acquiring bank file. Do not promise instant reversal to the customer.
5. If `REFUND_STATUS` is not yet `INITIATED`, initiate a merchant-side credit adjustment or customer refund per acquiring policy once the debit is verified and merchant non-receipt is confirmed.
6. Share the RRN/UTR and expected resolution window with the customer; log the case ID in the CRM.

## Escalation Rules
- Escalate to **L2 Acquiring Ops** if debit is confirmed, merchant credit is NO, and T+1 settlement window has passed with no matching entry in the settlement file.
- Escalate to **Bank/NPCI liaison** if RRN shows success at payer bank but acquirer file shows `FAILED` or missing record (switch mismatch).
- Escalate to **Fraud/Risk** if the same `CUST_ID` or device shows repeated debited-not-credited patterns within 72 hours.
- Do not escalate solely on customer urgency; escalation requires verified ledger mismatch.

## Required Documents
- Customer bank statement or passbook screenshot showing debit (masking unrelated transactions).
- Paytm transaction receipt with `TXN_ID`, amount, timestamp, and UPI RRN/UTR.
- Merchant order ID and merchant's payment dashboard screenshot (if merchant-initiated complaint).
- NPCI UPI dispute reference (if already raised).

## Expected Resolution Timeline
- **T+0 to T+1**: Auto-reconciliation and settlement batch processing; many cases self-resolve when the merchant credit posts on the next settlement cycle.
- **3–7 business days**: Manual reconciliation and acquirer adjustment after confirmed payer-side debit with missing merchant credit.
- **Up to 10 business days**: If NPCI/bank switch dispute is required for UPI leg mismatch.
