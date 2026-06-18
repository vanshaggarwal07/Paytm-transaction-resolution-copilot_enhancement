"""Tests for deterministic SOP-based fallback responses."""

from src.core.escalation_rules import determine_escalation
from src.core.sop_response_builder import build_sop_fallback_response
from src.core.transaction_lookup import lookup_transaction
from src.core.rag_retriever import retrieve_sop
from src.core.issue_rules import identify_issue
from src.core.sop_metadata import load_sop_metadata


def test_build_sop_fallback_response_has_four_sections() -> None:
    """Fallback response includes all required labeled sections."""
    transaction = lookup_transaction("MID000010", "ORD000010", "CUST000010")
    assert transaction is not None

    issue = identify_issue(transaction)
    sop = retrieve_sop(issue, top_k=1)[0]
    escalation = determine_escalation(
        transaction,
        load_sop_metadata(sop["file_path"]),
    )
    result = build_sop_fallback_response(
        transaction,
        issue,
        sop,
        escalation,
        complaint="Money deducted but merchant did not receive it",
    )

    assert "Explanation:" in result
    assert "Next Action:" in result
    assert "Escalation:" in result
    assert "Source:" in result
    assert "amount_debited_but_merchant_not_credited.md" in result
