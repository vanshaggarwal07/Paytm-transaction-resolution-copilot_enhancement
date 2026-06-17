"""Tests for semantic SOP retrieval."""

from src.core.rag_retriever import retrieve_sop


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
