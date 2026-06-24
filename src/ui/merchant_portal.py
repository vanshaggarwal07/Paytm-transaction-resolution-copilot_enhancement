"""Streamlit merchant portal for payment operations monitoring."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

import altair as alt
import pandas as pd
import streamlit as st

from src.core.merchant_analytics import (
    authenticate_merchant,
    get_flagged_transactions,
    get_issue_breakdown,
    get_merchant_alerts,
    get_merchant_summary,
)
from src.issue_taxonomy import IssueType

logger = logging.getLogger(__name__)

PAGE_LOGIN = "login"
PAGE_DASHBOARD = "dashboard"

# Merchant portal accent — deep Paytm blue. Customer portal uses light blue (#00baf2).
MERCHANT_PRIMARY_COLOR = "#003580"
MERCHANT_PRIMARY_LIGHT = "#1a4fa3"
MERCHANT_PRIMARY_DARK = "#00245a"

PAYMENT_MODE_OPTIONS: tuple[str, ...] = ("All", "UPI", "Card", "Wallet", "NetBanking")
FLAGGED_CSV_COLUMNS: tuple[str, ...] = (
    "ORDER_ID",
    "TXN_TIMESTAMP",
    "TXN_AMOUNT",
    "PAYMENT_MODE",
    "TXN_STATUS",
    "issue",
    "AGE_HOURS",
)

ISSUE_SEVERITY: dict[str, str] = {
    IssueType.NORMAL_SUCCESS.value: "green",
    IssueType.REFUND_COMPLETED.value: "green",
    IssueType.UPI_PENDING.value: "amber",
    IssueType.REFUND_PENDING.value: "amber",
    IssueType.SETTLEMENT_DELAY.value: "amber",
    IssueType.AMOUNT_DEBITED_MERCHANT_NOT_CREDITED.value: "red",
    IssueType.FAILED_PAYMENT.value: "red",
    IssueType.SETTLEMENT_FAILURE.value: "red",
    IssueType.CHARGEBACK_DISPUTE.value: "red",
    IssueType.DUPLICATE_DEBIT.value: "red",
    IssueType.RECONCILIATION_MISMATCH.value: "red",
}

SEVERITY_COLORS: dict[str, str] = {
    "green": "#22c55e",
    "amber": "#f59e0b",
    "red": "#ef4444",
}

RECOMMENDED_ACTIONS: dict[str, str] = {
    IssueType.AMOUNT_DEBITED_MERCHANT_NOT_CREDITED.value: (
        "Await T+1 settlement. Escalate if unresolved after 24h."
    ),
    IssueType.SETTLEMENT_DELAY.value: (
        "Check settlement cycle. Contact settlements team if > 48h."
    ),
    IssueType.CHARGEBACK_DISPUTE.value: (
        "Collect transaction proof. Respond within dispute window."
    ),
    IssueType.FAILED_PAYMENT.value: (
        "Transaction failed at bank. No action needed — customer not charged."
    ),
    IssueType.UPI_PENDING.value: "Await auto-reversal within 24-48h.",
}

DEFAULT_RECOMMENDED_ACTION = "Review with support team."

ALERT_BORDER_COLORS: dict[str, str] = {
    "critical": "#ef4444",
    "warning": "#f59e0b",
    "info": "#3b82f6",
}

ALERT_EMOJI: dict[str, str] = {
    "critical": "🔴",
    "warning": "🟡",
    "info": "🔵",
}


def _init_session_state() -> None:
    """Ensure merchant portal session keys exist."""
    defaults: dict[str, Any] = {
        "merchant_page": PAGE_LOGIN,
        "merchant": None,
        "login_error": None,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def _pct(part: int, total: int) -> float:
    """Return percentage of part relative to total."""
    if total <= 0:
        return 0.0
    return (part / total) * 100.0


def _short_issue_label(issue_name: str) -> str:
    """Shorten issue names for chart readability."""
    prefix = "Amount Debited but "
    if issue_name.startswith(prefix):
        return "Not Credited"
    return issue_name


def _issue_badge_html(issue_name: str) -> str:
    """Render a coloured HTML badge for an issue label."""
    severity = ISSUE_SEVERITY.get(issue_name, "amber")
    color = SEVERITY_COLORS[severity]
    return (
        f'<span class="issue-badge" style="background:{color};">'
        f"{issue_name}</span>"
    )


def _recommended_action(issue_name: str) -> str:
    """Return the recommended action for a given issue."""
    return RECOMMENDED_ACTIONS.get(issue_name, DEFAULT_RECOMMENDED_ACTION)


def _age_urgency_label(age_hours: Any) -> str:
    """Return urgency emoji and label for transaction age."""
    try:
        age = int(float(age_hours))
    except (TypeError, ValueError):
        return "🟢 Recent"

    if age > 72:
        return "🔴 Critical"
    if age > 24:
        return "🟡 Review"
    return "🟢 Recent"


def _build_issue_summary(breakdown: dict[str, int]) -> str:
    """Build a plain-English summary from issue breakdown counts."""
    nonzero = {issue: count for issue, count in breakdown.items() if count > 0}
    if not nonzero:
        return "No transactions recorded yet for this merchant."

    flagged_issues = {
        issue: count
        for issue, count in nonzero.items()
        if issue != IssueType.NORMAL_SUCCESS.value
    }
    chargebacks = nonzero.get(IssueType.CHARGEBACK_DISPUTE.value, 0)

    parts: list[str] = []

    if flagged_issues:
        top_issue, top_count = max(flagged_issues.items(), key=lambda item: item[1])
        parts.append(
            f"Your most common issue is {top_issue} ({top_count} transaction"
            f"{'' if top_count == 1 else 's'})."
        )
    elif IssueType.NORMAL_SUCCESS.value in nonzero:
        success_count = nonzero[IssueType.NORMAL_SUCCESS.value]
        parts.append(
            f"All {success_count} transaction{'s' if success_count != 1 else ''} "
            "completed successfully with no issues detected."
        )

    if chargebacks > 0:
        parts.append(
            f"{chargebacks} chargeback{'s' if chargebacks != 1 else ''} "
            "require immediate attention."
        )

    return " ".join(parts)


def _filter_flagged_transactions(
    flagged: list[dict[str, Any]],
    issue_filter: list[str],
    payment_mode: str,
    min_age_hours: int,
) -> list[dict[str, Any]]:
    """Apply flagged-transaction filters."""
    filtered = flagged

    if issue_filter:
        issue_set = set(issue_filter)
        filtered = [txn for txn in filtered if txn.get("issue") in issue_set]

    if payment_mode != "All":
        filtered = [txn for txn in filtered if txn.get("PAYMENT_MODE") == payment_mode]

    if min_age_hours > 0:
        filtered = [
            txn
            for txn in filtered
            if int(float(txn.get("AGE_HOURS", 0))) > min_age_hours
        ]

    return filtered


def _flagged_filter_keys(mid: str) -> tuple[str, str, str]:
    """Return session-state keys for flagged-transaction filters."""
    return (
        f"merchant_flagged_issues_{mid}",
        f"merchant_flagged_payment_mode_{mid}",
        f"merchant_flagged_min_age_{mid}",
    )


def _init_flagged_filters(mid: str, available_issues: list[str]) -> None:
    """Initialize flagged filter session state for a merchant."""
    issue_key, mode_key, age_key = _flagged_filter_keys(mid)
    if issue_key not in st.session_state:
        st.session_state[issue_key] = available_issues
    if mode_key not in st.session_state:
        st.session_state[mode_key] = "All"
    if age_key not in st.session_state:
        st.session_state[age_key] = 0


def _flagged_transactions_to_csv(transactions: list[dict[str, Any]]) -> str:
    """Serialize flagged transactions to CSV for ops-team export."""
    if not transactions:
        return ",".join(FLAGGED_CSV_COLUMNS) + "\n"

    export_df = pd.DataFrame(transactions)
    for column in FLAGGED_CSV_COLUMNS:
        if column not in export_df.columns:
            export_df[column] = ""
    return export_df[list(FLAGGED_CSV_COLUMNS)].to_csv(index=False)


def _portal_base_styles(primary: str, primary_light: str, primary_dark: str) -> str:
    """Shared portal style structure with accent colour injected per portal."""
    return f"""
        :root {{
            --portal-primary: {primary};
            --portal-primary-light: {primary_light};
            --portal-primary-dark: {primary_dark};
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
            box-shadow: 0 12px 32px rgba(0, 53, 128, 0.25);
        }}
        .portal-login-card h1 {{
            color: white !important;
            margin-bottom: 0.25rem;
        }}
        .portal-login-card p {{
            color: rgba(255, 255, 255, 0.92);
            margin-bottom: 0;
        }}
        .portal-header-bar {{
            background: #f8fafc;
            border: 1px solid #e2e8f0;
            border-left: 4px solid var(--portal-primary);
            border-radius: 12px;
            padding: 1rem 1.25rem;
            margin-bottom: 1.25rem;
        }}
        .portal-section-title {{
            color: var(--portal-primary);
            font-weight: 700;
            margin-bottom: 0.35rem;
        }}
        .portal-kpi-block {{
            background: #ffffff;
            border: 1px solid #e2e8f0;
            border-radius: 10px;
            padding: 0.25rem 0.5rem;
        }}
        .issue-badge {{
            display: inline-block;
            padding: 0.2rem 0.65rem;
            border-radius: 999px;
            color: white;
            font-size: 0.85rem;
            font-weight: 600;
        }}
        .alert-card {{
            background: #ffffff;
            border: 1px solid #e2e8f0;
            border-left-width: 5px;
            border-radius: 10px;
            padding: 1rem 1.1rem;
            margin-bottom: 0.85rem;
        }}
        .alert-count-badge {{
            display: inline-block;
            background: #f1f5f9;
            color: #334155;
            border-radius: 999px;
            padding: 0.15rem 0.55rem;
            font-size: 0.75rem;
            font-weight: 600;
            margin-left: 0.35rem;
        }}
        div[data-testid="stTabs"] button[aria-selected="true"] {{
            color: var(--portal-primary) !important;
            border-bottom-color: var(--portal-primary) !important;
        }}
        div[data-testid="stSidebar"] {{
            background-color: #f8fafc;
        }}
    """


def _inject_styles() -> None:
    """Apply merchant portal styling with deep-blue accent."""
    st.markdown(
        f"<style>{_portal_base_styles(MERCHANT_PRIMARY_COLOR, MERCHANT_PRIMARY_LIGHT, MERCHANT_PRIMARY_DARK)}</style>",
        unsafe_allow_html=True,
    )


def _render_issue_analytics(mid: str) -> None:
    """Issue Analytics tab — breakdown chart and summary."""
    breakdown = get_issue_breakdown(mid)
    nonzero_items = {issue: count for issue, count in breakdown.items() if count > 0}

    if nonzero_items:
        chart_items = nonzero_items
    else:
        chart_items = breakdown

    chart_rows = [
        {
            "issue": issue,
            "label": _short_issue_label(issue),
            "count": count,
            "severity": ISSUE_SEVERITY.get(issue, "amber"),
        }
        for issue, count in chart_items.items()
        if count > 0 or not nonzero_items
    ]

    if not chart_rows:
        st.info("No issue data available yet.")
        return

    chart_df = pd.DataFrame(chart_rows)
    chart = (
        alt.Chart(chart_df)
        .mark_bar(cornerRadiusTopLeft=4, cornerRadiusTopRight=4)
        .encode(
            x=alt.X("label:N", sort="-y", title="Issue"),
            y=alt.Y("count:Q", title="Transaction count"),
            color=alt.Color(
                "severity:N",
                scale=alt.Scale(
                    domain=["green", "amber", "red"],
                    range=[
                        SEVERITY_COLORS["green"],
                        SEVERITY_COLORS["amber"],
                        SEVERITY_COLORS["red"],
                    ],
                ),
                legend=alt.Legend(title="Severity"),
            ),
            tooltip=["issue", "count"],
        )
        .properties(title="Transaction Issues Breakdown")
    )
    st.altair_chart(chart, use_container_width=True)
    st.markdown(_build_issue_summary(breakdown))


def _render_flagged_transaction_card(txn: dict[str, Any], card_index: int) -> None:
    """Render a single flagged transaction expander card."""
    issue = str(txn.get("issue", "Unknown"))
    amount = txn.get("TXN_AMOUNT", "—")
    age_hours = txn.get("AGE_HOURS", "—")
    title = f"{issue} — ₹{amount} — {age_hours}h ago"

    with st.expander(title, expanded=card_index < 2):
        st.markdown(_issue_badge_html(issue), unsafe_allow_html=True)
        st.markdown(
            f"**Age:** {age_hours} hours · {_age_urgency_label(age_hours)}"
        )
        detail_cols = st.columns(2)
        with detail_cols[0]:
            st.markdown(f"**ORDER_ID:** {txn.get('ORDER_ID', '—')}")
            st.markdown(f"**TXN_TIMESTAMP:** {txn.get('TXN_TIMESTAMP', '—')}")
        with detail_cols[1]:
            st.markdown(f"**PAYMENT_MODE:** {txn.get('PAYMENT_MODE', '—')}")
            st.markdown(f"**TXN_STATUS:** {txn.get('TXN_STATUS', '—')}")
        st.markdown(f"**TXN_AMOUNT:** ₹{amount}")
        st.info(f"**Recommended Action:** {_recommended_action(issue)}")


def _render_flagged_transactions(mid: str) -> None:
    """Flagged Transactions tab — filters, CSV export, and cards."""
    flagged = get_flagged_transactions(mid)

    if not flagged:
        st.success("✅ No flagged transactions. All clear!")
        return

    available_issues = sorted({str(txn.get("issue", "")) for txn in flagged if txn.get("issue")})
    _init_flagged_filters(mid, available_issues)
    issue_key, mode_key, age_key = _flagged_filter_keys(mid)

    st.warning(f"⚠️ {len(flagged)} transactions require attention")

    with st.expander("Filter flagged transactions", expanded=False):
        st.multiselect(
            "Issue types",
            options=available_issues,
            key=issue_key,
        )
        st.selectbox(
            "PAYMENT_MODE",
            options=PAYMENT_MODE_OPTIONS,
            key=mode_key,
        )
        st.number_input(
            "Show transactions older than (hours)",
            min_value=0,
            step=1,
            key=age_key,
        )

    filtered = _filter_flagged_transactions(
        flagged=flagged,
        issue_filter=st.session_state[issue_key],
        payment_mode=st.session_state[mode_key],
        min_age_hours=int(st.session_state[age_key]),
    )

    st.caption(f"Showing {len(filtered)} of {len(flagged)} flagged transactions")

    st.download_button(
        label="Download flagged transactions as CSV",
        data=_flagged_transactions_to_csv(filtered),
        file_name=f"flagged_transactions_{mid}.csv",
        mime="text/csv",
        disabled=not filtered,
        use_container_width=False,
    )

    if not filtered:
        st.info("No flagged transactions match the current filters.")
        return

    for index, txn in enumerate(filtered):
        _render_flagged_transaction_card(txn, index)


def _build_alerts_summary(alerts: list[dict[str, Any]]) -> str:
    """Build the top-line alerts summary."""
    critical_count = sum(1 for alert in alerts if alert["severity"] == "critical")
    warning_count = sum(1 for alert in alerts if alert["severity"] == "warning")

    if critical_count == 0 and warning_count == 0:
        return "All clear"
    return f"{critical_count} critical, {warning_count} warnings"


def _render_alert_card(alert: dict[str, Any]) -> None:
    """Render a single styled alert card."""
    severity = str(alert["severity"])
    border_color = ALERT_BORDER_COLORS.get(severity, "#94a3b8")
    emoji = ALERT_EMOJI.get(severity, "ℹ️")
    count_badge = (
        f'<span class="alert-count-badge">{alert["transaction_count"]} txn</span>'
        if int(alert["transaction_count"]) > 0
        else ""
    )

    with st.container():
        st.markdown(
            f"""
            <div class="alert-card" style="border-left-color: {border_color};">
                <div><strong>{emoji} {alert["title"]}</strong>{count_badge}</div>
                <div style="margin-top: 0.45rem; color: #334155;">{alert["message"]}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if alert["recommended_action"]:
            st.info(f"**Recommended Action:** {alert['recommended_action']}")


