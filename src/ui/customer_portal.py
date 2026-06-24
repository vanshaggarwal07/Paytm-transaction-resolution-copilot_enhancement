"""Streamlit customer portal for viewing transactions and raising complaints."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

import pandas as pd
import requests
import streamlit as st

from src.core.customer_auth import authenticate_customer, get_customer_transactions

logger = logging.getLogger(__name__)

API_RESOLVE_URL = "http://localhost:8000/resolve"
REQUEST_TIMEOUT_SECONDS = 120

PAGE_LOGIN = "login"
PAGE_DASHBOARD = "dashboard"
PAGE_RESOLUTION = "resolution"

STATUS_LABELS = {
    "Success": "✅ Success",
    "Pending": "⏳ Pending",
    "Failed": "❌ Failed",
}


def _init_session_state() -> None:
    """Ensure default session keys exist for the customer portal flow."""
    defaults: dict[str, Any] = {
        "page": PAGE_LOGIN,
        "customer": None,
        "transactions": [],
        "selected_order_id": None,
        "complaint_text": "",
        "resolution": None,
        "resolution_error": None,
        "resolution_queued": False,
        "customer_feedback": None,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def _format_timestamp(raw_timestamp: str) -> str:
    """Format an ISO timestamp as DD MMM YYYY HH:MM."""
    try:
        parsed = datetime.fromisoformat(str(raw_timestamp))
        return parsed.strftime("%d %b %Y %H:%M")
    except ValueError:
        return str(raw_timestamp)


def _format_amount(raw_amount: Any) -> str:
    """Format a transaction amount in Indian rupee style."""
    try:
        return f"₹{float(raw_amount):,.2f}"
    except (TypeError, ValueError):
        return str(raw_amount)


def _build_transaction_table(transactions: list[dict[str, Any]]) -> pd.DataFrame:
    """Return a customer-facing transaction table with display columns only."""
    rows: list[dict[str, str]] = []
    for txn in transactions:
        status = str(txn.get("TXN_STATUS", ""))
        rows.append(
            {
                "Order ID": str(txn.get("ORDER_ID", "")),
                "Date & Time": _format_timestamp(str(txn.get("TXN_TIMESTAMP", ""))),
                "Amount": _format_amount(txn.get("TXN_AMOUNT")),
                "Payment Mode": str(txn.get("PAYMENT_MODE", "")),
                "Status": status,
                "Status Label": STATUS_LABELS.get(status, status),
            }
        )
    return pd.DataFrame(rows)


def _sign_out() -> None:
    """Clear portal session state and return to the login page."""
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    _init_session_state()
    st.rerun()


def _get_cached_transactions() -> list[dict[str, Any]]:
    """Return cached transactions, reloading from CSV when the cache is empty."""
    transactions = st.session_state.get("transactions") or []
    if transactions:
        return transactions

    customer = st.session_state.get("customer") or {}
    cust_id = str(customer.get("CUST_ID", "")).strip()
    if not cust_id:
        return []

    transactions = get_customer_transactions(cust_id)
    st.session_state["transactions"] = transactions
    return transactions


def _clear_resolution_state() -> None:
    """Clear resolution fetch results when leaving the resolution page."""
    st.session_state["resolution"] = None
    st.session_state["resolution_error"] = None
    st.session_state["resolution_queued"] = False
    st.session_state["customer_feedback"] = None


def _return_to_dashboard() -> None:
    """Return to the transaction dashboard and drop cached resolution data."""
    _clear_resolution_state()
    st.session_state["page"] = PAGE_DASHBOARD
    st.rerun()


def _find_transaction(order_id: str) -> dict[str, Any] | None:
    """Return the selected transaction from the cached customer transaction list."""
    for txn in _get_cached_transactions():
        if str(txn.get("ORDER_ID", "")) == order_id:
            return txn
    return None


def _fetch_resolution(transaction: dict[str, Any], complaint: str) -> tuple[str, dict[str, Any] | None]:
    """POST to /resolve and return a status tag plus the JSON payload when available."""
    payload = {
        "mid": transaction["MID"],
        "order_id": transaction["ORDER_ID"],
        "cust_id": transaction["CUST_ID"],
        "complaint": complaint,
    }
    try:
        response = requests.post(
            API_RESOLVE_URL,
            json=payload,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
    except requests.RequestException as exc:
        logger.warning("Resolution request failed: %s", exc)
        return "connection_error", None

    if response.status_code == 404:
        return "not_found", None

    try:
        data = response.json()
    except ValueError:
        logger.warning("Resolution response was not valid JSON")
        return "connection_error", None

    if response.status_code != 200:
        logger.warning("Resolution request returned HTTP %s", response.status_code)
        return "connection_error", None

    return "ok", data


def _render_login_page() -> None:
    """Render the customer sign-in page."""
    st.markdown(
        """
        <div style="text-align:center; padding: 1rem 0 0.5rem 0;">
            <h1 style="margin-bottom: 0.25rem;">💳 Paytm Customer Portal</h1>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.markdown("### Welcome back")

    username = st.text_input("USERNAME", key="login_username")
    password = st.text_input("PASSWORD", type="password", key="login_password")

    if st.button("Sign In", type="primary", width="stretch"):
        customer = authenticate_customer(username.strip(), password)
        if customer is None:
            st.error("Invalid username or password. Please try again.")
            return

        st.session_state["customer"] = {
            key: value for key, value in customer.items() if key != "PASSWORD"
        }
        st.session_state["page"] = PAGE_DASHBOARD
        st.session_state["selected_order_id"] = None
        st.session_state["complaint_text"] = ""
        st.session_state["transactions"] = []
        _clear_resolution_state()
        st.rerun()


