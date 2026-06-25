"""Unified landing page routing users to persona-specific portals."""

from __future__ import annotations

import webbrowser

import streamlit as st

CUSTOMER_URL = "http://localhost:8502"
AGENT_URL = "http://localhost:8501"
MERCHANT_URL = "http://localhost:8503"

PAGE_BACKGROUND = "#F4F6F8"
CARD_BORDER = "#E2E8F0"
TEXT_PRIMARY = "#1E293B"
TEXT_MUTED = "#64748B"

PORTALS: tuple[dict[str, str], ...] = (
    {
        "key": "customer",
        "emoji": "🧑‍💼",
        "title": "Customer",
        "description": (
            "View your transactions, raise complaints, and track resolution updates."
        ),
        "button_label": "Enter as Customer",
        "url": CUSTOMER_URL,
    },
    {
        "key": "agent",
        "emoji": "🎧",
        "title": "Support Agent",
        "description": (
            "Resolve payment disputes with AI-assisted SOP guidance and case history."
        ),
        "button_label": "Enter as Agent",
        "url": AGENT_URL,
    },
    {
        "key": "merchant",
        "emoji": "🏪",
        "title": "Merchant",
        "description": (
            "Monitor settlements, flagged transactions, and operational alerts."
        ),
        "button_label": "Enter as Merchant",
        "url": MERCHANT_URL,
    },
)

LANDING_CSS = f"""
<style>
  .stApp {{
    background-color: {PAGE_BACKGROUND};
  }}
  [data-testid="stHeader"] {{
    background: transparent;
  }}
  .block-container {{
    max-width: 1100px;
    padding-top: 2rem;
    padding-bottom: 2rem;
  }}
  .landing-header {{
    text-align: center;
    margin-bottom: 2.5rem;
  }}
  .landing-header h1 {{
    color: {TEXT_PRIMARY};
    font-size: 2.1rem;
    font-weight: 700;
    margin: 0 0 0.4rem 0;
  }}
  .landing-subheader {{
    color: {TEXT_MUTED};
    font-size: 1.05rem;
    margin: 0;
  }}
  .persona-card {{
    background: #ffffff;
    border: 1px solid {CARD_BORDER};
    border-radius: 14px;
    padding: 1.75rem 1.5rem 1.25rem;
    min-height: 290px;
    display: flex;
    flex-direction: column;
    align-items: center;
    text-align: center;
    transition: box-shadow 0.2s ease, transform 0.2s ease, border-color 0.2s ease;
  }}
  .persona-card:hover {{
    box-shadow: 0 10px 28px rgba(15, 23, 42, 0.09);
    transform: translateY(-3px);
    border-color: #CBD5E1;
  }}
  .persona-icon {{
    font-size: 2.75rem;
    line-height: 1;
    margin-bottom: 0.85rem;
  }}
  .persona-title {{
    color: {TEXT_PRIMARY};
    font-size: 1.25rem;
    font-weight: 700;
    margin: 0 0 0.6rem 0;
  }}
  .persona-desc {{
    color: {TEXT_MUTED};
    font-size: 0.95rem;
    line-height: 1.55;
    margin: 0 0 1.25rem 0;
    flex: 1;
  }}
  .portal-link-btn {{
    display: inline-block;
    background: {TEXT_PRIMARY};
    color: #ffffff !important;
    text-decoration: none;
    padding: 0.55rem 1.25rem;
    border-radius: 8px;
    font-weight: 600;
    font-size: 0.9rem;
    transition: background 0.15s ease;
  }}
  .portal-link-btn:hover {{
    background: #334155;
    color: #ffffff !important;
  }}
  .landing-footer {{
    text-align: center;
    color: #94A3B8;
    font-size: 0.82rem;
    margin-top: 3rem;
    padding-top: 1.5rem;
    border-top: 1px solid {CARD_BORDER};
  }}
  div[data-testid="column"] .stButton > button {{
    width: 100%;
    border-radius: 8px;
    font-weight: 600;
    background: {TEXT_PRIMARY};
    color: #ffffff;
    border: 1px solid {TEXT_PRIMARY};
  }}
  div[data-testid="column"] .stButton > button:hover {{
    background: #334155;
    border-color: #334155;
    color: #ffffff;
  }}
</style>
"""


def _init_session_state() -> None:
    if "selected_portal" not in st.session_state:
        st.session_state.selected_portal = None


def _render_portal_redirect(portal: dict[str, str]) -> None:
    url = portal["url"]
    st.info("Opening portal in new tab…")
    st.markdown(
        f'<a class="portal-link-btn" href="{url}" target="_blank" rel="noopener noreferrer">'
        f"Open {portal['title']} Portal →</a>",
        unsafe_allow_html=True,
    )
    st.markdown(f"Or copy this URL: `{url}`")


def _render_persona_card(portal: dict[str, str]) -> None:
    st.markdown(
        f"""
        <div class="persona-card">
          <div class="persona-icon">{portal["emoji"]}</div>
          <p class="persona-title">{portal["title"]}</p>
          <p class="persona-desc">{portal["description"]}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if st.button(portal["button_label"], key=f"enter_{portal['key']}", use_container_width=True):
        st.session_state.selected_portal = portal["key"]
        webbrowser.open(portal["url"], new=2)

    if st.session_state.selected_portal == portal["key"]:
        _render_portal_redirect(portal)


def main() -> None:
    st.set_page_config(
        page_title="Paytm Operations Platform",
        page_icon="💳",
        layout="wide",
        initial_sidebar_state="collapsed",
    )
    _init_session_state()
    st.markdown(LANDING_CSS, unsafe_allow_html=True)

    st.markdown(
        """
        <div class="landing-header">
          <h1>💳 Paytm Operations Platform</h1>
          <p class="landing-subheader">Select your portal to continue</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    col_customer, col_agent, col_merchant = st.columns(3, gap="large")
    with col_customer:
        _render_persona_card(PORTALS[0])
    with col_agent:
        _render_persona_card(PORTALS[1])
    with col_merchant:
        _render_persona_card(PORTALS[2])

    st.markdown(
        """
        <div class="landing-footer">
          Internal prototype — not for production use. Paytm Payments Services Ltd.
        </div>
        """,
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()
