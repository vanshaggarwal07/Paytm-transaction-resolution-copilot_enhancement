"""Generate agent-facing explanations grounded in transaction facts and SOPs."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from google import genai

from src.core.sop_response_builder import build_sop_fallback_response

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_ENV_PATH = _PROJECT_ROOT / ".env"

if not _ENV_PATH.exists():
    _ENV_PATH.write_text("GEMINI_API_KEY=your_key_here\n", encoding="utf-8")
    logger.warning(
        "Created %s with placeholder GEMINI_API_KEY. Replace your_key_here with "
        "your real key from Google AI Studio: https://aistudio.google.com",
        _ENV_PATH,
    )

load_dotenv(_ENV_PATH)

DEFAULT_MODEL = "gemini-2.0-flash"
FALLBACK_MODEL_CANDIDATES: tuple[str, ...] = (
    "gemini-2.0-flash",
    "gemini-2.5-flash-preview-05-20",
    "gemini-1.5-flash",
    "gemini-3.5-flash",
)
FALLBACK_RESPONSE = (
    "Unable to generate a response right now — please retry or escalate manually"
)

def _is_api_key_configured() -> bool:
    """Return True when a non-placeholder Gemini API key is available."""
    key = os.getenv("GEMINI_API_KEY", "")
    return bool(key) and key != "your_key_here"


client: genai.Client | None = None
if _is_api_key_configured():
    try:
        client = genai.Client()
    except ValueError as exc:
        client = None
        logger.warning("genai.Client() could not initialize: %s", exc)
else:
    logger.warning(
        "GEMINI_API_KEY is not configured in %s. "
        "SOP-based fallback responses will be used until a real key is added.",
        _ENV_PATH,
    )


def is_llm_configured() -> bool:
    """Return True when the Gemini client is ready to make API calls."""
    return client is not None and _is_api_key_configured()

# Resolved once on first successful call, or after flash-tier fallback discovery.
_ACTIVE_MODEL: str | None = None

RESPONSE_PROMPT_TEMPLATE = """You are a Paytm payment support copilot helping a human agent.
Your job is to EXPLAIN facts already determined by the rule engine — never to decide
transaction status, issue type, or escalation on your own.

STRICT RULES:
- Use ONLY the facts provided below. Never invent or assume any transaction detail,
  timeline, amount, status, or policy that is not explicitly given.
- Do not contradict the identified issue supplied to you.
- For Escalation: answer Yes or No, and name the team only if Yes — based STRICTLY
  on the SOP's Escalation Rules section, not your own judgement.
- Respond in exactly four clearly labeled sections with these headings:

Explanation:
(2-3 plain-language sentences on what happened, using only provided facts.)

Next Action:
(Concrete steps the agent should take now, grounded in the SOP resolution steps.)

Escalation:
(Yes or No — if Yes, name the specific team from the SOP escalation rules.)

Source:
(The SOP file name you used.)

IDENTIFIED ISSUE:
{issue}

TRANSACTION RECORD:
{transaction_json}

RETRIEVED SOP ({sop_filename}):
{sop_content}

CUSTOMER COMPLAINT (optional, may be empty):
{complaint}
"""


def _format_transaction(transaction: dict[str, Any]) -> str:
    """Serialize the transaction dictionary for inclusion in the prompt."""
    return json.dumps(transaction, indent=2, default=str)


def _sop_filename(sop: dict[str, Any]) -> str:
    """Extract the SOP markdown filename from a retrieval result."""
    return Path(sop["file_path"]).name


def _build_prompt(
    transaction: dict[str, Any],
    issue: str,
    sop: dict[str, Any],
    complaint: str,
) -> str:
    """Fill the response prompt template with grounded context."""
    return RESPONSE_PROMPT_TEMPLATE.format(
        issue=issue,
        transaction_json=_format_transaction(transaction),
        sop_filename=_sop_filename(sop),
        sop_content=sop["content"],
        complaint=complaint or "(none provided)",
    )


def _find_flash_model() -> str | None:
    """Return the first available flash-tier model name from the API."""
    if client is None:
        return None

    try:
        for model in client.models.list():
            model_name = getattr(model, "name", "") or ""
            short_name = model_name.split("/")[-1]
            if "flash" in short_name.lower():
                logger.info("Falling back to available flash model: %s", short_name)
                return short_name
    except Exception as exc:
        logger.error("Failed to list Gemini models: %s", exc)
    return None


def _resolve_model_name() -> str:
    """Resolve the Gemini model name, falling back if the default is unavailable."""
    global _ACTIVE_MODEL

    if _ACTIVE_MODEL is not None:
        return _ACTIVE_MODEL

    if client is None:
        raise RuntimeError("Gemini client is not configured — GEMINI_API_KEY is missing")

    errors: list[str] = []
    for candidate in FALLBACK_MODEL_CANDIDATES:
        try:
            client.models.generate_content(model=candidate, contents="Reply with OK.")
            _ACTIVE_MODEL = candidate
            if candidate != DEFAULT_MODEL:
                logger.warning("Using Gemini model %s (default %s unavailable)", candidate, DEFAULT_MODEL)
            return candidate
        except Exception as exc:
            errors.append(f"{candidate}: {exc}")

    fallback = _find_flash_model()
    if fallback is not None:
        _ACTIVE_MODEL = fallback
        logger.warning("Switched LLM model to discovered flash model: %s", fallback)
        return fallback

    raise RuntimeError(f"No Gemini flash model available. Attempts: {'; '.join(errors)}")


def generate_response(
    transaction: dict[str, Any],
    issue: str,
    sop: dict[str, Any],
    complaint: str = "",
) -> str:
    """Generate a grounded agent response using Gemini and the retrieved SOP."""
    if not is_llm_configured():
        logger.info("Using SOP-based fallback response for issue %r", issue)
        return build_sop_fallback_response(transaction, issue, sop, complaint)

    prompt = _build_prompt(transaction, issue, sop, complaint)

    try:
        model_name = _resolve_model_name()
        response = client.models.generate_content(model=model_name, contents=prompt)
        text = getattr(response, "text", None)
        if text and text.strip():
            return text.strip()
        logger.error("Gemini returned an empty response for issue %r", issue)
    except Exception as exc:
        logger.exception("Gemini generation failed: %s", exc)

    logger.info("Falling back to SOP-based response after Gemini failure for issue %r", issue)
    return build_sop_fallback_response(transaction, issue, sop, complaint)
