"""Evaluate RAG retrieval precision against labeled customer complaints."""

from __future__ import annotations

import logging
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd
from sentence_transformers import SentenceTransformer
from sentence_transformers.util import cos_sim

from src.core.rag_retriever import retrieve_sop

logger = logging.getLogger(__name__)

DEFAULT_COMPLAINTS_PATH = Path("data/complaints.csv")
EMBEDDING_MODEL_NAME = "all-MiniLM-L6-v2"


def _load_complaints(path: Path = DEFAULT_COMPLAINTS_PATH) -> pd.DataFrame:
    """Load the labeled complaints evaluation set."""
    try:
        return pd.read_csv(path, keep_default_na=False)
    except FileNotFoundError as exc:
        logger.error("Complaints file not found: %s", path)
        raise FileNotFoundError(f"Complaints file not found: {path}") from exc


def _rank_worst_misclassifications(
    misclassified: list[dict[str, str]],
    model: SentenceTransformer,
    limit: int = 5,
) -> list[dict[str, str]]:
    """Rank misclassified rows by retrieval confidence on the wrong SOP."""
    if not misclassified:
        return []

    complaints = [row["complaint"] for row in misclassified]
    retrieved_contents = [row["retrieved_issue_content"] for row in misclassified]
    complaint_embeddings = model.encode(complaints, normalize_embeddings=True)
    retrieved_embeddings = model.encode(retrieved_contents, normalize_embeddings=True)

    ranked: list[tuple[float, dict[str, str]]] = []
    for index, row in enumerate(misclassified):
        confidence = float(
            cos_sim(complaint_embeddings[index], retrieved_embeddings[index])[0][0]
        )
        ranked.append((confidence, row))

    ranked.sort(key=lambda item: item[0], reverse=True)
    return [row for _, row in ranked[:limit]]


def evaluate_retrieval(complaints_path: Path = DEFAULT_COMPLAINTS_PATH) -> None:
    """Run precision@1 evaluation and print summary metrics."""
    complaints = _load_complaints(complaints_path)
    total = len(complaints)
    correct = 0

    per_issue_correct: dict[str, int] = defaultdict(int)
    per_issue_total: dict[str, int] = defaultdict(int)
    misclassified: list[dict[str, str]] = []

    for _, row in complaints.iterrows():
        true_issue = row["TRUE_ISSUE"]
        complaint_text = row["CUSTOMER_COMPLAINT"]
        per_issue_total[true_issue] += 1

        try:
            results = retrieve_sop(complaint_text, top_k=1)
        except RuntimeError as exc:
            logger.error("Retrieval failed for %s: %s", row["COMPLAINT_ID"], exc)
            raise

        if not results:
            retrieved_issue = ""
            retrieved_content = ""
        else:
            retrieved_issue = results[0]["issue_name"]
            retrieved_content = results[0]["content"]

        if retrieved_issue == true_issue:
            correct += 1
            per_issue_correct[true_issue] += 1
        else:
            misclassified.append(
                {
                    "complaint_id": row["COMPLAINT_ID"],
                    "complaint": complaint_text,
                    "true_issue": true_issue,
                    "retrieved_issue": retrieved_issue,
                    "retrieved_issue_content": retrieved_content,
                }
            )

    precision_at_1 = (correct / total) * 100 if total else 0.0

    print(f"Overall precision@1: {precision_at_1:.1f}% ({correct}/{total})")
    print()
    print("Per-issue precision@1:")
    for issue in sorted(per_issue_total):
        issue_correct = per_issue_correct[issue]
        issue_total = per_issue_total[issue]
        issue_precision = (issue_correct / issue_total) * 100 if issue_total else 0.0
        print(f"  {issue}: {issue_precision:.1f}% ({issue_correct}/{issue_total})")

    print()
    print("5 worst misclassified examples (highest wrong-match confidence):")
    ranking_model = SentenceTransformer(EMBEDDING_MODEL_NAME)
    worst_examples = _rank_worst_misclassifications(misclassified, ranking_model, limit=5)

    if not worst_examples:
        print("  (none — perfect retrieval)")
        return

    for index, example in enumerate(worst_examples, start=1):
        print(f"\n  [{index}] {example['complaint_id']}")
        print(f"      Complaint: {example['complaint']}")
        print(f"      True issue: {example['true_issue']}")
        print(f"      Retrieved:  {example['retrieved_issue']}")


def main() -> None:
    """CLI entry point for retrieval evaluation."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    evaluate_retrieval()


if __name__ == "__main__":
    main()
