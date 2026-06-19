"""Tests for payment dashboard screenshot field extraction."""

from __future__ import annotations

import io

import pytest
from PIL import Image, ImageDraw

from src.core.image_extractor import (
    FIELD_NAMES,
    extract_fields_from_image,
    get_high_confidence_fields,
)


def test_get_high_confidence_fields_filters_levels() -> None:
    """Only high and medium confidence fields with values are returned."""
    extraction = {
        "MID": {"value": "MID000042", "confidence": "high"},
        "ORDER_ID": {"value": "ORD000042", "confidence": "medium"},
        "CUST_ID": {"value": "CUST000042", "confidence": "low"},
        "TXN_AMOUNT": {"value": "1499", "confidence": "high"},
        "PAYMENT_MODE": {"value": None, "confidence": "absent"},
        "TXN_STATUS": {"value": "Pending", "confidence": "medium"},
    }

    result = get_high_confidence_fields(extraction)

    print("\n--- filtered high/medium fields ---")
    print(result)
    print("--- end ---\n")

    assert result == {
        "MID": "MID000042",
        "ORDER_ID": "ORD000042",
        "TXN_AMOUNT": "1499",
        "TXN_STATUS": "Pending",
    }
    assert "CUST_ID" not in result
    assert "PAYMENT_MODE" not in result


def test_extract_fields_from_image_rejects_unsupported_media_type() -> None:
    """Unsupported MIME types raise ValueError before any API call."""
    with pytest.raises(ValueError, match="Unsupported media type"):
        extract_fields_from_image(b"fake-bytes", "application/pdf")


def _build_test_dashboard_image() -> tuple[bytes, str]:
    """Create a PNG screenshot-like image with fake transaction details."""
    image = Image.new("RGB", (800, 400), color="white")
    draw = ImageDraw.Draw(image)
    text = (
        "MID: MID000042  ORDER_ID: ORD000042  CUST_ID: CUST000042\n"
        "Amount: ₹1,499  Mode: UPI  Status: Success"
    )
    draw.text((20, 180), text, fill="black")

    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue(), "image/png"


def test_extract_fields_from_image_live_extraction() -> None:
    """Live Gemini vision call returns the expected extraction shape."""
    image_bytes, media_type = _build_test_dashboard_image()
    extraction = extract_fields_from_image(image_bytes, media_type)

    print("\n--- live vision extraction ---")
    for field in FIELD_NAMES:
        entry = extraction.get(field, {})
        print(f"{field}: value={entry.get('value')!r} confidence={entry.get('confidence')!r}")
    print("--- end ---\n")

    assert set(extraction.keys()) == set(FIELD_NAMES)
    for field in FIELD_NAMES:
        entry = extraction[field]
        assert isinstance(entry, dict)
        assert "value" in entry
        assert "confidence" in entry
