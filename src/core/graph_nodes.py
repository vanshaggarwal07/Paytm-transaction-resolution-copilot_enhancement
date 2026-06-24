"""LangGraph nodes for the Paytm resolution copilot."""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Optional

from src.core.escalation_rules import determine_escalation
from src.core.graph_state import CopilotState
from src.core.groundedness_verifier import verify_groundedness
from src.core.issue_rules import identify_issue
from src.core.llm_generator import (
    _get_client,
    generate_case_note,
    generate_content_with_model_fallback,
    generate_customer_reply,
    generate_response,
)
from src.core.rag_retriever import retrieve_sop_hybrid
from src.core.signal_reconciliation import reconcile_signals
from src.core.sop_metadata import load_sop_metadata
from src.core.transaction_lookup import lookup_transaction

logger = logging.getLogger(__name__)

CLARIFY_FALLBACK_QUESTIONS: list[str] = [
    "Can you clarify the exact nature of the issue — is this a refund request, "
    "a dispute, or a transaction not received by the merchant?"
]

CLARIFY_PROMPT_TEMPLATE = """You are helping a Paytm payment support agent resolve an ambiguous case.

The agent needs 1 to 3 clarifying questions to ask a colleague before choosing a resolution path.
Write questions as a support agent asking a colleague — not as a chatbot asking a customer.

TRANSACTION (structured fields only):
{transaction_json}

RULE-ENGINE IDENTIFIED ISSUE:
{rule_based_issue}

RECONCILIATION:
- conflict: {conflict}
- extracted_intents: {extracted_intents_json}
- unresolved_intents: {unresolved_intents_json}
- reconciliation_note: {reconciliation_note}

ORIGINAL CUSTOMER COMPLAINT:
{complaint_text}

Generate between 1 and 3 clarifying questions that would resolve the detected ambiguity.
Each question must:
- Reference specific details from the transaction or complaint (no generic "tell me more" questions).
- Be answerable with a short, factual response.
- Target the exact ambiguity (conflict, low-confidence intents, competing signals, or unparseable complaint).

Return ONLY a JSON array of strings — no preamble, no markdown fences, directly parseable by json.loads().
"""


def _enriched_complaint_text(state: CopilotState) -> str:
    """Append agent clarification answers to the original complaint when present."""
    complaint_text = (state.get("complaint_text") or "").strip()
    agent_answers = (state.get("agent_answers") or "").strip()
    if agent_answers:
        if complaint_text:
            return f"{complaint_text}\n\nAgent clarification: {agent_answers}"
        return f"Agent clarification: {agent_answers}"
    return complaint_text


def _reconciliation(state: CopilotState) -> dict[str, Any]:
    """Return reconciliation dict from state, or empty dict when missing."""
    reconciliation = state.get("reconciliation")
    return reconciliation if isinstance(reconciliation, dict) else {}


def _intent_confidence_map(extracted_intents: list[dict[str, Any]]) -> dict[str, str]:
    """Map intent names to their highest reported confidence."""
    confidence_rank = {"low": 0, "medium": 1, "high": 2}
    mapping: dict[str, str] = {}
    for intent in extracted_intents:
        name = intent.get("intent")
        confidence = str(intent.get("confidence", "")).strip().lower()
        if not isinstance(name, str) or not name.strip():
            continue
        if confidence not in confidence_rank:
            continue
        current = mapping.get(name)
        if current is None or confidence_rank[confidence] > confidence_rank[current]:
            mapping[name] = confidence
    return mapping


def evaluate_router_decision(state: CopilotState) -> tuple[str, bool, str]:
    """Return edge name, needs_clarification flag, and trigger reason."""
    agent_answers = (state.get("agent_answers") or "").strip()
    if agent_answers:
        return "resolve", False, "agent_answers_provided"

    reconciliation = _reconciliation(state)
    complaint_text = (state.get("complaint_text") or "").strip()
    extracted_intents = reconciliation.get("extracted_intents") or []
    unresolved_intents = reconciliation.get("unresolved_intents") or []

    if reconciliation.get("conflict") is True:
        return "clarify", True, "reconciliation_conflict"

    if extracted_intents and all(
        str(intent.get("confidence", "")).strip().lower() == "low"
        for intent in extracted_intents
        if isinstance(intent, dict)
    ):
        return "clarify", True, "all_intents_low_confidence"

    if len(unresolved_intents) > 1:
        confidence_by_intent = _intent_confidence_map(
            [intent for intent in extracted_intents if isinstance(intent, dict)]
        )
        if any(confidence_by_intent.get(name) == "high" for name in unresolved_intents):
            return "clarify", True, "multiple_unresolved_with_high_confidence"

    if complaint_text and not extracted_intents:
        return "clarify", True, "complaint_without_extracted_intents"

    return "resolve", False, "default_resolve"


