"""Integration test for Gemini-backed response generation."""

import re

from src.core.escalation_rules import determine_escalation
from src.core.issue_rules import identify_issue
from src.core.llm_generator import generate_response
from src.core.rag_retriever import retrieve_sop
from src.core.sop_metadata import load_sop_metadata
from src.core.transaction_lookup import lookup_transaction


def _escalation_section_text(response_text: str) -> str:
    """Extract the Escalation section body from a four-section response."""
    match = re.search(
        r"Escalation:\s*(.+?)(?:\n\s*\n|\nSource:|\Z)",
        response_text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    assert match, "Escalation section not found in response"
    return match.group(1).strip()


def test_generate_response_with_real_pipeline() -> None:
    """End-to-end smoke test: lookup, classify, retrieve SOP, and generate."""
    transaction = lookup_transaction("MID000012", "ORD000012", "CUST000012")
    assert transaction is not None

    issue = identify_issue(transaction)
    sop_results = retrieve_sop(
        "Settlement is still pending and merchant has not received funds yet",
        top_k=1,
    )
    assert sop_results

    sop = sop_results[0]
    sop_metadata = load_sop_metadata(sop["file_path"])
    escalation = determine_escalation(transaction, sop_metadata)

    complaint = (
        "I'm a merchant waiting for settlement on a successful UPI payment — "
        "dashboard still shows pending."
    )

    result = generate_response(
        transaction=transaction,
        issue=issue,
        sop=sop,
        escalation=escalation,
        complaint=complaint,
    )
    response_text, response_mode = result

    print("\n--- generate_response output ---")
    print(f"Issue: {issue}")
    print(f"Mode: {response_mode}")
    print(f"Pre-computed escalation: {escalation}")
    print(f"SOP: {sop['file_path']}")
    print(response_text)
    print("--- end output ---\n")

    assert isinstance(response_text, str)
    assert "Explanation:" in response_text
    assert "Next Action:" in response_text
    assert "Escalation:" in response_text
    assert "Source:" in response_text

    escalation_text = _escalation_section_text(response_text)
    first_line = escalation_text.splitlines()[0].strip().lower()
    if escalation["escalation_required"]:
        assert first_line.startswith("yes"), (
            f"Escalation section contradicts pre-computed decision: {escalation_text!r}"
        )
        if escalation["escalation_team"]:
            assert escalation["escalation_team"].lower() in response_text.lower()
    else:
        assert first_line.startswith("no"), (
            f"Escalation section contradicts pre-computed decision: {escalation_text!r}"
        )
