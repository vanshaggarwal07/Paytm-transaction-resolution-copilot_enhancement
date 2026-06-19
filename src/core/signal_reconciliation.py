"""Reconcile rule-engine issue signals with complaint-derived intent extraction."""

from __future__ import annotations

from typing import Any, Optional

from src.core.intent_extractor import extract_intents


def _intent_name(intent: dict[str, Any]) -> Optional[str]:
    """Return the taxonomy intent name from an extracted intent dict."""
    name = intent.get("intent")
    return name if isinstance(name, str) and name.strip() else None


def _format_intent_phrase(intent: dict[str, Any]) -> str:
    """Format an intent with its confidence for human-readable notes."""
    name = _intent_name(intent)
    if not name:
        return ""

    confidence = intent.get("confidence")
    if isinstance(confidence, str) and confidence.strip():
        return f"{name} ({confidence.strip()} confidence)"
    return name


def _build_reconciliation_note(
    rule_based_issue: str,
    extracted_intents: list[dict[str, Any]],
    *,
    agreement: bool,
    conflict: bool,
    unresolved_intents: list[str],
    no_complaint_signal: bool,
) -> str:
    """Build a human-readable reconciliation note from actual reconciliation values."""
    if no_complaint_signal:
        return "No complaint text provided."

    if agreement and not unresolved_intents:
        return f"Rule engine and complaint both identify {rule_based_issue}."

    if agreement and unresolved_intents:
        secondary_phrases = [
            phrase
            for intent in extracted_intents
            if _intent_name(intent) in unresolved_intents
            for phrase in [_format_intent_phrase(intent)]
            if phrase
        ]
        secondary_text = ", ".join(secondary_phrases) if secondary_phrases else ", ".join(
            unresolved_intents
        )
        return (
            f"Rule engine identified {rule_based_issue}; complaint also signals "
            f"{secondary_text}. Secondary intent flagged for agent review."
        )

    if conflict:
        complaint_phrases = [
            phrase
            for intent in extracted_intents
            for phrase in [_format_intent_phrase(intent)]
            if phrase
        ]
        complaint_text = ", ".join(complaint_phrases) if complaint_phrases else ", ".join(
            unresolved_intents
        )
        return (
            f"Rule engine identified {rule_based_issue}; complaint signals "
            f"{complaint_text} — conflict flagged for agent review."
        )

    return f"Rule engine identified {rule_based_issue}."


def reconcile_signals(
    rule_based_issue: str,
    complaint_text: Optional[str],
    transaction: dict[str, Any],
) -> dict[str, Any]:
    """Compare rule-engine issue with complaint-derived intent extraction."""
    _ = transaction  # Reserved for future transaction-aware reconciliation.

    if not complaint_text or not complaint_text.strip():
        return {
            "primary_issue": rule_based_issue,
            "extracted_intents": [],
            "agreement": True,
            "conflict": False,
            "unresolved_intents": [],
            "reconciliation_note": "No complaint text provided.",
        }

    extracted_intents = extract_intents(complaint_text.strip())
    if not extracted_intents:
        return {
            "primary_issue": rule_based_issue,
            "extracted_intents": [],
            "agreement": True,
            "conflict": False,
            "unresolved_intents": [],
            "reconciliation_note": "No complaint text provided.",
        }

    extracted_names = [_intent_name(intent) for intent in extracted_intents]
    intent_names = [name for name in extracted_names if name]

    if rule_based_issue in intent_names:
        unresolved_intents = [name for name in intent_names if name != rule_based_issue]
        return {
            "primary_issue": rule_based_issue,
            "extracted_intents": extracted_intents,
            "agreement": True,
            "conflict": False,
            "unresolved_intents": unresolved_intents,
            "reconciliation_note": _build_reconciliation_note(
                rule_based_issue,
                extracted_intents,
                agreement=True,
                conflict=False,
                unresolved_intents=unresolved_intents,
                no_complaint_signal=False,
            ),
        }

    return {
        "primary_issue": rule_based_issue,
        "extracted_intents": extracted_intents,
        "agreement": False,
        "conflict": True,
        "unresolved_intents": intent_names,
        "reconciliation_note": _build_reconciliation_note(
            rule_based_issue,
            extracted_intents,
            agreement=False,
            conflict=True,
            unresolved_intents=intent_names,
            no_complaint_signal=False,
        ),
    }