def node_router(state: CopilotState) -> str:
    """Return edge name and set needs_clarification on state in place."""
    edge, needs_clarification, trigger_reason = evaluate_router_decision(state)
    state["needs_clarification"] = needs_clarification
    state["_router_trigger_reason"] = trigger_reason
    logger.info(
        "router decision: edge=%s needs_clarification=%s trigger=%s",
        edge,
        needs_clarification,
        trigger_reason,
    )
    return edge


def node_router_flags(state: CopilotState) -> dict:
    """Persist router flags into graph state before conditional branching."""
    edge, needs_clarification, trigger_reason = evaluate_router_decision(state)
    logger.info(
        "router decision: edge=%s needs_clarification=%s trigger=%s",
        edge,
        needs_clarification,
        trigger_reason,
    )
    return {
        "needs_clarification": needs_clarification,
        "_router_trigger_reason": trigger_reason,
    }


def route_after_router(state: CopilotState) -> str:
    """Select clarify or resolve branch from persisted router flags."""
    return "clarify" if state.get("needs_clarification") else "resolve"


def _strip_json_fences(raw_text: str) -> str:
    """Remove optional markdown code fences from model output."""
    text = raw_text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return text.strip()


def _parse_questions_json(raw_output: str) -> Optional[list[str]]:
    """Parse model JSON output into a list of question strings."""
    if not raw_output.strip():
        return None

    try:
        parsed = json.loads(_strip_json_fences(raw_output))
        if not isinstance(parsed, list):
            raise ValueError(f"Expected JSON array, got {type(parsed).__name__}")
        questions = [str(item).strip() for item in parsed if str(item).strip()]
        if not questions or len(questions) > 3:
            raise ValueError(f"Expected 1-3 questions, got {len(questions)}")
        return questions
    except (json.JSONDecodeError, ValueError, TypeError) as exc:
        logger.warning(
            "Clarifying questions JSON parse failed (%s). raw_output=%r",
            exc,
            raw_output,
        )
        return None


def _build_clarify_prompt(state: CopilotState) -> str:
    """Build the clarifying-questions prompt from current graph state."""
    reconciliation = _reconciliation(state)
    transaction = state.get("transaction") or {}
    transaction_fields = {
        key: transaction.get(key)
        for key in (
            "TXN_ID",
            "ORDER_ID",
            "CUST_ID",
            "MID",
            "PAYMENT_MODE",
            "TXN_AMOUNT",
            "TXN_STATUS",
            "BANK_STATUS",
            "MERCHANT_CREDITED",
            "REFUND_STATUS",
            "SETTLEMENT_STATUS",
            "AGE_HOURS",
            "TXN_TIMESTAMP",
        )
        if key in transaction
    }

    return CLARIFY_PROMPT_TEMPLATE.format(
        transaction_json=json.dumps(transaction_fields, indent=2, default=str),
        rule_based_issue=state.get("rule_based_issue") or "Unknown",
        conflict=reconciliation.get("conflict"),
        extracted_intents_json=json.dumps(
            reconciliation.get("extracted_intents") or [], indent=2, default=str
        ),
        unresolved_intents_json=json.dumps(
            reconciliation.get("unresolved_intents") or [], indent=2, default=str
        ),
        reconciliation_note=reconciliation.get("reconciliation_note") or "",
        complaint_text=(state.get("complaint_text") or "").strip(),
    )


