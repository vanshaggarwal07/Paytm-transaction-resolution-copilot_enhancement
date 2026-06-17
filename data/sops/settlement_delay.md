# Settlement Delay

## Symptoms
- `TXN_STATUS` = Success, `MERCHANT_CREDITED` = YES at transaction level, but `SETTLEMENT_STATUS` = PENDING.
- Merchant reports successful payments in dashboard but funds not yet in their linked bank nodal/settlement account.
- Transaction age exceeds expected T+1 settlement window (e.g., txn on Friday, merchant expects credit by Monday EOD).
- No failure or chargeback flags on the transaction.

## Resolution Steps
1. Verify `MERCHANT_CREDITED` = YES and transaction is included in the settlement batch for business day D (cut-off typically 11:59 PM IST for same-day inclusion).
2. Check merchant settlement configuration: settlement cycle (T+1 default), hold flags, KYC/compliance holds, or negative balance adjustments.
3. Confirm whether the delay is due to a **bank holiday** or NPCI maintenance window — settlement files do not move on RBI-declared holidays.
4. Pull settlement batch ID and expected value date. T+1 means file generated on D+1 morning, merchant bank credits often same day or next clearing cycle.
5. If `SETTLEMENT_STATUS` = PENDING beyond **T+2 business days** from txn date, check for batch exceptions (amount cap, IFSC mismatch, name mismatch on nodal account).
6. Communicate expected value date to merchant; do not manually re-credit the merchant without settlement ops approval.

## Escalation Rules
- Escalate to **L2 Settlement Ops** when PENDING exceeds T+2 business days with no compliance hold.
- Escalate to **Merchant onboarding/KYC** when settlement is blocked due to expired documents or nodal account verification failure.
- Escalate to **Partner bank** when batch shows `SENT` but merchant bank confirms no credit after value date + 1 business day.

## Required Documents
- Merchant MID and settlement account details (last 4 digits of account, IFSC).
- Transaction list with `TXN_ID`, amounts, and txn dates in the delayed batch.
- Merchant settlement dashboard screenshot showing PENDING status.
- Settlement batch reference number from internal ops console.

## Expected Resolution Timeline
- **T+1 business day**: Standard settlement credit for included transactions.
- **T+2 business days**: Resolution of batch exceptions and re-presentment.
- **3–5 business days**: Partner bank trace if batch was sent but credit missing.
