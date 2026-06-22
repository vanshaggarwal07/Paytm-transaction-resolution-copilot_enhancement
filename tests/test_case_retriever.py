"""Tests for historical resolved-case retrieval."""

from src.core.case_retriever import SIMILARITY_THRESHOLD, retrieve_similar_cases


def test_retrieve_similar_cases_upi_pending_query() -> None:
    """UPI pending complaint returns only helpful cases above the threshold."""
    results = retrieve_similar_cases(
        "UPI payment stuck and not processed",
        "UPI Pending",
        top_k=3,
    )

    print("\n--- UPI Pending similar cases ---")
    for result in results:
        print(
            f"{result['CASE_ID']} | {result['ISSUE']} | "
            f"score={result['similarity_score']:.3f}"
        )
    print("--- end ---\n")

    for result in results:
        assert result["RATING"] == "helpful"
        assert result["similarity_score"] >= SIMILARITY_THRESHOLD


def test_retrieve_similar_cases_generic_query_threshold() -> None:
    """Very generic queries should return [] or only score-qualified matches."""
    results = retrieve_similar_cases(
        "something went wrong with my payment",
        "Failed Payment",
        top_k=3,
    )

    print("\n--- Generic query similar cases ---")
    if not results:
        print("(no cases met similarity threshold)")
    for result in results:
        print(
            f"{result['CASE_ID']} | {result['ISSUE']} | "
            f"score={result['similarity_score']:.3f}"
        )
    print("--- end ---\n")

    assert not results or all(
        result["similarity_score"] >= SIMILARITY_THRESHOLD for result in results
    )
