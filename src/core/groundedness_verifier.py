"""Verify agent responses are grounded in supplied transaction and SOP facts."""

from __future__ import annotations

import json
import logging
from typing import Any

from src.core.llm_generator import generate_content_with_model_fallback, _get_client

logger = logging.getLogger(__name__)

VERIFIER_PROMPT_TEMPLATE = """You are a strict fact-checker for a payment-support copilot.

You will receive FACTS (the only allowed source of truth) and a RESPONSE (text to audit).
Your job is to find claims in RESPONSE that are NOT directly supported by FACTS.

Rules:
- A claim is any concrete statement about amounts, statuses, IDs, timelines, teams,
  escalation outcomes, or policies.
- General formatting labels (e.g. section headings) are not claims.
- If every substantive claim in RESPONSE is directly supported by FACTS, output exactly
  the word NONE and nothing else.
- Otherwise, output each unsupported claim on its own line, prefixed with "- ".
- Do not add explanations, summaries, or markdown beyond the required format.

FACTS:
{facts_json}

RESPONSE:
{response_text}
"""

VERIFICATION_UNAVAILABLE = "verification_unavailable"


def _format_grounding_facts(grounding_facts: dict[str, Any]) -> str:
    """Serialize grounding facts for inclusion in the verifier prompt."""
    return json.dumps(grounding_facts, indent=2, default=str)


def _build_verifier_prompt(response_text: str, grounding_facts: dict[str, Any]) -> str:
    """Fill the verifier prompt template with facts and response text."""
    return VERIFIER_PROMPT_TEMPLATE.format(
        facts_json=_format_grounding_facts(grounding_facts),
        response_text=response_text.strip(),
    )


def _parse_verifier_output(raw_output: str) -> tuple[bool, list[str]]:
    """Parse verifier model output into verified flag and unsupported claims."""
    stripped = raw_output.strip()
    if stripped.upper() == "NONE":
        return True, []

    claims: list[str] = []
    for line in stripped.splitlines():
        if line.strip().startswith("- "):
            claim = line.strip()[2:].strip()
            if claim:
                claims.append(claim)
    return False, claims


def verify_groundedness(response_text: str, grounding_facts: dict[str, Any]) -> dict[str, Any]:
    """Check whether response_text is supported by grounding_facts via Gemini."""
    prompt = _build_verifier_prompt(response_text, grounding_facts)
    input_length = len(prompt)

    client = _get_client()
    if client is None:
        logger.warning(
            "Groundedness verification skipped: input_length=%s verified=None claim_count=0",
            input_length,
        )
        return {
            "verified": None,
            "unsupported_claims": [],
            "raw_verifier_output": VERIFICATION_UNAVAILABLE,
        }

    try:
        raw_output, _model_name = generate_content_with_model_fallback(client, prompt)
        if not raw_output:
            raise RuntimeError("Gemini verifier returned an empty response")

        verified, unsupported_claims = _parse_verifier_output(raw_output)
        logger.info(
            "Groundedness verification complete: input_length=%s verified=%s claim_count=%s",
            input_length,
            verified,
            len(unsupported_claims),
        )
        return {
            "verified": verified,
            "unsupported_claims": unsupported_claims,
            "raw_verifier_output": raw_output,
        }
    except Exception as exc:
        logger.exception("Groundedness verification failed: %s", exc)
        logger.info(
            "Groundedness verification unavailable: input_length=%s verified=None claim_count=0",
            input_length,
        )
        return {
            "verified": None,
            "unsupported_claims": [],
            "raw_verifier_output": VERIFICATION_UNAVAILABLE,
        }
