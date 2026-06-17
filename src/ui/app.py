"""Streamlit UI for the Paytm Transaction Resolution Copilot."""

from __future__ import annotations

import logging

import requests
import streamlit as st

logger = logging.getLogger(__name__)

API_HEALTH_URL = "http://localhost:8000/health"
API_RESOLVE_URL = "http://localhost:8000/resolve"
REQUEST_TIMEOUT_SECONDS = 60


def _call_resolve_api(
    mid: str,
    order_id: str,
    cust_id: str,
    complaint: str,
) -> tuple[dict | None, str | None]:
    """POST to the resolution API and return payload or a user-facing error."""
    payload = {
        "mid": mid.strip(),
        "order_id": order_id.strip(),
        "cust_id": cust_id.strip(),
        "complaint": complaint.strip(),
    }

    try:
        response = requests.post(
            API_RESOLVE_URL,
            json=payload,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
    except requests.ConnectionError:
        logger.error("Could not connect to API at %s", API_RESOLVE_URL)
        return None, (
            "Could not reach the resolution API at localhost:8000. "
            "Make sure the FastAPI server is running."
        )
    except requests.Timeout:
        logger.error("API request timed out for ORDER_ID=%s", order_id)
        return None, "The resolution API timed out. Please try again."
    except requests.RequestException as exc:
        logger.error("API request failed: %s", exc)
        return None, "Something went wrong while contacting the API. Please try again."

    if response.status_code == 404:
        return None, (
            "Transaction not found. Please check the MID, Order ID, and "
            "Customer ID and try again."
        )

    if response.status_code != 200:
        logger.error("API returned status %s: %s", response.status_code, response.text)
        detail = response.json().get("detail") if response.headers.get("content-type", "").startswith("application/json") else None
        return None, detail or "The resolution API returned an unexpected error."

    try:
        return response.json(), None
    except ValueError as exc:
        logger.error("Invalid JSON from API: %s", exc)
        return None, "Received an invalid response from the API."


def _render_escalation_badge(escalation_required: bool | None, note: str | None) -> None:
    """Show a colored escalation badge based on the parsed API response."""
    if escalation_required is True:
        st.markdown(
            '<span style="background-color:#dc3545;color:white;padding:4px 10px;'
            'border-radius:6px;font-weight:600;">Escalation Required</span>',
            unsafe_allow_html=True,
        )
    elif escalation_required is False:
        st.markdown(
            '<span style="background-color:#28a745;color:white;padding:4px 10px;'
            'border-radius:6px;font-weight:600;">No Escalation Required</span>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            '<span style="background-color:#6c757d;color:white;padding:4px 10px;'
            'border-radius:6px;font-weight:600;">Escalation Unknown</span>',
            unsafe_allow_html=True,
        )
        if note:
            st.caption(note)


def main() -> None:
    """Render the dispute resolution form and results."""
    st.set_page_config(page_title="Paytm Resolution Copilot", page_icon="💳", layout="centered")
    st.title("Paytm Transaction Resolution Copilot")
    st.caption("Look up a transaction and get grounded agent guidance.")

    try:
        health = requests.get(API_HEALTH_URL, timeout=5).json()
        if not health.get("llm_configured"):
            st.info(
                "Gemini API key not configured — showing **SOP-based guidance** from "
                "transaction facts. Add `GEMINI_API_KEY` to `.env` for AI-generated responses."
            )
    except requests.RequestException:
        st.warning("API health check failed — start FastAPI on port 8000 before resolving.")

    with st.form("resolve_form"):
        mid = st.text_input("MID", placeholder="e.g. MID000002")
        order_id = st.text_input("Order ID", placeholder="e.g. ORD000002")
        cust_id = st.text_input("Customer ID", placeholder="e.g. CUST000002")
        complaint = st.text_area(
            "Customer complaint (optional)",
            placeholder="Paste the customer's message here…",
            height=120,
        )
        submitted = st.form_submit_button("Resolve")

    if not submitted:
        return

    if not mid.strip() or not order_id.strip() or not cust_id.strip():
        st.warning("MID, Order ID, and Customer ID are required.")
        return

    with st.spinner("Resolving transaction…"):
        result, error_message = _call_resolve_api(mid, order_id, cust_id, complaint)

    if error_message:
        st.error(error_message)
        return

    assert result is not None
    st.header(result["issue"])
    _render_escalation_badge(result.get("escalation_required"), result.get("escalation_note"))
    if result.get("response_mode") == "sop_fallback":
        st.caption("Response mode: SOP-based (add GEMINI_API_KEY to .env for Gemini)")
    st.markdown(result["response"])
    st.caption(f"SOP source: {result.get('sop_source', 'unknown')}")


if __name__ == "__main__":
    main()
