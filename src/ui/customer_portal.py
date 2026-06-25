"""Streamlit customer portal for viewing transactions and raising complaints."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

import requests
import streamlit as st

from src.core.customer_auth import authenticate_customer, get_customer_transactions

logger = logging.getLogger(__name__)

API_RESOLVE_URL = "http://localhost:8000/resolve"
REQUEST_TIMEOUT_SECONDS = 120

PAGE_LOGIN = "login"
PAGE_DASHBOARD = "dashboard"
PAGE_RESOLUTION = "resolution"

CUSTOMER_PRIMARY_COLOR = "#00B9F1"
CUSTOMER_PRIMARY_LIGHT = "#33ccf5"
CUSTOMER_PRIMARY_DARK = "#0090c4"
PAGE_BACKGROUND = "#F8F9FA"

LOGIN_CSS = f"""
<style>
  :root {{
    --portal-primary: {CUSTOMER_PRIMARY_COLOR};
    --portal-primary-light: {CUSTOMER_PRIMARY_LIGHT};
    --portal-primary-dark: {CUSTOMER_PRIMARY_DARK};
  }}
  .portal-login-card {{
    background: linear-gradient(
      135deg,
      var(--portal-primary-dark) 0%,
      var(--portal-primary) 55%,
      var(--portal-primary-light) 100%
    );
    padding: 2.5rem 2rem;
    border-radius: 16px;
    color: white;
    margin-bottom: 1.5rem;
    box-shadow: 0 12px 32px rgba(0, 144, 196, 0.25);
  }}
  .portal-login-card h1 {{
    color: white !important;
    margin-bottom: 0.25rem;
  }}
  .portal-login-card p {{
    color: rgba(255, 255, 255, 0.92);
    margin-bottom: 0;
  }}
  div[data-testid="stFormSubmitButton"] > button {{
    border-radius: 10px !important;
    font-weight: 600;
  }}
  div[data-testid="stFormSubmitButton"] > button[kind="primaryFormSubmit"],
  div[data-testid="stFormSubmitButton"] > button[data-testid="stBaseButton-primaryFormSubmit"] {{
    background-color: {CUSTOMER_PRIMARY_COLOR} !important;
    border-color: {CUSTOMER_PRIMARY_COLOR} !important;
    color: #ffffff !important;
  }}
</style>
"""

DASHBOARD_CSS = f"""
<style>
  :root {{
    --portal-primary: {CUSTOMER_PRIMARY_COLOR};
    --portal-primary-light: {CUSTOMER_PRIMARY_LIGHT};
    --portal-primary-dark: {CUSTOMER_PRIMARY_DARK};
  }}
  .stApp {{
    background-color: {PAGE_BACKGROUND};
  }}
  [data-testid="stSidebar"] {{
    background-color: #ffffff;
    border-right: 1px solid #e6ebf2;
  }}
  [data-testid="stSidebar"] h3 {{
    color: {CUSTOMER_PRIMARY_COLOR};
    margin-bottom: 0.25rem;
  }}
  div.stButton > button {{
    border-radius: 10px !important;
    font-weight: 600;
    border: 1px solid #d7dee8;
  }}
  div.stButton > button[kind="primary"],
  div.stButton > button[data-testid="stBaseButton-primary"] {{
    background-color: {CUSTOMER_PRIMARY_COLOR} !important;
    border-color: {CUSTOMER_PRIMARY_COLOR} !important;
    color: #ffffff !important;
  }}
  div.stButton > button[kind="primary"]:hover,
  div.stButton > button[data-testid="stBaseButton-primary"]:hover {{
    background-color: #00a5d8 !important;
    border-color: #00a5d8 !important;
  }}
  .portal-brand {{
    color: {CUSTOMER_PRIMARY_COLOR};
    font-weight: 700;
    letter-spacing: 0.02em;
  }}
  .portal-card {{
    background: #ffffff;
    border: 1px solid #e6ebf2;
    border-radius: 12px;
    padding: 1rem 1.25rem;
    margin-bottom: 1rem;
  }}
  .portal-txn-table {{
    width: 100%;
    border-collapse: collapse;
    background: #ffffff;
    border: 1px solid #e6ebf2;
    border-radius: 12px;
    overflow: hidden;
    margin-bottom: 1rem;
  }}
  .portal-txn-table th {{
    background: #f1f5f9;
    color: #334155;
    text-align: left;
    padding: 0.75rem 1rem;
    font-size: 0.85rem;
    text-transform: uppercase;
    letter-spacing: 0.04em;
  }}
  .portal-txn-table td {{
    padding: 0.85rem 1rem;
    border-top: 1px solid #eef2f7;
    color: #1f2937;
    font-size: 0.95rem;
  }}
  .status-pill {{
    display: inline-block;
    padding: 0.2rem 0.65rem;
    border-radius: 999px;
    font-size: 0.8rem;
    font-weight: 600;
    white-space: nowrap;
  }}
  .status-pill-success {{
    background-color: #D1FAE5;
    color: #065F46;
  }}
  .status-pill-pending {{
    background-color: #FEF3C7;
    color: #92400E;
  }}
  .status-pill-failed {{
    background-color: #FEE2E2;
    color: #991B1B;
  }}
  .portal-reply-box {{
    background-color: #ffffff;
    border: 1px solid #e6ebf2;
    border-left: 4px solid {CUSTOMER_PRIMARY_COLOR};
    border-radius: 10px;
    padding: 1.25rem;
    line-height: 1.6;
    color: #1f2937;
  }}
