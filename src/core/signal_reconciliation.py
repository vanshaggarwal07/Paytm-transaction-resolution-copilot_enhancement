"""Reconcile rule-engine issue signals with complaint-derived SOP retrieval."""

from __future__ import annotations

from typing import Optional

from src.core.rag_retriever import retrieve_sop


def reconcile_signals(rule_based_issue: str, complaint_text: Optional[str]) -> dict:
    """Compare rule-engine issue with complaint-derived SOP retrieval."""
    if not complaint_text or not complaint_text.strip():
        return {
            "primary_issue": rule_based_issue,
            "secondary_issue": None,
            "agreement": True,
        }

    results = retrieve_sop(complaint_text.strip(), top_k=1)
    complaint_issue = results[0]["issue_name"] if results else rule_based_issue

    if complaint_issue == rule_based_issue:
        return {
            "primary_issue": rule_based_issue,
            "secondary_issue": None,
            "agreement": True,
        }

    return {
        "primary_issue": rule_based_issue,
        "secondary_issue": complaint_issue,
        "agreement": False,
    }