def node_clarify(state: CopilotState) -> dict:
    """Generate targeted clarifying questions for the detected ambiguity."""
    trigger_reason = state.get("_router_trigger_reason")
    if not trigger_reason:
        _, _, trigger_reason = evaluate_router_decision(state)

    questions: list[str]
    used_fallback = False

    client = _get_client()
    if client is None:
        questions = list(CLARIFY_FALLBACK_QUESTIONS)
        used_fallback = True
        logger.warning("Clarifying questions fallback: Gemini client unavailable")
    else:
        prompt = _build_clarify_prompt(state)
        try:
            raw_output, model_name = generate_content_with_model_fallback(client, prompt)
            parsed_questions = _parse_questions_json(raw_output)
            if parsed_questions is None:
                questions = list(CLARIFY_FALLBACK_QUESTIONS)
                used_fallback = True
            else:
                questions = parsed_questions
        except Exception as exc:
            logger.exception("Clarifying questions generation failed: %s", exc)
            questions = list(CLARIFY_FALLBACK_QUESTIONS)
            used_fallback = True

    logger.info(
        "clarify node: trigger=%s used_fallback=%s questions=%s",
        trigger_reason,
        used_fallback,
        questions,
    )

    return {"clarifying_questions": questions}


def node_lookup(state: CopilotState) -> dict:
    """Fill transaction and lookup_error."""
    result = lookup_transaction(
        state["mid"],
        state["order_id"],
        state["cust_id"],
    )
    if result is None:
        return {
            "transaction": None,
            "lookup_error": (
                f"No transaction found for MID={state['mid']}, "
                f"ORDER_ID={state['order_id']}, CUST_ID={state['cust_id']}."
            ),
        }
    return {"transaction": result, "lookup_error": None}


def node_identify_issue(state: CopilotState) -> dict:
    """Fill rule_based_issue."""
    issue = identify_issue(state["transaction"])
    return {"rule_based_issue": issue}


def node_reconcile(state: CopilotState) -> dict:
    """Fill reconciliation."""
    enriched_complaint = _enriched_complaint_text(state)
    result = reconcile_signals(
        state["rule_based_issue"],
        enriched_complaint,
        state["transaction"],
    )
    return {"reconciliation": result}


def node_retrieve(state: CopilotState) -> dict:
    """Fill sop."""
    reconciliation = _reconciliation(state)
    results = retrieve_sop_hybrid(
        query=state["rule_based_issue"],
        extracted_intents=reconciliation.get("extracted_intents") or [],
        transaction=state["transaction"],
        top_k=1,
    )
    return {"sop": results[0] if results else None}


def node_generate(state: CopilotState) -> dict:
    """Fill response_text and customer_reply."""
    from src.core.case_retriever import retrieve_similar_cases

    sop = state["sop"]
    sop_metadata = load_sop_metadata(sop["file_path"])
    escalation = determine_escalation(state["transaction"], sop_metadata)
    escalation_for_reply = {
        **escalation,
        "expected_resolution_hours": sop_metadata.get("expected_resolution_hours"),
    }
    enriched_complaint = _enriched_complaint_text(state)

    similar_cases: list[dict[str, Any]] = []
    try:
        similar_cases = retrieve_similar_cases(
            complaint_text=enriched_complaint,
            rule_based_issue=state["rule_based_issue"],
            top_k=3,
        )
    except Exception as exc:
        logger.warning("Similar case retrieval failed: %s", exc)
        similar_cases = []

    response_text, response_mode = generate_response(
        transaction=state["transaction"],
        issue=state["rule_based_issue"],
        sop=sop,
        escalation=escalation,
        complaint=enriched_complaint,
        similar_cases=similar_cases,
    )
    customer_reply = generate_customer_reply(
        transaction=state["transaction"],
        issue=state["rule_based_issue"],
        resolution_summary=response_text,
        escalation=escalation_for_reply,
    )
    return {
        "response_text": response_text,
        "response_mode": response_mode,
        "customer_reply": customer_reply,
        "similar_cases": similar_cases,
    }


def node_escalate(state: CopilotState) -> dict:
    """Fill escalation and case_note."""
    sop = state["sop"]
    sop_metadata = load_sop_metadata(sop["file_path"])
    escalation = determine_escalation(state["transaction"], sop_metadata)
    case_note = generate_case_note(
        transaction=state["transaction"],
        issue=state["rule_based_issue"],
        escalation=escalation,
        resolution_summary=state["response_text"] or "",
    )
    return {"escalation": escalation, "case_note": case_note}


def node_verify(state: CopilotState) -> dict:
    """Fill groundedness."""
    sop = state["sop"]
    grounding_facts = {
        "transaction": state["transaction"],
        "sop_content": sop["content"],
        "escalation": state["escalation"],
    }
    result = verify_groundedness(state["response_text"] or "", grounding_facts)
    return {"groundedness": result}


def node_error(state: CopilotState) -> dict:
    """Fill error."""
    return {"error": state["lookup_error"], "response_text": None}