def _render_dashboard_page() -> None:
    """Render transaction history and complaint submission."""
    customer = st.session_state.get("customer") or {}
    cust_id = customer.get("CUST_ID", "")
    customer_name = customer.get("NAME", "Customer")

    header_left, header_right = st.columns([5, 1])
    with header_left:
        st.header(f"Hello, {customer_name}")
        st.subheader("Your recent transactions")
    with header_right:
        st.write("")
        if st.button("Sign Out"):
            _sign_out()
            st.rerun()

    transactions = get_customer_transactions(cust_id)
    st.session_state["transactions"] = transactions
    if not transactions:
        st.info("No transactions found.")
        return

    table = _build_transaction_table(transactions)
    st.dataframe(table, width="stretch", hide_index=True)

    st.markdown("### Raise a Complaint")
    order_ids = [str(txn.get("ORDER_ID", "")) for txn in transactions if txn.get("ORDER_ID")]
    selected_order_id = st.selectbox("Select a transaction", order_ids, key="complaint_order_select")
    complaint_text = st.text_area(
        "Describe your issue",
        placeholder="e.g. Money was deducted but I haven't received confirmation",
        key="complaint_text_input",
    )

    if st.button("Submit Complaint", type="primary"):
        st.session_state["selected_order_id"] = selected_order_id
        st.session_state["complaint_text"] = complaint_text.strip()
        _clear_resolution_state()
        st.session_state["page"] = PAGE_RESOLUTION
        st.rerun()


def _ensure_resolution_loaded() -> bool:
    """Fetch /resolve once per complaint submission. Returns True when ready to render."""
    if st.session_state.get("resolution") is not None:
        return True
    if st.session_state.get("resolution_error"):
        return True

    order_id = st.session_state.get("selected_order_id")
    transaction = _find_transaction(str(order_id or ""))
    if transaction is None:
        st.session_state["resolution_error"] = "not_found"
        st.rerun()

    complaint = st.session_state.get("complaint_text") or ""
    with st.spinner("Our AI is looking into your case..."):
        status, payload = _fetch_resolution(transaction, complaint)

    if status == "not_found":
        st.session_state["resolution_error"] = "not_found"
        st.rerun()
    if status == "connection_error":
        st.session_state["resolution_error"] = "connection"
        st.rerun()

    assert payload is not None
    st.session_state["resolution"] = payload
    if payload.get("status") == "clarification_needed":
        st.session_state["resolution_queued"] = True
    st.rerun()


