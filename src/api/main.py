"""FastAPI application for payment dispute resolution."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Union

from fastapi import FastAPI, File, HTTPException, UploadFile
from pydantic import BaseModel

from src.core.case_retriever import rebuild_case_index
from src.core.case_retriever import retrieve_similar_cases
from src.core.copilot_graph import COPILOT_GRAPH
from src.core.graph_state import CopilotState
from src.core.image_extractor import (
    ALLOWED_MEDIA_TYPES,
    FIELD_NAMES,
    extract_fields_from_image,
    get_high_confidence_fields,
)
from src.core.llm_generator import is_llm_configured, is_llm_ready
from src.core.resolution_logger import (
    append_helpful_resolved_case,
    get_resolution_by_id,
    log_feedback,
    log_resolution,
)

logger = logging.getLogger(__name__)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

app = FastAPI(title="Paytm Transaction Resolution Copilot")


@app.on_event("startup")
def _warmup_pipeline() -> None:
    """Preload embeddings and Gemini model list so first /resolve is faster."""
    try:
        from src.core.case_retriever import _initialize_case_retriever
        from src.core.rag_retriever import _initialize_retriever

        _initialize_retriever()
        _initialize_case_retriever()
        if is_llm_configured():
            is_llm_ready()
        logger.info("Pipeline warmup complete")
    except Exception as exc:
        logger.warning("Pipeline warmup skipped: %s", exc)


class ResolveRequest(BaseModel):
    """Request body for the dispute resolution endpoint."""

    mid: str
    order_id: str
    cust_id: str
    complaint: str = ""
    agent_answers: str = ""


class RetrievalScores(BaseModel):
    """Hybrid retrieval component scores for the SOP actually used."""

    semantic: float
    intent: float
    structural: float
    final: float


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
    retrieval_scores: RetrievalScores
    escalation_required: Optional[bool] = None
    escalation_note: Optional[str] = None
    response: str
    response_mode: str
    customer_reply: str
    case_note: str
    groundedness_verified: Optional[bool] = None
    unsupported_claims: List[str] = []
    resolution_id: str
    similar_cases: List[Dict[str, Any]] = []


class FeedbackRequest(BaseModel):
    """Request body for post-resolution agent feedback."""

    resolution_id: str
    rating: Literal["helpful", "not_helpful"]
    comment: str = ""


class FeedbackResponse(BaseModel):
    """Acknowledgement after recording agent feedback."""

    status: Literal["recorded"]
    feedback_id: str


class ClarificationNeededResponse(BaseModel):
    """Returned when the graph stops to request agent clarification."""

    status: Literal["clarification_needed"]
    clarifying_questions: List[str]


class ExtractedField(BaseModel):
    """One vision-extracted transaction field with confidence."""

    value: Optional[str]
    confidence: str


class ImageExtractionResponse(BaseModel):
    """Vision extraction payload for pre-populating the resolve form."""

    MID: ExtractedField
    ORDER_ID: ExtractedField
    CUST_ID: ExtractedField
    TXN_AMOUNT: ExtractedField
    PAYMENT_MODE: ExtractedField
    TXN_STATUS: ExtractedField
    pre_populated: Dict[str, str]
    extraction_warning: Optional[str] = None


KEY_IDENTIFIER_FIELDS: tuple[str, ...] = ("MID", "ORDER_ID", "CUST_ID")
EXTRACTION_WARNING_MESSAGE = (
    "One or more key identifiers could not be extracted with confidence — "
    "please verify before submitting."
)


def _build_initial_state(request: ResolveRequest) -> CopilotState:
    """Map API request fields into the graph's initial CopilotState."""
    return {
        "mid": request.mid,
        "order_id": request.order_id,
        "cust_id": request.cust_id,
        "complaint_text": request.complaint,
        "agent_answers": request.agent_answers,
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


def _build_resolve_response(
    final_state: CopilotState,
    resolution_id: str,
) -> ResolveResponse:
    """Map a completed graph state into the full resolution API response."""
    reconciliation = final_state.get("reconciliation") or {}
    sop = final_state.get("sop") or {}
    escalation = final_state.get("escalation") or {}
    groundedness = final_state.get("groundedness") or {}

    primary_issue = reconciliation.get("primary_issue") or final_state.get("rule_based_issue") or ""
    sop_source = Path(sop["file_path"]).name if sop.get("file_path") else "unknown"
    retrieval_scores = RetrievalScores(
        semantic=float(sop.get("semantic_score", 0.0)),
        intent=float(sop.get("intent_score", 0.0)),
        structural=float(sop.get("structural_score", 0.0)),
        final=float(sop.get("final_score", 0.0)),
    )
    response_mode = final_state.get("response_mode") or (
        "sop_fallback" if not is_llm_configured() else "gemini"
    )
    escalation_note = escalation.get("reason", "")
    if response_mode == "sop_fallback" and not is_llm_configured():
        escalation_note = (
            f"{escalation_note} "
            "(Using SOP-based guidance — add GEMINI_API_KEY for Gemini responses.)"
        )

    if groundedness.get("verified") is False:
        logger.warning(
            "Groundedness flagged: mid=%s order_id=%s cust_id=%s txn_id=%s "
            "unsupported_claims=%s",
            final_state.get("mid"),
            final_state.get("order_id"),
            final_state.get("cust_id"),
            (final_state.get("transaction") or {}).get("TXN_ID"),
            groundedness.get("unsupported_claims"),
        )

    unresolved_intents = reconciliation.get("unresolved_intents") or []

    complaint_text = (final_state.get("complaint_text") or "").strip()
    agent_answers = (final_state.get("agent_answers") or "").strip()
    if agent_answers:
        enriched_complaint = (
            f"{complaint_text}\n\nAgent clarification: {agent_answers}".strip()
            if complaint_text
            else f"Agent clarification: {agent_answers}"
        )
    else:
        enriched_complaint = complaint_text

    similar_cases: list[dict[str, Any]] = []
    if enriched_complaint:
        try:
            similar_cases = retrieve_similar_cases(
                enriched_complaint,
                primary_issue,
                top_k=3,
            )
        except Exception as exc:
            logger.warning("Similar-case retrieval skipped: %s", exc)

    return ResolveResponse(
        issue=primary_issue,
        primary_issue=primary_issue,
        secondary_issue=unresolved_intents[0] if unresolved_intents else None,
        agreement=bool(reconciliation.get("agreement")),
        extracted_intents=reconciliation.get("extracted_intents") or [],
        unresolved_intents=unresolved_intents,
        conflict=bool(reconciliation.get("conflict")),
        reconciliation_note=reconciliation.get("reconciliation_note") or "",
        sop_source=sop_source,
        retrieval_scores=retrieval_scores,
        escalation_required=escalation.get("escalation_required"),
        escalation_note=escalation_note,
        response=final_state.get("response_text") or "",
        response_mode=response_mode,
        customer_reply=final_state.get("customer_reply") or "",
        case_note=final_state.get("case_note") or "",
        groundedness_verified=groundedness.get("verified"),
        unsupported_claims=groundedness.get("unsupported_claims") or [],
        resolution_id=resolution_id,
        similar_cases=similar_cases,
    )


@app.get("/health")
def health() -> Dict[str, Any]:
    """Return a simple health check payload."""
    return {
        "status": "ok",
        "llm_configured": is_llm_configured(),
        "llm_ready": is_llm_ready(),
    }


@app.post(
    "/resolve",
    response_model=Union[ResolveResponse, ClarificationNeededResponse],
    responses={
        200: {
            "description": (
                "Either a full resolution payload or a clarification request. "
                "Check for `status: clarification_needed` to distinguish the two shapes."
            ),
        },
        404: {"description": "Transaction not found for the provided identifiers."},
        500: {"description": "Transaction data unavailable or resolution pipeline failed."},
    },
)
def resolve(
    request: ResolveRequest,
) -> Union[ResolveResponse, ClarificationNeededResponse]:
    """Resolve a dispute via the copilot LangGraph.

    This endpoint returns one of two distinct 200-response shapes:

    1. **Clarification needed** — when signals are ambiguous and the graph stops
       before generating a resolution:
       ``{"status": "clarification_needed", "clarifying_questions": [...]}``

    2. **Full resolution** — when the graph completes the resolve path:
       the standard issue/reconciliation/SOP/response payload.

    Callers must branch on ``status`` (present only in the clarification shape)
    or on the presence of ``clarifying_questions`` vs ``response``.
    """
    logger.info(
        "resolve request: mid=%s order_id=%s cust_id=%s complaint=%r agent_answers=%r",
        request.mid,
        request.order_id,
        request.cust_id,
        request.complaint,
        request.agent_answers,
    )

    initial_state = _build_initial_state(request)

    try:
        final_state = COPILOT_GRAPH.invoke(initial_state)
    except (FileNotFoundError, ValueError) as exc:
        logger.error("Transaction data unavailable: %s", exc)
        raise HTTPException(
            status_code=500,
            detail="Transaction data is unavailable. Please try again later.",
        ) from exc
    except Exception as exc:
        logger.exception(
            "Resolution graph failed for ORDER_ID=%s: %s",
            request.order_id,
            exc,
        )
        raise HTTPException(
            status_code=500,
            detail="Resolution pipeline failed. Please try again later.",
        ) from exc

    if final_state.get("error"):
        logger.info(
            "transaction not found: mid=%s order_id=%s cust_id=%s error=%s",
            request.mid,
            request.order_id,
            request.cust_id,
            final_state["error"],
        )
        raise HTTPException(status_code=404, detail=final_state["error"])

    if final_state.get("needs_clarification"):
        questions = final_state.get("clarifying_questions") or []
        logger.info(
            "clarification needed: mid=%s order_id=%s cust_id=%s questions=%s",
            request.mid,
            request.order_id,
            request.cust_id,
            questions,
        )
        return ClarificationNeededResponse(
            status="clarification_needed",
            clarifying_questions=questions,
        )

    sop = final_state.get("sop")
    if sop is None:
        raise HTTPException(
            status_code=500,
            detail=(
                f"No SOP found for identified issue: "
                f"{final_state.get('rule_based_issue')!r}."
            ),
        )

    if not final_state.get("response_text"):
        raise HTTPException(
            status_code=500,
            detail="Resolution pipeline completed without a response.",
        )

    resolution_id = log_resolution(final_state)
    return _build_resolve_response(final_state, resolution_id)


@app.post("/feedback", response_model=FeedbackResponse)
def feedback(request: FeedbackRequest) -> FeedbackResponse:
    """Record agent feedback for a prior resolution."""
    resolution_row = get_resolution_by_id(request.resolution_id)
    if resolution_row is None:
        raise HTTPException(status_code=404, detail="Resolution ID not found")

    feedback_id = log_feedback(
        resolution_id=request.resolution_id,
        rating=request.rating,
        comment=request.comment,
    )

    if request.rating == "helpful":
        append_helpful_resolved_case(resolution_row)
        rebuild_case_index()

    return FeedbackResponse(status="recorded", feedback_id=feedback_id)


def _build_extraction_warning(extraction: dict[str, Any]) -> Optional[str]:
    """Return amber warning text when key identifiers are low-confidence or absent."""
    for field in KEY_IDENTIFIER_FIELDS:
        entry = extraction.get(field) or {}
        confidence = str(entry.get("confidence", "absent")).strip().lower()
        if confidence in {"low", "absent"}:
            return EXTRACTION_WARNING_MESSAGE
    return None


def _build_image_extraction_response(extraction: dict[str, Any]) -> ImageExtractionResponse:
    """Map raw vision extraction into the API response model."""
    field_payload = {
        field: ExtractedField(
            value=(extraction.get(field) or {}).get("value"),
            confidence=str((extraction.get(field) or {}).get("confidence", "absent")),
        )
        for field in FIELD_NAMES
    }
    return ImageExtractionResponse(
        **field_payload,
        pre_populated=get_high_confidence_fields(extraction),
        extraction_warning=_build_extraction_warning(extraction),
    )


@app.post("/extract-image", response_model=ImageExtractionResponse)
async def extract_image(file: UploadFile = File(...)) -> ImageExtractionResponse:
    """Extract transaction identifiers from a dashboard screenshot.

    Accepts multipart form upload (PNG, JPEG, or WebP). Returns per-field
    confidence levels plus ``pre_populated`` values for the resolve form.
    This is a pre-step only — agents should review and edit before POST /resolve.
    """
    content_type = (file.content_type or "").strip().lower()
    if content_type not in ALLOWED_MEDIA_TYPES:
        allowed = ", ".join(sorted(ALLOWED_MEDIA_TYPES))
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type {file.content_type!r}. Allowed types: {allowed}.",
        )

    image_bytes = await file.read()
    if not image_bytes:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    logger.info(
        "extract-image request: filename=%r content_type=%s bytes=%s",
        file.filename,
        content_type,
        len(image_bytes),
    )

    extraction = extract_fields_from_image(image_bytes, content_type)
    return _build_image_extraction_response(extraction)
