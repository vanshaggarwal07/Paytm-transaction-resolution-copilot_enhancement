"""End-to-end tests for the copilot LangGraph."""

from __future__ import annotations

import json
from typing import Any

from src.core.copilot_graph import COPILOT_GRAPH
from src.core.graph_state import CopilotState

MID = "MID000002"
ORDER_ID = "ORD000002"
CUST_ID = "CUST000002"

CONFLICT_COMPLAINT = (
    "The card issuer raised a chargeback dispute on a previously successful "
    "transaction. The merchant reports a reversal debit from their settlement "
    "account and the customer claims an unauthorised transaction despite "
    "earlier success status."
)

AGENT_ANSWERS = (
    "The customer confirmed the transaction was authorised — this is a "
    "settlement delay issue, not a dispute."
)


def _base_invoke_state(**overrides: Any) -> CopilotState:
    """Build a complete initial state for COPILOT_GRAPH.invoke()."""
    state: CopilotState = {
        "mid": MID,
        "order_id": ORDER_ID,
        "cust_id": CUST_ID,
        "complaint_text": "",
        "agent_answers": "",
        "transaction": None,
        "lookup_error": None,
        "rule_based_issue": None,
        "reconciliation": None,
        "needs_clarification": False,
        "clarifying_questions": [],
        "sop": None,
        "response_text": None,
        "response_mode": None,
        "customer_reply": None,
        "escalation": None,
        "groundedness": None,
        "case_note": None,
        "error": None,
    }
    state.update(overrides)  # type: ignore[typeddict-item]
    return state


def _print_final_state(label: str, final_state: dict[str, Any]) -> None:
    """Print the full graph state at END for manual inspection."""
    print(f"\n{'=' * 80}")
    print(label)
    print(f"{'=' * 80}")
    print(json.dumps(final_state, indent=2, default=str))
    print(f"{'=' * 80}\n")


def test_copilot_graph_clean_resolution_without_complaint() -> None:
    """Test 1: no complaint text follows the resolve path to a generated response."""
    final_state = COPILOT_GRAPH.invoke(_base_invoke_state())

    _print_final_state("Test 1 — clean resolution path (no complaint)", final_state)

    assert final_state["error"] is None
    assert final_state["needs_clarification"] is False
    assert final_state["response_text"] is not None
    assert len(str(final_state["response_text"]).strip()) > 0


def test_copilot_graph_clarification_path_on_conflict() -> None:
    """Test 2: conflict complaint stops at clarify without generating a resolution."""
    final_state = COPILOT_GRAPH.invoke(
        _base_invoke_state(complaint_text=CONFLICT_COMPLAINT)
    )

    _print_final_state("Test 2 — clarification path (conflict complaint)", final_state)

    assert final_state["needs_clarification"] is True
    assert isinstance(final_state["clarifying_questions"], list)
    assert len(final_state["clarifying_questions"]) >= 1
    assert final_state["response_text"] is None


def test_copilot_graph_post_clarification_resolution() -> None:
    """Test 3: agent answers skip clarification and complete the resolve path."""
    final_state = COPILOT_GRAPH.invoke(
        _base_invoke_state(
            complaint_text=CONFLICT_COMPLAINT,
            agent_answers=AGENT_ANSWERS,
        )
    )

    _print_final_state("Test 3 — post-clarification resolution", final_state)

    assert final_state["needs_clarification"] is False
    assert final_state["response_text"] is not None
    assert len(str(final_state["response_text"]).strip()) > 0
