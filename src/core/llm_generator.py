"""Generate agent-facing explanations grounded in transaction facts and SOPs."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Optional, Tuple

from dotenv import load_dotenv
from google import genai

from src.core.sop_response_builder import build_case_note_fallback, build_sop_fallback_response

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_ENV_PATH = _PROJECT_ROOT / ".env"

load_dotenv(_ENV_PATH, override=True)

DEFAULT_MODEL = "gemini-2.0-flash"
FALLBACK_MODEL_CANDIDATES: tuple[str, ...] = (
    "gemini-2.0-flash",
    "gemini-2.5-flash",
    "gemini-2.5-flash-preview-05-20",
    "gemini-1.5-flash",
    "gemini-3.5-flash",
)

_ACTIVE_MODEL: Optional[str] = None
_client: Optional[genai.Client] = None
_client_key: Optional[str] = None
_llm_ready: Optional[bool] = None


def _get_api_key() -> str:
    """Reload and return a normalized Gemini API key from the environment."""
    load_dotenv(_ENV_PATH, override=True)
    raw_key = os.getenv("GEMINI_API_KEY", "") or os.getenv("GOOGLE_API_KEY", "")
    return raw_key.strip().strip('"').strip("'")


def _get_client() -> Optional[genai.Client]:
    """Return a Gemini client, creating one when a key is available."""
    global _client, _client_key, _llm_ready, _ACTIVE_MODEL

    api_key = _get_api_key()
    if not api_key or api_key == "your_key_here":
        _client = None
        _client_key = None
        _llm_ready = None
        _ACTIVE_MODEL = None
        return None

    os.environ["GEMINI_API_KEY"] = api_key

    if _client is None or _client_key != api_key:
        _llm_ready = None
        _ACTIVE_MODEL = None
        try:
            _client = genai.Client(api_key=api_key)
            _client_key = api_key
        except ValueError as exc:
            logger.warning("genai.Client() could not initialize: %s", exc)
            _client = None
            _client_key = None

    return _client


def is_llm_configured() -> bool:
    """Return True when a Gemini API key is present and the client can start."""
    api_key = _get_api_key()
    return bool(api_key) and api_key != "your_key_here" and _get_client() is not None


def _is_auth_error(exc: Exception) -> bool:
    """Return True when Gemini rejected the API key."""
    message = str(exc).lower()
    return "401" in message or "unauthenticated" in message or "invalid authentication" in message


def is_llm_ready() -> bool:
    """Return True when Gemini accepts the configured API key."""
    global _llm_ready, _ACTIVE_MODEL

    if not is_llm_configured():
        _llm_ready = False
        return False

    if _llm_ready is not None:
        return _llm_ready

    client = _get_client()
    assert client is not None

    for candidate in FALLBACK_MODEL_CANDIDATES:
        try:
            client.models.generate_content(model=candidate, contents="Reply with OK.")
            _ACTIVE_MODEL = candidate
            _llm_ready = True
            return True
        except Exception as exc:
            if _is_auth_error(exc):
                logger.error("Gemini rejected the API key: %s", exc)
                _llm_ready = False
                return False
            logger.warning("Gemini model %s unavailable during readiness check: %s", candidate, exc)

    _llm_ready = False
    return False


RESPONSE_PROMPT_TEMPLATE = """You are a Paytm payment support copilot helping a human agent.
Your job is to EXPLAIN facts already determined by the rule engine — never to decide
transaction status or issue identification on your own.

You are NOT deciding whether to escalate — that decision has already been made by the
business rules engine. Your only job is to phrase it clearly for the agent.

STRICT RULES:
- Use ONLY the facts provided below. Never invent or assume any transaction detail,
  timeline, amount, status, or policy that is not explicitly given.
- Do not contradict the identified issue supplied to you.
- For the Escalation section: state Yes or No exactly matching ESCALATION_REQUIRED below.
  If Yes, name ESCALATION_TEAM exactly as given. Include the escalation REASON as context.
  Do not override or second-guess the pre-computed escalation decision.
