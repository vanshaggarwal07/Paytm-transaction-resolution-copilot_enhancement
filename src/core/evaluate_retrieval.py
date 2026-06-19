"""Evaluate complaint understanding: semantic RAG vs hybrid retrieval vs intents."""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

import pandas as pd

from src.core.intent_extractor import extract_intents
from src.core.rag_retriever import retrieve_sop, retrieve_sop_hybrid
from src.core.transaction_lookup import _load_transactions

logger = logging.getLogger(__name__)

DEFAULT_COMPLAINTS_PATH = Path("data/complaints.csv")
INTENT_EXTRACTION_DELAY_SECONDS = 4.5


def _load_complaints(path: Path = DEFAULT_COMPLAINTS_PATH) -> pd.DataFrame:
    """Load the labeled complaints evaluation set."""
    try:
        return pd.read_csv(path, keep_default_na=False)
    except FileNotFoundError as exc:
        logger.error("Complaints file not found: %s", path)
        raise FileNotFoundError(f"Complaints file not found: {path}") from exc


def _transaction_for_order(order_id: str) -> dict[str, Any]:
    """Return the transaction row for an order ID, or an empty dict if missing."""
    transactions = _load_transactions()
    matches = transactions[transactions["ORDER_ID"] == order_id]
    if matches.empty:
        return {}
    return matches.iloc[0].to_dict()


def _intent_names(intents: list[dict[str, Any]]) -> list[str]:
    """Return taxonomy intent names from extracted intent dicts."""
    names: list[str] = []
    for intent in intents:
        name = intent.get("intent")
        if isinstance(name, str) and name.strip():
            names.append(name.strip())
    return names


def _print_ranking_change_cases(changes: list[dict[str, Any]], limit: int = 5) -> None:
    """Print cases where hybrid retrieval changed the top-1 result."""
    print("Top 5 cases where hybrid changed the top-1 result:")

    if not changes:
        print("  (none — semantic and hybrid agreed on every complaint)")
        return

    for index, change in enumerate(changes[:limit], start=1):
        outcome = "FIXED" if change["hybrid_correct"] and not change["semantic_correct"] else (
            "REGRESSION" if change["semantic_correct"] and not change["hybrid_correct"] else
            "CHANGED (both wrong or both right)"
        )
        print(f"\n  [{index}] {change['complaint_id']} — {outcome}")
        print(f"      True issue:     {change['true_issue']}")
        print(f"      Semantic top-1: {change['semantic_issue']}")
        print(f"      Hybrid top-1:   {change['hybrid_issue']}")
        print(f"      Hybrid scores:  {change['hybrid_scores']}")
        print(f"      Extracted:      {_intent_names(change['extracted_intents']) or '(none)'}")
        print(f"      Complaint:      {change['complaint'][:120]}...")


