"""Tests for semantic and hybrid SOP retrieval."""

from src.core.rag_retriever import retrieve_sop, retrieve_sop_hybrid


def test_retrieve_sop_exact_issue_name_query() -> None:
    """A query matching an issue name returns that issue as the top hit."""
    results = retrieve_sop("UPI Pending", top_k=1)

    assert len(results) >= 1
    assert results[0]["issue_name"] == "UPI Pending"
    assert results[0]["file_path"].endswith("upi_pending.md")


def test_retrieve_sop_free_text_query() -> None:
    """Semantic retrieval on casual complaint text returns a plausible SOP."""
    query = "my payment is stuck and hasn't gone through yet"
    results = retrieve_sop(query, top_k=3)

    assert len(results) >= 1
    print("\n--- Free-text retrieval results ---")
    print(f"Query: {query!r}")
    for index, result in enumerate(results, start=1):
        print(f"{index}. {result['issue_name']} (file={result['file_path']})")


def test_retrieve_sop_hybrid_exact_issue_name_query() -> None:
    """Hybrid retrieval still returns the exact issue name as the top hit."""
    transaction = {"PAYMENT_MODE": "UPI", "AGE_HOURS": 12}
    extracted_intents = [
        {
            "intent": "UPI Pending",
            "confidence": "high",
            "evidence": "payment is stuck and hasn't gone through yet",
        }
    ]

    results = retrieve_sop_hybrid(
        "UPI Pending",
        extracted_intents=extracted_intents,
        transaction=transaction,
        top_k=1,
    )

    assert len(results) >= 1
    assert results[0]["issue_name"] == "UPI Pending"
    assert results[0]["file_path"].endswith("upi_pending.md")
    assert "final_score" in results[0]
    assert "semantic_score" in results[0]
    assert "intent_score" in results[0]
    assert "structural_score" in results[0]


def test_retrieve_sop_hybrid_free_text_query() -> None:
    """Hybrid retrieval on casual complaint text returns a plausible top SOP."""
    query = "my payment is stuck and hasn't gone through yet"
    transaction = {"PAYMENT_MODE": "UPI", "AGE_HOURS": 12}
    extracted_intents = [
        {
            "intent": "UPI Pending",
            "confidence": "high",
            "evidence": "payment is stuck and hasn't gone through yet",
        }
    ]

    baseline = retrieve_sop(query, top_k=3)
    results = retrieve_sop_hybrid(
        query,
        extracted_intents=extracted_intents,
        transaction=transaction,
        top_k=3,
    )

    assert len(results) >= 1
    print("\n--- Hybrid free-text retrieval results ---")
    print(f"Query: {query!r}")
    for index, result in enumerate(results, start=1):
        print(
            f"{index}. {result['issue_name']} "
            f"(final={result['final_score']:.3f}, "
            f"semantic={result['semantic_score']:.3f}, "
            f"intent={result['intent_score']:.3f}, "
            f"structural={result['structural_score']:.3f})"
        )

    baseline_top = baseline[0]["issue_name"] if baseline else None
    hybrid_top = results[0]["issue_name"]
    assert hybrid_top == baseline_top or hybrid_top in {
        issue["issue_name"] for issue in baseline
    }
