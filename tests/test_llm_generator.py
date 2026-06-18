"""Integration test for Gemini-backed response generation."""

from src.core.issue_rules import identify_issue
from src.core.llm_generator import generate_response
from src.core.rag_retriever import retrieve_sop
from src.core.transaction_lookup import lookup_transaction


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

    complaint = (
        "I'm a merchant waiting for settlement on a successful UPI payment — "
        "dashboard still shows pending."
    )

    result = generate_response(
        transaction=transaction,
        issue=issue,
        sop=sop_results[0],
        complaint=complaint,
    )
    response_text, response_mode = result

    print("\n--- generate_response output ---")
    print(f"Issue: {issue}")
    print(f"Mode: {response_mode}")
    print(f"SOP: {sop_results[0]['file_path']}")
    print(response_text)
    print("--- end output ---\n")

    assert isinstance(response_text, str)
    assert "Explanation:" in response_text
    assert "Next Action:" in response_text
    assert "Escalation:" in response_text
    assert "Source:" in response_text
