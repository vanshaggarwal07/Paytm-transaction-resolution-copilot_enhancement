"""Streamlit UI for the Paytm Transaction Resolution Copilot."""

from __future__ import annotations

import logging
from typing import Any

import requests
import streamlit as st

logger = logging.getLogger(__name__)

API_HEALTH_URL = "http://localhost:8000/health"
API_RESOLVE_URL = "http://localhost:8000/resolve"
API_EXTRACT_IMAGE_URL = "http://localhost:8000/extract-image"
REQUEST_TIMEOUT_SECONDS = 120

MODE_MANUAL = "Manual Input"
MODE_UPLOAD = "Upload Screenshot"

UI_PHASE_INITIAL = "initial"
UI_PHASE_CLARIFICATION = "clarification"

SCREENSHOT_FIELDS: tuple[tuple[str, str], ...] = (
    ("MID", "MID"),
    ("ORDER_ID", "Order ID"),
    ("CUST_ID", "Customer ID"),
    ("TXN_AMOUNT", "Transaction amount"),
    ("PAYMENT_MODE", "Payment mode"),
    ("TXN_STATUS", "Transaction status"),
)


def _init_session_state() -> None:
    """Ensure session keys exist for the two-phase resolve flow."""
    defaults = {
        "ui_phase": UI_PHASE_INITIAL,
        "input_mode": MODE_MANUAL,
        "mid": "",
        "order_id": "",
        "cust_id": "",
        "complaint": "",
        "agent_answers": "",
        "clarifying_questions": [],
        "result": None,
        "extraction": None,
        "extraction_failed": False,
        "extraction_warning": None,
        "screenshot_field_values": {
            field: "" for field, _ in SCREENSHOT_FIELDS
        },
        "screenshot_complaint": "",
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


def _call_extract_image_api(
    image_bytes: bytes,
    filename: str,
    content_type: str,
) -> tuple[dict | None, str | None]:
    """POST screenshot bytes to /extract-image."""
    try:
        response = requests.post(
            API_EXTRACT_IMAGE_URL,
            files={"file": (filename, image_bytes, content_type)},
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
    except requests.ConnectionError:
        logger.error("Could not connect to API at %s", API_EXTRACT_IMAGE_URL)
        return None, (
            "Could not reach the extraction API at localhost:8000. "
            "Make sure the FastAPI server is running."
        )
    except requests.Timeout:
        return None, "Screenshot extraction timed out. Please try again."
    except requests.RequestException as exc:
        logger.error("Extract-image request failed: %s", exc)
        return None, "Something went wrong while contacting the API. Please try again."

    if response.status_code != 200:
        logger.error("Extract-image returned status %s: %s", response.status_code, response.text)
        try:
            detail = response.json().get("detail")
        except ValueError:
            detail = response.text
        return None, detail or "Screenshot extraction failed."

    try:
        return response.json(), None
    except ValueError as exc:
        logger.error("Invalid JSON from extract-image API: %s", exc)
        return None, "Received an invalid response from the extraction API."


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


def render_resolution(response: dict, complaint_provided: bool) -> None:
    """Render the full resolution panel from a completed /resolve response."""
    primary_issue = response.get("primary_issue") or response.get("issue", "Unknown")
    st.markdown(f"## **{primary_issue}**")
    _render_escalation_badge(response.get("escalation_required"), response.get("escalation_note"))
    _render_intent_panel(response, complaint_provided)
    if response.get("response_mode") == "sop_fallback":
        st.info(
            "Showing SOP-based guidance (Gemini unavailable). Resolution still works — "
            "refresh your API key in `.env` and restart the servers for AI explanations."
        )
    _render_groundedness_badge(response)
    st.markdown(response["response"])
    st.caption(f"SOP source: {response.get('sop_source', 'unknown')}")
    _render_retrieval_breakdown(response)
    st.subheader("Copy case note")
    st.text_area(
        "Case note",
        value=response.get("case_note", ""),
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


def _confidence_tag_html(confidence: str) -> str:
    """Return a small coloured confidence tag for screenshot field rows."""
    normalized = (confidence or "absent").strip().lower()
    if normalized == "high":
        return (
            '<span style="color:#28a745;font-size:0.85rem;">'
            "● High confidence</span>"
        )
    if normalized == "medium":
        return (
            '<span style="color:#ffc107;font-size:0.85rem;">'
            "● Verify</span>"
        )
    return (
        '<span style="color:#dc3545;font-size:0.85rem;">'
        "● Not found — enter manually</span>"
    )


def _apply_extraction_to_fields(extraction: dict[str, Any]) -> None:
    """Populate editable screenshot fields from an extraction response."""
    pre_populated = extraction.get("pre_populated") or {}
    for field, _label in SCREENSHOT_FIELDS:
        entry = extraction.get(field) or {}
        value = entry.get("value")
        st.session_state.screenshot_field_values[field] = (
            pre_populated.get(field)
            or (str(value) if value is not None else "")
            or ""
        )


def _upload_content_type(uploaded_file: Any) -> str:
    """Map Streamlit upload metadata to an API-supported MIME type."""
    if uploaded_file.type == "image/jpg":
        return "image/jpeg"
    return uploaded_file.type or "image/png"


def _render_manual_form() -> None:
    """Manual input mode: existing MID / order / customer / complaint form."""
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
            render_resolution(st.session_state.result, complaint_provided)
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


def _render_upload_mode() -> None:
    """Screenshot upload mode: extract fields from image, then resolve."""
    uploaded_file = st.file_uploader(
        "Upload a transaction dashboard screenshot",
        type=["png", "jpg", "jpeg", "webp"],
    )

    if uploaded_file is not None:
        st.image(uploaded_file, caption="Uploaded screenshot", use_container_width=True)

    if st.button("Extract fields", type="secondary"):
        if uploaded_file is None:
            st.warning("Upload a screenshot before extracting fields.")
        else:
            image_bytes = uploaded_file.getvalue()
            with st.spinner("Reading screenshot..."):
                payload, error_message = _call_extract_image_api(
                    image_bytes,
                    uploaded_file.name,
                    _upload_content_type(uploaded_file),
                )

            if error_message:
                st.error("Extraction failed — please enter the fields manually.")
                st.session_state.extraction = None
                st.session_state.extraction_failed = True
                st.session_state.extraction_warning = None
                st.session_state.screenshot_field_values = {
                    field: "" for field, _ in SCREENSHOT_FIELDS
                }
            else:
                assert payload is not None
                st.session_state.extraction = payload
                st.session_state.extraction_failed = False
                st.session_state.extraction_warning = payload.get("extraction_warning")
                _apply_extraction_to_fields(payload)

    show_fields = (
        st.session_state.extraction is not None or st.session_state.extraction_failed
    )

    if show_fields:
        if st.session_state.extraction_warning:
            st.warning(st.session_state.extraction_warning)

        st.subheader("Extracted fields")
        for field, label in SCREENSHOT_FIELDS:
            entry = (st.session_state.extraction or {}).get(field, {})
            confidence = str(entry.get("confidence", "absent"))
            col_input, col_tag = st.columns([4, 1])
            with col_input:
                st.session_state.screenshot_field_values[field] = st.text_input(
                    label,
                    value=st.session_state.screenshot_field_values.get(field, ""),
                    key=f"screenshot_field_{field}",
                )
            with col_tag:
                st.markdown(_confidence_tag_html(confidence), unsafe_allow_html=True)

        screenshot_complaint = st.text_area(
            "Customer complaint (optional)",
            value=st.session_state.screenshot_complaint,
            placeholder="Paste the customer's message here…",
            height=120,
            key="screenshot_complaint_input",
        )
        st.session_state.screenshot_complaint = screenshot_complaint
        st.caption("Hindi, English or Hinglish — all supported.")

        if st.button("Resolve", type="primary"):
            mid = st.session_state.screenshot_field_values.get("MID", "").strip()
            order_id = st.session_state.screenshot_field_values.get("ORDER_ID", "").strip()
            cust_id = st.session_state.screenshot_field_values.get("CUST_ID", "").strip()

            if not mid or not order_id or not cust_id:
                st.warning("MID, Order ID, and Customer ID are required.")
                return

            with st.spinner("Resolving transaction…"):
                payload, error_message, status_code = _call_resolve_api(
                    mid,
                    order_id,
                    cust_id,
                    screenshot_complaint,
                )

            if error_message:
                st.error(error_message)
                if status_code == 404:
                    _reset_to_initial()
                return

            assert payload is not None
            _handle_resolve_response(
                payload,
                mid=mid,
                order_id=order_id,
                cust_id=cust_id,
                complaint=screenshot_complaint,
            )
            st.rerun()

    if st.session_state.result is not None and st.session_state.ui_phase == UI_PHASE_INITIAL:
        complaint_provided = bool(st.session_state.screenshot_complaint.strip())
        render_resolution(st.session_state.result, complaint_provided)


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
            st.session_state.screenshot_complaint = ""
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
        st.session_state.screenshot_complaint = ""
        st.rerun()

    if not submit_answers:
        return

    if not any(answer.strip() for answer in answers):
        st.warning("Please answer at least one question before submitting.")
        return

    agent_answers = _format_agent_answers(questions, answers)
    st.session_state.agent_answers = agent_answers

    with st.spinner("Resolving with your answers…"):
        complaint = (
            st.session_state.complaint
            if st.session_state.input_mode == MODE_MANUAL
            else st.session_state.screenshot_complaint
        )
        payload, error_message, status_code = _call_resolve_api(
            st.session_state.mid,
            st.session_state.order_id,
            st.session_state.cust_id,
            complaint,
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
            st.session_state.screenshot_complaint = ""
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
        complaint=complaint,
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

    input_mode = st.radio(
        "Input mode",
        [MODE_MANUAL, MODE_UPLOAD],
        index=0 if st.session_state.input_mode == MODE_MANUAL else 1,
        horizontal=True,
        key="input_mode_radio",
    )
    st.session_state.input_mode = input_mode

    if st.session_state.ui_phase == UI_PHASE_CLARIFICATION:
        _render_clarification_form()
        return

    if input_mode == MODE_UPLOAD:
        _render_upload_mode()
        return

    _render_manual_form()


if __name__ == "__main__":
    main()
