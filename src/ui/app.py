"""Streamlit UI for the Paytm Transaction Resolution Copilot."""

from __future__ import annotations

import logging
from typing import Any

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
        try:
            detail = response.json().get("detail")
        except ValueError:
            detail = response.text
        return None, detail or "The resolution API returned an unexpected error."

    try:
        return response.json(), None
    except ValueError as exc:
        logger.error("Invalid JSON from API: %s", exc)
        return None, "Received an invalid response from the API."


def _confidence_for_intent(
    extracted_intents: list[dict[str, Any]],
    intent_name: str,
) -> str:
    """Return the confidence level for a named intent from extracted intents."""
    for intent in extracted_intents:
        if intent.get("intent") == intent_name:
            confidence = intent.get("confidence")
            if isinstance(confidence, str) and confidence.strip():
                return confidence.strip()
    return "unknown"


def _render_intent_panel(result: dict, complaint_provided: bool) -> None:
    """Show intent reconciliation below the escalation badge."""
    if not complaint_provided:
        return

    agreement = result.get("agreement", True)
    conflict = result.get("conflict", False)
    unresolved_intents = result.get("unresolved_intents") or []
    extracted_intents = result.get("extracted_intents") or []
    reconciliation_note = result.get("reconciliation_note", "")

    st.subheader("Intent Analysis")

    if conflict:
        st.markdown(
            '<span style="background-color:#dc3545;color:white;padding:4px 10px;'
            'border-radius:6px;font-weight:600;">Signal conflict detected</span>',
            unsafe_allow_html=True,
        )
        if reconciliation_note:
            st.markdown(reconciliation_note)
        if extracted_intents:
            st.markdown("**What the complaint is signalling:**")
            for intent in extracted_intents:
                name = intent.get("intent", "Unknown")
                confidence = intent.get("confidence", "unknown")
                evidence = intent.get("evidence", "")
                st.markdown(
                    f"- **{name}** ({confidence} confidence)"
                    + (f' — *"{evidence}"*' if evidence else "")
                )
        st.caption("Apply judgment before acting — transaction data and complaint signals disagree.")
        return

    if agreement and not unresolved_intents:
        st.markdown(
            '<span style="background-color:#28a745;color:white;padding:4px 10px;'
            'border-radius:6px;font-weight:600;">All signals aligned</span>',
            unsafe_allow_html=True,
        )
        if reconciliation_note:
            st.caption(reconciliation_note)
        return

    if agreement and unresolved_intents:
        st.markdown(
            '<span style="background-color:#28a745;color:white;padding:4px 10px;'
            'border-radius:6px;font-weight:600;">Primary confirmed</span>',
            unsafe_allow_html=True,
        )
        if reconciliation_note:
            st.caption(reconciliation_note)
        st.markdown(
            '<div style="background-color:#fff3cd;border-left:4px solid #ffc107;'
            'padding:10px 12px;margin-top:8px;border-radius:4px;">'
            "<strong>Additional signals detected</strong></div>",
            unsafe_allow_html=True,
        )
        for intent_name in unresolved_intents:
            confidence = _confidence_for_intent(extracted_intents, intent_name)
            st.markdown(f"- **{intent_name}** ({confidence} confidence)")
        st.caption(
            "Primary issue is solid, but review these secondary signals before closing the case."
        )


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


def _render_groundedness_badge(result: dict) -> None:
    """Show groundedness trust signal before the agent reads the resolution."""
    verified = result.get("groundedness_verified")
    unsupported_claims = result.get("unsupported_claims") or []

    if verified is True:
        st.markdown(
            '<span style="background-color:#28a745;color:white;padding:4px 10px;'
            'border-radius:6px;font-weight:600;">Verified</span>',
            unsafe_allow_html=True,
        )
        return

    if verified is None:
        st.markdown(
            '<span style="background-color:#ffc107;color:#212529;padding:4px 10px;'
            'border-radius:6px;font-weight:600;">Could not verify</span>',
            unsafe_allow_html=True,
        )
        return

    st.markdown(
        '<span style="background-color:#dc3545;color:white;padding:4px 10px;'
        'border-radius:6px;font-weight:600;">Flagged — review unsupported claims</span>',
        unsafe_allow_html=True,
    )
    for claim in unsupported_claims:
        st.markdown(f"- {claim}")


def _render_retrieval_breakdown(result: dict) -> None:
    """Show hybrid retrieval component scores in a collapsed transparency expander."""
    retrieval_scores = result.get("retrieval_scores") or {}
    semantic = float(retrieval_scores.get("semantic", 0.0))
    intent = float(retrieval_scores.get("intent", 0.0))
    structural = float(retrieval_scores.get("structural", 0.0))

    with st.expander("Retrieval breakdown", expanded=False):
        st.caption("How semantic, intent, and structural signals ranked the retrieved SOP.")
        st.markdown(f"**Semantic** — {semantic:.3f}")
        st.progress(min(max(semantic, 0.0), 1.0))
        st.markdown(f"**Intent** — {intent:.3f}")
        st.progress(min(max(intent, 0.0), 1.0))
        st.markdown(f"**Structural** — {structural:.3f}")
        st.progress(min(max(structural, 0.0), 1.0))


def main() -> None:
    """Render the dispute resolution form and results."""
    st.set_page_config(page_title="Paytm Resolution Copilot", page_icon="💳", layout="centered")
    st.title("Paytm Transaction Resolution Copilot")
    st.caption("Look up a transaction and get grounded agent guidance.")

    try:
        health = requests.get(API_HEALTH_URL, timeout=30).json()
        if not health.get("llm_configured"):
            st.warning(
                "No Gemini API key found in `.env`. Add `GEMINI_API_KEY=` (no quotes) from "
                "[Google AI Studio](https://aistudio.google.com/apikey), then restart the servers."
            )
        elif not health.get("llm_ready"):
            st.warning(
                "Gemini API key is present but rejected (expired or invalid). "
                "Create a **new** key at [Google AI Studio](https://aistudio.google.com/apikey), "
                "update `.env` as `GEMINI_API_KEY=your_key` with no quotes, and restart `./run_demo.sh`."
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
        st.caption("Hindi, English or Hinglish — all supported.")
        submitted = st.form_submit_button("Resolve")

    if not submitted:
        return

    if not mid.strip() or not order_id.strip() or not cust_id.strip():
        st.warning("MID, Order ID, and Customer ID are required.")
        return

    complaint_provided = bool(complaint.strip())

    with st.spinner("Resolving transaction…"):
        result, error_message = _call_resolve_api(mid, order_id, cust_id, complaint)

    if error_message:
        st.error(error_message)
        return

    assert result is not None
    primary_issue = result.get("primary_issue") or result.get("issue", "Unknown")
    st.markdown(f"## **{primary_issue}**")
    _render_escalation_badge(result.get("escalation_required"), result.get("escalation_note"))
    _render_intent_panel(result, complaint_provided)
    if result.get("response_mode") == "sop_fallback":
        st.info(
            "Showing SOP-based guidance (Gemini unavailable). Resolution still works — "
            "refresh your API key in `.env` and restart the servers for AI explanations."
        )
    _render_groundedness_badge(result)
    st.markdown(result["response"])
    st.caption(f"SOP source: {result.get('sop_source', 'unknown')}")
    _render_retrieval_breakdown(result)
    st.subheader("Copy case note")
    st.text_area(
        "Case note",
        value=result.get("case_note", ""),
        height=140,
        label_visibility="collapsed",
    )


if __name__ == "__main__":
    main()