def _render_alerts_panel(mid: str) -> None:
    """Alerts tab — portfolio alerts and recommendations."""
    alerts = get_merchant_alerts(mid)
    now_label = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    st.markdown('<p class="portal-section-title">Alerts & Recommendations</p>', unsafe_allow_html=True)
    st.caption(f"Last updated: {now_label}")

    summary_text = _build_alerts_summary(alerts)
    if summary_text == "All clear":
        st.success(summary_text)
    else:
        st.warning(summary_text)

    for alert in alerts:
        _render_alert_card(alert)


def _sign_out() -> None:
    """Clear merchant session and return to login."""
    st.session_state["merchant"] = None
    st.session_state["merchant_page"] = PAGE_LOGIN
    st.session_state["login_error"] = None


def _render_login_page() -> None:
    """Render the merchant sign-in experience."""
    st.markdown(
        """
        <div class="portal-login-card">
            <h1>🏪 Paytm Merchant Portal</h1>
            <p>Monitor your payment operations</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    col_left, col_center, col_right = st.columns([1, 1.2, 1])
    with col_center:
        st.markdown("### Sign in to your account")
        st.caption("Use your merchant username and password to access the dashboard.")

        with st.form("merchant_login_form", clear_on_submit=False):
            username = st.text_input("USERNAME", placeholder="e.g. prabhu002")
            password = st.text_input("PASSWORD", type="password", placeholder="Enter password")
            submitted = st.form_submit_button("Sign In", use_container_width=True, type="primary")

        if submitted:
            merchant = authenticate_merchant(username.strip(), password)
            if merchant is None:
                st.session_state["login_error"] = "Invalid username or password. Please try again."
            else:
                st.session_state["merchant"] = merchant
                st.session_state["merchant_page"] = PAGE_DASHBOARD
                st.session_state["login_error"] = None
                st.rerun()

        if st.session_state.get("login_error"):
            st.error(st.session_state["login_error"])


def _render_sidebar(merchant: dict[str, Any]) -> None:
    """Render merchant profile summary and sign out."""
    with st.sidebar:
        st.markdown("### Merchant Portal")
        st.markdown(f"**{merchant['MERCHANT_NAME']}**")
        st.caption(f"Business: {merchant['BUSINESS_TYPE']}")
        st.caption(f"City: {merchant['CITY']}")
        st.caption(f"MID: {merchant['MID']}")
        st.caption(f"Onboarded: {merchant['ONBOARDED_SINCE']}")
        st.divider()
        if st.button("Sign Out", key="sidebar_sign_out", use_container_width=True):
            _sign_out()
            st.rerun()


def _render_merchant_header(merchant: dict[str, Any]) -> None:
    """Overview tab — merchant identity bar."""
    st.markdown('<div class="portal-header-bar">', unsafe_allow_html=True)
    col_name, col_type, col_city, col_since = st.columns([2.4, 1.5, 1.3, 1.5])

    with col_name:
        st.markdown(f"**{merchant['MERCHANT_NAME']}**")
        st.caption("Merchant account")
    with col_type:
        st.markdown(f"**{merchant['BUSINESS_TYPE']}**")
        st.caption("Business type")
    with col_city:
        st.markdown(f"**{merchant['CITY']}**")
        st.caption("City")
    with col_since:
        st.markdown(f"**{merchant['ONBOARDED_SINCE']}**")
        st.caption("Onboarded since")

    st.markdown("</div>", unsafe_allow_html=True)


def _render_summary_metrics(mid: str) -> None:
    """Overview tab — eight KPI cards from merchant summary."""
    summary = get_merchant_summary(mid)
    total = summary["total"]
    successful = summary["successful"]
    failed = summary["failed"]
    pending = summary["pending"]
    flagged = summary["flagged"]

    success_pct = _pct(successful, total)
    flagged_pct = _pct(flagged, total)
    flagged_delta = f"-{flagged_pct:.0f}%" if flagged > 0 else None

    row_one = st.columns(4)
    row_two = st.columns(4)

    with row_one[0]:
        st.metric("Total Transactions", total)
    with row_one[1]:
        st.metric(
            "Successful",
            successful,
            delta=f"{success_pct:.0f}% of total" if total > 0 else None,
        )
    with row_one[2]:
        st.metric("Failed", failed)
    with row_one[3]:
        st.metric("Pending", pending)

    with row_two[0]:
        st.metric("Settlement Issues", summary["settlement_issues"])
    with row_two[1]:
        st.metric("Chargebacks", summary["chargebacks"])
    with row_two[2]:
        st.metric("Not Credited", summary["merchant_not_credited"])
    with row_two[3]:
        st.metric(
            "Flagged",
            flagged,
            delta=flagged_delta,
            delta_color="inverse" if flagged > 0 else "off",
        )


def _render_dashboard_page(merchant: dict[str, Any]) -> None:
    """Render the tabbed merchant monitoring dashboard."""
    st.title("Dashboard")
    st.caption("Overview of your payment health and operational risk.")

    overview_tab, analytics_tab, flagged_tab, alerts_tab = st.tabs(
        ["📊 Overview", "📈 Issue Analytics", "🚩 Flagged Transactions", "⚡ Alerts"]
    )

    with overview_tab:
        _render_merchant_header(merchant)
        st.markdown('<p class="portal-section-title">Summary metrics</p>', unsafe_allow_html=True)
        _render_summary_metrics(merchant["MID"])

    with analytics_tab:
        _render_issue_analytics(merchant["MID"])

    with flagged_tab:
        _render_flagged_transactions(merchant["MID"])

    with alerts_tab:
        _render_alerts_panel(merchant["MID"])


def main() -> None:
    """Entry point for the merchant portal Streamlit app."""
    st.set_page_config(
        page_title="Paytm Merchant Portal",
        page_icon="🏪",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    _init_session_state()
    _inject_styles()

    merchant = st.session_state.get("merchant")

    if merchant is None:
        _render_login_page()
        return

    _render_sidebar(merchant)
    _render_dashboard_page(merchant)


if __name__ == "__main__":
    main()