- Respond in exactly four clearly labeled sections with these headings:

Explanation:
(2-3 plain-language sentences on what happened, using only provided facts.)

Next Action:
(Concrete steps the agent should take now, grounded in the SOP resolution steps.)

Escalation:
(Yes or No per ESCALATION_REQUIRED — if Yes, name ESCALATION_TEAM and briefly cite REASON.)

Source:
(The SOP file name you used.)

IDENTIFIED ISSUE:
{issue}

ESCALATION DECISION (pre-computed — do not change):
- ESCALATION_REQUIRED: {escalation_required}
- ESCALATION_TEAM: {escalation_team}
- REASON: {escalation_reason}

TRANSACTION RECORD:
{transaction_json}

RETRIEVED SOP ({sop_filename}):
{sop_content}

CUSTOMER COMPLAINT (optional, may be empty):
{complaint}
"""

CASE_NOTE_PROMPT_TEMPLATE = """You are drafting an internal case note for a payment-support ticketing system.
The audience is other agents and team leads — not the customer.

STRICT RULES:
- Write exactly 2-4 sentences in past tense and third person.
- Use a formal, concise tone suitable for CRM/ticket history.
- Do not address the customer directly (no "you", "your", or salutations).
- Include the identified issue, payment amount, case age in hours, payment mode,
  and the pre-computed escalation outcome exactly as provided.
- Use ONLY the facts below. Do not invent transaction details or policy.
- Output plain prose only — no headings, bullets, or markdown.

IDENTIFIED ISSUE:
{issue}

ESCALATION DECISION (pre-computed — do not change):
- ESCALATION_REQUIRED: {escalation_required}
- ESCALATION_TEAM: {escalation_team}
- REASON: {escalation_reason}

TRANSACTION RECORD:
{transaction_json}

