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


def _format_escalation_line(escalation: dict[str, Any]) -> str:
    """Format the Escalation section from a pre-computed escalation decision."""
    if escalation.get("escalation_required"):
        team = escalation.get("escalation_team") or "the appropriate support team"
        return f"Yes — {team} ({escalation.get('reason', '')})"
    return f"No ({escalation.get('reason', '')})"


def build_sop_fallback_response(
    transaction: dict[str, Any],
    issue: str,
    sop: dict[str, Any],
    escalation: dict[str, Any],
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

    escalation_line = _format_escalation_line(escalation)

    return (
        f"Explanation:\n{explanation}\n\n"
        f"Next Action:\n{next_action}\n\n"
        f"Escalation:\n{escalation_line}\n\n"
        f"Source:\n{sop_filename}"
    )


def build_case_note_fallback(
    transaction: dict[str, Any],
    issue: str,
    escalation: dict[str, Any],
    resolution_summary: str,
) -> str:
    """Compose a deterministic ticketing case note from transaction facts."""
    txn_id = transaction.get("TXN_ID", "unknown")
    order_id = transaction.get("ORDER_ID", "unknown")
    amount = transaction.get("TXN_AMOUNT", "unknown")
    payment_mode = transaction.get("PAYMENT_MODE", "unknown")
    age_hours = transaction.get("AGE_HOURS", "unknown")

    if escalation.get("escalation_required"):
        team = escalation.get("escalation_team") or "the appropriate support team"
        escalation_sentence = (
            f"Escalation to {team} was required ({escalation.get('reason', '')})."
        )
    else:
        escalation_sentence = (
            f"No escalation was required ({escalation.get('reason', '')})."
        )

    summary_sentence = ""
    if resolution_summary.strip():
        first_line = resolution_summary.strip().splitlines()[0]
        summary_sentence = f" Resolution guidance indicated: {first_line[:200]}."

    return (
        f"Transaction {txn_id} (order {order_id}) was reviewed and classified as "
        f"\"{issue}\". The {payment_mode} payment of ₹{amount} had been open for "
        f"{age_hours} hours at the time of review.{summary_sentence} "
        f"{escalation_sentence}"
    )