def _render_customer_reply(customer_reply: str) -> None:
    """Render the customer-facing reply in a lightly styled container."""
    escaped = (
        customer_reply.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace("\n", "<br>")
    )
    st.markdown(
        f"""
        <div style="background-color:#f7f9fc; border:1px solid #e6ebf2;
                    border-radius:10px; padding:1.25rem; line-height:1.6;">
            {escaped}
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_resolution_page() -> None:
    """Render the customer resolution page."""
    if not _ensure_resolution_loaded():
        return

    resolution_error = st.session_state.get("resolution_error")
    if resolution_error == "not_found":
        st.error("We could not find the details for this transaction. Please contact support.")
        if st.button("← Go back"):
            _return_to_dashboard()
        return

    if resolution_error == "connection":
        st.warning("Our systems are temporarily unavailable. Please try again in a few minutes.")
        if st.button("← Go back", key="back_connection_error"):
            _return_to_dashboard()
        return

    resolution = st.session_state.get("resolution")
    if resolution is None:
        st.info("Loading your case update...")
        return

    if st.session_state.get("resolution_queued") or resolution.get("status") == "clarification_needed":
        st.success(
            "We're reviewing your case. Our support team will be in touch shortly."
        )
        if st.button("← Back to transactions"):
            _return_to_dashboard()
        return

    customer_reply = str(resolution.get("customer_reply") or "").strip()
    escalation_required = resolution.get("escalation_required")

    st.markdown("### Here's what we found")
    if escalation_required is True:
        st.info("🔄 Your case has been escalated to our team")
    else:
        st.success("✅ Your issue is being resolved")

    if customer_reply:
        with st.container():
            _render_customer_reply(customer_reply)
    else:
        st.info("We're preparing an update for you. Please check back shortly.")

    feedback = st.session_state.get("customer_feedback")
    if feedback == "helpful":
        st.success("Thank you for your feedback!")
        if st.button("← Back to transactions", key="back_after_helpful"):
            _return_to_dashboard()
        return
    if feedback == "not_helpful":
        st.warning("We're sorry to hear that. A support agent will review your case shortly.")
        if st.button("← Back to transactions", key="back_after_not_helpful"):
            _return_to_dashboard()
        return

    st.markdown("#### Was this helpful?")
    helpful_col, not_helpful_col, _spacer = st.columns([1, 1, 2])
    with helpful_col:
        if st.button("👍 Yes, thank you", width="stretch"):
            st.session_state["customer_feedback"] = "helpful"
            st.rerun()
    with not_helpful_col:
        if st.button("👎 No, I need more help", width="stretch"):
            st.session_state["customer_feedback"] = "not_helpful"
            st.rerun()

    if st.button("← Back to transactions", key="back_before_feedback"):
        _return_to_dashboard()


def main() -> None:
    """Run the customer portal application."""
    st.set_page_config(
        page_title="Paytm Customer Portal",
        page_icon="💳",
        layout="wide",
    )
    _init_session_state()

    page = st.session_state.get("page", PAGE_LOGIN)
    if page != PAGE_LOGIN and not st.session_state.get("customer"):
        st.session_state["page"] = PAGE_LOGIN
        page = PAGE_LOGIN

    if page == PAGE_LOGIN:
        _render_login_page()
    elif page == PAGE_DASHBOARD:
        _render_dashboard_page()
    elif page == PAGE_RESOLUTION:
        _render_resolution_page()
    else:
        st.session_state["page"] = PAGE_LOGIN
        st.rerun()


if __name__ == "__main__":
    main()
