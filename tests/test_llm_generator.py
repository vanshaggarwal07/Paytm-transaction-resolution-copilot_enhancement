"""Integration test for Gemini-backed response generation."""

import re

from src.core.escalation_rules import determine_escalation
from src.core.issue_rules import identify_issue
from src.core.llm_generator import (
    _build_prompt,
    format_historical_cases_block,
    generate_case_note,
    generate_customer_reply,
    generate_response,
)
from src.core.rag_retriever import retrieve_sop, retrieve_sop_hybrid
from src.core.sop_metadata import load_sop_metadata
from src.core.transaction_lookup import lookup_transaction


def _escalation_section_text(response_text: str) -> str:
    """Extract the Escalation section body from a four-section response."""
    match = re.search(
        r"\*{0,2}Escalation:\*{0,2}\s*(.+?)(?:\n\s*\n|\n\*{0,2}Source:|\Z)",
        response_text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    assert match, "Escalation section not found in response"
    return re.sub(r"^\*+|\*+$", "", match.group(1).strip(), flags=re.MULTILINE)


def _first_meaningful_line(text: str) -> str:
    """Return the first non-empty line with markdown emphasis stripped."""
    for line in text.splitlines():
        cleaned = re.sub(r"^\*+|\*+$", "", line).strip()
        if cleaned:
            return cleaned.lower()
    return ""


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
    first_line = _first_meaningful_line(escalation_text)
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


def test_generate_case_note_with_real_pipeline() -> None:
    """End-to-end smoke test: produce a ticketing case note from a resolved transaction."""
    transaction = lookup_transaction("MID000002", "ORD000002", "CUST000002")
    assert transaction is not None

    issue = identify_issue(transaction)
    sop = retrieve_sop(issue, top_k=1)[0]
    sop_metadata = load_sop_metadata(sop["file_path"])
    escalation = determine_escalation(transaction, sop_metadata)

    complaint = "Settlement is still pending and merchant has not received funds yet."
    response_text, _response_mode = generate_response(
        transaction=transaction,
        issue=issue,
        sop=sop,
        escalation=escalation,
        complaint=complaint,
    )

    case_note = generate_case_note(
        transaction=transaction,
        issue=issue,
        escalation=escalation,
        resolution_summary=response_text,
    )

    print("\n--- generate_case_note output ---")
    print(f"Issue: {issue}")
    print(f"Escalation: {escalation}")
    print(case_note)
    print("--- end output ---\n")

    assert isinstance(case_note, str)
    assert len(case_note.strip()) > 0
    assert (
        "Settlement Delay" in case_note
        or "settlement delay" in case_note.lower()
        or "settlement" in case_note.lower()
        or str(transaction["TXN_ID"]) in case_note
    )
    assert str(transaction["TXN_AMOUNT"]) in case_note or "2677" in case_note


def test_generate_customer_reply_with_real_transaction() -> None:
    """End-to-end smoke test: produce a customer-facing reply for a resolved case."""
    transaction = lookup_transaction("MID000002", "ORD000002", "CUST000002")
    assert transaction is not None

    issue = identify_issue(transaction)
    resolution_summary = (
        "Explanation:\n"
        "Transaction TXN000002 for order ORD000002 was a Wallet payment of ₹2677.33 "
        "with TXN_STATUS=Success and SETTLEMENT_STATUS=PENDING. The case had been "
        "open for 146 hours.\n\n"
        "Next Action:\n"
        "Verify MERCHANT_CREDITED = YES and check settlement batch inclusion.\n\n"
        "Escalation:\n"
        "Yes — L2 Settlement Ops (settlement delay 146h, exceeds 48h threshold)\n\n"
        "Source:\n"
        "settlement_delay.md"
    )
    escalation = {
        "escalation_required": True,
        "escalation_team": "L2 Settlement Ops",
        "reason": "settlement delay 146h, exceeds 48h threshold",
        "expected_resolution_hours": 24,
    }

    customer_reply = generate_customer_reply(
        transaction=transaction,
        issue=issue,
        resolution_summary=resolution_summary,
        escalation=escalation,
    )

    print("\n--- generate_customer_reply output ---")
    print(f"Issue: {issue}")
    print(f"Escalation: {escalation}")
    print(customer_reply)
    print("--- end output ---\n")

    assert isinstance(customer_reply, str)
    assert len(customer_reply.strip()) > 0
    assert "2677" in customer_reply or "2,677" in customer_reply
    assert "wallet" in customer_reply.lower()
    assert "l2" not in customer_reply.lower()
    assert "sop" not in customer_reply.lower()
    assert "faiss" not in customer_reply.lower()


def _mock_similar_case(
    case_id: str,
    issue: str,
    *,
    score: float = 0.85,
) -> dict:
    """Build a mock historical case dict for prompt inspection tests."""
    return {
        "CASE_ID": case_id,
        "ISSUE": issue,
        "COMPLAINT": f"Sample complaint for {case_id}",
        "RESOLUTION_SUMMARY": f"Resolution steps applied for {case_id}",
        "OUTCOME": "Resolved",
        "RATING": "helpful",
        "similarity_score": score,
    }


def test_generate_response_includes_historical_cases_in_prompt() -> None:
    """Historical cases and SOP issue appear in the prompt sent to the model."""
    transaction = lookup_transaction("MID000017", "ORD000017", "CUST000017")
    assert transaction is not None

    issue = identify_issue(transaction)
    sop_results = retrieve_sop_hybrid(
        query=issue,
        extracted_intents=[],
        transaction=transaction,
        top_k=1,
    )
    assert sop_results

    sop = sop_results[0]
    sop_metadata = load_sop_metadata(sop["file_path"])
    escalation = determine_escalation(transaction, sop_metadata)
    similar_cases = [
        _mock_similar_case("CASE-MOCK-001", issue, score=0.91),
        _mock_similar_case("CASE-MOCK-002", issue, score=0.78),
    ]
    complaint = "UPI payment is stuck in pending status for several hours."

    prompt = _build_prompt(
        transaction=transaction,
        issue=issue,
        sop=sop,
        escalation=escalation,
        complaint=complaint,
        similar_cases=similar_cases,
    )

    print("\n--- generate_response prompt (historical cases) ---")
    print(prompt)
    print("--- end prompt ---\n")

    assert "CASE-MOCK-001" in prompt or "CASE-MOCK-002" in prompt
    assert issue in prompt

    response_text, _response_mode = generate_response(
        transaction=transaction,
        issue=issue,
        sop=sop,
        escalation=escalation,
        complaint=complaint,
        similar_cases=similar_cases,
    )
    assert isinstance(response_text, str)
    assert len(response_text.strip()) > 0


def test_generate_response_with_empty_historical_cases() -> None:
    """Empty similar_cases still produces a valid four-section response."""
    transaction = lookup_transaction("MID000010", "ORD000010", "CUST000010")
    assert transaction is not None

    issue = identify_issue(transaction)
    sop = retrieve_sop(issue, top_k=1)[0]
    sop_metadata = load_sop_metadata(sop["file_path"])
    escalation = determine_escalation(transaction, sop_metadata)

    response_text, _response_mode = generate_response(
        transaction=transaction,
        issue=issue,
        sop=sop,
        escalation=escalation,
        complaint="Money deducted but merchant never received payment",
        similar_cases=[],
    )

    assert isinstance(response_text, str)
    assert len(response_text.strip()) > 0
    assert any(
        header in response_text
        for header in ("Explanation:", "Next Action:", "Escalation:", "Source:")
    )


def test_generate_response_backward_compatible_without_similar_cases() -> None:
    """Existing callers without similar_cases continue to work unchanged."""
    transaction = lookup_transaction("MID000010", "ORD000010", "CUST000010")
    assert transaction is not None

    issue = identify_issue(transaction)
    sop = retrieve_sop(issue, top_k=1)[0]
    sop_metadata = load_sop_metadata(sop["file_path"])
    escalation = determine_escalation(transaction, sop_metadata)

    response_text, response_mode = generate_response(
        transaction=transaction,
        issue=issue,
        sop=sop,
        escalation=escalation,
        complaint="Money deducted but merchant never received payment",
    )

    assert isinstance(response_text, str)
    assert len(response_text.strip()) > 0
    assert response_mode in ("gemini", "sop_fallback")


def test_historical_cases_capped_at_three_in_prompt() -> None:
    """Only the top three similar cases are injected into the prompt."""
    transaction = lookup_transaction("MID000017", "ORD000017", "CUST000017")
    assert transaction is not None

    issue = identify_issue(transaction)
    sop = retrieve_sop_hybrid(
        query=issue,
        extracted_intents=[],
        transaction=transaction,
        top_k=1,
    )[0]
    sop_metadata = load_sop_metadata(sop["file_path"])
    escalation = determine_escalation(transaction, sop_metadata)
    similar_cases = [
        _mock_similar_case(f"CASE-CAP-{index:03d}", issue, score=0.95 - index * 0.05)
        for index in range(5)
    ]

    historical_block = format_historical_cases_block(similar_cases)

    print("\n--- historical block (case cap) ---")
    print(historical_block)
    print("--- end historical block ---\n")

    assert historical_block.count("--- Case ") == 3
    assert "CASE-CAP-004" not in historical_block
    assert "CASE-CAP-000" in historical_block
