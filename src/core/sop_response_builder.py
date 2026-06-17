"""Build a deterministic agent response from transaction facts and SOP text."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any


def _parse_sop_section(content: str, heading: str) -> str:
    """Extract a markdown section body by heading name."""
    pattern = rf"## {re.escape(heading)}\s*\n(.*?)(?=\n## |\Z)"
    match = re.search(pattern, content, flags=re.DOTALL)
    return match.group(1).strip() if match else ""


def _bullet_lines(section_text: str, limit: int = 3) -> list[str]:
    """Return up to `limit` non-empty bullet or numbered lines from a section."""
    lines: list[str] = []
    for raw_line in section_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith(("-", "*")) or re.match(r"^\d+\.", line):
            cleaned = re.sub(r"^[-*]\s*", "", line)
            cleaned = re.sub(r"^\d+\.\s*", "", cleaned)
            lines.append(cleaned)
        if len(lines) >= limit:
            break
    return lines


def _first_escalation_team(escalation_text: str) -> str:
    """Extract the first escalation team name from SOP escalation rules."""
    match = re.search(r"\*\*([^*]+)\*\*", escalation_text)
    if match:
        return match.group(1).strip()
    match = re.search(r"Escalate to\s+([^\n]+)", escalation_text, flags=re.IGNORECASE)
    return match.group(1).strip() if match else "the appropriate support team"


def _should_escalate(issue: str, transaction: dict[str, Any]) -> bool:
    """Apply simple fact-based thresholds aligned with SOP escalation guidance."""
    age_hours = int(transaction.get("AGE_HOURS", 0))

    if issue == "Amount Debited but Merchant Not Credited":
        return transaction.get("MERCHANT_CREDITED") == "NO" and age_hours >= 24

    if issue == "Settlement Delay":
        return transaction.get("SETTLEMENT_STATUS") == "PENDING" and age_hours >= 48

    if issue == "Settlement Failure":
        return transaction.get("SETTLEMENT_STATUS") == "FAILED"

    if issue == "Refund Pending":
        return transaction.get("REFUND_STATUS") == "INITIATED" and age_hours >= 168

    if issue == "UPI Pending":
        return transaction.get("TXN_STATUS") == "Pending" and age_hours >= 48

    return False


def build_sop_fallback_response(
    transaction: dict[str, Any],
    issue: str,
    sop: dict[str, Any],
    complaint: str = "",
) -> str:
    """Compose a four-section response using only transaction facts and SOP text."""
    content = sop["content"]
    sop_filename = Path(sop["file_path"]).name

    txn_id = transaction.get("TXN_ID", "unknown")
    order_id = transaction.get("ORDER_ID", "unknown")
    amount = transaction.get("TXN_AMOUNT", "unknown")
    txn_status = transaction.get("TXN_STATUS", "unknown")
    bank_status = transaction.get("BANK_STATUS", "unknown")
    merchant_credited = transaction.get("MERCHANT_CREDITED", "unknown")
    age_hours = transaction.get("AGE_HOURS", "unknown")

    explanation = (
        f"Transaction {txn_id} for order {order_id} shows TXN_STATUS={txn_status}, "
        f"BANK_STATUS={bank_status}, and MERCHANT_CREDITED={merchant_credited} "
        f"for ₹{amount}. The case has been open for {age_hours} hours and is classified "
        f"as \"{issue}\"."
    )
    if complaint.strip():
        explanation += f" The customer reported: \"{complaint.strip()}\"."

    resolution_section = _parse_sop_section(content, "Resolution Steps")
    next_steps = _bullet_lines(resolution_section, limit=3)
    if not next_steps:
        next_steps = ["Review the retrieved SOP and verify all transaction fields in CRM."]
    next_action = "\n".join(f"- {step}" for step in next_steps)

    escalation_section = _parse_sop_section(content, "Escalation Rules")
    team = _first_escalation_team(escalation_section)
    if _should_escalate(issue, transaction):
        escalation = f"Yes — {team}"
    else:
        escalation = "No"

    return (
        f"Explanation:\n{explanation}\n\n"
        f"Next Action:\n{next_action}\n\n"
        f"Escalation:\n{escalation}\n\n"
        f"Source:\n{sop_filename}"
    )