</style>
"""


def _init_session_state() -> None:
    """Ensure default session keys exist for the customer portal flow."""
    defaults: dict[str, Any] = {
        "page": PAGE_LOGIN,
        "customer": None,
        "login_error": None,
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


def _inject_portal_styles(*, login_page: bool = False) -> None:
    """Inject portal CSS — login page uses merchant-style header without light bg override."""
    st.markdown(LOGIN_CSS if login_page else DASHBOARD_CSS, unsafe_allow_html=True)


def _mask_email(email: str) -> str:
    """Mask an email as first 3 characters + *** + @domain."""
    normalized = str(email).strip()
    if "@" not in normalized:
        return "***"
    local_part, domain = normalized.split("@", 1)
    prefix = local_part[:3] if len(local_part) >= 3 else local_part
    return f"{prefix}***@{domain}"


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


def _status_pill_html(status: str) -> str:
    """Return an HTML status badge pill for the given transaction status."""
    css_class = {
        "Success": "status-pill-success",
        "Pending": "status-pill-pending",
        "Failed": "status-pill-failed",
    }.get(status, "status-pill-pending")
    label = {
        "Success": "Success",
        "Pending": "Pending",
        "Failed": "Failed",
    }.get(status, status)
    return f'<span class="status-pill {css_class}">{label}</span>'


def _render_transactions_table(transactions: list[dict[str, Any]]) -> None:
    """Render the customer transaction history as an HTML table with status pills."""
    rows: list[str] = []
    for txn in transactions:
        status = str(txn.get("TXN_STATUS", ""))
        rows.append(
            "<tr>"
            f"<td>{txn.get('ORDER_ID', '')}</td>"
            f"<td>{_format_timestamp(str(txn.get('TXN_TIMESTAMP', '')))}</td>"
            f"<td>{_format_amount(txn.get('TXN_AMOUNT'))}</td>"
            f"<td>{txn.get('PAYMENT_MODE', '')}</td>"
            f"<td>{_status_pill_html(status)}</td>"
            "</tr>"
        )

    table_html = (
        '<table class="portal-txn-table">'
        "<thead><tr>"
        "<th>Order ID</th>"
        "<th>Date &amp; Time</th>"
        "<th>Amount</th>"
        "<th>Payment Mode</th>"
        "<th>Status</th>"
        "</tr></thead>"
        f"<tbody>{''.join(rows)}</tbody>"
        "</table>"
    )
    st.markdown(table_html, unsafe_allow_html=True)


def _transaction_metrics(
    transactions: list[dict[str, Any]],
) -> tuple[int, int, int]:
    """Return total, successful, and pending/failed transaction counts."""
    total = len(transactions)
    successful = sum(1 for txn in transactions if txn.get("TXN_STATUS") == "Success")
    pending_or_failed = sum(
        1 for txn in transactions if txn.get("TXN_STATUS") in ("Pending", "Failed")
    )
    return total, successful, pending_or_failed


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


def _render_sidebar() -> None:
    """Render authenticated navigation in the sidebar."""
    customer = st.session_state.get("customer") or {}
    with st.sidebar:
        st.markdown(
            f'<p class="portal-brand">💳 Paytm</p>',
            unsafe_allow_html=True,
        )
        st.markdown(f"### {customer.get('NAME', 'Customer')}")
        st.markdown(
            f"<small>{_mask_email(str(customer.get('EMAIL', '')))}</small>",
            unsafe_allow_html=True,
        )
        st.divider()
        if st.button("My Transactions", width="stretch"):
            _clear_resolution_state()
            st.session_state["page"] = PAGE_DASHBOARD
            st.rerun()
        if st.button("Sign Out", width="stretch"):
            _sign_out()


def _render_login_page() -> None:
    """Render the customer sign-in experience."""
    st.markdown(
        """
        <div class="portal-login-card">
            <h1>🧑‍💼 Paytm Customer Portal</h1>
            <p>Manage your transactions and payment support</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    col_left, col_center, col_right = st.columns([1, 1.2, 1])
    with col_center:
        st.markdown("### Sign in to your account")
        st.caption("Use your customer username and password to access the dashboard.")

        with st.form("customer_login_form", clear_on_submit=False):
            username = st.text_input("USERNAME", placeholder="e.g. henry010")
            password = st.text_input("PASSWORD", type="password", placeholder="Enter password")
            submitted = st.form_submit_button("Sign In", use_container_width=True, type="primary")

        if submitted:
            customer = authenticate_customer(username.strip(), password)
            if customer is None:
                st.session_state["login_error"] = "Invalid username or password. Please try again."
            else:
                st.session_state["customer"] = {
                    key: value for key, value in customer.items() if key != "PASSWORD"
                }
                st.session_state["page"] = PAGE_DASHBOARD
                st.session_state["selected_order_id"] = None
                st.session_state["complaint_text"] = ""
                st.session_state["transactions"] = []
                st.session_state["login_error"] = None
                _clear_resolution_state()
                st.rerun()

        if st.session_state.get("login_error"):
            st.error(st.session_state["login_error"])


