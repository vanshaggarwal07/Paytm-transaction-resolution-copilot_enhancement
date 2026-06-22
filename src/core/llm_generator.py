"""Generate agent-facing explanations grounded in transaction facts and SOPs."""

from __future__ import annotations

import json
import logging
import math
import os
from pathlib import Path
from typing import Any, Optional, Tuple

from dotenv import load_dotenv
from google import genai

from src.core.sop_response_builder import (
    build_case_note_fallback,
    build_customer_reply_fallback,
    build_sop_fallback_response,
)

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_ENV_PATH = _PROJECT_ROOT / ".env"

load_dotenv(_ENV_PATH, override=True)

DEFAULT_MODEL = "gemini-3.1-flash-lite"
FALLBACK_MODEL_CANDIDATES: tuple[str, ...] = (
    "gemini-3.1-flash-lite",
    "gemini-2.5-flash-lite",
    "gemini-3-flash-preview",
    "gemini-flash-latest",
    "gemini-2.0-flash-lite",
    "gemini-2.5-flash",
    "gemini-2.0-flash",
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


def _is_quota_error(exc: Exception) -> bool:
    """Return True when Gemini rejected the request due to rate or quota limits."""
    message = str(exc).lower()
    return "429" in message or "resource_exhausted" in message or "quota" in message


def _list_flash_model_names(client: genai.Client) -> set[str]:
    """Return flash-tier model short names advertised by the Gemini API."""
    names: set[str] = set()
    try:
        for model in client.models.list():
            model_name = getattr(model, "name", "") or ""
            short_name = model_name.split("/")[-1]
            if "flash" in short_name.lower():
                names.add(short_name)
    except Exception as exc:
        logger.error("Failed to list Gemini models: %s", exc)
    return names


def _ordered_model_candidates(client: genai.Client) -> list[str]:
    """Return configured fallback candidates that exist in the Gemini API."""
    available = _list_flash_model_names(client)
    ordered = [model for model in FALLBACK_MODEL_CANDIDATES if model in available]
    if ordered:
        return ordered
    return [model for model in FALLBACK_MODEL_CANDIDATES]


def generate_content_with_model_fallback(
    client: genai.Client,
    contents: str,
) -> tuple[str, str]:
    """Generate content, trying fallback models when quota or availability errors occur."""
    global _ACTIVE_MODEL

    candidates = _ordered_model_candidates(client)
    if not candidates:
        raise RuntimeError("No Gemini flash models are available for this API key")

    if _ACTIVE_MODEL and _ACTIVE_MODEL in candidates:
        candidates = [_ACTIVE_MODEL] + [model for model in candidates if model != _ACTIVE_MODEL]

    last_exc: Optional[Exception] = None
    for model_name in candidates:
        try:
            response = client.models.generate_content(model=model_name, contents=contents)
            text = _extract_response_text(response)
            _ACTIVE_MODEL = model_name
            if model_name != DEFAULT_MODEL:
                logger.info("Using Gemini model %s", model_name)
            return text, model_name
        except Exception as exc:
            if _is_auth_error(exc):
                raise
            last_exc = exc
            if _is_quota_error(exc):
                logger.warning(
                    "Gemini model %s quota exhausted, trying next candidate",
                    model_name,
                )
                if _ACTIVE_MODEL == model_name:
                    _ACTIVE_MODEL = None
                continue
            logger.warning("Gemini model %s unavailable: %s", model_name, exc)

    if last_exc is not None:
        raise last_exc
    raise RuntimeError("No Gemini model could generate content")


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

    try:
        _, model_name = generate_content_with_model_fallback(client, "Reply with OK.")
        _ACTIVE_MODEL = model_name
        _llm_ready = True
        return True
    except Exception as exc:
        if _is_auth_error(exc):
            logger.error("Gemini rejected the API key: %s", exc)
        else:
            logger.warning("Gemini readiness check failed: %s", exc)
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

CUSTOMER_REPLY_PROMPT_TEMPLATE = """You are writing a customer-facing message from the Paytm payments support team.
The audience is the customer — not an internal agent, engineer, or operations team.

TONE AND STYLE:
- Warm, empathetic, and professional. Acknowledge the inconvenience without being sycophantic.
- Write in first person plural ("We have reviewed...", "We understand...").
- Use plain language a customer would understand. No jargon.
- Write exactly 4-6 sentences. Do not write more than 6 sentences.
- Output only the customer message text — no headings, bullets, salutation labels, or markdown.

MUST INCLUDE:
- Reference the specific payment amount and payment mode provided below so the message feels personalised.
- One sentence explaining what happened in plain language.
- A clear statement of what happens next and by when, grounded in the RESOLUTION SUMMARY below.

ESCALATION HANDLING:
- If ESCALATION_REQUIRED is True: tell the customer their case has been escalated for priority review.
  Say they will hear back within FOLLOWUP_BUSINESS_DAYS business day(s).
  Do not name internal teams, tiers, or escalation codes.
- If ESCALATION_REQUIRED is False: close warmly with confirmation that the issue is resolved or being monitored.

NEVER MENTION:
- SOP names, internal team codes (L2, L3), FAISS, policy documents, or any system internals.

IDENTIFIED ISSUE:
{issue}

ESCALATION_REQUIRED: {escalation_required}
FOLLOWUP_BUSINESS_DAYS: {followup_business_days}

TRANSACTION RECORD:
{transaction_json}

RESOLUTION SUMMARY (translate into plain customer language — do not copy internal headings):
{resolution_summary}
"""


def _followup_business_days(escalation: dict[str, Any]) -> int:
    """Convert expected resolution hours to business days for customer messaging."""
    hours = escalation.get("expected_resolution_hours")
    if hours is None:
        return 3
    return max(1, math.ceil(int(hours) / 8))


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


def _build_customer_reply_prompt(
    transaction: dict[str, Any],
    issue: str,
    resolution_summary: str,
    escalation: dict[str, Any],
) -> str:
    """Fill the customer-reply prompt template with grounded context."""
    escalation_required = bool(escalation.get("escalation_required"))
    followup_days = _followup_business_days(escalation) if escalation_required else 0
    return CUSTOMER_REPLY_PROMPT_TEMPLATE.format(
        issue=issue,
        escalation_required=escalation_required,
        followup_business_days=followup_days if escalation_required else "N/A",
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
    """Return the cached or preferred Gemini model without burning quota on probes."""
    global _ACTIVE_MODEL

    if _ACTIVE_MODEL is not None:
        return _ACTIVE_MODEL

    candidates = _ordered_model_candidates(client)
    if candidates:
        return candidates[0]

    return _find_flash_model(client)


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
        text, _model_name = generate_content_with_model_fallback(client, prompt)
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
        text, _model_name = generate_content_with_model_fallback(client, prompt)
        if text:
            return text
        logger.error("Gemini returned an empty case note for issue %r", issue)
    except Exception as exc:
        logger.exception("Gemini case note generation failed: %s", exc)

    logger.info("Falling back to template case note after Gemini failure for issue %r", issue)
    return build_case_note_fallback(transaction, issue, escalation, resolution_summary)


def generate_customer_reply(
    transaction: dict[str, Any],
    issue: str,
    resolution_summary: str,
    escalation: dict[str, Any],
) -> str:
    """Generate a warm customer-facing reply; falls back to a template if Gemini fails."""
    client = _get_client()
    if client is None:
        logger.info("Using template customer reply for issue %r (no API key)", issue)
        return build_customer_reply_fallback(
            transaction, issue, resolution_summary, escalation
        )

    prompt = _build_customer_reply_prompt(transaction, issue, resolution_summary, escalation)

    try:
        text, _model_name = generate_content_with_model_fallback(client, prompt)
        if text:
            return text
        logger.error("Gemini returned an empty customer reply for issue %r", issue)
    except Exception as exc:
        logger.exception("Gemini customer reply generation failed: %s", exc)

    logger.info(
        "Falling back to template customer reply after Gemini failure for issue %r",
        issue,
    )
    return build_customer_reply_fallback(transaction, issue, resolution_summary, escalation)
