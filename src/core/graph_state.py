"""LangGraph state schema for the Paytm resolution copilot."""

from typing import Optional, TypedDict


class CopilotState(TypedDict):
    """Single state object flowing through every node in the copilot graph."""

    # --- inputs ---
    mid: str
    order_id: str
    cust_id: str
    complaint_text: str
    agent_answers: str  # answers to clarifying questions, empty string if not yet provided

    # --- lookup ---
    transaction: Optional[dict]
    lookup_error: Optional[str]

    # --- issue identification ---
    rule_based_issue: Optional[str]

    # --- reconciliation ---
    reconciliation: Optional[dict]

    # --- clarification ---
    needs_clarification: bool
    clarifying_questions: list[str]

    # --- retrieval ---
    sop: Optional[dict]

    # --- generation ---
    response_text: Optional[str]
    response_mode: Optional[str]
    customer_reply: Optional[str]
    escalation: Optional[dict]
    groundedness: Optional[dict]
    case_note: Optional[str]

    # --- final ---
    error: Optional[str]