def _render_dashboard_page() -> None:
    """Render transaction history and complaint submission."""
    _render_sidebar()

    customer = st.session_state.get("customer") or {}
    cust_id = customer.get("CUST_ID", "")
    customer_name = customer.get("NAME", "Customer")

    st.header(f"Hello, {customer_name}")
    st.subheader("Your recent transactions")

    transactions = get_customer_transactions(cust_id)
    st.session_state["transactions"] = transactions
    if not transactions:
        st.info("No transactions found.")
        return

    total_count, success_count, pending_failed_count = _transaction_metrics(transactions)
    metric_col_1, metric_col_2, metric_col_3 = st.columns(3)
    with metric_col_1:
        st.metric("Total Transactions", total_count)
    with metric_col_2:
        st.metric("Successful", success_count)
    with metric_col_3:
        st.metric("Pending or Failed", pending_failed_count)

    _render_transactions_table(transactions)

    st.markdown("### Raise a Complaint")
    order_ids = [str(txn.get("ORDER_ID", "")) for txn in transactions if txn.get("ORDER_ID")]
    selected_order_id = st.selectbox("Select a transaction", order_ids, key="complaint_order_select")
    complaint_text = st.text_area(
        "Describe your issue",
        placeholder="e.g. Money was deducted but I haven't received confirmation",
        key="complaint_text_input",
    )

    if st.button("Submit Complaint", type="primary", width="stretch"):
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
        f'<div class="portal-reply-box">{escaped}</div>',
        unsafe_allow_html=True,
    )


def _render_resolution_page() -> None:
    """Render the customer resolution page."""
    _render_sidebar()

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
        initial_sidebar_state="collapsed",
    )
    _init_session_state()

    page = st.session_state.get("page", PAGE_LOGIN)
    if page != PAGE_LOGIN and not st.session_state.get("customer"):
        st.session_state["page"] = PAGE_LOGIN
        page = PAGE_LOGIN

    _inject_portal_styles(login_page=(page == PAGE_LOGIN))

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
