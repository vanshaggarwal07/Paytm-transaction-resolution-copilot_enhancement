"""Tests for LangGraph node routing and clarification."""

from src.core.graph_nodes import evaluate_router_decision, node_router
from src.core.graph_state import CopilotState
from src.core.signal_reconciliation import reconcile_signals
from src.core.transaction_lookup import lookup_transaction


def _base_state(**overrides: object) -> CopilotState:
    """Build a minimal CopilotState for router tests."""
    state: CopilotState = {
        "mid": "MID000001",
        "order_id": "ORD000001",
        "cust_id": "CUST000001",
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


def test_router_conflict_returns_clarify() -> None:
    """Condition 1: reconciliation conflict routes to clarify."""
    state = _base_state(
        reconciliation={
            "conflict": True,
            "extracted_intents": [
                {
                    "intent": "Chargeback / Dispute",
                    "confidence": "high",
                    "evidence": "chargeback dispute",
                }
            ],
            "unresolved_intents": ["Chargeback / Dispute"],
            "reconciliation_note": "conflict flagged",
        }
    )

    edge = node_router(state)

    print(f"conflict branch edge: {edge}")
    assert edge == "clarify"
    assert state["needs_clarification"] is True


def test_router_all_low_confidence_returns_clarify() -> None:
    """Condition 2: non-empty extracted intents all low confidence routes to clarify."""
    state = _base_state(
        reconciliation={
            "conflict": False,
            "extracted_intents": [
                {"intent": "Refund Pending", "confidence": "low", "evidence": "maybe refund"},
                {"intent": "UPI Pending", "confidence": "low", "evidence": "stuck maybe"},
            ],
            "unresolved_intents": ["Refund Pending", "UPI Pending"],
            "reconciliation_note": "low confidence only",
        }
    )

    edge = node_router(state)

    print(f"all-low-confidence branch edge: {edge}")
    assert edge == "clarify"
    assert state["needs_clarification"] is True


def test_router_multiple_unresolved_high_confidence_returns_clarify() -> None:
    """Condition 3: multiple unresolved intents with a high-confidence signal routes to clarify."""
    state = _base_state(
        reconciliation={
            "conflict": False,
            "extracted_intents": [
                {
                    "intent": "Settlement Delay",
                    "confidence": "high",
                    "evidence": "settlement pending",
                },
                {
                    "intent": "Chargeback / Dispute",
                    "confidence": "high",
                    "evidence": "bank dispute",
                },
            ],
            "unresolved_intents": ["Settlement Delay", "Chargeback / Dispute"],
            "reconciliation_note": "competing high-confidence signals",
        }
    )

    edge = node_router(state)

    print(f"multiple-unresolved-high branch edge: {edge}")
    assert edge == "clarify"
    assert state["needs_clarification"] is True


def test_router_complaint_without_intents_returns_clarify() -> None:
    """Condition 4: complaint present but no extracted intents routes to clarify."""
    state = _base_state(
        complaint_text="kuch gadbad ho gayi payment mein",
        reconciliation={
            "conflict": False,
            "extracted_intents": [],
            "unresolved_intents": [],
            "reconciliation_note": "no intents extracted",
        },
    )

    edge = node_router(state)

    print(f"complaint-without-intents branch edge: {edge}")
    assert edge == "clarify"
    assert state["needs_clarification"] is True


def test_router_default_returns_resolve() -> None:
    """Condition 6: otherwise routes to resolve."""
    state = _base_state(
        complaint_text="Settlement is still pending on my merchant dashboard.",
        reconciliation={
            "conflict": False,
            "extracted_intents": [
                {
                    "intent": "Settlement Delay",
                    "confidence": "high",
                    "evidence": "settlement still pending",
                }
            ],
            "unresolved_intents": [],
            "reconciliation_note": "aligned",
        },
        rule_based_issue="Settlement Delay",
    )

    edge = node_router(state)

    print(f"default branch edge: {edge}")
    assert edge == "resolve"
    assert state["needs_clarification"] is False


def test_router_agent_answers_guard_overrides_conflict() -> None:
    """Condition 5: agent answers always resolve, even when conflict is true."""
    state = _base_state(
        agent_answers="Colleague confirmed this is a chargeback dispute, not settlement delay.",
        reconciliation={
            "conflict": True,
            "extracted_intents": [
                {
                    "intent": "Chargeback / Dispute",
                    "confidence": "high",
                    "evidence": "chargeback dispute",
                }
            ],
            "unresolved_intents": ["Chargeback / Dispute"],
            "reconciliation_note": "conflict flagged",
        },
    )

    edge = node_router(state)

    print(f"agent-answers guard edge: {edge}")
    assert edge == "resolve"
    assert state["needs_clarification"] is False


def test_evaluate_router_decision_reports_trigger_reason() -> None:
    """Router evaluation should expose the trigger reason for logging."""
    edge, needs_clarification, reason = evaluate_router_decision(
        _base_state(
            reconciliation={
                "conflict": True,
                "extracted_intents": [],
                "unresolved_intents": [],
                "reconciliation_note": "conflict",
            }
        )
    )

    assert edge == "clarify"
    assert needs_clarification is True
    assert reason == "reconciliation_conflict"
