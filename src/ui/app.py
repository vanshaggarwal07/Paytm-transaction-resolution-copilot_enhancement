"""Streamlit UI for the Paytm Transaction Resolution Copilot."""

from __future__ import annotations

import logging
from typing import Any

import requests
import streamlit as st

logger = logging.getLogger(__name__)

API_HEALTH_URL = "http://localhost:8000/health"
API_RESOLVE_URL = "http://localhost:8000/resolve"
REQUEST_TIMEOUT_SECONDS = 120

UI_PHASE_INITIAL = "initial"
UI_PHASE_CLARIFICATION = "clarification"


def _init_session_state() -> None:
    """Ensure session keys exist for the two-phase resolve flow."""
    defaults = {
        "ui_phase": UI_PHASE_INITIAL,
        "mid": "",
        "order_id": "",
        "cust_id": "",
        "complaint": "",
        "agent_answers": "",
        "clarifying_questions": [],
        "result": None,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def _reset_to_initial() -> None:
    """Clear clarification state and return to the initial form."""
    st.session_state.ui_phase = UI_PHASE_INITIAL
    st.session_state.agent_answers = ""
    st.session_state.clarifying_questions = []
    st.session_state.result = None


def _format_agent_answers(questions: list[str], answers: list[str]) -> str:
    """Build Q/A context string for the second /resolve call."""
    blocks: list[str] = []
    for index, (question, answer) in enumerate(zip(questions, answers), start=1):
        cleaned_answer = answer.strip()
        if cleaned_answer:
            blocks.append(f"Q{index}: {question}\nA: {cleaned_answer}")
    return "\n\n".join(blocks)


def _call_resolve_api(
    mid: str,
    order_id: str,
    cust_id: str,
    complaint: str,
    agent_answers: str = "",
) -> tuple[dict | None, str | None, int | None]:
    """POST to the resolution API and return payload, error message, and status code."""
    payload = {
        "mid": mid.strip(),
        "order_id": order_id.strip(),
        "cust_id": cust_id.strip(),
        "complaint": complaint.strip(),
        "agent_answers": agent_answers.strip(),
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
        ), None
    except requests.Timeout:
        logger.error("API request timed out for ORDER_ID=%s", order_id)
        return None, "The resolution API timed out. Please try again.", None
    except requests.RequestException as exc:
        logger.error("API request failed: %s", exc)
        return None, "Something went wrong while contacting the API. Please try again.", None

    if response.status_code == 404:
        return None, (
            "Transaction not found. Please check the MID, Order ID, and "
            "Customer ID and try again."
        ), 404

    if response.status_code != 200:
        logger.error("API returned status %s: %s", response.status_code, response.text)
        try:
            detail = response.json().get("detail")
        except ValueError:
            detail = response.text
        return None, detail or "The resolution API returned an unexpected error.", response.status_code

    try:
        return response.json(), None, response.status_code
    except ValueError as exc:
        logger.error("Invalid JSON from API: %s", exc)
        return None, "Received an invalid response from the API.", response.status_code


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


def _render_resolution_result(result: dict, complaint_provided: bool) -> None:
    """Render the full resolution panel from a completed /resolve response."""
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


def _handle_resolve_response(
    payload: dict,
    *,
    mid: str,
    order_id: str,
    cust_id: str,
    complaint: str,
) -> None:
    """Route API response into clarification or resolution UI state."""
    st.session_state.mid = mid
    st.session_state.order_id = order_id
    st.session_state.cust_id = cust_id
    st.session_state.complaint = complaint

    if payload.get("status") == "clarification_needed":
        st.session_state.ui_phase = UI_PHASE_CLARIFICATION
        st.session_state.clarifying_questions = payload.get("clarifying_questions") or []
        st.session_state.result = None
        return

    st.session_state.ui_phase = UI_PHASE_INITIAL
    st.session_state.clarifying_questions = []
    st.session_state.result = payload


def _render_initial_form() -> None:
    """State 1: initial transaction lookup and optional complaint."""
    with st.form("resolve_form"):
        mid = st.text_input("MID", value=st.session_state.mid, placeholder="e.g. MID000002")
        order_id = st.text_input(
            "Order ID",
            value=st.session_state.order_id,
            placeholder="e.g. ORD000002",
        )
        cust_id = st.text_input(
            "Customer ID",
            value=st.session_state.cust_id,
            placeholder="e.g. CUST000002",
        )
        complaint = st.text_area(
            "Customer complaint (optional)",
            value=st.session_state.complaint,
            placeholder="Paste the customer's message here…",
            height=120,
        )
        st.caption("Hindi, English or Hinglish — all supported.")
        submitted = st.form_submit_button("Resolve")

    if not submitted:
        if st.session_state.result is not None:
            complaint_provided = bool(st.session_state.complaint.strip())
            _render_resolution_result(st.session_state.result, complaint_provided)
        return

    if not mid.strip() or not order_id.strip() or not cust_id.strip():
        st.warning("MID, Order ID, and Customer ID are required.")
        return

    with st.spinner("Resolving transaction…"):
        payload, error_message, status_code = _call_resolve_api(mid, order_id, cust_id, complaint)

    if error_message:
        st.error(error_message)
        if status_code == 404:
            _reset_to_initial()
            st.session_state.mid = ""
            st.session_state.order_id = ""
            st.session_state.cust_id = ""
            st.session_state.complaint = ""
        return

    assert payload is not None
    _handle_resolve_response(
        payload,
        mid=mid,
        order_id=order_id,
        cust_id=cust_id,
        complaint=complaint,
    )
    st.rerun()


def _render_clarification_form() -> None:
    """State 2: collect agent answers to clarifying questions."""
    st.markdown("### The assistant needs more information")
    st.caption(
        f"Transaction: **{st.session_state.mid}** / "
        f"**{st.session_state.order_id}** / **{st.session_state.cust_id}**"
    )

    questions = st.session_state.clarifying_questions or []
    if not questions:
        st.warning("No clarifying questions were returned. Start over and try again.")
        if st.button("Start over", type="secondary"):
            _reset_to_initial()
            st.session_state.mid = ""
            st.session_state.order_id = ""
            st.session_state.cust_id = ""
            st.session_state.complaint = ""
            st.rerun()
        return

    with st.form("clarification_form"):
        answers: list[str] = []
        for index, question in enumerate(questions, start=1):
            st.markdown(f"**{index}. {question}**")
            answers.append(
                st.text_input(
                    f"Answer {index}",
                    key=f"clarify_answer_{index}",
                    label_visibility="collapsed",
                    placeholder="Type a short factual answer…",
                )
            )

        col_submit, col_reset = st.columns([1, 1])
        with col_submit:
            submit_answers = st.form_submit_button("Submit answers", type="primary")
        with col_reset:
            start_over = st.form_submit_button("Start over")

    if start_over:
        _reset_to_initial()
        st.session_state.mid = ""
        st.session_state.order_id = ""
        st.session_state.cust_id = ""
        st.session_state.complaint = ""
        st.rerun()

    if not submit_answers:
        return

    if not any(answer.strip() for answer in answers):
        st.warning("Please answer at least one question before submitting.")
        return

    agent_answers = _format_agent_answers(questions, answers)
    st.session_state.agent_answers = agent_answers

    with st.spinner("Resolving with your answers…"):
        payload, error_message, status_code = _call_resolve_api(
            st.session_state.mid,
            st.session_state.order_id,
            st.session_state.cust_id,
            st.session_state.complaint,
            agent_answers=agent_answers,
        )

    if error_message:
        st.error(error_message)
        if status_code == 404:
            _reset_to_initial()
            st.session_state.mid = ""
            st.session_state.order_id = ""
            st.session_state.cust_id = ""
            st.session_state.complaint = ""
            st.rerun()
        return

    assert payload is not None
    if payload.get("status") == "clarification_needed":
        st.session_state.clarifying_questions = payload.get("clarifying_questions") or []
        st.warning("More clarification is still needed. Review the updated questions below.")
        st.rerun()

    _handle_resolve_response(
        payload,
        mid=st.session_state.mid,
        order_id=st.session_state.order_id,
        cust_id=st.session_state.cust_id,
        complaint=st.session_state.complaint,
    )
    st.rerun()


def main() -> None:
    """Render the dispute resolution form and results."""
    st.set_page_config(page_title="Paytm Resolution Copilot", page_icon="💳", layout="centered")
    st.title("Paytm Transaction Resolution Copilot")
    st.caption("Look up a transaction and get grounded agent guidance.")

    _init_session_state()

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

    if st.session_state.ui_phase == UI_PHASE_CLARIFICATION:
        _render_clarification_form()
        return

    _render_initial_form()


if __name__ == "__main__":
    main()
