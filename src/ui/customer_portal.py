"""Streamlit customer portal for viewing transactions and raising complaints."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import pandas as pd
import streamlit as st

from src.core.customer_auth import authenticate_customer, get_customer_transactions

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
        "selected_order_id": None,
        "complaint_text": "",
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
    st.session_state["page"] = PAGE_LOGIN
    st.session_state["customer"] = None
    st.session_state["selected_order_id"] = None
    st.session_state["complaint_text"] = ""


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

    if st.button("Sign In", type="primary", use_container_width=True):
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
    if not transactions:
        st.info("No transactions found.")
        return

    table = _build_transaction_table(transactions)
    st.dataframe(table, use_container_width=True, hide_index=True)

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
        st.session_state["page"] = PAGE_RESOLUTION
        st.rerun()


def _render_resolution_page() -> None:
    """Render the resolution placeholder page."""
    if st.button("← Back to transactions"):
        st.session_state["page"] = PAGE_DASHBOARD
        st.rerun()

    with st.spinner("Fetching resolution..."):
        st.markdown("### Resolution")
        st.write(f"**Selected Order ID:** {st.session_state.get('selected_order_id') or '(none)'}")
        complaint = st.session_state.get("complaint_text") or ""
        st.write(f"**Complaint:** {complaint if complaint else '(none provided)'}")


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