def evaluate_retrieval(complaints_path: Path = DEFAULT_COMPLAINTS_PATH) -> None:
    """Run semantic vs hybrid precision@1 on every labeled complaint."""
    complaints = _load_complaints(complaints_path)
    total = len(complaints)

    semantic_correct = 0
    hybrid_correct = 0
    per_issue_semantic: dict[str, int] = defaultdict(int)
    per_issue_hybrid: dict[str, int] = defaultdict(int)
    per_issue_total: dict[str, int] = defaultdict(int)
    ranking_changes: list[dict[str, Any]] = []

    for index, (_, row) in enumerate(complaints.iterrows()):
        true_issue = row["TRUE_ISSUE"]
        complaint_text = row["CUSTOMER_COMPLAINT"]
        complaint_id = row["COMPLAINT_ID"]
        order_id = row["ORDER_ID"]
        per_issue_total[true_issue] += 1

        semantic_results = retrieve_sop(complaint_text, top_k=1)
        semantic_issue = semantic_results[0]["issue_name"] if semantic_results else ""
        if semantic_issue == true_issue:
            semantic_correct += 1
            per_issue_semantic[true_issue] += 1

        if index > 0:
            time.sleep(INTENT_EXTRACTION_DELAY_SECONDS)
        extracted_intents = extract_intents(complaint_text)
        transaction = _transaction_for_order(order_id)

        hybrid_results = retrieve_sop_hybrid(
            complaint_text,
            extracted_intents=extracted_intents,
            transaction=transaction,
            top_k=1,
        )
        hybrid_issue = hybrid_results[0]["issue_name"] if hybrid_results else ""
        hybrid_top = hybrid_results[0] if hybrid_results else {}
        if hybrid_issue == true_issue:
            hybrid_correct += 1
            per_issue_hybrid[true_issue] += 1

        if semantic_issue != hybrid_issue:
            ranking_changes.append(
                {
                    "complaint_id": complaint_id,
                    "complaint": complaint_text,
                    "true_issue": true_issue,
                    "semantic_issue": semantic_issue,
                    "hybrid_issue": hybrid_issue,
                    "semantic_correct": semantic_issue == true_issue,
                    "hybrid_correct": hybrid_issue == true_issue,
                    "extracted_intents": extracted_intents,
                    "hybrid_scores": {
                        "semantic_score": hybrid_top.get("semantic_score"),
                        "intent_score": hybrid_top.get("intent_score"),
                        "structural_score": hybrid_top.get("structural_score"),
                        "final_score": hybrid_top.get("final_score"),
                    },
                }
            )

    semantic_precision = (semantic_correct / total) * 100 if total else 0.0
    hybrid_precision = (hybrid_correct / total) * 100 if total else 0.0

    print("=" * 72)
    print("SEMANTIC ONLY — retrieve_sop precision@1")
    print("=" * 72)
    print(f"Overall precision@1: {semantic_precision:.1f}% ({semantic_correct}/{total})", flush=True)
    print()
    print("Per-issue precision@1:")
    for issue in sorted(per_issue_total):
        issue_total = per_issue_total[issue]
        issue_precision = (per_issue_semantic[issue] / issue_total) * 100 if issue_total else 0.0
        print(f"  {issue}: {issue_precision:.1f}% ({per_issue_semantic[issue]}/{issue_total})")
    print()

    print("=" * 72)
    print("HYBRID — retrieve_sop_hybrid precision@1")
    print("=" * 72)
    print(f"Overall precision@1: {hybrid_precision:.1f}% ({hybrid_correct}/{total})")
    print()
    print("Per-issue precision@1:")
    for issue in sorted(per_issue_total):
        issue_total = per_issue_total[issue]
        issue_precision = (per_issue_hybrid[issue] / issue_total) * 100 if issue_total else 0.0
        print(f"  {issue}: {issue_precision:.1f}% ({per_issue_hybrid[issue]}/{issue_total})")
    print()

    print("=" * 72)
    print("COMPARISON — semantic-only vs hybrid precision@1")
    print("=" * 72)
    print(f"Semantic-only precision@1: {semantic_precision:.1f}%")
    print(f"Hybrid precision@1:        {hybrid_precision:.1f}%")
    delta = hybrid_precision - semantic_precision
    print(f"Delta:                     {delta:+.1f} percentage points")
    if hybrid_precision > semantic_precision:
        print(
            f"Hybrid retrieval is HIGHER by {delta:.1f} points "
            f"({hybrid_precision:.1f}% vs {semantic_precision:.1f}%)."
        )
    elif semantic_precision > hybrid_precision:
        print(
            f"WARNING: Hybrid precision@1 is LOWER than semantic-only by "
            f"{abs(delta):.1f} points ({hybrid_precision:.1f}% vs {semantic_precision:.1f}%). "
            "Tune WEIGHT_* constants in hybrid_scorer.py before touching the API."
        )
    else:
        print(f"Both retrieval modes are equal at {semantic_precision:.1f}%.")
    print()
    _print_ranking_change_cases(ranking_changes)
    print()
    print(f"Evaluation set size: {total} complaints")
    print()


def main() -> None:
    """CLI entry point for retrieval evaluation."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    evaluate_retrieval()


if __name__ == "__main__":
    main()
