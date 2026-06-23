---
issue: "Refund Completed"
escalation_required: true
escalation_threshold_hours: 168
escalation_team: "L2 Refunds Ops"
expected_resolution_hours: 120
---
# Refund Completed

## Symptoms
- `REFUND_STATUS` = COMPLETED in Paytm systems for the original `TXN_ID`.
- Customer disputes non-receipt despite completed refund status in CRM.
- Merchant or customer requests proof of refund for accounting or chargeback defence.
- Possible mismatch between Paytm refund completion timestamp and customer's bank posting date.

## Resolution Steps
1. Pull refund leg details: refund `TXN_ID`/reference, completion timestamp, amount, and destination (source VPA, card last-4, or wallet).
2. Share the refund RRN/ARN (Acquirer Reference Number for cards) with the customer for bank tracing.
3. Explain posting lag: **COMPLETED** at Paytm means funds were released to the acquirer/issuer; the customer's bank may post **1–5 business days** later on UPI/card rails.
4. Ask customer to check "credit" entries and pending authorizations, not only the original debit line.
5. If customer still cannot locate credit after 7 business days from completion date, initiate issuer trace using refund RRN/ARN.
6. If trace confirms credit posted, provide bank posting date and close. If trace confirms failure, re-open as **Refund Pending** and re-initiate per policy.

## Escalation Rules
- Escalate to **L2 Refunds Ops** when issuer trace shows no credit 7+ business days after `REFUND_STATUS` = COMPLETED.
- Escalate to **Chargeback team** if card issuer initiated a chargeback on a transaction already refunded (double-recovery risk).
- No escalation needed if issuer trace confirms credit posted and customer education resolves the query.

## Required Documents
- Refund completion proof: CRM screenshot or automated refund advice with RRN/ARN.
- Customer bank statement for the refund window.
- Original transaction receipt for amount and date matching.

## Expected Resolution Timeline
- **Immediate**: Provide refund reference and completion proof to customer.
- **1–5 business days**: Typical issuer posting after Paytm marks refund COMPLETED.
- **5–10 business days**: Issuer trace and manual adjustment if credit genuinely missing despite COMPLETED status.
