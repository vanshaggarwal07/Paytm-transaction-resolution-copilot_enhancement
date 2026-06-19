"""Hybrid SOP ranking: semantic similarity plus intent and structural signals."""

from __future__ import annotations

from typing import Any

WEIGHT_SEMANTIC = 0.5
WEIGHT_INTENT = 0.35
WEIGHT_STRUCTURAL = 0.15

CONFIDENCE_SCORES: dict[str, float] = {
    "high": 1.0,
    "medium": 0.6,
    "low": 0.3,
}

CARD_STRUCTURAL_ISSUES: frozenset[str] = frozenset(
    {"Failed Payment", "Chargeback / Dispute"}
)


def _intent_score(issue_name: str, extracted_intents: list[dict[str, Any]]) -> float:
    """Score intent alignment for one candidate; max confidence when duplicated."""
    matched_scores: list[float] = []
    for intent in extracted_intents:
        if intent.get("intent") != issue_name:
            continue
        confidence = str(intent.get("confidence", "")).strip().lower()
        matched_scores.append(CONFIDENCE_SCORES.get(confidence, 0.0))
    return max(matched_scores) if matched_scores else 0.0


def _structural_score(
    candidate: dict[str, Any],
    transaction: dict[str, Any],
    extracted_intents: list[dict[str, Any]],
) -> float:
    """Rule-based alignment between transaction fields and SOP domain."""
    issue_name = candidate.get("issue_name", "")
    sop_metadata = candidate.get("sop_metadata") or {}
    payment_mode = transaction.get("PAYMENT_MODE", "")
    age_hours = transaction.get("AGE_HOURS", 0)

    score = 0.0

    if payment_mode == "UPI" and "UPI" in issue_name:
        score += 1.0

    if payment_mode == "Card" and issue_name in CARD_STRUCTURAL_ISSUES:
        score += 1.0

    if (
        issue_name == "Chargeback / Dispute"
        and _intent_score(issue_name, extracted_intents) >= CONFIDENCE_SCORES["high"]
    ):
        score += 1.0

    if payment_mode == "Wallet" and "Settlement" in issue_name:
        score += 1.0

    expected_resolution_hours = sop_metadata.get("expected_resolution_hours")
    if expected_resolution_hours is not None and age_hours > expected_resolution_hours:
        score += 0.5

    return min(score, 1.0)


def compute_hybrid_scores(
    candidates: list[dict[str, Any]],
    semantic_scores: list[float],
    extracted_intents: list[dict[str, Any]],
    transaction: dict[str, Any],
) -> list[dict[str, Any]]:
    """Re-rank SOP candidates with transparent semantic, intent, and structural scores."""
    if len(candidates) != len(semantic_scores):
        raise ValueError(
            f"candidates and semantic_scores length mismatch: "
            f"{len(candidates)} vs {len(semantic_scores)}"
        )

    scored: list[dict[str, Any]] = []
    for candidate, semantic_score in zip(candidates, semantic_scores):
        entry = dict(candidate)
        intent_score = _intent_score(entry.get("issue_name", ""), extracted_intents)
        structural_score = _structural_score(entry, transaction, extracted_intents)
        final_score = (
            WEIGHT_SEMANTIC * semantic_score
            + WEIGHT_INTENT * intent_score
            + WEIGHT_STRUCTURAL * structural_score
        )
        final_score = max(0.0, min(1.0, final_score))

        entry["semantic_score"] = semantic_score
        entry["intent_score"] = intent_score
        entry["structural_score"] = structural_score
        entry["final_score"] = final_score
        scored.append(entry)

    scored.sort(key=lambda item: item["final_score"], reverse=True)
    return scored
