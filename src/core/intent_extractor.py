"""Extract customer complaint intents using Gemini and the issue taxonomy."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from src.core.llm_generator import generate_content_with_model_fallback, _get_client
from src.issue_taxonomy import ISSUE_NAMES

logger = logging.getLogger(__name__)

INTENT_EXTRACTION_PROMPT_TEMPLATE = """You are an intent extraction system for a Paytm payment support copilot.

Read the customer complaint and identify every distinct issue the customer may be describing,
including overlapping or implied issues.

ALLOWED ISSUE NAMES (use these strings verbatim only — never invent labels):
{taxonomy_list}

Return a JSON array of identified intents. Each object must contain:
- "intent": one of the allowed issue names above, copied exactly
- "confidence": "high", "medium", or "low"
- "evidence": the exact phrase from the complaint that supports this intent

Disambiguation guidance:
- "Amount Debited but Merchant Not Credited": customer paid but merchant did not receive funds.
- "UPI Pending": UPI payment stuck in pending state (not yet success/fail).
- "Refund Pending": refund initiated or promised but not yet received.
- "Chargeback / Dispute": customer disputes the transaction, does not recognise the charge,
  or contacted their bank to challenge it — even if a refund was also mentioned.
- "Failed Payment": payment explicitly failed or was declined.
- "Settlement Delay": merchant waiting for settlement payout after a successful transaction.
- "Normal Success": customer confirms everything is fine and has NO unresolved issue.
  Do NOT tag when "successful" only describes the underlying transaction while the customer
  is complaining about a different problem (e.g. settlement still pending).
- For vague complaints with no specific payment symptom (e.g. "something went wrong"),
  return [] unless a taxonomy label clearly applies — if unsure, use "low" confidence, never "high".

Rules:
- If multiple issues are described or implied, return multiple objects in the array.
- If no recognizable intent is found, return an empty array [].
- Return ONLY the JSON array — no preamble, no markdown fences, no explanation.
- The output must be directly parseable by json.loads().

CUSTOMER COMPLAINT:
{complaint_text}
"""


def _format_taxonomy_list() -> str:
    """Format taxonomy issue names for injection into the prompt."""
    return "\n".join(f"- {issue_name}" for issue_name in ISSUE_NAMES)


def _build_intent_prompt(complaint_text: str) -> str:
    """Fill the intent extraction prompt with taxonomy and complaint text."""
    return INTENT_EXTRACTION_PROMPT_TEMPLATE.format(
        taxonomy_list=_format_taxonomy_list(),
        complaint_text=complaint_text.strip(),
    )


def _strip_json_fences(raw_text: str) -> str:
    """Remove optional markdown code fences from model output."""
    text = raw_text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return text.strip()


def _parse_intent_json(raw_output: str) -> list[dict[str, Any]]:
    """Parse model JSON output into a list of intent dicts."""
    if not raw_output.strip():
        return []

    try:
        parsed = json.loads(_strip_json_fences(raw_output))
        if not isinstance(parsed, list):
            raise ValueError(f"Expected JSON array, got {type(parsed).__name__}")
        return parsed
    except (json.JSONDecodeError, ValueError, TypeError) as exc:
        logger.warning(
            "Intent extraction JSON parse failed (%s). raw_output=%r",
            exc,
            raw_output,
        )
        return []


def _request_intent_raw_output(complaint_text: str) -> str:
    """Call Gemini and return the raw intent-extraction model text."""
    client = _get_client()
    if client is None:
        logger.warning("Intent extraction skipped: Gemini client unavailable")
        return ""

    prompt = _build_intent_prompt(complaint_text)

    try:
        raw_output, _model_name = generate_content_with_model_fallback(client, prompt)
        return raw_output
    except Exception as exc:
        logger.exception("Intent extraction API call failed: %s", exc)
        return ""


def extract_intents(complaint_text: str) -> list[dict[str, Any]]:
    """Return parsed complaint intents, or [] on empty input or any failure."""
    if not complaint_text or not complaint_text.strip():
        return []

    raw_output = _request_intent_raw_output(complaint_text)
    return _parse_intent_json(raw_output)
