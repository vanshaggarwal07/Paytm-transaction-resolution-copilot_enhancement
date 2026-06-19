"""Live LLM test for node_clarify on a real conflict state."""

from src.core.graph_nodes import node_clarify, node_router
from src.core.graph_state import CopilotState
from src.core.signal_reconciliation import reconcile_signals
from src.core.transaction_lookup import lookup_transaction


def _conflict_state_from_prompt_24_case_3() -> CopilotState:
    """Build graph state from Prompt 24 signal-reconciliation conflict test case."""
    transaction = lookup_transaction("MID000002", "ORD000002", "CUST000002")
    assert transaction is not None

    complaint = (
        "The card issuer raised a chargeback dispute on a previously successful "
        "transaction. The merchant reports a reversal debit from their settlement "
        "account and the customer claims an unauthorised transaction despite "
        "earlier success status."
    )
    reconciliation = reconcile_signals(
        rule_based_issue="Settlement Delay",
        complaint_text=complaint,
        transaction=transaction,
    )

    state: CopilotState = {
        "mid": "MID000002",
        "order_id": "ORD000002",
        "cust_id": "CUST000002",
        "complaint_text": complaint,
        "agent_answers": "",
        "transaction": transaction,
        "lookup_error": None,
        "rule_based_issue": "Settlement Delay",
        "reconciliation": reconciliation,
        "needs_clarification": False,
        "clarifying_questions": [],
        "sop": None,
        "response_text": None,
        "response_mode": None,
        "escalation": None,
        "groundedness": None,
        "case_note": None,
        "error": None,
    }
    node_router(state)
    return state


def test_node_clarify_conflict_case_generates_questions() -> None:
    """node_clarify should return 1-3 targeted questions for a real conflict state."""
    state = _conflict_state_from_prompt_24_case_3()
    result = node_clarify(state)
    questions = result["clarifying_questions"]

    print("\n--- node_clarify conflict-case questions ---")
    for index, question in enumerate(questions, start=1):
        print(f"{index}. {question}")
    print("--- end ---\n")

    assert isinstance(questions, list)
    assert 1 <= len(questions) <= 3
    assert all(isinstance(question, str) and question.strip() for question in questions)
