# Reconciliation Mismatch

## Symptoms
- Internal ledger totals do not match acquirer/NPCI settlement file for a given business date.
- Transaction may show Success in CRM but absent from bank reconciliation file, or present with different amount/status.
- `MERCHANT_CREDITED` or `SETTLEMENT_STATUS` may disagree between txn-level view and batch-level reconciliation report.
- Identified during daily reco job or merchant complaint after audit; not always visible to end customer initially.

## Resolution Steps
1. Isolate the mismatch scope: single `TXN_ID`, batch ID, or full-day file variance (count and amount delta).
2. Pull three-way match: Paytm txn ledger, NPCI UPI switch file (for UPI), and acquirer/partner bank settlement file for the same value date.
3. Classify mismatch type: **timing** (txn on D, file on D+1), **status drift** (Success vs Failed between switch and ledger), **amount delta** (partial capture or currency rounding), or **duplicate entry**.
4. For timing mismatches, document expected auto-resolution on next reco cycle (T+1); no customer action unless debit/credit impact confirmed.
5. For status drift, freeze further settlement on the disputed `TXN_ID` until switch and ledger agree; follow **Amount Debited but Merchant Not Credited** or **Failed Payment** SOP based on verified payer impact.
6. Log reco ticket with variance amount; settlement ops must approve any manual adjusting entry.

## Escalation Rules
- Escalate to **L2 Reconciliation** for any variance > ₹500 or involving >5 transactions on the same MID/date.
- Escalate to **NPCI/bank liaison** when switch file and acquirer file disagree on final status.
- Escalate to **Audit/Finance** when variance suggests systemic file ingestion failure (not isolated txn).

## Required Documents
- Reconciliation variance report with business date, batch ID, and delta summary.
- Txn-level dump: `TXN_ID`, amount, status, RRN/UTR, timestamps.
- NPCI/acquirer file excerpt for the disputed record(s).
- Merchant MID and settlement account for impact assessment.

## Expected Resolution Timeline
- **T+1 business day**: Timing mismatches often clear on next reco run after full file receipt.
- **3–5 business days**: Status drift investigation and switch/bank confirmation.
- **7–10 business days**: Manual adjustment and merchant/customer notification if financial impact confirmed.
