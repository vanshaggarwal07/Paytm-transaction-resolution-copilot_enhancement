---
issue: "Settlement Failure"
escalation_required: true
escalation_threshold_hours: null
escalation_team: "L2 Settlement Ops"
expected_resolution_hours: 48
---
# Settlement Failure

## Symptoms
- `SETTLEMENT_STATUS` = FAILED for a transaction where `MERCHANT_CREDITED` = YES at txn level.
- Merchant did not receive settlement credit; internal batch shows reject from partner bank or nodal account.
- Common reject reasons: invalid IFSC, account closed, name mismatch, amount exceeds per-txn settlement limit, compliance freeze on MID.
- Merchant may see Success payments in dashboard but corresponding settlement line marked FAILED.

## Resolution Steps
1. Pull settlement failure reason code from the batch response file (NACH/UPI settlement or IMPS reject code).
2. Verify merchant nodal account status: active, matching registered name, correct IFSC for the account type (current vs savings restrictions per RBI PA guidelines).
3. If failure is **correctable** (e.g., updated IFSC on file), merchant must submit updated bank proof; settlement ops will re-present on next cycle after verification.
4. If failure is **compliance hold** (KYC expired, risk flag), route to merchant compliance — settlement cannot proceed until hold cleared.
5. Do not re-initiate individual txn settlement manually without batch ops; failed items are re-batched after root cause fix.
6. Inform merchant of reject reason and required action; funds remain in nodal escrow until successful re-presentment.

## Escalation Rules
- Escalate to **L2 Settlement Ops** immediately on any FAILED settlement with verified merchant-valid txn.
- Escalate to **Compliance/Risk** when failure reason is regulatory hold or AML flag.
- Escalate to **Partner bank** when reject code indicates technical/file format error on Paytm's outbound batch (not merchant error).

## Required Documents
- Settlement failure advice with reject code and batch ID.
- Cancelled cheque or bank letter for nodal account verification (if IFSC/account issue).
- Updated KYC documents if compliance-related reject.
- List of affected `TXN_ID`s and amounts.

## Expected Resolution Timeline
- **1–2 business days**: Re-presentment after merchant corrects bank details on file.
- **3–7 business days**: Compliance review and hold release before re-batch.
- **Up to 10 business days**: Partner bank investigation for technical rejects or disputed escrow movements.
