"""FastAPI application for payment dispute resolution."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from src.core.groundedness_verifier import verify_groundedness
from src.core.escalation_rules import determine_escalation
from src.core.issue_rules import identify_issue
from src.core.llm_generator import generate_case_note, generate_response, is_llm_configured, is_llm_ready
from src.core.rag_retriever import retrieve_sop
from src.core.signal_reconciliation import reconcile_signals
from src.core.sop_metadata import load_sop_metadata
from src.core.sop_response_builder import build_sop_fallback_response
from src.core.transaction_lookup import lookup_transaction

logger = logging.getLogger(__name__)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

app = FastAPI(title="Paytm Transaction Resolution Copilot")


class ResolveRequest(BaseModel):
    """Request body for the dispute resolution endpoint."""

    mid: str
    order_id: str
    cust_id: str
    complaint: str = ""


class ResolveResponse(BaseModel):
    """Structured resolution payload returned to the agent UI."""

    issue: str
    primary_issue: str
    secondary_issue: Optional[str] = None
    agreement: bool
    extracted_intents: List[Dict[str, Any]] = []
    unresolved_intents: List[str] = []
    conflict: bool = False
    reconciliation_note: str = ""
    sop_source: str
    escalation_required: Optional[bool] = None
    escalation_note: Optional[str] = None
    response: str
    response_mode: str
    case_note: str
    groundedness_verified: Optional[bool] = None
    unsupported_claims: List[str] = []


@app.get("/health")
def health() -> Dict[str, Any]:
    """Return a simple health check payload."""
    return {
        "status": "ok",
        "llm_configured": is_llm_configured(),
        "llm_ready": is_llm_ready(),
    }


@app.post("/resolve", response_model=ResolveResponse)
def resolve(request: ResolveRequest) -> ResolveResponse:
    """Look up a transaction, identify the issue, retrieve SOP, and generate guidance."""
    logger.info(
        "resolve request: mid=%s order_id=%s cust_id=%s complaint=%r",
        request.mid,
        request.order_id,
        request.cust_id,
        request.complaint,
    )

    try:
        transaction = lookup_transaction(request.mid, request.order_id, request.cust_id)
    except (FileNotFoundError, ValueError) as exc:
        logger.error("Transaction data unavailable: %s", exc)
        raise HTTPException(
            status_code=500,
            detail="Transaction data is unavailable. Please try again later.",
        ) from exc

    if transaction is None:
        logger.info(
            "transaction not found: mid=%s order_id=%s cust_id=%s",
            request.mid,
            request.order_id,
            request.cust_id,
        )
        raise HTTPException(
            status_code=404,
            detail=(
                f"No transaction found for MID={request.mid}, "
                f"ORDER_ID={request.order_id}, CUST_ID={request.cust_id}."
            ),
        )

    issue = identify_issue(transaction)
    signals = reconcile_signals(issue, request.complaint, transaction)
    logger.info(
        "signal reconciliation: mid=%s order_id=%s cust_id=%s reconciliation=%s",
        request.mid,
        request.order_id,
        request.cust_id,
        signals,
    )

    primary_issue = signals["primary_issue"]
    # Rule-engine primary_issue is ground truth for SOP retrieval and LLM grounding.
    sop_results = retrieve_sop(primary_issue, top_k=1)
    if not sop_results:
        raise HTTPException(
            status_code=500,
            detail=f"No SOP found for identified issue: {primary_issue}.",
        )

    sop = sop_results[0]
    sop_source = Path(sop["file_path"]).name
    sop_metadata = load_sop_metadata(sop["file_path"])
    escalation = determine_escalation(transaction, sop_metadata)

    try:
        response_text, response_mode = generate_response(
            transaction=transaction,
            issue=primary_issue,
            sop=sop,
            escalation=escalation,
            complaint=request.complaint,
        )
    except Exception as exc:
        logger.exception("Resolution pipeline failed for ORDER_ID=%s: %s", request.order_id, exc)
        response_text = build_sop_fallback_response(
            transaction, primary_issue, sop, escalation, request.complaint
        )
        response_mode = "sop_fallback"

    grounding_facts = {
        "transaction": transaction,
        "sop_content": sop["content"],
        "escalation": escalation,
    }
    groundedness = verify_groundedness(response_text, grounding_facts)

    if groundedness["verified"] is False:
        logger.warning(
            "Groundedness flagged: mid=%s order_id=%s cust_id=%s txn_id=%s "
            "unsupported_claims=%s",
            request.mid,
            request.order_id,
            request.cust_id,
            transaction.get("TXN_ID"),
            groundedness["unsupported_claims"],
        )

    case_note = generate_case_note(
        transaction=transaction,
        issue=primary_issue,
        escalation=escalation,
        resolution_summary=response_text,
    )

    escalation_note = escalation["reason"]
    if response_mode == "sop_fallback" and not is_llm_configured():
        escalation_note = (
            f"{escalation['reason']} "
            "(Using SOP-based guidance — add GEMINI_API_KEY for Gemini responses.)"
        )

    return ResolveResponse(
        issue=signals["primary_issue"],
        primary_issue=signals["primary_issue"],
        secondary_issue=(
            signals["unresolved_intents"][0] if signals["unresolved_intents"] else None
        ),
        agreement=signals["agreement"],
        extracted_intents=signals["extracted_intents"],
        unresolved_intents=signals["unresolved_intents"],
        conflict=signals["conflict"],
        reconciliation_note=signals["reconciliation_note"],
        sop_source=sop_source,
        escalation_required=escalation["escalation_required"],
        escalation_note=escalation_note,
        response=response_text,
        response_mode=response_mode,
        case_note=case_note,
        groundedness_verified=groundedness["verified"],
        unsupported_claims=groundedness["unsupported_claims"],
    )