RESOLUTION SUMMARY (from agent guidance already generated):
{resolution_summary}
"""


def _format_transaction(transaction: dict[str, Any]) -> str:
    """Serialize the transaction dictionary for inclusion in the prompt."""
    return json.dumps(transaction, indent=2, default=str)


def _sop_filename(sop: dict[str, Any]) -> str:
    """Extract the SOP markdown filename from a retrieval result."""
    return Path(sop["file_path"]).name


def _build_case_note_prompt(
    transaction: dict[str, Any],
    issue: str,
    escalation: dict[str, Any],
    resolution_summary: str,
) -> str:
    """Fill the case-note prompt template with grounded context."""
    team = escalation.get("escalation_team")
    return CASE_NOTE_PROMPT_TEMPLATE.format(
        issue=issue,
        escalation_required=escalation.get("escalation_required"),
        escalation_team=team if team else "(none)",
        escalation_reason=escalation.get("reason", ""),
        transaction_json=_format_transaction(transaction),
        resolution_summary=resolution_summary.strip() or "(none provided)",
    )


def _build_prompt(
    transaction: dict[str, Any],
    issue: str,
    sop: dict[str, Any],
    escalation: dict[str, Any],
    complaint: str,
) -> str:
    """Fill the response prompt template with grounded context."""
    team = escalation.get("escalation_team")
    return RESPONSE_PROMPT_TEMPLATE.format(
        issue=issue,
        escalation_required=escalation.get("escalation_required"),
        escalation_team=team if team else "(none)",
        escalation_reason=escalation.get("reason", ""),
        transaction_json=_format_transaction(transaction),
        sop_filename=_sop_filename(sop),
        sop_content=sop["content"],
        complaint=complaint or "(none provided)",
    )


def _extract_response_text(response: Any) -> str:
    """Safely extract text from a Gemini response object."""
    text = getattr(response, "text", None)
    if text and str(text).strip():
        return str(text).strip()

    candidates = getattr(response, "candidates", None) or []
    parts: list[str] = []
    for candidate in candidates:
        content = getattr(candidate, "content", None)
        if not content:
            continue
        for part in getattr(content, "parts", None) or []:
            part_text = getattr(part, "text", None)
            if part_text:
                parts.append(str(part_text))
    return "\n".join(parts).strip()


def _find_flash_model(client: genai.Client) -> Optional[str]:
    """Return the first available flash-tier model name from the API."""
    try:
        for model in client.models.list():
            model_name = getattr(model, "name", "") or ""
            short_name = model_name.split("/")[-1]
            if "flash" in short_name.lower():
                logger.info("Discovered flash model: %s", short_name)
                return short_name
    except Exception as exc:
        logger.error("Failed to list Gemini models: %s", exc)
    return None


def _resolve_model_name(client: genai.Client) -> Optional[str]:
    """Resolve the Gemini model name, falling back if the default is unavailable."""
    global _ACTIVE_MODEL

    if _ACTIVE_MODEL is not None:
        return _ACTIVE_MODEL

    for candidate in FALLBACK_MODEL_CANDIDATES:
        try:
            client.models.generate_content(model=candidate, contents="Reply with OK.")
            _ACTIVE_MODEL = candidate
            if candidate != DEFAULT_MODEL:
                logger.warning("Using Gemini model %s (default %s unavailable)", candidate, DEFAULT_MODEL)
            return candidate
        except Exception as exc:
            if _is_auth_error(exc):
                logger.error("Gemini rejected the API key while resolving model: %s", exc)
                return None
            logger.warning("Gemini model %s unavailable: %s", candidate, exc)

    _ACTIVE_MODEL = _find_flash_model(client)
    return _ACTIVE_MODEL


def generate_response(
    transaction: dict[str, Any],
    issue: str,
    sop: dict[str, Any],
    escalation: dict[str, Any],
    complaint: str = "",
) -> Tuple[str, str]:
    """Generate agent guidance; returns (response_text, response_mode)."""
    client = _get_client()
    if client is None:
        logger.info("Using SOP-based fallback response for issue %r (no API key)", issue)
        return (
            build_sop_fallback_response(transaction, issue, sop, escalation, complaint),
            "sop_fallback",
        )

    prompt = _build_prompt(transaction, issue, sop, escalation, complaint)

    try:
        model_name = _resolve_model_name(client)
        if model_name is None:
            raise RuntimeError("No Gemini model could be resolved")

        response = client.models.generate_content(model=model_name, contents=prompt)
        text = _extract_response_text(response)
        if text:
            return text, "gemini"
        logger.error("Gemini returned an empty response for issue %r", issue)
    except Exception as exc:
        logger.exception("Gemini generation failed: %s", exc)

    logger.info("Falling back to SOP-based response after Gemini failure for issue %r", issue)
    return (
        build_sop_fallback_response(transaction, issue, sop, escalation, complaint),
        "sop_fallback",
    )


def generate_case_note(
    transaction: dict[str, Any],
    issue: str,
    escalation: dict[str, Any],
    resolution_summary: str,
) -> str:
    """Generate a formal ticketing case note; falls back to a template if Gemini fails."""
    client = _get_client()
    if client is None:
        logger.info("Using template case note for issue %r (no API key)", issue)
        return build_case_note_fallback(transaction, issue, escalation, resolution_summary)

    prompt = _build_case_note_prompt(transaction, issue, escalation, resolution_summary)

    try:
        model_name = _resolve_model_name(client)
        if model_name is None:
            raise RuntimeError("No Gemini model could be resolved")

        response = client.models.generate_content(model=model_name, contents=prompt)
        text = _extract_response_text(response)
        if text:
            return text
        logger.error("Gemini returned an empty case note for issue %r", issue)
    except Exception as exc:
        logger.exception("Gemini case note generation failed: %s", exc)

    logger.info("Falling back to template case note after Gemini failure for issue %r", issue)
    return build_case_note_fallback(transaction, issue, escalation, resolution_summary)
