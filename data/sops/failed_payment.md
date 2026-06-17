# Failed Payment

## Symptoms
- `TXN_STATUS` = Failed and `BANK_STATUS` = FAILED.
- `MERCHANT_CREDITED` = NO; no settlement or refund pipeline should be active (`REFUND_STATUS` = NA).
- Customer attempted payment but order was not confirmed; may report seeing a debit SMS despite failed status.
- Common payer-side messages: insufficient funds, UPI PIN incorrect, transaction declined, issuer timeout.

## Resolution Steps
1. Confirm failed status in switch and acquiring logs; capture failure reason code (e.g., `Z9` insufficient funds, `U30` debit timeout, `U69` collect expired).
2. Clarify with customer: a **failed** UPI txn should not result in a permanent debit. Some banks show temporary blocks that auto-release within 24–48 hours.
3. If customer provides bank evidence of a **permanent debit** despite Failed status, treat as data mismatch — open reconciliation ticket; do not ask customer to repay.
4. Advise customer to retry with a different payment mode or after confirming balance, using a **new** payment attempt (not the same stuck session if QR/collect expired).
5. Confirm merchant order remains unpaid; merchant should not fulfil until a separate Success txn is recorded.
6. Close case as Failed with no refund if no debit is verified. Document failure reason for merchant visibility.

## Escalation Rules
- Escalate to **L2 Acquiring Ops** when switch shows Failed but remitter bank confirms settled debit (rare switch reversal lag).
- Escalate to **Risk** if failure reason indicates suspected fraud block — customer must contact their bank.
- Escalate to **Bank liaison** when failure code is `U30`/`U69` and customer reports hold >48 hours.

## Required Documents
- Paytm failed transaction receipt with failure reason code if available.
- Customer bank UPI history screenshot showing failed or reversed entry.
- Merchant `ORDER_ID` showing unpaid status.

## Expected Resolution Timeline
- **Immediate**: Confirm failed status and advise retry path.
- **24–48 hours**: Temporary bank holds from failed attempts should auto-release.
- **3–7 business days**: Reconciliation if permanent debit exists against a Failed switch record.
