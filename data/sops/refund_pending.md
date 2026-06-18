---
issue: "Refund Pending"
escalation_required: true
escalation_threshold_hours: 168
escalation_team: "L2 Refunds Ops"
expected_resolution_hours: 120
---
# Refund Pending

## Symptoms
- Original transaction was successful at payer side but `MERCHANT_CREDITED` = NO, or merchant agreed to refund.
- `REFUND_STATUS` = INITIATED; customer has not received credit back to source account/wallet.
- Customer sees refund initiated in Paytm app but bank/wallet balance unchanged.
- `TXN_STATUS` remains Success on the original txn; separate refund leg is in flight.

## Resolution Steps
1. Confirm original `TXN_ID`, refund initiation timestamp, and refund amount (must match original or approved partial amount).
2. Verify refund rail: UPI refunds credit to source VPA/bank; card refunds post to same card (may appear as unsettled credit); wallet refunds to Paytm wallet balance.
3. Check refund pipeline stage: initiated → submitted to acquirer → acknowledged by issuer. Each hop can take 1–3 business days.
4. For UPI refunds, trace the refund RRN. Issuer banks often take **T+2 to T+5 business days** to reflect credit even after acquirer submission.
5. If refund is INITIATED for more than **7 business days** without issuer credit, raise a refund status enquiry with the acquiring partner.
6. Communicate that weekends and bank holidays do not count toward issuer processing SLAs.

## Escalation Rules
- Escalate to **L2 Refunds Ops** when `REFUND_STATUS` = INITIATED for >7 business days with acquirer acknowledgment.
- Escalate to **Card network / UPI issuer** when acquirer confirms refund success but customer bank shows no credit after 10 business days.
- Escalate to **Compliance** if refund amount differs from approved amount without documented partial-refund approval.

## Required Documents
- Original transaction receipt (`TXN_ID`, amount, date).
- Refund initiation confirmation (SMS/app notification screenshot with refund reference).
- Customer bank/card statement covering the period from refund initiation (debit and credit lines visible).

## Expected Resolution Timeline
- **1–3 business days**: Wallet-to-wallet or same-rail instant refund paths.
- **5–7 business days**: Standard UPI/card refund to source account per NPCI and issuer SLAs.
- **Up to 10 business days**: Issuer enquiry and manual credit adjustment if refund leg is stuck post-acquirer submission.
