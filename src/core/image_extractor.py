"""Extract transaction identifiers from payment dashboard screenshots via Gemini vision."""

from __future__ import annotations

import base64
import json
import logging
import re
from typing import Any, Optional

from src.core.llm_generator import _get_client

logger = logging.getLogger(__name__)

ALLOWED_MEDIA_TYPES: frozenset[str] = frozenset(
    {"image/png", "image/jpeg", "image/webp"}
)

FIELD_NAMES: tuple[str, ...] = (
    "MID",
    "ORDER_ID",
    "CUST_ID",
    "TXN_AMOUNT",
    "PAYMENT_MODE",
    "TXN_STATUS",
)

VALID_CONFIDENCE_LEVELS: frozenset[str] = frozenset(
    {"high", "medium", "low", "absent"}
)

VISION_MODEL_CANDIDATES: tuple[str, ...] = (
    "gemini-3.5-flash",
    "gemini-3.1-flash-lite",
    "gemini-2.5-flash-lite",
    "gemini-3-flash-preview",
    "gemini-flash-latest",
    "gemini-2.0-flash-lite",
    "gemini-2.5-flash",
    "gemini-2.0-flash",
)

EXTRACTION_PROMPT = """You are an OCR and field-extraction system for a Paytm payment support copilot.

Examine the provided payment dashboard or transaction record screenshot.

Extract these specific fields if visible:
- MID (Merchant ID)
- ORDER_ID
- CUST_ID (Customer ID)
- TXN_AMOUNT
- PAYMENT_MODE
- TXN_STATUS

For each field return a confidence level:
- "high": clearly visible and unambiguous
- "medium": partially visible or inferred
- "low": guessed from context
- "absent": not visible in the image at all

Return ONLY a JSON object with this exact shape and nothing else — no preamble, no markdown fences:
{
  "MID": {"value": "<string or null>", "confidence": "<level>"},
  "ORDER_ID": {"value": "<string or null>", "confidence": "<level>"},
  "CUST_ID": {"value": "<string or null>", "confidence": "<level>"},
  "TXN_AMOUNT": {"value": "<string or null>", "confidence": "<level>"},
  "PAYMENT_MODE": {"value": "<string or null>", "confidence": "<level>"},
  "TXN_STATUS": {"value": "<string or null>", "confidence": "<level>"}
}

Rules:
- If a field is not visible, set value to null and confidence to "absent".
- NEVER fabricate or guess a value and mark it "high".
- If uncertain, use "medium" or "low".
- Accuracy of identifiers matters more than completeness; null is safer than a wrong MID.
- The output must be directly parseable by json.loads().
"""


def _empty_extraction() -> dict[str, dict[str, Optional[str]]]:
    """Return an all-absent extraction dict used when vision extraction fails."""
    return {
        field: {"value": None, "confidence": "absent"}
        for field in FIELD_NAMES
    }


def _validate_media_type(media_type: str) -> str:
    """Reject unsupported MIME types before any API call."""
    normalized = media_type.strip().lower()
    if normalized not in ALLOWED_MEDIA_TYPES:
        allowed = ", ".join(sorted(ALLOWED_MEDIA_TYPES))
        raise ValueError(
            f"Unsupported media type {media_type!r}. Allowed types: {allowed}."
        )
    return normalized


def _strip_json_fences(raw_text: str) -> str:
    """Remove optional markdown code fences from model output."""
    text = raw_text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return text.strip()


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


def _normalize_field_entry(entry: Any) -> dict[str, Optional[str]]:
    """Normalize one field entry to value/confidence shape."""
    if not isinstance(entry, dict):
        return {"value": None, "confidence": "absent"}

    value = entry.get("value")
    if value is not None:
        value = str(value).strip() or None

    confidence = str(entry.get("confidence", "absent")).strip().lower()
    if confidence not in VALID_CONFIDENCE_LEVELS:
        confidence = "absent"

    if value is None:
        confidence = "absent"

    return {"value": value, "confidence": confidence}


def _parse_extraction_json(raw_output: str) -> dict[str, dict[str, Optional[str]]]:
    """Parse and validate model JSON output into the extraction dict."""
    parsed = json.loads(_strip_json_fences(raw_output))
    if not isinstance(parsed, dict):
        raise ValueError(f"Expected JSON object, got {type(parsed).__name__}")

    extraction: dict[str, dict[str, Optional[str]]] = {}
    for field in FIELD_NAMES:
        if field not in parsed:
            raise ValueError(f"Missing field {field!r} in extraction output")
        extraction[field] = _normalize_field_entry(parsed[field])
    return extraction


def _build_vision_contents(image_bytes: bytes, media_type: str) -> list[dict[str, Any]]:
    """Build multimodal Gemini contents payload for vision extraction."""
    b64 = base64.b64encode(image_bytes).decode("utf-8")
    return [
        {
            "parts": [
                {"inline_data": {"mime_type": media_type, "data": b64}},
                {"text": EXTRACTION_PROMPT},
            ]
        }
    ]


def _generate_vision_content(client: Any, contents: list[dict[str, Any]]) -> str:
    """Call Gemini vision models with fallback across flash candidates."""
    last_exc: Optional[Exception] = None
    for model_name in VISION_MODEL_CANDIDATES:
        try:
            response = client.models.generate_content(model=model_name, contents=contents)
            text = _extract_response_text(response)
            if text:
                if model_name != VISION_MODEL_CANDIDATES[0]:
                    logger.info("Vision extraction used Gemini model %s", model_name)
                return text
            raise RuntimeError(f"Gemini model {model_name} returned empty vision response")
        except Exception as exc:
            last_exc = exc
            logger.warning("Vision model %s failed: %s", model_name, exc)
            continue

    if last_exc is not None:
        raise last_exc
    raise RuntimeError("No Gemini vision models are available for this API key")


def extract_fields_from_image(image_bytes: bytes, media_type: str) -> dict:
    """Extract transaction identifiers from a dashboard screenshot."""
    validated_media_type = _validate_media_type(media_type)

    client = _get_client()
    if client is None:
        logger.warning("Vision extraction skipped: Gemini client unavailable")
        return _empty_extraction()

    contents = _build_vision_contents(image_bytes, validated_media_type)
    raw_output = ""

    try:
        raw_output = _generate_vision_content(client, contents)
        return _parse_extraction_json(raw_output)
    except Exception as exc:
        logger.warning(
            "Vision extraction failed (%s). raw_response=%r",
            exc,
            raw_output,
        )
        return _empty_extraction()


def get_high_confidence_fields(extraction: dict) -> dict:
    """Return flat pre-population dict for fields with high or medium confidence."""
    result: dict[str, str] = {}
    for field in FIELD_NAMES:
        entry = extraction.get(field) or {}
        confidence = str(entry.get("confidence", "absent")).strip().lower()
        value = entry.get("value")
        if confidence in {"high", "medium"} and value:
            result[field] = str(value)
    return result
