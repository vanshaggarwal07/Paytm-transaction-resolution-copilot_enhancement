"""Evaluate complaint understanding: RAG precision@1 vs intent extraction hit rate."""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

import pandas as pd

from src.core.intent_extractor import extract_intents
from src.core.rag_retriever import retrieve_sop

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


def _intent_names(intents: list[dict[str, Any]]) -> list[str]:
    """Return taxonomy intent names from extracted intent dicts."""
    names: list[str] = []
    for intent in intents:
        name = intent.get("intent")
        if isinstance(name, str) and name.strip():
            names.append(name.strip())
    return names


def _evaluate_precision_at_1(complaints: pd.DataFrame) -> tuple[float, int, int]:
    """Measure legacy RAG precision@1 using retrieve_sop(complaint, top_k=1)."""
    total = len(complaints)
    correct = 0

    per_issue_correct: dict[str, int] = defaultdict(int)
    per_issue_total: dict[str, int] = defaultdict(int)

    for _, row in complaints.iterrows():
        true_issue = row["TRUE_ISSUE"]
        complaint_text = row["CUSTOMER_COMPLAINT"]
        per_issue_total[true_issue] += 1

        try:
            results = retrieve_sop(complaint_text, top_k=1)
        except RuntimeError as exc:
            logger.error("Retrieval failed for %s: %s", row["COMPLAINT_ID"], exc)
            raise

        retrieved_issue = results[0]["issue_name"] if results else ""
        if retrieved_issue == true_issue:
            correct += 1
            per_issue_correct[true_issue] += 1

    precision_at_1 = (correct / total) * 100 if total else 0.0

    print("=" * 72)
    print("BASELINE — RAG retrieval precision@1 (retrieve_sop, top_k=1)")
    print("=" * 72)
    print(f"Overall precision@1: {precision_at_1:.1f}% ({correct}/{total})", flush=True)
    print()
    print("Per-issue precision@1:")
    for issue in sorted(per_issue_total):
        issue_correct = per_issue_correct[issue]
        issue_total = per_issue_total[issue]
        issue_precision = (issue_correct / issue_total) * 100 if issue_total else 0.0
        print(f"  {issue}: {issue_precision:.1f}% ({issue_correct}/{issue_total})")
    print()

    return precision_at_1, correct, total


def _evaluate_intent_extraction(complaints: pd.DataFrame) -> tuple[float, int, int]:
    """Measure intent extraction hit rate and related pipeline metrics."""
    total = len(complaints)
    hits = 0
    multi_intent_complaints = 0
    total_intents = 0
    low_confidence_intents = 0
    misses: list[dict[str, Any]] = []

    per_issue_hits: dict[str, int] = defaultdict(int)
    per_issue_total: dict[str, int] = defaultdict(int)

    for index, (_, row) in enumerate(complaints.iterrows()):
        true_issue = row["TRUE_ISSUE"]
        complaint_text = row["CUSTOMER_COMPLAINT"]
        complaint_id = row["COMPLAINT_ID"]
        per_issue_total[true_issue] += 1

        if index > 0:
            time.sleep(INTENT_EXTRACTION_DELAY_SECONDS)

        intents = extract_intents(complaint_text)
        intent_names = _intent_names(intents)
        total_intents += len(intents)

        if len(intents) > 1:
            multi_intent_complaints += 1

        for intent in intents:
            if intent.get("confidence") == "low":
                low_confidence_intents += 1

        if true_issue in intent_names:
            hits += 1
            per_issue_hits[true_issue] += 1
        else:
            misses.append(
                {
                    "complaint_id": complaint_id,
                    "complaint": complaint_text,
                    "true_issue": true_issue,
                    "extracted_intents": intents,
                    "extracted_names": intent_names,
                }
            )

    hit_rate = (hits / total) * 100 if total else 0.0
    multi_intent_rate = (multi_intent_complaints / total) * 100 if total else 0.0
    low_confidence_rate = (
        (low_confidence_intents / total_intents) * 100 if total_intents else 0.0
    )

    print("=" * 72)
    print("INTENT EXTRACTION — extract_intents() pipeline")
    print("=" * 72)
    print(f"Intent extraction hit rate: {hit_rate:.1f}% ({hits}/{total})")
    print(
        "  (TRUE_ISSUE appeared in any extracted intent, not just top-1 retrieval)"
    )
    print(f"Multi-intent rate: {multi_intent_rate:.1f}% ({multi_intent_complaints}/{total})")
    print(
        f"Low-confidence rate: {low_confidence_rate:.1f}% "
        f"({low_confidence_intents}/{total_intents} intents)"
    )
    print()
    print("Per-issue intent hit rate:")
    for issue in sorted(per_issue_total):
        issue_hits = per_issue_hits[issue]
        issue_total = per_issue_total[issue]
        issue_hit_rate = (issue_hits / issue_total) * 100 if issue_total else 0.0
        print(f"  {issue}: {issue_hit_rate:.1f}% ({issue_hits}/{issue_total})")
    print()
    print("5 worst misses (TRUE_ISSUE absent from extracted intents):")

    if not misses:
        print("  (none — perfect intent extraction)")
    else:
        for index, miss in enumerate(misses[:5], start=1):
            print(f"\n  [{index}] {miss['complaint_id']}")
            print(f"      Complaint: {miss['complaint']}")
            print(f"      True issue: {miss['true_issue']}")
            print(f"      Extracted:  {miss['extracted_names'] or '(none)'}")

    print()
    return hit_rate, hits, total


def evaluate_retrieval(complaints_path: Path = DEFAULT_COMPLAINTS_PATH) -> None:
    """Run baseline RAG precision@1 and intent extraction metrics; print comparison."""
    complaints = _load_complaints(complaints_path)

    precision_at_1, _rag_correct, total = _evaluate_precision_at_1(complaints)
    hit_rate, _intent_hits, _intent_total = _evaluate_intent_extraction(complaints)

    print("=" * 72)
    print("COMPARISON — precision@1 vs intent extraction hit rate")
    print("=" * 72)
    print(f"RAG precision@1:              {precision_at_1:.1f}%")
    print(f"Intent extraction hit rate:     {hit_rate:.1f}%")
    delta = hit_rate - precision_at_1
    if hit_rate > precision_at_1:
        print(
            f"Intent extraction is HIGHER by {delta:.1f} percentage points "
            f"({hit_rate:.1f}% vs {precision_at_1:.1f}%)."
        )
    elif precision_at_1 > hit_rate:
        print(
            f"RAG precision@1 is HIGHER by {abs(delta):.1f} percentage points "
            f"({precision_at_1:.1f}% vs {hit_rate:.1f}%)."
        )
    else:
        print(f"Both metrics are equal at {precision_at_1:.1f}%.")
    print(f"Evaluation set size: {total} complaints")
    print()


def main() -> None:
    """CLI entry point for retrieval and intent extraction evaluation."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    evaluate_retrieval()


if __name__ == "__main__":
    main()
