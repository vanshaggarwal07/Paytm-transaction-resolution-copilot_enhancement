"""FastAPI application for payment dispute resolution."""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from src.core.issue_rules import identify_issue
from src.core.llm_generator import generate_response, is_llm_configured
from src.core.rag_retriever import retrieve_sop
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
    sop_source: str
    escalation_required: Optional[bool] = None
    escalation_note: Optional[str] = None
    response: str
    response_mode: str


def _parse_escalation(response_text: str) -> tuple[Optional[bool], Optional[str]]:
    """Extract Yes/No escalation from the labeled Escalation section if present."""
    match = re.search(
        r"Escalation:\s*(.+?)(?:\n\s*\n|\nSource:|\Z)",
        response_text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if not match:
        return None, "Could not locate an Escalation section in the model response."

    escalation_text = match.group(1).strip()
    first_line = escalation_text.splitlines()[0].strip().lower()

    if first_line.startswith("yes"):
        return True, None
    if first_line.startswith("no"):
        return False, None

    return None, f"Could not parse escalation answer from: {escalation_text!r}"


@app.get("/health")
def health() -> Dict[str, Any]:
    """Return a simple health check payload."""
    return {"status": "ok", "llm_configured": is_llm_configured()}


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
    logger.info(
        "identified issue: %s for mid=%s order_id=%s cust_id=%s",
        issue,
        request.mid,
        request.order_id,
        request.cust_id,
    )

    # Use the rule-engine issue name for retrieval: SOP headings match taxonomy
    # exactly, while complaint text can describe the wrong issue or use vague wording.
    sop_results = retrieve_sop(issue, top_k=1)
    if not sop_results:
        raise HTTPException(
            status_code=500,
            detail=f"No SOP found for identified issue: {issue}.",
        )

    sop = sop_results[0]
    sop_source = Path(sop["file_path"]).name

    response_mode = "gemini" if is_llm_configured() else "sop_fallback"
    response_text = generate_response(
        transaction=transaction,
        issue=issue,
        sop=sop,
        complaint=request.complaint,
    )

    escalation_required, escalation_note = _parse_escalation(response_text)

    return ResolveResponse(
        issue=issue,
        sop_source=sop_source,
        escalation_required=escalation_required,
        escalation_note=escalation_note,
        response=response_text,
        response_mode=response_mode,
    )
