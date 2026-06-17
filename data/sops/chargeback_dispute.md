# Chargeback / Dispute

## Symptoms
- Card issuer or customer's bank has raised a chargeback/dispute on a previously successful transaction.
- Merchant reports reversal debit from settlement account or chargeback deduction notice.
- Customer may claim non-receipt of goods, unauthorised transaction, or duplicate charge despite earlier Success status.
- `SETTLEMENT_STATUS` may show adjustment; original `TXN_STATUS` remains Success unless retroactively updated by dispute outcome.

## Resolution Steps
1. Retrieve chargeback case ID, reason code (e.g., Visa 10.4 fraud, 13.1 merchandise not received), and dispute amount from card network portal.
2. Check representment deadline — typically **30–45 calendar days** from chargeback initiation depending on network (Visa/Mastercard/RuPay); missing deadline results in automatic merchant/customer fund loss per scheme rules.
3. Gather merchant representment evidence: delivery proof, IP/device fingerprint, customer communication, refund policy acceptance, and prior refund status if any.
4. For UPI disputes raised via NPCI complaint handle (`complaint@npci.org.in` or bank app), trace dispute status in UPI dispute management system; NPCI timelines often allow **up to 30 days** for resolution between remitter and beneficiary banks.
5. If Paytm already refunded the customer (`REFUND_STATUS` = COMPLETED), submit refund proof in representment to avoid double liability.
6. Communicate outcome timeline to merchant and customer; do not promise dispute reversal before network/bank ruling.

## Escalation Rules
- Escalate to **Chargeback/Disputes team** immediately on receipt — representment windows are hard deadlines.
- Escalate to **Fraud** for reason codes indicating unauthorised/fraud (10.4, 4837, etc.).
- Escalate to **Legal** when dispute amount exceeds ₹50,000 or involves regulatory complaint (ombudsman/Banking Mohtasib).
- Escalate to **NPCI liaison** for UPI dispute stuck beyond 30-day bank-to-bank SLA.

## Required Documents
- Chargeback advice with case ID, reason code, amount, and response deadline.
- Original transaction details: `TXN_ID`, auth code, amount, timestamp, card last-4 (never full PAN).
- Merchant representment pack: invoice, shipping/ delivery proof, customer OTP/consent logs (per PA-DSS policy).
- Refund proof if applicable (`REFUND_STATUS`, RRN/ARN).
- Customer correspondence related to the complaint.

## Expected Resolution Timeline
- **7–14 days**: Initial merchant notification and evidence collection for representment.
- **30–45 days**: Card network chargeback cycle (provisional credit to customer may occur earlier; final liability at ruling).
- **Up to 30 days**: NPCI UPI dispute resolution between participant banks.
- **Additional 30–60 days**: Pre-arbitration/arbitration if representment is contested (card networks).
